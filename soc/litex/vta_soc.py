#!/usr/bin/env python3
"""Generate the minimal TY1B-compatible LiteX/VTA simulation SoC."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

from litex.soc.integration.builder import Builder
from litex.soc.integration.common import get_mem_data
from litex.build.sim.config import SimConfig
from ty1b_soc import TY1BSimpleVTASoC


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("soc_config", ROOT / "tools" / "soc_config.py")
SOC_CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SOC_CONFIG)


class VTABuilder(Builder):
    """Use a case firmware package in place of LiteX's default BIOS."""

    def __init__(self, *args, case_dir=None, **kwargs):
        self.case_dir = case_dir
        super().__init__(*args, **kwargs)

    def add_software_package(self, name, src_dir=None):
        if name == "bios" and self.case_dir is not None:
            src_dir = str(self.case_dir)
        super().add_software_package(name, src_dir)


def make_sim_config(config, case_dir):
    sim_config = SimConfig()
    sim_config.add_clocker("sys_clk", freq_hz=config["soc"]["clock_hz"])
    if case_dir is not None:
        sim_config.add_module("serial2console", "serial")
    return sim_config


def make_builder(soc, case_dir, build_dir, compile_software, compile_gateware):
    return VTABuilder(
        soc,
        case_dir=case_dir,
        output_dir=str(build_dir),
        csr_csv=str(build_dir / "csr.csv"),
        compile_software=compile_software,
        compile_gateware=compile_gateware,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--build", action="store_true", help="compile the Verilator simulator")
    parser.add_argument("--no-run", action="store_true", help="build simulation artifacts without starting Vsim")
    parser.add_argument("--case-dir", type=Path, help="compile this generated single-operator case as BIOS")
    args = parser.parse_args()
    config = SOC_CONFIG.validate(SOC_CONFIG.load_config(args.config), require_ip=True)
    case_dir = args.case_dir.resolve() if args.case_dir else None
    rom_init = None
    ddr_init = None
    sram_init = None

    if args.build and case_dir is not None:
        # First generate the software environment and compile the case ELF.
        # Its Makefile emits independent ROM and DDR binaries.  This pass does
        # not compile a simulator; the final pass below embeds both images.
        prepare_soc = TY1BSimpleVTASoC(config, case_dir)
        prepare_builder = make_builder(
            prepare_soc,
            case_dir,
            args.build_dir,
            compile_software=True,
            compile_gateware=False,
        )
        prepare_builder.build(
            sim_config=make_sim_config(config, case_dir),
            run=False,
        )

        image_dir = args.build_dir / "software" / "bios"
        rom_image = image_dir / "bios.bin"
        sram_image = image_dir / "sram.bin"
        ddr_image = image_dir / "ddr.bin"
        if not rom_image.is_file() or not sram_image.is_file() or not ddr_image.is_file():
            raise FileNotFoundError(
                f"case build did not produce {rom_image}, {sram_image} and {ddr_image}")
        rom_init = get_mem_data(
            str(rom_image),
            data_width=32,
            endianness=prepare_soc.cpu.endianness,
            mem_size=SOC_CONFIG.number(config["rom"]["size"]),
        )
        ddr_init = get_mem_data(
            str(ddr_image),
            data_width=32,
            endianness=prepare_soc.cpu.endianness,
            mem_size=SOC_CONFIG.number(config["ddr"]["size"]),
        )
        sram_init = get_mem_data(
            str(sram_image),
            data_width=32,
            endianness=prepare_soc.cpu.endianness,
            mem_size=SOC_CONFIG.number(config["sram"]["size"]),
        )
        print(
            f"Memory images: ROM={rom_image.stat().st_size} bytes, "
            f"SRAM={sram_image.stat().st_size} bytes, "
            f"DDR={ddr_image.stat().st_size} bytes (expected data)")

    # The minimal profile has no timer.  A no-case architecture generation
    # therefore leaves ROM empty; case builds use the precompiled ROM image
    # and preload the second image directly into the DDR3 simulation model.
    soc = TY1BSimpleVTASoC(
        config,
        case_dir,
        rom_init=rom_init,
        ddr_init=ddr_init,
        sram_init=sram_init,
    )
    builder = make_builder(
        soc,
        case_dir,
        args.build_dir,
        compile_software=False,
        compile_gateware=args.build,
    )
    builder.build(
        sim_config=make_sim_config(config, case_dir),
        run=args.build and not args.no_run,
    )


if __name__ == "__main__":
    main()
