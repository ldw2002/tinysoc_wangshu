"""LiteX wrapper for a frozen APB32 + AXI VTA RTL package."""

import hashlib
import json
from pathlib import Path

from migen import ClockSignal, Constant, Display, FSM, If, Instance, Module, NextState, NextValue, ResetSignal, Signal
from litex.soc.interconnect import axi, wishbone


class WishboneToAPB32(Module):
    """Single-request Wishbone to APB4 bridge used for the VTA VCR."""

    def __init__(self, address_width=16, base_address=0):
        self.wb = wishbone.Interface(data_width=32, adr_width=30, addressing="word")
        self.paddr = Signal(address_width)
        self.psel = Signal()
        self.penable = Signal()
        self.pwrite = Signal()
        self.pwdata = Signal(32)
        self.pstrb = Signal(4)
        self.pprot = Signal(3)
        self.prdata = Signal(32)
        self.pready = Signal()
        self.pslverr = Signal()
        address_mask = (1 << address_width) - 1
        local_base = base_address & address_mask

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If(self.wb.cyc & self.wb.stb,
                # APB request fields must remain stable through SETUP and
                # ACCESS, after the originating Wishbone request is accepted.
                NextValue(
                    self.paddr,
                    (self.wb.adr[: max(0, address_width - 2)] << 2) - local_base),
                NextValue(self.pwrite, self.wb.we),
                NextValue(self.pwdata, self.wb.dat_w),
                NextValue(self.pstrb, self.wb.sel),
                NextValue(self.pprot, 0),
                NextState("SETUP")))
        fsm.act("SETUP", self.psel.eq(1), NextState("ACCESS"))
        fsm.act("ACCESS",
            self.psel.eq(1), self.penable.eq(1),
            If(self.pready,
                self.wb.dat_r.eq(self.prdata),
                self.wb.ack.eq(~self.pslverr),
                self.wb.err.eq(self.pslverr),
                NextState("IDLE")))


class FrozenVTA(Module):
    def __init__(self, platform, ip_dir, control_base=0, sim_debug=False):
        ip_dir = Path(ip_dir)
        manifest = json.loads((ip_dir / "manifest.json").read_text())
        if manifest["host_protocol"] != "apb4" or manifest["host_data_width"] != 32:
            raise ValueError("FrozenVTA requires an APB4 32-bit host package")
        if manifest["memory_protocol"] != "axi4":
            raise ValueError("FrozenVTA requires an AXI4 memory interface")
        interface_path = ip_dir / manifest.get("interface_file", "interface.json")
        if not interface_path.is_file():
            raise ValueError(
                f"missing generated VTA interface mapping: {interface_path}; "
                "run make interface-sync")
        interface_bytes = interface_path.read_bytes()
        digest = hashlib.sha256(interface_bytes).hexdigest()
        if digest != manifest.get("interface_sha256"):
            raise ValueError(
                f"stale VTA interface mapping: {interface_path}; "
                "run make interface-sync")
        interface = json.loads(interface_bytes)
        if interface.get("schema_version") != 1:
            raise ValueError("unsupported VTA interface mapping schema")
        if interface.get("top") != manifest["top"]:
            raise ValueError("VTA interface mapping and manifest top modules differ")
        if interface.get("protocols") != {"host": "apb4", "memory": "axi4"}:
            raise ValueError("VTA interface mapping must describe APB4 + AXI4")

        widths = interface["widths"]
        width = widths["memory_data"]
        if width not in (32, 64, 128):
            raise ValueError("VTA memory data width must be 32, 64 or 128")
        if width != manifest["memory_data_width"]:
            raise ValueError("VTA interface and manifest memory widths differ")

        for entry in (ip_dir / "filelist.f").read_text().splitlines():
            entry = entry.strip()
            if entry and not entry.startswith("#"):
                platform.add_source(str(ip_dir / entry))

        control = WishboneToAPB32(
            address_width=widths["host_address"],
            base_address=control_base,
        )
        self.submodules.control = control
        ports = {port["name"]: port for port in interface["ports"]}
        roles = interface["roles"]
        params = {}

        def bind(role, value):
            port_name = roles[role]
            direction = ports[port_name]["direction"]
            prefix = {"input": "i_", "output": "o_", "inout": "io_"}[direction]
            params[prefix + port_name] = value

        def bind_optional(role, value):
            if role in roles:
                bind(role, value)
                return True
            return False

        def bind_output(role, target, default=0):
            if role not in roles:
                self.comb += target.eq(default)
                return
            port = ports[roles[role]]
            if port["width"] == len(target):
                bind(role, target)
                return
            adapted = Signal(port["width"])
            bind(role, adapted)
            self.comb += target.eq(adapted)

        def discard_output(role):
            if role in roles:
                bind(role, Signal(ports[roles[role]]["width"]))

        reset = ResetSignal("sys")
        if interface.get("reset_active_low"):
            reset = ~reset
        bind("clock", ClockSignal("sys"))
        bind("reset", reset)
        bind_optional("host.pclk", ClockSignal("sys"))
        bind("host.paddr", control.paddr)
        bind("host.psel", control.psel)
        bind("host.penable", control.penable)
        bind("host.pwrite", control.pwrite)
        bind("host.pwdata", control.pwdata)
        # Plain APB4 host ports have neither PSTRB nor PPROT; only wire them up
        # when the frozen RTL actually exposes them.
        bind_optional("host.pstrb", control.pstrb)
        bind_optional("host.pprot", control.pprot)
        bind("host.prdata", control.prdata)
        bind("host.pready", control.pready)
        bind("host.pslverr", control.pslverr)
        discard_output("interrupt")

        self.axi = raw = a = axi.AXIInterface(
            data_width=width,
            address_width=widths["memory_address"],
            id_width=widths["memory_id"],
        )
        # AXI4 LEN is eight bits.  Keeping only four bits silently truncates
        # legal 16--256 beat bursts (notably 32-bit instruction fetches).
        bind("memory.aw.ready", raw.aw.ready)
        bind("memory.aw.valid", raw.aw.valid)
        bind("memory.aw.addr", raw.aw.addr)
        bind_output("memory.aw.id", raw.aw.id)
        bind_output("memory.aw.len", raw.aw.len)
        bind("memory.aw.size", raw.aw.size)
        bind("memory.aw.burst", raw.aw.burst)
        bind_output("memory.aw.lock", raw.aw.lock)
        bind_output("memory.aw.cache", raw.aw.cache)
        bind_output("memory.aw.prot", raw.aw.prot)
        bind_output("memory.aw.qos", raw.aw.qos)
        discard_output("memory.aw.region")
        discard_output("memory.aw.user")

        bind("memory.w.ready", raw.w.ready)
        bind("memory.w.valid", raw.w.valid)
        bind("memory.w.data", raw.w.data)
        bind("memory.w.strb", raw.w.strb)
        bind("memory.w.last", raw.w.last)
        discard_output("memory.w.id")
        discard_output("memory.w.user")

        bind("memory.b.ready", raw.b.ready)
        bind("memory.b.valid", raw.b.valid)
        bind("memory.b.resp", raw.b.resp)
        bind_optional("memory.b.id", raw.b.id)
        if "memory.b.user" in roles:
            bind("memory.b.user", Constant(0, ports[roles["memory.b.user"]]["width"]))

        bind("memory.ar.ready", raw.ar.ready)
        bind("memory.ar.valid", raw.ar.valid)
        bind("memory.ar.addr", raw.ar.addr)
        bind_output("memory.ar.id", raw.ar.id)
        bind_output("memory.ar.len", raw.ar.len)
        bind("memory.ar.size", raw.ar.size)
        bind("memory.ar.burst", raw.ar.burst)
        bind_output("memory.ar.lock", raw.ar.lock)
        bind_output("memory.ar.cache", raw.ar.cache)
        bind_output("memory.ar.prot", raw.ar.prot)
        bind_output("memory.ar.qos", raw.ar.qos)
        discard_output("memory.ar.region")
        discard_output("memory.ar.user")

        bind("memory.r.ready", raw.r.ready)
        bind("memory.r.valid", raw.r.valid)
        bind("memory.r.data", raw.r.data)
        bind("memory.r.resp", raw.r.resp)
        bind("memory.r.last", raw.r.last)
        bind_optional("memory.r.id", raw.r.id)
        if "memory.r.user" in roles:
            bind("memory.r.user", Constant(0, ports[roles["memory.r.user"]]["width"]))

        overrides = interface.get("overrides", {})
        for port_name, value in overrides.get("ties", {}).items():
            params["i_" + port_name] = Constant(value, ports[port_name]["width"])
        for port_name in overrides.get("ignored_outputs", []):
            params["o_" + port_name] = Signal(ports[port_name]["width"])

        self.specials += Instance(manifest["top"], **params)
        if sim_debug:
            ar_seen = Signal()
            self.sync += [
                If(~a.ar.valid, ar_seen.eq(0)),
                If(a.ar.valid & ~ar_seen,
                    ar_seen.eq(1),
                    Display("[vta-axi] ARVALID addr=%08x len=%d ready=%d",
                            a.ar.addr, a.ar.len, a.ar.ready)),
                If(a.ar.valid & a.ar.ready,
                    Display("[vta-axi] AR addr=%08x len=%d size=%d id=%d",
                            a.ar.addr, a.ar.len, a.ar.size, a.ar.id)),
                If(a.r.valid & a.r.ready & a.r.last,
                    Display("[vta-axi] RLAST id=%d resp=%d", a.r.id, a.r.resp)),
                If(a.aw.valid & a.aw.ready,
                    Display("[vta-axi] AW addr=%08x len=%d size=%d id=%d",
                            a.aw.addr, a.aw.len, a.aw.size, a.aw.id)),
                If(a.b.valid & a.b.ready,
                    Display("[vta-axi] B id=%d resp=%d", a.b.id, a.b.resp)),
            ]
