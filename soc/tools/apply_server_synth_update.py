#!/usr/bin/env python3
"""Verify a server bundle and optionally apply its project delta with backups."""
import argparse
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def verify(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        path = (bundle / entry['path']).resolve()
        if bundle not in path.parents or not path.is_file() or digest(path) != entry['sha256']:
            raise ValueError('bundle checksum mismatch: ' + entry['path'])
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--apply', action='store_true', help='otherwise only report the proposed update')
    args = parser.parse_args()
    try:
        bundle = args.bundle_dir.resolve()
        manifest = verify(bundle)
        print('Bundle SHA256 checks passed: %d files' % len(manifest['files']))
        if args.verify_only:
            if args.apply:
                raise ValueError('--verify-only and --apply cannot be combined')
            return 0
        if args.project_root is None:
            raise ValueError('provide --project-root, or use --verify-only')
        project = args.project_root.expanduser().resolve()
        if not (project / 'soc').is_dir() or not (project / 'generated').is_dir():
            raise ValueError('--project-root must contain soc/ and generated/')
        rtl = project / manifest['reference_rtl']['path']
        rtl_matches = rtl.is_file() and digest(rtl) == manifest['reference_rtl']['sha256']
        skipped, updates = [], []
        for entry in manifest['files']:
            if not entry['path'].startswith('project_update/'):
                continue
            relative = Path(entry['path']).relative_to('project_update')
            if relative.as_posix() == 'soc/synth/profiles.json' and not rtl_matches:
                skipped.append(relative.as_posix())
                continue
            destination = (project / relative).resolve()
            if project not in destination.parents:
                raise ValueError('destination escapes project: ' + str(relative))
            if destination.exists() and not destination.is_file():
                raise ValueError('destination is not a regular file: ' + str(relative))
            if not destination.exists() or digest(destination) != entry['sha256']:
                updates.append((bundle / entry['path'], destination, relative))
        print('Local reference RTL matches server RTL: ' + str(rtl_matches))
        print('Files to update: %d; skipped: %s' % (len(updates), ', '.join(skipped) or 'none'))
        if skipped:
            print('Server RTL differs: profiles.json is preserved. Create a server-specific profile from profiles.server.example.json.')
        if not args.apply:
            print('Dry run only. Add --apply to copy these files with backups.')
            return 0
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        backup = project / 'soc/build/server-synth-backups' / stamp
        backup.mkdir(parents=True)
        records = []
        for source, destination, relative in updates:
            existed = destination.exists()
            if existed:
                previous = backup / 'previous' / relative
                previous.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, previous)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(source.read_bytes())
                shutil.copymode(source, temporary)
                os.replace(temporary, destination)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            records.append({'path': relative.as_posix(), 'previous_file_backed_up': existed,
                            'installed_sha256': digest(destination)})
        (backup / 'update_report.json').write_text(json.dumps({
            'bundle': manifest['name'], 'skipped': skipped, 'files': records}, indent=2) + '\n', encoding='utf-8')
        print('Update complete; backup and report: ' + str(backup))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print('Update failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
