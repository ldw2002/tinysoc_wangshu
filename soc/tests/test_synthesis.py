"""Protect hierarchical resource accounting and simulation/source separation."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('synthesis_runner', ROOT / 'soc/tools/run_synthesis.py')
synthesis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(synthesis)


class SynthesisTests(unittest.TestCase):
    def test_resource_counts_include_every_instance(self):
        netlist = {'modules': {
            'leaf': {'cells': {
                'ram': {'type': '$mem_v2', 'parameters': {'WIDTH': '1000', 'SIZE': '100000'}},
                'ff': {'type': '$dffe', 'parameters': {'WIDTH': '10000'}},
                'latch': {'type': '$dlatch', 'parameters': {'WIDTH': '1'}},
            }},
            'middle': {'cells': {'a': {'type': 'leaf'}, 'b': {'type': 'leaf'}}},
            'top': {'cells': {'a': {'type': 'middle'}, 'b': {'type': 'middle'},
                              'gate': {'type': '$_AND_', 'parameters': {}}}},
        }}
        result = synthesis.resources(netlist, 'top')
        self.assertEqual(result['memory_arrays'], 4)
        self.assertEqual(result['memory_bits'], 4 * 8 * 32)
        self.assertEqual(result['register_bits'], 4 * 16)
        self.assertEqual(result['latch_cells'], 4)
        self.assertEqual(result['leaf_cells'], 13)

    def test_blackbox_is_not_expanded_as_implemented_logic(self):
        netlist = {'modules': {
            'macro': {'attributes': {'blackbox': '1'}, 'cells': {'dummy': {'type': '$_AND_'}}},
            'top': {'cells': {'ram': {'type': 'macro'}}},
        }}
        self.assertEqual(synthesis.resources(netlist, 'top')['cells_by_type'], {'macro': 1})

    def test_functional_sram_substitute_is_not_a_synthesis_source(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / 'profiles.json'
            profile.write_text(json.dumps({'bad': {
                'top': 'sram2p8x128', 'defines': ['SYNTHESIS'],
                'sources': ['soc/sim/models/npu_sram_behavioral.sv'],
            }}))
            with self.assertRaisesRegex(ValueError, 'simulation substitutes'):
                synthesis.load_profile(profile, 'bad', None)

    def test_tool_failure_invalidates_previous_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'summary.json').write_text('{"status":"passed"}')
            (output / 'report.md').write_text('old success')
            argv = ['run_synthesis.py', '--profile', 'vcr', '--build-dir', directory]
            failure = synthesis.subprocess.CalledProcessError(1, ['fake-yosys', '-V'])
            with mock.patch.object(synthesis.sys, 'argv', argv), \
                    mock.patch.object(synthesis, 'find_yosys', return_value='fake-yosys'), \
                    mock.patch.object(synthesis.subprocess, 'run', side_effect=failure), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(synthesis.main(), 1)
            self.assertEqual(json.loads((output / 'summary.json').read_text())['status'], 'failed')
            self.assertFalse((output / 'report.md').exists())


if __name__ == '__main__':
    unittest.main()
