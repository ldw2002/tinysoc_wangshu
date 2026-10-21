#!/usr/bin/env python3
"""Check the tools required by the frozen-RTL SoC simulation flow.

The full TVM-VTA repository keeps Chisel's ``sbt`` toolchain in the
``tvm_py310`` Conda environment.  This migration package intentionally ships
pre-generated RTL, so simulation only needs LiteX's Python packages, a host
``make``, Verilator, and a RISC-V cross compiler.  The checks below mirror the
fallbacks used by ``scripts/sim_build.sh`` instead of requiring the original
developer's absolute Conda paths.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"missing {label}: {path}")


def require_any(paths: tuple[Path, ...], label: str) -> Path:
    for path in paths:
        if path.is_file():
            return path
    choices = ", ".join(str(path) for path in paths)
    raise SystemExit(f"missing {label}; checked: {choices}")


def tool_roots(soc: Path) -> tuple[Path, ...]:
    roots = []
    configured = os.environ.get("TINYVTA_TOOLS_DIR")
    if configured:
        roots.append(Path(configured).expanduser().resolve())
    roots.append(soc.parent / "tools")
    return tuple(dict.fromkeys(path.resolve() for path in roots))


def main() -> None:
    soc = Path(__file__).resolve().parents[1]
    conda = Path(sys.base_prefix)
    roots = tool_roots(soc)

    if sys.version_info[:2] != (3, 10):
        raise SystemExit(
            f"unsupported Python {platform.python_version()}; "
            "this SoC environment is validated with Python 3.10"
        )

    # These are the tools consumed by the Linux simulation path.  Prefer the
    # active Conda environment, then use the self-contained tools shipped next
    # to the migration package.  ``verilator_bin`` is checked because the
    # bundled compatibility wrapper invokes it directly.
    linux_tools = tuple(root / "linux" / "usr" for root in roots)
    verilator = require_any(
        (conda / "bin" / "verilator",) + tuple(
            path / "bin" / executable
            for path in linux_tools
            for executable in ("verilator", "verilator_bin")
        ),
        "Verilator",
    )
    require_any(
        (conda / "bin" / "make", Path(shutil.which("make") or "")),
        "make",
    )
    riscv = require_any(
        tuple(
            root / "xpack-riscv-none-elf-gcc-15.2.0-1" /
            "bin" / "riscv-none-elf-gcc"
            for root in roots
        ) + tuple(
            path / "bin" / "riscv64-unknown-elf-gcc"
            for path in linux_tools
        ),
        "RISC-V toolchain",
    )
    for module in ("litex", "litedram", "migen", "packaging", "serial"):
        if importlib.util.find_spec(module) is None:
            raise SystemExit(f"missing Python package in soc/.venv: {module}")
    if platform.system() == "Darwin":
        if shutil.which("xcrun") is None:
            raise SystemExit("missing xcrun; install Apple Command Line Tools")
        sdk = subprocess.check_output(
            ("xcrun", "--show-sdk-path"), text=True).strip()
        require_file(Path(sdk) / "usr" / "include" / "c++" / "v1",
                     "Apple SDK libc++ headers")

    # sbt, cmake and OpenJDK are only needed to regenerate RTL from Chisel.
    # They are intentionally optional because this package consumes frozen RTL
    # and ``make rtl`` only synchronizes its manifest/checksum metadata.
    rtl_tools = tuple(
        conda / "bin" / name for name in ("sbt", "cmake")
    )
    missing_rtl = [str(path) for path in rtl_tools if not path.is_file()]
    if not (conda / "lib" / "jvm").is_dir():
        missing_rtl.append(str(conda / "lib" / "jvm"))
    suffix = ""
    if missing_rtl:
        suffix = " (optional Chisel tools unavailable: " + ", ".join(missing_rtl) + ")"
    print(
        f"SoC environment valid: venv={sys.prefix}, "
        f"verilator={verilator}, riscv={riscv}{suffix}"
    )


if __name__ == "__main__":
    main()
