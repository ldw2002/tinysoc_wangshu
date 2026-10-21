"""Minimal TY1B-compatible CPU + VTA LiteX integration model."""

from __future__ import annotations

import math

from litex.build.generic_platform import Pins, Subsignal
from litex.build.io import CRG
from litex.build.sim import SimPlatform
from litex.build.sim.platform import SimFinish, SimMarker
from litex.soc.integration.soc import SoCCSRHandler, SoCRegion
from litex.soc.integration.soc_core import SoCCore
from litex.soc.interconnect import axi
from litedram import modules as litedram_modules
from litedram.phy.model import SDRAMPHYModel, sdram_module_nphases
from axi_burst_splitter import AXIBurstSplitter
from vta_ip import FrozenVTA


TY1B_SIMPLE_HARDWARE_PERIPHERALS = ("cpu", "axi", "npu", "ddr", "uart")
TY1B_SIMPLE_IO = [
    ("sys_clk", 0, Pins(1)),
    ("serial", 0,
        Subsignal("source_valid", Pins(1)),
        Subsignal("source_ready", Pins(1)),
        Subsignal("source_data", Pins(8)),
        Subsignal("sink_valid", Pins(1)),
        Subsignal("sink_ready", Pins(1)),
        Subsignal("sink_data", Pins(8))),
]


def _number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


class TY1BSimplePlatform(SimPlatform):
    def __init__(self):
        super().__init__("SIM", TY1B_SIMPLE_IO)


class ExactSizeSoCRegion(SoCRegion):
    """Decode a byte-exact region instead of rounding it to a power of two."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.size_pow2 = self.size

    def decoder(self, bus):
        word_shift = int(math.log2(bus.data_width // 8))
        origin = self.origin >> word_shift
        limit = (self.origin + self.size) >> word_shift
        return lambda address: (address >= origin) & (address < limit)


class TY1BSimpleVTASoC(SoCCore):
    """Minimal CPU/AXI/DDR/VTA/UART compatibility model.

    LiteDRAM supplies the verification model for the external read/write DDR
    subsystem.  A real TY1B integration replaces the model with its board DDR
    controller at the same AXI memory boundary.  There is no SoC SRAM, LiteX
    controller, timer or L2 cache.  UART remains available for case results.
    """

    hardware_peripherals = TY1B_SIMPLE_HARDWARE_PERIPHERALS

    def check_bios_requirements(self):
        for name in ("rom", "main_ram"):
            if name not in self.bus.regions:
                raise ValueError(f"TY1B-simple firmware requires the {name} region")
        # SoCCore's default check unconditionally requires timer0. The simple
        # profile intentionally has no timer; its case Makefile supplies the
        # small link-compatibility accessors instead.

    def __init__(self, config, case_dir=None, rom_init=None, ddr_init=None, sram_init=None):
        platform = TY1BSimplePlatform()
        self.crg = CRG(platform.request("sys_clk"))

        rom_size = _number(config["rom"]["size"])
        simulation_helpers = case_dir is not None
        self.mem_map = dict(SoCCore.mem_map)
        self.mem_map.update({
            "rom": _number(config["rom"]["base"]),
            "sram": _number(config["sram"]["base"]),
            "main_ram": _number(config["ddr"]["base"]),
            "csr": _number(config["uart"]["base"]),
        })
        uart = config["uart"]
        csr_size = _number(uart["size"])
        csr_address_width = csr_size.bit_length() - 3
        # LiteX's CSR datapath supports this width, but its public whitelist
        # starts at 14 (a 64 KiB byte aperture).  Ten CSR word-address bits
        # produce the requested 4 KiB byte aperture.
        if csr_address_width == 10 and 10 not in SoCCSRHandler.supported_address_width:
            SoCCSRHandler.supported_address_width = [
                10, *SoCCSRHandler.supported_address_width]
        self.csr_map = {
            "uart": 0,
            "sdram": 1,
            "sim_finish": 2,
            "sim_marker": 3,
        }
        super().__init__(
            platform,
            clk_freq=config["soc"]["clock_hz"],
            ident="",
            cpu_type=config["soc"]["cpu"],
            cpu_variant=config["soc"].get("cpu_variant", "standard"),
            bus_standard="axi",
            bus_data_width=32,
            bus_address_width=config["soc"]["address_width"],
            integrated_rom_size=rom_size,
            integrated_rom_init=[] if rom_init is None else rom_init,
            integrated_sram_size=0,
            integrated_main_ram_size=0,
            csr_address_width=csr_address_width,
            csr_paging=_number(uart["csr_paging"]),
            with_ctrl=False,
            with_uart=True,
            uart_name="sim",
            with_timer=False,
            irq_n_irqs=1,
        )

        self.bus.regions["rom"].cached = False

        ddr = config["ddr"]
        ddr_module_cls = getattr(litedram_modules, ddr["model"])
        ddr_rate = "1:{}".format(sdram_module_nphases[ddr_module_cls.memtype])
        ddr_module = ddr_module_cls(ddr["clock_hz"], ddr_rate)
        self.sdrphy = SDRAMPHYModel(
            module=ddr_module,
            data_width=ddr["phy_data_width"],
            clk_freq=ddr["clock_hz"],
            init=[] if ddr_init is None else ddr_init,
        )
        self.add_sdram(
            "sdram",
            phy=self.sdrphy,
            module=ddr_module,
            size=_number(ddr["size"]),
            l2_cache_size=ddr["l2_size"],
            l2_cache_min_data_width=128,
            l2_cache_reverse=False,
        )
        # LiteX's stock SoCRegion rounds non-power-of-two decode windows up.
        # Preserve the configured 160 KiB DDR aperture byte-for-byte.
        self.bus.regions["main_ram"] = ExactSizeSoCRegion(
            origin=_number(ddr["base"]),
            size=_number(ddr["size"]),
            mode="rwx",
        )
        # Mark the shared DDR region uncached in the SoC memory map.  The
        # VexRiscv-standard L1 policy is address based, so the case runtime
        # also flushes its D-cache around DMA.  A hardware port must either
        # provide a truly uncached alias or implement the same cache hooks.
        self.bus.regions["main_ram"].cached = ddr["cached"]
        self.add_constant("SDRAM_TEST_DISABLE")

        # Add the optional on-chip SRAM as a byte-exact bus region.  Its data
        # image is preloaded by the case build so the VTA DMA can read hot
        # buffers without touching the DDR3 model.
        sram = config["sram"]
        self.add_ram(
            "sram",
            origin=_number(sram["base"]),
            size=_number(sram["size"]),
            contents=[] if sram_init is None else sram_init,
        )
        self.bus.regions["sram"] = ExactSizeSoCRegion(
            origin=_number(sram["base"]),
            size=_number(sram["size"]),
            mode="rwx",
        )
        self.bus.regions["sram"].cached = False

        if simulation_helpers:
            # LiteX's sim_finish() helper references the marker count, so keep
            # the marker bank but omit the unused trace bank.  Together with
            # DDR control and UART, this fits exactly in four 1 KiB CSR pages.
            self.submodules.sim_finish = SimFinish()
            self.submodules.sim_marker = SimMarker()
            self.comb += platform.trace.eq(0)
        else:
            self.comb += platform.trace.eq(1)

        self.submodules.vta = npu = FrozenVTA(
            platform,
            config["_vta_ip_dir"],
            control_base=_number(config["vta"]["vcr_base"]),
            sim_debug=simulation_helpers,
        )
        self.bus.add_slave("npu_vcr", npu.control.wb, SoCRegion(
            origin=_number(config["vta"]["vcr_base"]),
            size=_number(config["vta"]["vcr_size"]),
            cached=False,
        ))

        self.npu_dma = npu_dma = axi.AXIInterface(
            data_width=config["vta"]["memory_data_width"],
            address_width=config["soc"]["address_width"],
            id_width=8,
        )
        self.submodules.npu_burst_splitter = AXIBurstSplitter(
            npu.axi, npu_dma, max_beats=128)
        self.bus.add_master("npu_dma", npu_dma)

        self.add_constant("VTA_VCR_BASE", _number(config["vta"]["vcr_base"]))
        self.add_constant("VTA_MEMORY_DATA_WIDTH", config["vta"]["memory_data_width"])
        self.add_constant("DDR_BASE", _number(ddr["base"]))
        self.add_constant("DDR_SIZE", _number(ddr["size"]))
        self.add_constant("SRAM_BASE", _number(sram["base"]))
        self.add_constant("SRAM_SIZE", _number(sram["size"]))
        self.add_constant("UART_BASE", _number(uart["base"]))
        self.add_constant("UART_SIZE", csr_size)
        self.add_constant("SOC_ARCH_TY1B_SIMPLE")
        self.add_constant("SOC_MEMORY_DDR")
        self.add_constant("SOC_CASE_COMPATIBLE")
        if simulation_helpers:
            self.add_config("BIOS_NO_BOOT")
            self.add_config("BIOS_NO_DELAYS")
            self.add_config("BIOS_NO_PROMPT")
            self.add_constant("TY1B_SIMPLE_SIMULATION_HELPERS")
            if ddr_init is not None:
                self.add_constant("SOC_DDR_PRELOADED")
        self.case_dir = case_dir
