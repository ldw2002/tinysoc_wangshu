#!/usr/bin/env python3
"""Extract and validate the frozen VTA top-level interface.

Verilator is used as the Verilog parser.  The generated interface.json maps
stable semantic roles to the actual RTL port names, allowing the LiteX wrapper
to survive ordinary top-level port renames without hand-editing Python code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IP_DIR = REPO_ROOT / "generated" / "vta-ip" / "apb32-axi64"
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "ty1b_simple_npu.json"


@dataclass(frozen=True)
class Role:
    direction: str
    aliases: tuple[str, ...]
    required: bool = True
    widths: tuple[int, ...] | None = None


def _role(direction, *aliases, required=True, widths=None):
    return Role(direction, tuple(aliases), required, widths)


# Aliases are compared against the normalized suffix of a port.  This accepts
# both Chisel names (io_mem_aw_bits_addr) and conventional names (m_axi_awaddr).
ROLES = {
    "clock": _role("input", "clock", "clk", "aclk", widths=(1,)),
    "reset": _role("input", "reset", "rst", "resetn", "rstn", "areset", "aresetn", widths=(1,)),
    "host.paddr": _role("input", "paddr"),
    "host.psel": _role("input", "psel", widths=(1,)),
    "host.penable": _role("input", "penable", widths=(1,)),
    "host.pwrite": _role("input", "pwrite", widths=(1,)),
    "host.pwdata": _role("input", "pwdata"),
    # APB slave clock; in this SoC it shares the main system clock.
    "host.pclk": _role("input", "pclk", required=False, widths=(1,)),
    # APB4 has no write strobe; only APB5 adds PSTRB.  Treat it as optional so
    # RTL whose host port set is plain APB4 still maps cleanly.
    "host.pstrb": _role("input", "pstrb", required=False),
    "host.pprot": _role("input", "pprot", required=False, widths=(3,)),
    "host.prdata": _role("output", "prdata"),
    "host.pready": _role("output", "pready", widths=(1,)),
    "host.pslverr": _role("output", "pslverr", widths=(1,)),
    # Interrupt line; the simulation profile has no interrupt consumer.
    "interrupt": _role("output", "intr", required=False, widths=(1,)),
    "memory.aw.ready": _role("input", "awready", widths=(1,)),
    "memory.aw.valid": _role("output", "awvalid", widths=(1,)),
    "memory.aw.addr": _role("output", "awaddr"),
    "memory.aw.id": _role("output", "awid", required=False),
    "memory.aw.user": _role("output", "awuser", required=False),
    "memory.aw.len": _role("output", "awlen", widths=(4, 8)),
    "memory.aw.size": _role("output", "awsize", widths=(3,)),
    "memory.aw.burst": _role("output", "awburst", widths=(2, 3)),
    "memory.aw.lock": _role("output", "awlock", required=False, widths=(1, 2)),
    "memory.aw.cache": _role("output", "awcache", required=False, widths=(4,)),
    "memory.aw.prot": _role("output", "awprot", required=False, widths=(3,)),
    "memory.aw.qos": _role("output", "awqos", required=False, widths=(4,)),
    "memory.aw.region": _role("output", "awregion", required=False, widths=(4,)),
    "memory.w.ready": _role("input", "wready", widths=(1,)),
    "memory.w.valid": _role("output", "wvalid", widths=(1,)),
    "memory.w.data": _role("output", "wdata"),
    "memory.w.strb": _role("output", "wstrb"),
    "memory.w.last": _role("output", "wlast", widths=(1,)),
    "memory.w.id": _role("output", "wid", required=False),
    "memory.w.user": _role("output", "wuser", required=False),
    "memory.b.ready": _role("output", "bready", widths=(1,)),
    "memory.b.valid": _role("input", "bvalid", widths=(1,)),
    "memory.b.resp": _role("input", "bresp", widths=(2,)),
    "memory.b.id": _role("input", "bid", required=False),
    "memory.b.user": _role("input", "buser", required=False),
    "memory.ar.ready": _role("input", "arready", widths=(1,)),
    "memory.ar.valid": _role("output", "arvalid", widths=(1,)),
    "memory.ar.addr": _role("output", "araddr"),
    "memory.ar.id": _role("output", "arid", required=False),
    "memory.ar.user": _role("output", "aruser", required=False),
    "memory.ar.len": _role("output", "arlen", widths=(4, 8)),
    "memory.ar.size": _role("output", "arsize", widths=(3,)),
    "memory.ar.burst": _role("output", "arburst", widths=(2, 3)),
    "memory.ar.lock": _role("output", "arlock", required=False, widths=(1, 2)),
    "memory.ar.cache": _role("output", "arcache", required=False, widths=(4,)),
    "memory.ar.prot": _role("output", "arprot", required=False, widths=(3,)),
    "memory.ar.qos": _role("output", "arqos", required=False, widths=(4,)),
    "memory.ar.region": _role("output", "arregion", required=False, widths=(4,)),
    "memory.r.ready": _role("output", "rready", widths=(1,)),
    "memory.r.valid": _role("input", "rvalid", widths=(1,)),
    "memory.r.data": _role("input", "rdata"),
    "memory.r.resp": _role("input", "rresp", widths=(2,)),
    "memory.r.last": _role("input", "rlast", widths=(1,)),
    "memory.r.id": _role("input", "rid", required=False),
    "memory.r.user": _role("input", "ruser", required=False),
}


def canonical(name: str) -> str:
    value = "".join(character for character in name.lower() if character.isalnum())
    return value.replace("bits", "")


def parse_assignment(value: str, label: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError(f"{label} must use NAME=VALUE syntax: {value!r}")
    key, item = value.split("=", 1)
    if not key or not item:
        raise ValueError(f"{label} must use NAME=VALUE syntax: {value!r}")
    return key, item


def find_verilator() -> Path:
    configured = os.environ.get("VERILATOR")
    candidates = [Path(configured)] if configured else []
    discovered = shutil.which("verilator")
    if discovered:
        candidates.append(Path(discovered))
    candidates.extend((
        REPO_ROOT / "tools" / "linux" / "usr" / "bin" / "verilator",
        REPO_ROOT / "tools" / "xpack-riscv-none-elf-gcc-15.2.0-1" / "bin" / "verilator",
    ))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError("Verilator not found; set VERILATOR or install the bundled tools")


def dtype_width(dtype_id: str, dtypes: dict[str, ET.Element], stack=()) -> int:
    if dtype_id in stack:
        raise ValueError(f"recursive Verilator dtype {dtype_id}")
    dtype = dtypes.get(dtype_id)
    if dtype is None:
        raise ValueError(f"Verilator XML references unknown dtype {dtype_id}")
    left, right = dtype.get("left"), dtype.get("right")
    if left is not None and right is not None:
        try:
            return abs(int(left, 0) - int(right, 0)) + 1
        except ValueError as error:
            raise ValueError(f"non-constant width in dtype {dtype_id}") from error
    subtype = dtype.get("sub_dtype_id")
    if subtype is not None:
        return dtype_width(subtype, dtypes, stack + (dtype_id,))
    return 1


def extract_ports(ip_dir: Path, top: str) -> list[dict]:
    filelist = ip_dir / "filelist.f"
    if not filelist.is_file():
        raise ValueError(f"missing RTL file list: {filelist}")
    verilator = find_verilator()
    with tempfile.TemporaryDirectory(prefix="tinyvta-interface-") as temporary:
        xml_path = Path(temporary) / "vta.xml"
        command = [
            str(verilator), "--xml-only", "--top-module", top,
            "--xml-output", str(xml_path), "-f", str(filelist),
        ]
        result = subprocess.run(
            command, cwd=ip_dir, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False)
        if result.returncode != 0 or not xml_path.is_file():
            detail = result.stdout.strip()
            raise ValueError(f"Verilator could not parse top {top!r}:\n{detail}")
        root = ET.parse(xml_path).getroot()

    module = next((
        item for item in root.iter("module")
        if item.get("name") == top and item.get("topModule") == "1"
    ), None)
    if module is None:
        raise ValueError(f"Verilator XML contains no top module {top!r}")
    dtypes = {
        item.get("id"): item for item in root.iter()
        if item.get("id") is not None and item.tag.endswith("dtype")
    }
    ports = []
    for item in module.findall("var"):
        direction = item.get("dir")
        if direction not in {"input", "output", "inout"}:
            continue
        ports.append({
            "name": item.get("name"),
            "direction": direction,
            "width": dtype_width(item.get("dtype_id"), dtypes),
        })
    if not ports:
        raise ValueError(f"top module {top!r} exposes no ports")
    return ports


def infer_bindings(ports: list[dict], overrides: dict[str, str]) -> dict[str, str]:
    by_name = {port["name"]: port for port in ports}
    bindings = {}
    used = set()
    for role, port_name in overrides.items():
        if role not in ROLES:
            raise ValueError(f"unknown semantic role in --map: {role}")
        if port_name not in by_name:
            raise ValueError(f"--map {role} refers to missing port {port_name!r}")
        bindings[role] = port_name
        used.add(port_name)

    for role, specification in ROLES.items():
        if role in bindings:
            continue
        matches = [
            port["name"] for port in ports
            if port["name"] not in used
            and port["direction"] == specification.direction
            and any(canonical(port["name"]).endswith(alias) for alias in specification.aliases)
        ]
        if len(matches) > 1:
            raise ValueError(
                f"ambiguous ports for {role}: {', '.join(matches)}; "
                f"select one with --map {role}=PORT")
        if matches:
            bindings[role] = matches[0]
            used.add(matches[0])
        elif specification.required:
            raise ValueError(
                f"no port recognized for required role {role}; "
                f"supply --map {role}=PORT")
    return bindings


def validate_bindings(
    ports: list[dict], bindings: dict[str, str], ties: dict[str, int], ignored: list[str]
) -> dict:
    by_name = {port["name"]: port for port in ports}
    assigned = set(bindings.values())
    if len(assigned) != len(bindings):
        duplicates = sorted(name for name in assigned if list(bindings.values()).count(name) > 1)
        raise ValueError(f"one RTL port is mapped to multiple roles: {', '.join(duplicates)}")

    for role, port_name in bindings.items():
        port = by_name[port_name]
        specification = ROLES[role]
        if port["direction"] != specification.direction:
            raise ValueError(
                f"{port_name} is {port['direction']}, but role {role} requires "
                f"{specification.direction}")
        if specification.widths and port["width"] not in specification.widths:
            allowed = "/".join(str(width) for width in specification.widths)
            raise ValueError(f"{port_name} width is {port['width']}; role {role} requires {allowed}")

    for port_name, value in ties.items():
        port = by_name.get(port_name)
        if port is None:
            raise ValueError(f"tie refers to missing port {port_name!r}")
        if port["direction"] != "input":
            raise ValueError(f"only input ports can be tied: {port_name}")
        if value < 0 or value >= 1 << port["width"]:
            raise ValueError(f"tie value {value} does not fit {port_name}[{port['width'] - 1}:0]")

    for port_name in ignored:
        port = by_name.get(port_name)
        if port is None:
            raise ValueError(f"ignored output does not exist: {port_name!r}")
        if port["direction"] != "output":
            raise ValueError(f"only output ports can be ignored: {port_name}")

    claimed = assigned | set(ties) | set(ignored)
    unknown = [port for port in ports if port["name"] not in claimed]
    if unknown:
        details = ", ".join(
            f"{port['name']}({port['direction']}[{port['width']}])" for port in unknown)
        raise ValueError(
            "unhandled top-level ports: " + details + "; use --map ROLE=PORT, "
            "--tie INPUT=VALUE, or --ignore-output OUTPUT")

    def width(role):
        return by_name[bindings[role]]["width"]

    host_data = width("host.pwdata")
    if width("host.prdata") != host_data:
        raise ValueError("APB PWDATA and PRDATA widths differ")
    if host_data != 32:
        raise ValueError("the current LiteX control bridge supports APB4 data width 32 only")
    if "host.pstrb" in bindings:
        if host_data % 8 or width("host.pstrb") != host_data // 8:
            raise ValueError("APB PSTRB width must equal host data width / 8")

    memory_data = width("memory.w.data")
    if width("memory.r.data") != memory_data:
        raise ValueError("AXI WDATA and RDATA widths differ")
    if memory_data not in {32, 64, 128}:
        raise ValueError("the LiteX wrapper supports AXI data widths 32, 64, or 128")
    if width("memory.w.strb") != memory_data // 8:
        raise ValueError("AXI WSTRB width must equal memory data width / 8")
    address_widths = {width(role) for role in ("memory.aw.addr", "memory.ar.addr")}
    if len(address_widths) != 1:
        raise ValueError("AXI AWADDR and ARADDR widths differ")
    id_roles = [role for role in bindings if role.endswith(".id")]
    id_widths = {width(role) for role in id_roles}
    if len(id_widths) > 1:
        raise ValueError("AXI ID port widths differ")

    return {
        "host_address": width("host.paddr"),
        "host_data": host_data,
        "memory_address": address_widths.pop(),
        "memory_data": memory_data,
        "memory_id": id_widths.pop() if id_widths else 1,
    }


def interface_digest(ports: list[dict]) -> str:
    payload = json.dumps(ports, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def load_existing(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read existing interface description: {error}") from error
    return data


def load_config(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read SoC configuration {path}: {error}") from error


def build_description(args, manifest, existing, ports):
    old_overrides = existing.get("overrides", {}) if not args.clear_overrides else {}
    role_overrides = dict(old_overrides.get("roles", {}))
    ties = {name: int(value) for name, value in old_overrides.get("ties", {}).items()}
    ignored = list(old_overrides.get("ignored_outputs", []))
    reset_active_low = old_overrides.get("reset_active_low")

    for value in args.map:
        role, port = parse_assignment(value, "--map")
        role_overrides[role] = port
    for value in args.tie:
        port, constant = parse_assignment(value, "--tie")
        ties[port] = int(constant, 0)
    ignored.extend(args.ignore_output)
    ignored = sorted(set(ignored))
    if args.reset_active_low:
        reset_active_low = True
    elif args.reset_active_high:
        reset_active_low = False

    bindings = infer_bindings(ports, role_overrides)
    widths = validate_bindings(ports, bindings, ties, ignored)
    reset_name = bindings["reset"]
    if reset_active_low is None:
        reset_active_low = canonical(reset_name).endswith(("resetn", "rstn", "aresetn"))
    overrides = {
        "roles": dict(sorted(role_overrides.items())),
        "ties": dict(sorted(ties.items())),
        "ignored_outputs": ignored,
        "reset_active_low": reset_active_low,
    }
    return {
        "schema_version": 1,
        "top": manifest["top"],
        "rtl_port_sha256": interface_digest(ports),
        "protocols": {"host": "apb4", "memory": "axi4"},
        "widths": widths,
        "reset_active_low": reset_active_low,
        "roles": dict(sorted(bindings.items())),
        "overrides": overrides,
        "ports": ports,
    }


def expected_manifest(manifest: dict, description: dict, interface_bytes: bytes) -> dict:
    result = dict(manifest)
    widths = description["widths"]
    result.update({
        "variant": f"apb{widths['host_data']}-axi{widths['memory_data']}",
        "host_protocol": "apb4",
        "host_data_width": widths["host_data"],
        "host_address_width": widths["host_address"],
        "memory_protocol": "axi4",
        "memory_data_width": widths["memory_data"],
        "memory_address_width": widths["memory_address"],
        "memory_id_width": widths["memory_id"],
        "interface_file": "interface.json",
        "interface_sha256": hashlib.sha256(interface_bytes).hexdigest(),
    })
    return result


def validate_config(config: dict | None, manifest: dict) -> list[str]:
    if config is None:
        return []
    vta = config.get("vta", {})
    mismatches = []
    expected = {
        "host_protocol": manifest["host_protocol"],
        "host_data_width": manifest["host_data_width"],
        "memory_protocol": manifest["memory_protocol"],
        "memory_data_width": manifest["memory_data_width"],
    }
    for key, value in expected.items():
        if vta.get(key) != value:
            mismatches.append(f"config vta.{key}={vta.get(key)!r}, RTL requires {value!r}")
    soc_width = config.get("soc", {}).get("address_width")
    if soc_width != manifest["memory_address_width"]:
        mismatches.append(
            f"config soc.address_width={soc_width!r}, RTL requires "
            f"{manifest['memory_address_width']!r}")
    return mismatches


def parse_args():
    parser = argparse.ArgumentParser(
        description="generate or validate the LiteX mapping for a VTA RTL top")
    parser.add_argument("--ip-dir", type=Path, default=DEFAULT_IP_DIR)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--map", action="append", default=[], metavar="ROLE=PORT",
                        help="override automatic semantic port recognition")
    parser.add_argument("--tie", action="append", default=[], metavar="INPUT=VALUE",
                        help="tie an additional RTL input to an integer constant")
    parser.add_argument("--ignore-output", action="append", default=[], metavar="PORT",
                        help="explicitly leave an additional RTL output unused")
    reset = parser.add_mutually_exclusive_group()
    reset.add_argument("--reset-active-low", action="store_true",
                       help="override automatic reset-polarity recognition")
    reset.add_argument("--reset-active-high", action="store_true",
                       help="override automatic reset-polarity recognition")
    parser.add_argument("--clear-overrides", action="store_true",
                        help="discard all interface overrides saved previously")
    parser.add_argument("--list-roles", action="store_true",
                        help="print semantic roles accepted by --map and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_roles:
        for role in ROLES:
            print(role)
        return 0
    if args.check and (
        args.map or args.tie or args.ignore_output or args.clear_overrides
        or args.reset_active_low or args.reset_active_high
    ):
        print("error: --check cannot change interface overrides", file=sys.stderr)
        return 2
    ip_dir = args.ip_dir.resolve()
    manifest_path = ip_dir / "manifest.json"
    interface_path = ip_dir / "interface.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("host_protocol") != "apb4" or manifest.get("memory_protocol") != "axi4":
            raise ValueError("this generator supports an APB4 host and AXI4 memory interface")
        top = manifest.get("top")
        if not isinstance(top, str) or not top:
            raise ValueError("manifest.json has no valid top module")
        rtl_path = ip_dir / "rtl" / "vta.v"
        rtl_digest = hashlib.sha256(rtl_path.read_bytes()).hexdigest()
        if rtl_digest != manifest.get("rtl_sha256"):
            raise ValueError("RTL hash is stale; run make rtl-sync before interface-sync")
        existing = load_existing(interface_path)
        ports = extract_ports(ip_dir, top)
        description = build_description(args, manifest, existing, ports)
        interface_bytes = (json.dumps(description, indent=2, ensure_ascii=True) + "\n").encode()
        updated_manifest = expected_manifest(manifest, description, interface_bytes)
        manifest_bytes = (json.dumps(updated_manifest, indent=2, ensure_ascii=True) + "\n").encode()
        config = load_config(args.config.resolve() if args.config else None)
        mismatches = validate_config(config, updated_manifest)
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    pending = []
    if not interface_path.is_file() or interface_path.read_bytes() != interface_bytes:
        pending.append("interface.json")
    if manifest_path.read_bytes() != manifest_bytes:
        pending.append("manifest.json")

    print(f"IP package : {ip_dir}")
    print(f"top        : {top} ({len(ports)} ports)")
    print(f"host       : APB4 {description['widths']['host_data']}-bit")
    print(
        f"memory     : AXI4 {description['widths']['memory_data']}-bit data, "
        f"{description['widths']['memory_address']}-bit address")

    if args.check:
        if pending:
            print("out of sync: " + ", ".join(pending), file=sys.stderr)
            return 1
        if mismatches:
            print("configuration mismatch: " + "; ".join(mismatches), file=sys.stderr)
            return 1
        print("VTA RTL interface mapping is up to date")
        return 0
    if args.dry_run:
        print("would update: " + (", ".join(pending) if pending else "nothing"))
        for mismatch in mismatches:
            print("warning: " + mismatch, file=sys.stderr)
        return 0

    if "interface.json" in pending:
        interface_path.write_bytes(interface_bytes)
    if "manifest.json" in pending:
        manifest_path.write_bytes(manifest_bytes)
    print("updated: " + (", ".join(pending) if pending else "nothing"))
    for mismatch in mismatches:
        print("warning: " + mismatch, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
