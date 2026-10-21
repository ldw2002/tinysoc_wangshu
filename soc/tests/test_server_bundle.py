"""Protect server update backups, RTL isolation, and offline input validation."""
from hashlib import sha256
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('server_update', ROOT / 'soc/tools/apply_server_synth_update.py')
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)
spec = importlib.util.spec_from_file_location('offline_install', ROOT / 'soc/tools/install_synth_offline.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ServerBundleTests(unittest.TestCase):
    def test_quota_error_is_visible_when_log_cannot_be_saved(self):
        failure = installer.subprocess.CompletedProcess(
            ['python', 'yowasp-yosys', '-V'], 1, '', 'OSError: [Errno 122] Disk quota exceeded\n')
        stderr = io.StringIO()
        with mock.patch.object(installer.subprocess, 'run', return_value=failure), \
                mock.patch.object(Path, 'write_text', side_effect=OSError(122, 'Disk quota exceeded')), \
                contextlib.redirect_stderr(stderr), self.assertRaisesRegex(ValueError, 'startup failed'):
            installer.check_yosys_startup('python', 'yowasp-yosys', Path('/unused'), {})
        self.assertIn('OSError: [Errno 122] Disk quota exceeded', stderr.getvalue())
        self.assertIn('YOWASP_CACHE_DIR', stderr.getvalue())

    def test_startup_error_is_visible_and_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            failure = installer.subprocess.CompletedProcess(
                ['python', 'yowasp-yosys', '-V'], 1, '', "ModuleNotFoundError: No module named '_ctypes'\n")
            stderr = io.StringIO()
            with mock.patch.object(installer.subprocess, 'run', return_value=failure), \
                    contextlib.redirect_stderr(stderr), self.assertRaisesRegex(ValueError, 'startup failed'):
                installer.check_yosys_startup('python', 'yowasp-yosys', prefix, {})
            self.assertIn("No module named '_ctypes'", stderr.getvalue())
            self.assertIn("No module named '_ctypes'", (prefix / 'yosys-startup.log').read_text())

    def test_update_preserves_server_rtl_makefile_and_different_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bundle, project = base / 'bundle', base / 'server'
            (bundle / 'project_update/soc/synth').mkdir(parents=True)
            (project / 'soc/synth').mkdir(parents=True)
            (project / 'generated').mkdir()
            (project / 'generated/vta.v').write_text('server RTL')
            (project / 'soc/Makefile').write_text('server Makefile')
            (project / 'soc/synth/profiles.json').write_text('server profile')
            (project / 'soc/synth/server.mk').write_text('old entry')
            profile = bundle / 'project_update/soc/synth/profiles.json'
            entry = bundle / 'project_update/soc/synth/server.mk'
            profile.write_text('reference profile')
            entry.write_text('new entry')
            manifest = {'name': 'fixture', 'reference_rtl': {'path': 'generated/vta.v', 'sha256': 'different'},
                        'files': [{'path': str(path.relative_to(bundle).as_posix()),
                                   'sha256': sha256(path.read_bytes()).hexdigest()} for path in [profile, entry]]}
            (bundle / 'manifest.json').write_text(json.dumps(manifest))
            argv = ['apply', '--bundle-dir', str(bundle), '--project-root', str(project)]
            with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(update.main(), 0)
            self.assertEqual((project / 'soc/synth/server.mk').read_text(), 'old entry')
            with mock.patch.object(sys, 'argv', argv + ['--apply']), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(update.main(), 0)
            self.assertEqual((project / 'soc/synth/server.mk').read_text(), 'new entry')
            self.assertEqual((project / 'soc/synth/profiles.json').read_text(), 'server profile')
            self.assertEqual((project / 'generated/vta.v').read_text(), 'server RTL')
            self.assertEqual((project / 'soc/Makefile').read_text(), 'server Makefile')
            backups = list((project / 'soc/build/server-synth-backups').glob('*/previous/soc/synth/server.mk'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), 'old entry')

    def test_corrupt_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / 'payload').write_bytes(b'changed')
            (bundle / 'manifest.json').write_text(json.dumps({'files': [{'path': 'payload', 'sha256': 'wrong'}]}))
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                update.verify(bundle)

    def test_installer_rejects_corruption_before_creating_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            prefix = bundle / 'unused-install'
            (bundle / 'wheelhouse_manifest.json').write_text(json.dumps({
                'files': [{'path': 'missing.whl', 'sha256': 'wrong'}]}))
            argv = ['install', '--bundle-dir', str(bundle), '--prefix', str(prefix)]
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(sys, 'platform', 'linux'), \
                    mock.patch.object(installer.platform, 'machine', return_value='x86_64'), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(installer.main(), 1)
            self.assertFalse(prefix.exists())


if __name__ == '__main__':
    unittest.main()
