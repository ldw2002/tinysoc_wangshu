#!/usr/bin/env python3
"""Prepare or run Synopsys DC directly from the shared RTL synthesis profiles."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from run_synthesis import ROOT, load_profile

TEMPLATE = ROOT / 'soc/synth/dc/run_dc.tcl'
REPORTS = ['check_design.rpt', 'resources_elaborated.rpt', 'design.rpt',
           'check_design_mapped.rpt', 'check_timing.rpt', 'resources_mapped.rpt',
           'area.rpt', 'timing.rpt', 'qor.rpt']
PRODUCTS = ['result.json', 'console.log', 'elaborated.ddc', 'mapped.ddc', 'mapped.v', 'mapped.sdc']


def tcl_word(value):
    """A double-quoted Tcl word, with all substitutions escaped."""
    value = str(value).replace('\\', '/') if isinstance(value, Path) else str(value)
    if any(char in value for char in '\x00\n\r'):
        raise ValueError('newline/NUL is not allowed in Tcl settings')
    return '"' + ''.join('\\' + char if char in '\\"$[]' else char for char in value) + '"'


def tcl_list(values):
    return '[list ' + ' '.join(tcl_word(value) for value in values) + ']'


def guard_assertions(source):
    """Guard only standalone one-line immediate assertions; fail on other forms.

    Mask strings/comments before looking for assertions so Scala messages and
    comments are untouched. The original synthesis input is never overwritten.
    """
    mask = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda match: re.sub(r'[^\n]', ' ', match.group()), source)
    original_lines = source.splitlines(keepends=True)
    code_lines = mask.splitlines(keepends=True)
    output = []
    count = 0
    for original, code in zip(original_lines, code_lines):
        if re.search(r'\bassert\b', code):
            if not re.fullmatch(r'\s*assert\s*\([^\n]*\)\s*;\s*', code):
                raise ValueError('unsupported assertion form; use explicit synthesis guards in RTL: ' + original.strip())
            indent = re.match(r'[ \t]*', original).group()
            output += [indent + '// synopsys translate_off\n', original.rstrip('\r\n') + '\n',
                       indent + '// synopsys translate_on\n']
            count += 1
        else:
            output.append(original)
    return ''.join(output), count


def load_config(filename, stage):
    config = {'target_libraries': [], 'link_libraries': [], 'search_paths': [],
              'sdc': None, 'compile_command': 'compile'}
    base = ROOT
    if filename:
        filename = filename.resolve()
        supplied = json.loads(filename.read_text(encoding='utf-8'))
        if not isinstance(supplied, dict) or set(supplied) - set(config):
            raise ValueError('DC config must be an object with only documented keys')
        config.update(supplied)
        base = filename.parent

    def resolve(value):
        if not isinstance(value, str) or not value:
            raise ValueError('DC paths must be nonempty strings')
        return (base / os.path.expandvars(os.path.expanduser(value))).resolve()

    for key in ['target_libraries', 'link_libraries', 'search_paths']:
        if not isinstance(config[key], list):
            raise ValueError(key + ' must be a list')
        config[key] = [resolve(value) for value in config[key]]
        for path in config[key]:
            if not (path.is_dir() if key == 'search_paths' else path.is_file()):
                raise ValueError('missing ' + key + ': ' + str(path))
            if key != 'search_paths' and path.suffix.lower() != '.db':
                raise ValueError('DC libraries must be compiled .db files: ' + str(path))
    config['sdc'] = resolve(config['sdc']) if config['sdc'] is not None else None
    if config['sdc'] is not None and not config['sdc'].is_file():
        raise ValueError('missing SDC: ' + str(config['sdc']))
    if config['compile_command'] not in ('compile', 'compile_ultra'):
        raise ValueError('compile_command must be compile or compile_ultra')
    if stage == 'map' and (not config['target_libraries'] or config['sdc'] is None):
        raise ValueError('map requires target_libraries (.db) and an explicit SDC in --config')
    return config


def prepare(output, profile, sources, config, stage, token):
    rtl = output / 'rtl'
    rtl.mkdir(exist_ok=True)
    records, views = [], []
    for index, source in enumerate(sources):
        raw = source.read_bytes()
        text = raw.decode('utf-8')
        count = 0
        if profile.get('dc', {}).get('guard_simple_immediate_assertions', False):
            text, count = guard_assertions(text)
        view = rtl / ('%02d_' % index + source.name)
        view.write_bytes(text.encode('utf-8'))
        views.append(view)
        records.append({'path': str(source), 'sha256': sha256(raw).hexdigest(),
                        'dc_view': view.relative_to(output).as_posix(),
                        'dc_view_sha256': sha256(view.read_bytes()).hexdigest(),
                        'guarded_assertions': count})
    # Relative source-directory paths keep include lookup valid when the whole
    # repository (including its build bundle) moves to a Linux server.
    include_dirs = list(dict.fromkeys(source.parent for source in sources))
    includes = []
    for path in include_dirs:
        try:
            relative = Path(os.path.relpath(path, output))
        except ValueError:
            # Windows custom build directories can be on another drive.
            includes.append(tcl_word(path))
        else:
            includes.append('[file normalize [file join $DC_RUN_ROOT %s]]' % tcl_word(relative))
    settings = [
        '# Generated; invoke through run_dc.tcl, which sets dc_script_root.',
        'set DC_RUN_ROOT $dc_script_root',
        'set DC_RUN_TOKEN ' + tcl_word(token),
        'set DC_TOP ' + tcl_word(profile['top']),
        'set DC_STAGE ' + tcl_word(stage),
        'set DC_SOURCES [list ' + ' '.join('[file join $DC_RUN_ROOT %s]' %
             tcl_word(view.relative_to(output)) for view in views) + ']',
        'set DC_DEFINES ' + tcl_list(profile['defines']),
        'set DC_SEARCH_PATH [concat [list ' + ' '.join(includes) + '] ' +
            tcl_list(config['search_paths']) + ']',
        'set DC_TARGET_LIBRARIES ' + tcl_list(config['target_libraries']),
        'set DC_LINK_LIBRARIES ' + tcl_list(config['link_libraries']),
        'set DC_SDC ' + tcl_word(config['sdc'] or ''),
        'set DC_COMPILE_COMMAND ' + tcl_word(config['compile_command']),
    ]
    (output / 'settings.tcl').write_text('\n'.join(settings) + '\n', encoding='utf-8')
    shutil.copyfile(TEMPLATE, output / 'run_dc.tcl')
    return records


def validate_result(output, token, top, stage, returncode):
    if returncode:
        raise ValueError('DC returned exit code %s; inspect console.log' % returncode)
    result_path = output / 'result.json'
    if not result_path.is_file():
        raise ValueError('DC did not write result.json; check startup/license errors in console.log')
    result = json.loads(result_path.read_text(encoding='utf-8'))
    for key, expected in [('status', 'passed'), ('token', token), ('top', top), ('stage', stage)]:
        if result.get(key) != expected:
            raise ValueError('DC completion mismatch for %s: %r' % (key, result.get(key)))
    log = (output / 'console.log').read_text(encoding='utf-8', errors='replace')
    if re.search(r'^\s*(?:Error|Fatal):', log, re.MULTILINE | re.IGNORECASE):
        raise ValueError('DC reported errors despite completion; inspect console.log')
    expected = ['reports/' + name for name in REPORTS[:3]]
    expected += (['mapped.ddc', 'mapped.v', 'mapped.sdc'] +
                 ['reports/' + name for name in REPORTS[3:]]) if stage == 'map' else ['elaborated.ddc']
    for relative in expected:
        path = output / relative
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError('missing/empty DC output: ' + relative)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='vta-local')
    parser.add_argument('--profiles', type=Path, default=ROOT / 'soc/synth/profiles.json')
    parser.add_argument('--top')
    parser.add_argument('--stage', choices=['elaborate', 'map'], default='elaborate')
    parser.add_argument('--config', type=Path, help='library/SDC JSON; required for map')
    parser.add_argument('--dc', default='dc_shell', help='DC/DC NXT executable')
    parser.add_argument('--dc-arg', action='append', default=[], help='extra executable argument (repeatable)')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--timeout', type=int, default=3600)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.profile):
        parser.error('profile name may contain only letters, digits, underscore, and hyphen')
    output = (args.build_dir or ROOT / 'soc/build/synthesis-dc' / args.profile / args.stage).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Only invalidate products owned by this runner; never recursively clean a
    # user-specified build directory. WORK is unique for each invocation.
    for relative in PRODUCTS + ['reports/' + name for name in REPORTS]:
        (output / relative).unlink(missing_ok=True)
    token = str(uuid.uuid4())
    summary = {'backend': 'design_compiler', 'status': 'preparing', 'token': token,
               'profile': args.profile, 'stage': args.stage, 'prepare_only': args.prepare_only,
               'scope': 'Selected RTL profile; not the complete simulation SoC'}
    summary_path = output / 'summary.json'

    def save():
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    save()
    started = time.monotonic()
    try:
        profile, sources = load_profile(args.profiles, args.profile, args.top)
        config = load_config(args.config, args.stage)
        summary['top'] = profile['top']
        summary['defines'] = profile['defines']
        summary['config'] = {key: [str(p) for p in value] if isinstance(value, list)
                             else str(value) if isinstance(value, Path) else value for key, value in config.items()}
        summary['library_and_constraint_inputs'] = [
            {'path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}
            for path in dict.fromkeys(config['target_libraries'] + config['link_libraries'] +
                                      ([config['sdc']] if config['sdc'] else []))]
        summary['sources'] = prepare(output, profile, sources, config, args.stage, token)
        summary['status'] = 'prepared'
        save()
        if args.prepare_only:
            print('DC bundle prepared (not executed): ' + str(output))
            return 0
        executable = shutil.which(args.dc)
        if not executable:
            raise ValueError('DC executable not found: %s; install/load DC on the server, or use --prepare-only' % args.dc)
        command = [executable, *args.dc_arg, '-f', str(output / 'run_dc.tcl')]
        summary.update(status='running', command=command)
        save()
        with (output / 'console.log').open('w', encoding='utf-8') as console:
            completed = subprocess.run(command, cwd=output, stdout=console, stderr=subprocess.STDOUT,
                                       timeout=args.timeout, check=False)
        result = validate_result(output, token, profile['top'], args.stage, completed.returncode)
        summary.update(status='passed', tool_version=result.get('version', 'unknown'))
        print('DC %s passed: %s' % (args.stage, output))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        summary.update(status='failed', error=str(error))
        print('DC flow failed: ' + str(error), file=sys.stderr)
        return 1
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        save()


if __name__ == '__main__':
    sys.exit(main())
