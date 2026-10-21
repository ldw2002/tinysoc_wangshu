#!/usr/bin/env bash
# Adapt the BC NPU case sources to the TY1B-simple SoC address map.
#
# Usage: patch_bc_case.sh <case-dir>
set -eu

case_dir=${1:?usage: $0 <case-dir>}

model="$case_dir/bc_npu_model.h"

if [ ! -f "$model" ]; then
    echo "missing $model" >&2
    exit 2
fi

# The VTA control registers sit at 0xf0001000 in this SoC instead of the
# ASIC/FPGA map's 0x41000000.  The register offsets themselves are identical.
sed -i 's|#define VTA_BADDR[[:space:]]\+0x41000000|#define VTA_BADDR 0xf0001000|' "$model"

echo "=== VTA_BADDR after patching ==="
grep -n 'VTA_BADDR' "$model" | head -5

# Show any remaining busy-wait loops so they can be given a timeout if wanted.
echo "=== busy-wait loops ==="
grep -n 'while (_REG_INT' "$model" | head -10
