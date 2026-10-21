#!/usr/bin/env python3
"""Build a checksummed server delta and offline Yosys wheelhouse archive."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
NAME = 'tinysoc_server_synth_20261021'


def copy(source, target):
    if source.is_dir():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'soc/build/server_bundle')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'deliverables')
    args = parser.parse_args()
    work = args.work_dir.resolve()
    stage = work / ('stage-' + uuid.uuid4().hex) / NAME
    stage.mkdir(parents=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    offline = stage / 'offline_yosys'
    copy(work / 'wheelhouse', offline / 'wheelhouse')
    copy(ROOT / 'soc/synth/requirements-centos7.txt', offline / 'requirements.txt')
    copy(ROOT / 'soc/tools/install_synth_offline.py', offline / 'install_synth_offline.py')
    inputs = [offline / 'requirements.txt', *sorted((offline / 'wheelhouse').glob('*.whl'))]
    wheel_manifest = {'target': 'Linux x86_64 / glibc 2.17 / Python >=3.10', 'files': [
        {'path': path.relative_to(offline).as_posix(), 'sha256': sha256(path.read_bytes()).hexdigest()}
        for path in inputs]}
    (offline / 'wheelhouse_manifest.json').write_text(json.dumps(wheel_manifest, indent=2) + '\n', encoding='utf-8')

    delta = stage / 'project_update'
    paths = [
        'soc/synth', 'soc/sim/models', 'soc/sim/filelist_sram_behavioral.f',
        'soc/tools/run_synthesis.py', 'soc/tools/run_dc_synthesis.py',
        'soc/tools/install_synth_offline.py', 'soc/tools/package_server_synth.py',
        'soc/tools/apply_server_synth_update.py', 'soc/tools/test_sram_models.py',
        'soc/scripts/setup_synth_env.sh', 'soc/tests/test_synthesis.py',
        'soc/tests/test_dc_synthesis.py', 'soc/tests/test_server_bundle.py',
        'soc/tests/fixtures/dc_mock.tcl', 'docs/Server_RTL_Audit_20261020.md',
        'generated/vta-ip/server-memory-20261020',
    ]
    for relative in paths:
        copy(ROOT / relative, delta / relative)
    reference = stage / 'reference_project'
    copy(delta, reference)
    rtl_relative = 'generated/vta-ip/apb32-axi64/rtl/vta.v'
    copy(ROOT / rtl_relative, reference / rtl_relative)
    copy(ROOT / 'generated/vta-ip/apb32-axi64/manifest.json',
         reference / 'generated/vta-ip/apb32-axi64/manifest.json')
    copy(ROOT / 'soc/Makefile', stage / 'review/soc.Makefile')
    copy(ROOT / 'soc/tools/apply_server_synth_update.py', stage / 'apply_server_synth_update.py')
    copy(ROOT / 'soc/synth/SERVER_BUNDLE.md', stage / 'README_服务器部署.md')
    copy(work / 'validation', stage / 'validation')
    files = sorted(path for path in stage.rglob('*') if path.is_file())
    records = [{'path': path.relative_to(stage).as_posix(), 'size_bytes': path.stat().st_size,
                'sha256': sha256(path.read_bytes()).hexdigest()} for path in files]
    manifest = {'name': NAME, 'date': '2026-10-21',
                'scope': 'Offline generic synthesis + DC scripts + SRAM simulation additions; not a whole SoC release',
                'reference_rtl': {'path': rtl_relative, 'sha256': sha256((ROOT / rtl_relative).read_bytes()).hexdigest()},
                'files': records}
    (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    checksums = ''.join('%s  %s\n' % (entry['sha256'], entry['path']) for entry in records)
    checksums += sha256((stage / 'manifest.json').read_bytes()).hexdigest() + '  manifest.json\n'
    (stage / 'SHA256SUMS').write_text(checksums, encoding='utf-8')
    archive = output / (NAME + '.tar.gz')
    stamp = int(datetime(2026, 10, 21, tzinfo=timezone.utc).timestamp())
    with tarfile.open(archive, 'w:gz') as tar:
        for path in sorted(stage.rglob('*')):
            if not path.is_file():
                continue
            info = tar.gettarinfo(str(path), arcname=NAME + '/' + path.relative_to(stage).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = stamp
            info.mode = 0o755 if path.suffix == '.sh' else 0o644
            with path.open('rb') as stream:
                tar.addfile(info, stream)
    checksum = sha256(archive.read_bytes()).hexdigest()
    (output / (archive.name + '.sha256')).write_text(checksum + '  ' + archive.name + '\n', encoding='utf-8')
    copy(stage / 'README_服务器部署.md', output / 'SERVER_DEPLOY_20261021.md')
    print(json.dumps({'archive': str(archive), 'size_bytes': archive.stat().st_size,
                      'sha256': checksum, 'stage': str(stage)}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
