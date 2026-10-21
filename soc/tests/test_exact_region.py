import importlib.util
import sys
import unittest
from pathlib import Path

from migen import Module, Signal
from migen.sim import run_simulation


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "litex"))
SPEC = importlib.util.spec_from_file_location(
    "ty1b_soc", ROOT / "litex" / "ty1b_soc.py")
TY1B_SOC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TY1B_SOC)


class _Bus:
    data_width = 32


class ExactSizeSoCRegionTest(unittest.TestCase):
    def test_exact_160_kib_decode_boundaries(self):
        region = TY1B_SOC.ExactSizeSoCRegion(
            origin=0x40000000,
            size=0x00028000,
        )
        address = Signal(30)
        selected = Signal()
        dut = Module()
        dut.comb += selected.eq(region.decoder(_Bus())(address))

        checks = [
            (0x3ffffffc, 0),
            (0x40000000, 1),
            (0x4001fffc, 1),
            (0x40020000, 1),
            (0x40027ffc, 1),
            (0x40028000, 0),
        ]

        def process():
            for byte_address, expected in checks:
                yield address.eq(byte_address >> 2)
                yield
                self.assertEqual(
                    (yield selected), expected, hex(byte_address))

        run_simulation(dut, process())


if __name__ == "__main__":
    unittest.main()
