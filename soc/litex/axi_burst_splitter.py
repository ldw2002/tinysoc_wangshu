"""Split long AXI4 INCR bursts before a downstream width converter."""

from migen import FSM, If, Mux, NextState, NextValue, Signal
from litex.gen import LiteXModule
from litex.soc.interconnect.axi import BURST_INCR, RESP_OKAY


class AXIBurstSplitter(LiteXModule):
    """Limit AXI4 INCR bursts while preserving the upstream transaction."""

    def __init__(self, upstream, downstream, max_beats=128):
        if upstream.data_width != downstream.data_width:
            raise ValueError("AXIBurstSplitter requires equal data widths")
        if upstream.address_width != downstream.address_width:
            raise ValueError("AXIBurstSplitter requires equal address widths")
        if not 1 <= max_beats <= 256:
            raise ValueError("max_beats must be between 1 and 256")

        self._add_read_path(upstream, downstream, max_beats)
        self._add_write_path(upstream, downstream, max_beats)

    def _add_read_path(self, upstream, downstream, max_beats):
        address = Signal.like(upstream.ar.addr)
        remaining = Signal(9)
        chunk_remaining = Signal(9)
        burst_id = Signal.like(upstream.ar.id)
        size = Signal.like(upstream.ar.size)
        lock = Signal.like(upstream.ar.lock)
        prot = Signal.like(upstream.ar.prot)
        cache = Signal.like(upstream.ar.cache)
        qos = Signal.like(upstream.ar.qos)
        region = Signal.like(upstream.ar.region)
        chunk_beats = Signal(9)
        self.comb += chunk_beats.eq(Mux(remaining > max_beats, max_beats, remaining))

        read_fsm = FSM(reset_state="IDLE")
        self.submodules.read_fsm = read_fsm
        read_fsm.act("IDLE",
            upstream.ar.ready.eq(1),
            If(upstream.ar.valid,
                NextValue(address, upstream.ar.addr),
                NextValue(remaining, upstream.ar.len + 1),
                NextValue(burst_id, upstream.ar.id),
                NextValue(size, upstream.ar.size),
                NextValue(lock, upstream.ar.lock),
                NextValue(prot, upstream.ar.prot),
                NextValue(cache, upstream.ar.cache),
                NextValue(qos, upstream.ar.qos),
                NextValue(region, upstream.ar.region),
                NextState("ISSUE"),
            ),
        )
        read_fsm.act("ISSUE",
            downstream.ar.valid.eq(1),
            downstream.ar.addr.eq(address),
            downstream.ar.len.eq(chunk_beats - 1),
            downstream.ar.size.eq(size),
            downstream.ar.burst.eq(BURST_INCR),
            downstream.ar.id.eq(burst_id),
            downstream.ar.lock.eq(lock),
            downstream.ar.prot.eq(prot),
            downstream.ar.cache.eq(cache),
            downstream.ar.qos.eq(qos),
            downstream.ar.region.eq(region),
            If(downstream.ar.ready,
                NextValue(chunk_remaining, chunk_beats),
                NextValue(address, address + (chunk_beats << size)),
                NextState("DATA"),
            ),
        )
        read_fsm.act("DATA",
            *downstream.r.connect(upstream.r, omit={"last"}),
            upstream.r.last.eq(remaining == 1),
            If(downstream.r.valid & upstream.r.ready,
                NextValue(remaining, remaining - 1),
                NextValue(chunk_remaining, chunk_remaining - 1),
                If(chunk_remaining == 1,
                    If(remaining == 1,
                        NextState("IDLE"),
                    ).Else(
                        NextState("ISSUE"),
                    ),
                ),
            ),
        )

    def _add_write_path(self, upstream, downstream, max_beats):
        address = Signal.like(upstream.aw.addr)
        remaining = Signal(9)
        chunk_remaining = Signal(9)
        burst_id = Signal.like(upstream.aw.id)
        size = Signal.like(upstream.aw.size)
        lock = Signal.like(upstream.aw.lock)
        prot = Signal.like(upstream.aw.prot)
        cache = Signal.like(upstream.aw.cache)
        qos = Signal.like(upstream.aw.qos)
        region = Signal.like(upstream.aw.region)
        response = Signal(2, reset=RESP_OKAY)
        chunk_beats = Signal(9)
        self.comb += chunk_beats.eq(Mux(remaining > max_beats, max_beats, remaining))

        write_fsm = FSM(reset_state="IDLE")
        self.submodules.write_fsm = write_fsm
        write_fsm.act("IDLE",
            upstream.aw.ready.eq(1),
            If(upstream.aw.valid,
                NextValue(address, upstream.aw.addr),
                NextValue(remaining, upstream.aw.len + 1),
                NextValue(burst_id, upstream.aw.id),
                NextValue(size, upstream.aw.size),
                NextValue(lock, upstream.aw.lock),
                NextValue(prot, upstream.aw.prot),
                NextValue(cache, upstream.aw.cache),
                NextValue(qos, upstream.aw.qos),
                NextValue(region, upstream.aw.region),
                NextValue(response, RESP_OKAY),
                NextState("ISSUE"),
            ),
        )
        write_fsm.act("ISSUE",
            downstream.aw.valid.eq(1),
            downstream.aw.addr.eq(address),
            downstream.aw.len.eq(chunk_beats - 1),
            downstream.aw.size.eq(size),
            downstream.aw.burst.eq(BURST_INCR),
            downstream.aw.id.eq(burst_id),
            downstream.aw.lock.eq(lock),
            downstream.aw.prot.eq(prot),
            downstream.aw.cache.eq(cache),
            downstream.aw.qos.eq(qos),
            downstream.aw.region.eq(region),
            If(downstream.aw.ready,
                NextValue(chunk_remaining, chunk_beats),
                NextValue(address, address + (chunk_beats << size)),
                NextState("DATA"),
            ),
        )
        write_fsm.act("DATA",
            *upstream.w.connect(downstream.w, omit={"last"}),
            downstream.w.last.eq(chunk_remaining == 1),
            If(upstream.w.valid & downstream.w.ready,
                NextValue(remaining, remaining - 1),
                NextValue(chunk_remaining, chunk_remaining - 1),
                If(chunk_remaining == 1,
                    NextState("DOWNSTREAM-RESP"),
                ),
            ),
        )
        write_fsm.act("DOWNSTREAM-RESP",
            downstream.b.ready.eq(1),
            If(downstream.b.valid,
                If(downstream.b.resp != RESP_OKAY,
                    NextValue(response, downstream.b.resp),
                ),
                If(remaining == 0,
                    NextState("UPSTREAM-RESP"),
                ).Else(
                    NextState("ISSUE"),
                ),
            ),
        )
        write_fsm.act("UPSTREAM-RESP",
            upstream.b.valid.eq(1),
            upstream.b.resp.eq(response),
            upstream.b.id.eq(burst_id),
            If(upstream.b.ready,
                NextState("IDLE"),
            ),
        )
