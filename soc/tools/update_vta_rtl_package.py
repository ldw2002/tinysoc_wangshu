#!/usr/bin/env python3
"""Rename a packaged VTA RTL top module and synchronize its metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IP_DIR = REPO_ROOT / "generated" / "vta-ip" / "apb32-axi64"
DEFAULT_RTL = Path("rtl/vta.v")
VERILOG_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def module_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"^(?P<prefix>[ \t]*module[ \t]+){re.escape(name)}"
        rf"(?=[ \t]*(?:#[ \t]*)?\()",
        re.MULTILINE,
    )


def replace_top_module(rtl: bytes, old_top: str, new_top: str) -> tuple[bytes, bool]:
    try:
        text = rtl.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("RTL must be UTF-8 text") from error

    old_matches = list(module_pattern(old_top).finditer(text))
    new_matches = list(module_pattern(new_top).finditer(text))

    if old_top == new_top:
        if len(old_matches) != 1:
            raise ValueError(
                f"expected exactly one declaration of module {old_top!r}, "
                f"found {len(old_matches)}"
            )
        return rtl, False

    if new_matches:
        if len(new_matches) != 1 or old_matches:
            raise ValueError(
                f"cannot safely rename {old_top!r} to {new_top!r}: "
                "both names or duplicate declarations exist"
            )
        # The RTL was renamed manually; only its metadata needs synchronization.
        return rtl, False

    if len(old_matches) != 1:
        raise ValueError(
            f"expected exactly one declaration of module {old_top!r}, "
            f"found {len(old_matches)}"
        )

    updated, count = module_pattern(old_top).subn(
        lambda match: f"{match.group('prefix')}{new_top}", text, count=1
    )
    assert count == 1
    return updated.encode("utf-8"), True


def update_checksum_file(contents: str, rtl_name: str, digest: str) -> str:
    lines = contents.splitlines(keepends=True)
    checksum_pattern = re.compile(
        r"^(?P<digest>[0-9a-fA-F]{64})(?P<separator>[ \t]+\*?)"
        r"(?P<filename>[^\r\n]+)(?P<newline>\r?\n)?$"
    )
    matches = []

    for index, line in enumerate(lines):
        match = checksum_pattern.match(line)
        if match and Path(match.group("filename")).as_posix() == rtl_name:
            matches.append((index, match))

    if len(matches) > 1:
        raise ValueError(f"multiple checksum entries found for {rtl_name}")
    if matches:
        index, match = matches[0]
        newline = match.group("newline") or ""
        lines[index] = f"{digest}{match.group('separator')}{rtl_name}{newline}"
    else:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.append(f"{digest}  {rtl_name}\n")
    return "".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rename the VTA top module, then synchronize manifest.json and "
            "rtl.sha256 with the RTL file."
        )
    )
    parser.add_argument(
        "--ip-dir",
        type=Path,
        default=DEFAULT_IP_DIR,
        help=f"VTA IP package directory (default: {DEFAULT_IP_DIR})",
    )
    parser.add_argument(
        "--rtl",
        type=Path,
        default=DEFAULT_RTL,
        help=f"RTL path relative to --ip-dir (default: {DEFAULT_RTL})",
    )
    parser.add_argument(
        "--top",
        help=(
            "desired top-module name; omit it to retain the manifest top and "
            "only synchronize/check hashes"
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify that RTL, manifest and checksum metadata already agree",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="show the required updates without writing files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ip_dir = args.ip_dir.resolve()
    manifest_path = ip_dir / "manifest.json"
    checksum_path = ip_dir / "rtl.sha256"
    rtl_path = (ip_dir / args.rtl).resolve()

    try:
        rtl_relative = rtl_path.relative_to(ip_dir).as_posix()
    except ValueError:
        print("error: --rtl must point inside --ip-dir", file=sys.stderr)
        return 2

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checksum_text = checksum_path.read_text(encoding="utf-8")
        rtl_bytes = rtl_path.read_bytes()
    except (OSError, json.JSONDecodeError) as error:
        print(f"error: unable to read VTA IP package: {error}", file=sys.stderr)
        return 2

    old_top = manifest.get("top")
    if not isinstance(old_top, str) or not VERILOG_IDENTIFIER.fullmatch(old_top):
        print("error: manifest.json has no valid Verilog top name", file=sys.stderr)
        return 2
    new_top = args.top or old_top
    if not VERILOG_IDENTIFIER.fullmatch(new_top):
        print(f"error: invalid Verilog module name: {new_top!r}", file=sys.stderr)
        return 2

    try:
        updated_rtl, rtl_changed = replace_top_module(rtl_bytes, old_top, new_top)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    digest = hashlib.sha256(updated_rtl).hexdigest()
    old_digest = manifest.get("rtl_sha256")
    manifest["top"] = new_top
    manifest["rtl_sha256"] = digest
    updated_manifest = json.dumps(manifest, indent=2, ensure_ascii=True) + "\n"
    try:
        updated_checksum = update_checksum_file(checksum_text, rtl_relative, digest)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    current_manifest = manifest_path.read_text(encoding="utf-8")
    changes = {
        "RTL module declaration": rtl_changed,
        "manifest.json": current_manifest != updated_manifest,
        "rtl.sha256": checksum_text != updated_checksum,
    }

    print(f"IP package : {ip_dir}")
    print(f"RTL        : {rtl_relative}")
    print(f"top        : {old_top} -> {new_top}")
    print(f"SHA256     : {old_digest or '<missing>'} -> {digest}")

    pending = [name for name, changed in changes.items() if changed]
    if args.check:
        if pending:
            print("out of sync: " + ", ".join(pending), file=sys.stderr)
            return 1
        print("VTA RTL package metadata is up to date")
        return 0

    if args.dry_run:
        print("would update: " + (", ".join(pending) if pending else "nothing"))
        return 0

    if rtl_changed:
        rtl_path.write_bytes(updated_rtl)
    if changes["manifest.json"]:
        manifest_path.write_bytes(updated_manifest.encode("utf-8"))
    if changes["rtl.sha256"]:
        checksum_path.write_bytes(updated_checksum.encode("utf-8"))

    print("updated: " + (", ".join(pending) if pending else "nothing"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
