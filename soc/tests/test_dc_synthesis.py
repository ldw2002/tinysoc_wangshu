"""DC preparation contracts and optional real Tcl parser tests, without DC."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import run_dc_synthesis as dc
sys.path.pop(0)

TCL = os.environ.get('DC_TEST_TCL') or shutil.which('tclsh')
FIXTURE = Path(__file__).parent / 'fixtures/dc_mock.tcl'


class DcPreparationTests(unittest.TestCase):
    def test_guard_only_real_standalone_assertions(self):
        raw = ('// assert(foo);\n/* assert(bar); */\n'
               'initial $display("assert(fake);\\\"quoted\\\"");\n'
               '  assert(a == b); // original comment\n')
        view, count = dc.guard_assertions(raw)
        self.assertEqual(count, 1)
        self.assertIn('// synopsys translate_off\n  assert(a == b); // original comment', view)
        self.assertEqual(view.replace('  // synopsys translate_off\n', '').replace(
            '  // synopsys translate_on\n', ''), raw)
        for unsupported in ['assert property(foo);\n', 'assert(foo) else $fatal;\n',
                            'if (x) assert(foo);\n', 'assert(\nfoo);\n']:
            with self.subTest(unsupported=unsupported), self.assertRaises(ValueError):
                dc.guard_assertions(unsupported)

    def test_map_requires_real_library_and_explicit_sdc(self):
        with self.assertRaisesRegex(ValueError, 'map requires'):
            dc.load_config(None, 'map')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            config = path / 'dc.json'
            config.write_text(json.dumps({'target_libraries': ['missing.db'], 'sdc': 'clock.sdc'}))
            with self.assertRaisesRegex(ValueError, 'missing target_libraries'):
                dc.load_config(config, 'map')
            (path / 'cells.db').write_bytes(b'fixture; not a real library')
            (path / 'clock.sdc').write_text('create_clock -period 5 [get_ports clock]\n')
            config.write_text(json.dumps({'target_libraries': ['cells.db'], 'sdc': 'clock.sdc'}))
            self.assertEqual(dc.load_config(config, 'map')['sdc'], path.resolve() / 'clock.sdc')

    def test_prepare_leaves_raw_rtl_unchanged_and_has_no_success_marker(self):
        profile, sources = dc.load_profile(dc.ROOT / 'soc/synth/profiles.json', 'vta-local', None)
        before = sources[0].read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            records = dc.prepare(output, profile, sources, dc.load_config(None, 'elaborate'), 'elaborate', 'new-token')
            self.assertGreater(records[0]['guarded_assertions'], 0)
            self.assertFalse((output / 'result.json').exists())
            self.assertNotEqual(records[0]['sha256'], records[0]['dc_view_sha256'])
        self.assertEqual(sources[0].read_bytes(), before)

    def test_failed_run_invalidates_previous_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'summary.json').write_text('{"status":"passed"}')
            (output / 'result.json').write_text('{"status":"passed"}')
            (output / 'elaborated.ddc').write_text('old product')
            argv = ['dc', '--profile', 'vcr', '--build-dir', directory, '--dc', 'not-installed']
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(dc.shutil, 'which', return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(dc.main(), 1)
            self.assertEqual(json.loads((output / 'summary.json').read_text())['status'], 'failed')
            self.assertFalse((output / 'result.json').exists())
            self.assertFalse((output / 'elaborated.ddc').exists())

    def test_exit_zero_without_completion_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'did not write result'):
                dc.validate_result(Path(directory), 'token', 'Top', 'elaborate', 0)

    def test_stale_completion_token_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'result.json').write_text(json.dumps({
                'status': 'passed', 'token': 'old', 'top': 'Top', 'stage': 'elaborate'}))
            with self.assertRaisesRegex(ValueError, 'token'):
                dc.validate_result(output, 'new', 'Top', 'elaborate', 0)


@unittest.skipUnless(TCL, 'set DC_TEST_TCL to enable Tcl parser/control-flow validation')
class DcTclTests(unittest.TestCase):
    def test_tcl_words_do_not_substitute_user_text(self):
        value = 'a space $env(HOME) [error injected] "quote" {brace} \\ slash'
        completed = subprocess.run([TCL], input='puts ' + dc.tcl_word(value) + '\n',
                                   text=True, capture_output=True, check=True)
        self.assertEqual(completed.stdout.rstrip('\n'), value)

    def run_fixture(self, stage, failure=None):
        with tempfile.TemporaryDirectory(prefix='dc $[] space ') as directory:
            output = Path(directory)
            source = output / 'input.v'
            source.write_text('module Top(input clock); endmodule\n')
            config = dc.load_config(None, 'elaborate')
            if stage == 'map':
                sdc = output / 'clock.sdc'
                sdc.write_text('create_clock -period 5 [get_ports clock]\n')
                config.update(target_libraries=[output / 'fixture.db'], sdc=sdc)
            profile = {'top': 'Top', 'defines': ['SYNTHESIS']}
            dc.prepare(output, profile, [source], config, stage, 'test-token')
            env = dict(os.environ)
            if failure:
                env['DC_MOCK_FAILURE'] = failure
            else:
                env.pop('DC_MOCK_FAILURE', None)
            completed = subprocess.run([TCL, str(FIXTURE), str(output / 'run_dc.tcl')],
                                       env=env, text=True, capture_output=True)
            result = json.loads((output / 'result.json').read_text())
            if failure:
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertEqual(result['status'], 'failed')
            else:
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                (output / 'console.log').write_text(completed.stdout + completed.stderr)
                dc.validate_result(output, 'test-token', 'Top', stage, completed.returncode)
                self.assertIn('MOCK', result['version'])

    def test_elaborate_control_flow(self):
        self.run_fixture('elaborate')

    def test_map_control_flow(self):
        self.run_fixture('map')

    def test_dc_failures_propagate(self):
        for step in ['link', 'check_design', 'compile', 'unmapped']:
            with self.subTest(step=step):
                self.run_fixture('map', step)


if __name__ == '__main__':
    unittest.main()
