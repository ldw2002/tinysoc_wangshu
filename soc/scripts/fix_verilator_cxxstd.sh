#!/usr/bin/env bash
# Make Verilator's bundled verilated.mk build C++ as C++11 on old hosts.
#
# verilated.mk assigns CXX/LINK with "=", which overrides the exported CXX of
# the caller.  CentOS 7 compiles C++ as C++98 by default while the LiteX
# simulator sources use C++11 (veril.cpp uses nullptr), so the language
# standard has to be attached to the CXX make variable itself.  The same file
# carries -faligned-new and -Wno-bool-operation, which GCC 4.8 does not know.
#
# Usage:
#   fix_verilator_cxxstd.sh <verilator-root|path/to/verilated.mk>
#
# The call is idempotent and silent when the file is already correct.  Exits 3
# when the file exists but cannot be repaired (for example a read-only bundle).
set -eu

target=${1:?usage: fix_verilator_cxxstd.sh <verilator-root|verilated.mk>}
if [[ -d ${target} ]]; then
  verilated_mk=${target}/include/verilated.mk
else
  verilated_mk=${target}
fi

# Nothing to do when the bundle does not ship a verilated.mk at all.
[[ -f ${verilated_mk} ]] || exit 0

# Already pinned to C++11: nothing to do.
if grep -q '^CXX = .*-std=gnu++11' "${verilated_mk}"; then
  exit 0
fi

if [[ ! -w ${verilated_mk} ]]; then
  echo "warning: ${verilated_mk} is not writable" >&2
  echo "         the host g++ must compile the LiteX simulator as C++11" >&2
  echo "         patch CXX manually to: /usr/bin/g++ -std=gnu++11" >&2
  exit 3
fi

sed -i -e 's|^CXX = .*|CXX = /usr/bin/g++ -std=gnu++11|' \
       -e 's|^LINK = .*|LINK = /usr/bin/g++|' \
       -e 's|^CFG_CXXFLAGS_STD_NEWEST = .*|CFG_CXXFLAGS_STD_NEWEST = -std=gnu++11|' \
       -e 's|^CFG_CXXFLAGS_NO_UNUSED = .*|CFG_CXXFLAGS_NO_UNUSED =|' \
       "${verilated_mk}"

echo "pinned ${verilated_mk} to the C++11 host toolchain"
