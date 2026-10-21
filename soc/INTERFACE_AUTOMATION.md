# VTA top-interface automation

`tools/update_vta_interface.py` asks Verilator to parse the frozen VTA RTL and
writes `generated/vta-ip/apb32-axi64/interface.json`. LiteX consumes semantic
roles from that file instead of hard-coding Verilog port names.

After replacing or editing `rtl/vta.v`, run:

```bash
cd /mnt/d/VSCode/tinyvta-simple-soc/soc
make rtl
make rtl-check
make interface-test
make sim CASE=dense_gemm_bias_clip
make run CASE=dense_gemm_bias_clip
```

`make rtl` updates the RTL checksum first, then regenerates the interface map.
The generator recognizes the existing Chisel names and conventional
`s_apb_*`/`m_axi_*` names. It also updates interface widths in `manifest.json`.
If a data or address width changes, update `config/ty1b_simple_npu.json` to
match the warning before building the SoC.

For a non-standard rename, bind a semantic role explicitly:

```bash
make rtl INTERFACE_ARGS="--map clock=core_clk --map reset=core_reset_n"
```

Names ending in `reset_n`, `rst_n`, or `areset_n` are treated as active-low.
For an unusual name, specify the polarity explicitly:

```bash
make rtl INTERFACE_ARGS="--map reset=core_reset_l --reset-active-low"
```

Additional inputs must have an explicit constant and unused outputs must be
acknowledged. This prevents a new functional signal from being silently lost:

```bash
make rtl INTERFACE_ARGS="--tie test_enable=0 --ignore-output debug_status"
```

The overrides are saved in `interface.json` and reused by later `make rtl`
commands. Use `INTERFACE_ARGS="--clear-overrides ..."` to replace them.
Run `python tools/update_vta_interface.py --list-roles` to list valid semantic
role names for `--map`.

Protocol changes are intentionally not inferred. Replacing APB4 or AXI4 with
a different protocol requires a corresponding LiteX bridge implementation.
