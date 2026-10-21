import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "soc_config", ROOT / "tools" / "soc_config.py")
SOC_CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SOC_CONFIG)


class SoCAddressMapTest(unittest.TestCase):
    def setUp(self):
        self.config = SOC_CONFIG.load_config(
            ROOT / "config" / "ty1b_simple_npu.json")

    def test_compact_address_map(self):
        config = SOC_CONFIG.validate(self.config)
        regions = [
            (SOC_CONFIG.number(config["rom"]["base"]),
             SOC_CONFIG.number(config["rom"]["size"])),
            (SOC_CONFIG.number(config["ddr"]["base"]),
             SOC_CONFIG.number(config["ddr"]["size"])),
            (SOC_CONFIG.number(config["uart"]["base"]),
             SOC_CONFIG.number(config["uart"]["size"])),
            (SOC_CONFIG.number(config["vta"]["vcr_base"]),
             SOC_CONFIG.number(config["vta"]["vcr_size"])),
        ]
        self.assertEqual(regions, [
            (0x00000000, 0x00020000),
            (0x40000000, 0x00028000),
            (0xf0000000, 0x00001000),
            (0xf0001000, 0x00001000),
        ])
        self.assertEqual(regions[2][0] + regions[2][1], regions[3][0])

    def test_gap_is_rejected(self):
        config = json.loads(json.dumps({
            key: value for key, value in self.config.items()
            if not key.startswith("_")
        }))
        config["_config_path"] = self.config["_config_path"]
        config["vta"]["vcr_base"] = "0xf0002000"
        with self.assertRaisesRegex(ValueError, "must be contiguous"):
            SOC_CONFIG.validate(config, require_ip=False)


if __name__ == "__main__":
    unittest.main()
