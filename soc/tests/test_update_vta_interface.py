import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


SOC_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SOC_DIR.parent
SPEC = importlib.util.spec_from_file_location(
    "update_vta_interface", SOC_DIR / "tools" / "update_vta_interface.py")
INTERFACE_TOOL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INTERFACE_TOOL
SPEC.loader.exec_module(INTERFACE_TOOL)


def current_ports():
    interface = json.loads((
        REPO_ROOT / "generated" / "vta-ip" / "apb32-axi64" /
        "interface.json").read_text())
    return interface["ports"]


def conventional_name(name):
    if name == "clock":
        return "clk"
    if name == "reset":
        return "reset_n"
    if name.startswith("io_host_"):
        return "s_apb_" + name.removeprefix("io_host_")
    if name.startswith("io_mem_"):
        return "m_axi_" + name.removeprefix("io_mem_").replace("_bits_", "")
    return name


class InterfaceMappingTests(unittest.TestCase):
    def test_conventional_apb_axi_names_are_inferred(self):
        ports = [dict(port, name=conventional_name(port["name"]))
                 for port in current_ports()]
        bindings = INTERFACE_TOOL.infer_bindings(ports, {})
        widths = INTERFACE_TOOL.validate_bindings(ports, bindings, {}, [])

        self.assertEqual(bindings["clock"], "clk")
        self.assertEqual(bindings["reset"], "reset_n")
        self.assertEqual(bindings["host.paddr"], "s_apb_paddr")
        self.assertEqual(bindings["memory.aw.addr"], "m_axi_awaddr")
        self.assertEqual(widths["memory_data"], 64)

        description = INTERFACE_TOOL.build_description(
            SimpleNamespace(
                clear_overrides=False, map=[], tie=[], ignore_output=[],
                reset_active_low=False, reset_active_high=False),
            {"top": "VTA_Top"}, {}, ports)
        self.assertTrue(description["reset_active_low"])

    def test_unknown_input_must_be_tied(self):
        ports = current_ports() + [
            {"name": "debug_enable", "direction": "input", "width": 1}]
        bindings = INTERFACE_TOOL.infer_bindings(ports, {})
        with self.assertRaisesRegex(ValueError, "unhandled top-level ports"):
            INTERFACE_TOOL.validate_bindings(ports, bindings, {}, [])
        INTERFACE_TOOL.validate_bindings(
            ports, bindings, {"debug_enable": 0}, [])

    def test_unknown_output_must_be_explicitly_ignored(self):
        ports = current_ports() + [
            {"name": "debug_status", "direction": "output", "width": 8}]
        bindings = INTERFACE_TOOL.infer_bindings(ports, {})
        with self.assertRaisesRegex(ValueError, "unhandled top-level ports"):
            INTERFACE_TOOL.validate_bindings(ports, bindings, {}, [])
        INTERFACE_TOOL.validate_bindings(
            ports, bindings, {}, ["debug_status"])

    def test_axi_data_widths_must_match(self):
        ports = current_ports()
        ports = [
            dict(port, width=32)
            if port["name"] == "io_mem_r_bits_data" else dict(port)
            for port in ports
        ]
        bindings = INTERFACE_TOOL.infer_bindings(ports, {})
        with self.assertRaisesRegex(ValueError, "WDATA and RDATA widths differ"):
            INTERFACE_TOOL.validate_bindings(ports, bindings, {}, [])


if __name__ == "__main__":
    unittest.main()
