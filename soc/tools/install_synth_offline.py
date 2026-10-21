#!/usr/bin/env python3
"""Install a verified wheelhouse into a standalone user venv, without a network."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import venv


def check_yosys_startup(python, yosys, prefix, env):
    """Keep the real startup error instead of only reporting the exit code."""
    command = [str(python), str(yosys), '-V']
    logfile = prefix / 'yosys-startup.log'

    def save_log(text):
        try:
            logfile.write_text(text, encoding='utf-8')
            return str(logfile)
        except OSError as error:
            # The startup error itself may be a HOME quota error. Never hide
            # stderr behind another failure while trying to save diagnostics.
            print('Could not save startup log: ' + str(error), file=sys.stderr)
            return 'not saved; see startup output above'

    try:
        completed = subprocess.run(command, env=env, capture_output=True,
                                   text=True, check=False, timeout=180)
    except subprocess.TimeoutExpired as error:
        def as_text(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
        stdout, stderr = as_text(error.stdout), as_text(error.stderr)
        if stdout:
            print(stdout, file=sys.stderr, end='')
        if stderr:
            print(stderr, file=sys.stderr, end='')
        saved = save_log('Startup timed out after 180 seconds.\n' + stdout + stderr)
        raise ValueError('Yosys startup timed out; diagnostic log: ' + saved) from error
    if completed.returncode:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end='')
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end='')
    saved = save_log('Command: ' + repr(command) + '\nExit code: ' + str(completed.returncode) +
                     '\n--- stdout ---\n' + completed.stdout + '\n--- stderr ---\n' + completed.stderr)
    if completed.returncode:
        if 'Disk quota exceeded' in completed.stderr:
            print('Set YOWASP_CACHE_DIR to a writable project/scratch filesystem with available quota, then retry -V.', file=sys.stderr)
        raise ValueError('Yosys startup failed (exit %s); diagnostic log: %s' % (completed.returncode, saved))
    return completed.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--prefix', type=Path, default=Path.home() / '.local/share/tinysoc-synth-centos7')
    args = parser.parse_args()
    prefix = args.prefix.expanduser().resolve()
    marker = prefix / 'tinysoc_offline_install.json'
    state = None
    try:
        if sys.version_info < (3, 10):
            raise ValueError('Python >=3.10 is required; invoke with the existing Python 3.10 executable')
        if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'amd64'):
            raise ValueError('This wheelhouse targets Linux x86_64 only')
        bundle = args.bundle_dir.resolve()
        manifest = json.loads((bundle / 'wheelhouse_manifest.json').read_text(encoding='utf-8'))
        for item in manifest['files']:
            path = (bundle / item['path']).resolve()
            if bundle not in path.parents:
                raise ValueError('invalid wheelhouse manifest path')
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('offline input checksum mismatch: ' + item['path'])
        runtime = prefix / 'venv'
        if prefix.exists() and any(prefix.iterdir()) and not marker.is_file():
            raise ValueError('nonempty prefix is not owned by this installer; choose a new --prefix')
        prefix.mkdir(parents=True, exist_ok=True)
        state = {'installer': 'tinysoc-synth-offline', 'status': 'installing',
                 'base_python': sys.executable, 'platform': platform.platform(),
                 'libc': platform.libc_ver(), 'manifest': manifest}
        marker.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
        if not (runtime / 'bin/python').is_file():
            # pip is bootstrapped from its supplied wheel, not ensurepip/network.
            venv.EnvBuilder(with_pip=False, symlinks=True).create(runtime)
        python = runtime / 'bin/python'
        wheels = bundle / 'wheelhouse'
        pip_wheel = wheels / 'pip-24.3.1-py3-none-any.whl'
        env = dict(os.environ, PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX='1',
                   PIP_DISABLE_PIP_VERSION_CHECK='1', PYTHONNOUSERSITE='1')
        bootstrap = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('pip',run_name='__main__')"
        command = [str(python), '-I', '-c', bootstrap, str(pip_wheel), 'install',
                   '--no-index', '--no-cache-dir', '--only-binary=:all:', '--find-links', str(wheels),
                   'pip==24.3.1', '-r', str(bundle / 'requirements.txt')]
        subprocess.run(command, env=env, check=True)
        subprocess.run([str(python), '-I', '-m', 'pip', 'check'], env=env, check=True)
        # Use the interpreter explicitly, avoiding dependence on `which` or PATH.
        yosys = runtime / 'bin/yowasp-yosys'
        version = check_yosys_startup(python, yosys, prefix, env)
        state.update(status='passed', yosys_version=version)
        marker.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
        print(version)
        print('Offline environment ready: ' + str(runtime))
        print('Use SYNTH_ENV_DIR=' + str(prefix))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        if state is not None:
            state.update(status='failed', error=str(error))
            marker.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
        print('Offline installation failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
