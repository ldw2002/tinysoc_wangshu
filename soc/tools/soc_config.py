#!/usr/bin/env python3
"""Validate Mini VTA SoC configuration and generate shared constants."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


TY1B_SIMPLE_ARCHITECTURE = "tvm-vta-ty1b-simple"
TY1B_SIMPLE_PERIPHERALS = ["cpu", "axi", "npu", "ddr", "sram", "uart"]


def number(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError(f"expected integer or integer string, got {value!r}")


def _merge(base, override):
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path, parents=()):
    path = path.resolve()
    if path in parents:
        raise ValueError(f"configuration inheritance cycle at {path}")
    data = json.loads(path.read_text())
    parent = data.pop("extends", None)
    if parent is not None:
        data = _merge(load_config(path.parent / parent, parents + (path,)), data)
    data["_config_path"] = path.resolve()
    return data


def region(name, section, *, allow_non_power_of_two=False):
    base, size = number(section["base"]), number(section["size"])
    if size <= 0:
        raise ValueError(f"{name}.size must be positive")
    if not allow_non_power_of_two and size & (size - 1):
        raise ValueError(f"{name}.size must be a positive power of two")
    alignment = 0x1000 if allow_non_power_of_two else size
    if base % alignment:
        raise ValueError(f"{name}.base must be aligned to 0x{alignment:x} bytes")
    return name, base, size


def validate(data, require_ip=True):
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    if data["soc"]["address_width"] != 32:
        raise ValueError("the first release supports a 32-bit address space")
    if data["vta"]["host_protocol"] != "apb4" or data["vta"]["host_data_width"] != 32:
        raise ValueError("the VTA host interface must be APB4 32-bit")
    if data["vta"]["vcr_frontend"] != "apb32":
        raise ValueError("the VTA control frontend must be APB32")
    if data["vta"]["memory_protocol"] != "axi4":
        raise ValueError("the VTA DMA interface must be AXI4")
    if data["vta"]["memory_data_width"] not in {32, 64, 128}:
        raise ValueError("the VTA AXI data width must be 32, 64 or 128")
    ddr = data.get("ddr", {})
    if not ddr.get("enabled"):
        raise ValueError("the TY1B-simple main memory must be DDR")
    if ddr.get("data_width") not in {32, 64, 128}:
        raise ValueError("ddr.data_width must be 32, 64 or 128")
    if ddr.get("type") != "DDR3" or ddr.get("model") != "MT41K256M8":
        raise ValueError("the validated simulation DDR3 model is MT41K256M8")
    if ddr.get("phy_data_width") != 8:
        raise ValueError("the MT41K256M8 simulation PHY must be 8 bits wide")
    if not isinstance(ddr.get("clock_hz"), int) or ddr["clock_hz"] <= 0:
        raise ValueError("ddr.clock_hz must be a positive integer")
    if ddr["clock_hz"] != data["soc"]["clock_hz"]:
        raise ValueError("the current DDR model must use the system clock")
    if ddr.get("l2_size") != 0:
        raise ValueError("the TY1B-simple profile does not include an L2 cache")
    if ddr.get("cached") is not False:
        raise ValueError("the verification DDR region must be uncached for VTA DMA coherency")
    if number(data["rom"].get("size", 0)) != 0x20000:
        raise ValueError("rom.size must be 128 KiB")
    sram = data.get("sram", {})
    if number(sram.get("size", 0)) != 0x20000:
        raise ValueError("sram.size must be 128 KiB")
    if number(ddr.get("size", 0)) != 0x28000:
        raise ValueError("ddr.size must be 160 KiB")
    if number(data["vta"].get("vcr_size", 0)) != 0x1000:
        raise ValueError("vta.vcr_size must be 4 KiB")

    architecture = data.get("architecture")
    if architecture is not None:
        architecture_name = architecture.get("name")
        if architecture_name != TY1B_SIMPLE_ARCHITECTURE:
            raise ValueError(f"unsupported architecture {architecture.get('name')!r}")
        if architecture.get("peripherals") != TY1B_SIMPLE_PERIPHERALS:
            raise ValueError(
                f"{architecture_name} requires {'/'.join(TY1B_SIMPLE_PERIPHERALS)}")
        if data["soc"]["clock_hz"] != 200_000_000:
            raise ValueError(f"{architecture_name} system clock must be 200 MHz")
        if data["soc"]["cpu"] != "vexriscv":
            raise ValueError(f"the current {architecture_name} model requires vexriscv")

    uart = data.get("uart", {})
    if number(uart.get("size", 0)) != 0x1000:
        raise ValueError("uart.size must be 4 KiB")
    if number(uart.get("csr_paging", 0)) != 0x400:
        raise ValueError("uart.csr_paging must be 1 KiB for the 4 KiB CSR aperture")

    regions = [
        region("rom", data["rom"]),
        region("sram", sram),
        region("ddr", data["ddr"], allow_non_power_of_two=True),
        region("uart", uart),
        region("vta-vcr", {
            "base": data["vta"]["vcr_base"],
            "size": data["vta"]["vcr_size"],
        }),
    ]
    for index, (name_a, base_a, size_a) in enumerate(regions):
        if base_a + size_a > 1 << 32:
            raise ValueError(f"{name_a} exceeds the 32-bit address space")
        for name_b, base_b, size_b in regions[index + 1 :]:
            if max(base_a, base_b) < min(base_a + size_a, base_b + size_b):
                raise ValueError(f"address regions {name_a} and {name_b} overlap")

    _, uart_base, uart_size = regions[3]
    _, vta_base, _ = regions[4]
    if uart_base + uart_size != vta_base:
        raise ValueError("address regions uart and vta-vcr must be contiguous")

    config_dir = data["_config_path"].parent
    ip_dir = (config_dir / data["vta"]["ip_dir"]).resolve()
    if require_ip:
        manifest_path = ip_dir / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"frozen VTA manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        rtl_path = ip_dir / "rtl" / "vta.v"
        rtl_digest = hashlib.sha256(rtl_path.read_bytes()).hexdigest()
        if rtl_digest != manifest.get("rtl_sha256"):
            raise ValueError(f"frozen VTA RTL hash mismatch: {rtl_path}")
        vta_config_path = ip_dir / "vta_config.json"
        config_digest = hashlib.sha256(vta_config_path.read_bytes()).hexdigest()
        if config_digest != manifest.get("vta_config_sha256"):
            raise ValueError(f"frozen VTA config hash mismatch: {vta_config_path}")
        expected = {
            "host_protocol": "apb4",
            "host_data_width": 32,
            "memory_protocol": data["vta"]["memory_protocol"],
            "memory_data_width": data["vta"]["memory_data_width"],
        }
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise ValueError(f"VTA manifest {key}={manifest.get(key)!r}, expected {value!r}")
        interface_path = ip_dir / manifest.get("interface_file", "interface.json")
        if not interface_path.is_file():
            raise ValueError(
                f"generated VTA interface mapping not found: {interface_path}; "
                "run make interface-sync")
        interface_bytes = interface_path.read_bytes()
        interface_digest = hashlib.sha256(interface_bytes).hexdigest()
        if interface_digest != manifest.get("interface_sha256"):
            raise ValueError(
                f"generated VTA interface mapping hash mismatch: {interface_path}")
        interface = json.loads(interface_bytes)
        if interface.get("top") != manifest.get("top"):
            raise ValueError("VTA interface mapping and manifest top modules differ")
        widths = interface.get("widths", {})
        interface_expected = {
            "host_data": manifest["host_data_width"],
            "memory_data": manifest["memory_data_width"],
            "memory_address": manifest["memory_address_width"],
        }
        for key, value in interface_expected.items():
            if widths.get(key) != value:
                raise ValueError(
                    f"VTA interface {key}={widths.get(key)!r}, expected {value!r}")
    data["_vta_ip_dir"] = ip_dir
    return data


def emit(data, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    values = {
        "SOC_CLOCK_HZ": data["soc"]["clock_hz"],
        "ROM_BASE": number(data["rom"]["base"]),
        "ROM_SIZE": number(data["rom"]["size"]),
        "SRAM_BASE": number(data["sram"]["base"]),
        "SRAM_SIZE": number(data["sram"]["size"]),
        "DDR_BASE": number(data["ddr"]["base"]),
        "DDR_SIZE": number(data["ddr"]["size"]),
        "DDR_DATA_WIDTH": data["ddr"]["data_width"],
        "UART_BASE": number(data["uart"]["base"]),
        "UART_SIZE": number(data["uart"]["size"]),
        "VTA_VCR_BASE": number(data["vta"]["vcr_base"]),
        "VTA_VCR_SIZE": number(data["vta"]["vcr_size"]),
        "VTA_MEMORY_DATA_WIDTH": data["vta"]["memory_data_width"],
    }
    architecture_name = data.get("architecture", {}).get("name")
    if architecture_name == TY1B_SIMPLE_ARCHITECTURE:
        values["SOC_ARCH_TY1B_SIMPLE"] = 1
        values["SOC_MEMORY_DDR"] = 1
        values["SOC_CASE_COMPATIBLE"] = 1
    header = ["/* Generated; do not edit. */", "#pragma once"]
    verilog = ["// Generated; do not edit."]
    for key, value in values.items():
        header.append(f"#define {key} 0x{value:x}u" if key.endswith(("BASE", "SIZE")) else f"#define {key} {value}u")
        verilog.append(f"`define {key} {value}")
    (output / "soc_config.h").write_text("\n".join(header) + "\n")
    (output / "soc_config.vh").write_text("\n".join(verilog) + "\n")
    clean = {key: value for key, value in data.items() if not key.startswith("_")}
    (output / "soc_config.resolved.json").write_text(json.dumps(clean, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "generate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--config", type=Path, required=True)
        cmd.add_argument("--allow-missing-ip", action="store_true")
        if name == "generate":
            cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = validate(load_config(args.config), require_ip=not args.allow_missing_ip)
    if args.command == "generate":
        emit(config, args.output)
    print(f"configuration valid: {args.config}")


if __name__ == "__main__":
    main()
