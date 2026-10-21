#!/usr/bin/env bash
# Build a LiteX/Verilator executable without running it.
set -eu

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
soc_dir=$(cd -- "${script_dir}/.." && pwd)
project_dir=$(cd -- "${soc_dir}/.." && pwd)
build_dir=$(realpath -m "${1:?usage: $0 build-dir config [case-dir]}")
config=$(realpath "${2:?usage: $0 build-dir config [case-dir]}")
case_dir=${3:+$(realpath "$3")}
python=${SOC_PYTHON:-${soc_dir}/.venv/bin/python}

if [[ ! -x ${python} ]]; then
  echo "missing SoC Python environment: ${python}" >&2
  echo "create it once with the tvm_py310 Python and install soc/requirements.txt" >&2
  exit 2
fi

args=(--config "${config}" --build-dir "${build_dir}" --build --no-run)
if [[ -n ${case_dir} ]]; then
  args+=(--case-dir "${case_dir}")
fi

cd ${soc_dir}
conda_env_dir=${CONDA_ENV_DIR:-${CONDA_PREFIX:-}}
if [[ -n ${TINYVTA_TOOLS_DIR:-} ]]; then
  tools_dir=$(realpath -m "${TINYVTA_TOOLS_DIR}")
else
  tools_dir=${project_dir}/tools
fi
xpack_dir=${tools_dir}/xpack-riscv-none-elf-gcc-15.2.0-1
linux_tools_dir=${tools_dir}/linux/usr
linux_host_dir=${tools_dir}/linux-host/usr
if [[ -n ${RISCV_TOOLCHAIN_DIR:-} ]]; then
  riscv_dir=${RISCV_TOOLCHAIN_DIR}
elif [[ -x ${xpack_dir}/bin/riscv-none-elf-gcc ]]; then
  riscv_dir=${xpack_dir}
elif [[ -x ${linux_tools_dir}/bin/riscv64-unknown-elf-gcc ]]; then
  riscv_dir=${linux_tools_dir}
else
  echo "missing RISC-V toolchain under ${tools_dir}" >&2
  echo "copy the tools bundle into ${project_dir}/tools or set TINYVTA_TOOLS_DIR" >&2
  exit 2
fi
tool_path=${soc_dir}/.venv/bin:${riscv_dir}/bin
if [[ ${riscv_dir} == ${linux_tools_dir} ]]; then
  export RISCV_DEB_ROOT=${linux_tools_dir}
  export VERILATOR_DEB_ROOT=${linux_tools_dir}
  export VERILATOR_ROOT=${linux_tools_dir}/share/verilator
  tool_path=${script_dir}/verilator_deb_compat:${script_dir}/riscv_deb_compat:${tool_path}
fi
if [[ -n ${conda_env_dir} ]]; then
  tool_path=${tool_path}:${conda_env_dir}/bin
fi
export PATH=${tool_path}:${PATH}

if ! command -v verilator >/dev/null 2>&1; then
  echo "missing Verilator under ${tools_dir} and on PATH" >&2
  echo "copy the tools bundle into ${project_dir}/tools or set TINYVTA_TOOLS_DIR" >&2
  exit 2
fi

# Verilator's bundled verilated.mk assigns CXX/LINK with "=", so it overrides
# the exported CC/CXX of whoever calls make.  On CentOS 7 that silently drops
# the C++ standard back to C++98 while the LiteX simulator sources use C++11,
# so repair the copy that ships inside the tools bundle.
verilator_root=${VERILATOR_ROOT:-${linux_tools_dir}/share/verilator}
if [[ -x /usr/bin/g++ ]]; then
  bash "${script_dir}/fix_verilator_cxxstd.sh" "${verilator_root}" || true
fi

# LiteX forwards CFLAGS to Verilator's -CFLAGS, and Verilator places that text
# after the compiler in the generated compile line.  A "-std=..." reaching that
# position overrides the C++11 standard again, so drop any language standard a
# caller exported: the C standard belongs on CC instead.
for var in CFLAGS CXXFLAGS CPPFLAGS; do
  eval "value=\${${var}:-}"
  [[ -n ${value} ]] || continue
  export "${var}=$(printf '%s' "${value}" | sed -e 's/-std=[^[:space:]]*//g')"
done

if [[ $(uname -s) != Darwin && -d ${linux_host_dir}/include ]]; then
  linux_host_lib=${linux_host_dir}/lib/x86_64-linux-gnu
  export CPATH=${linux_host_dir}/include${CPATH:+:${CPATH}}
  export LIBRARY_PATH=${linux_host_lib}${LIBRARY_PATH:+:${LIBRARY_PATH}}
  export LD_LIBRARY_PATH=${linux_host_lib}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
fi

if [[ $(uname -s) != Darwin ]]; then
  ${python} litex/vta_soc.py "${args[@]}"
  gateware=${build_dir}/gateware
  if [[ ! -f ${gateware}/build_sim.sh ]]; then
    echo "LiteX generation did not produce ${gateware}/build_sim.sh" >&2
    exit 2
  fi
  (cd ${gateware} && bash ./build_sim.sh)
  test -x ${gateware}/obj_dir/Vsim
  echo "SoC simulator built: ${gateware}/obj_dir/Vsim"
  exit 0
fi

if [[ -z ${conda_env_dir} ]]; then
  conda_env_dir=$(${python} -c 'import sys; print(sys.base_prefix)')
fi
apple_cxx=$(xcrun --find clang++)
apple_ar=$(xcrun --find ar)
sdk_root=${SDKROOT:-$(xcrun --show-sdk-path)}
sdk_cxx_headers=${sdk_root}/usr/include/c++/v1
litex_sim_core=${soc_dir}/.venv/lib/python3.10/site-packages/litex/build/sim/core

if [[ ! -x ${riscv_dir}/bin/riscv-none-elf-gcc ]]; then
  echo "missing RISC-V toolchain: ${riscv_dir}" >&2
  exit 2
fi
for required in ${conda_env_dir}/bin/verilator ${apple_cxx} ${apple_ar}; do
  if [[ ! -x ${required} ]]; then
    echo "missing tool in tvm_py310: ${required}" >&2
    exit 2
  fi
done
if [[ ! -d ${sdk_cxx_headers} ]]; then
  echo "missing Apple SDK libc++ headers: ${sdk_cxx_headers}" >&2
  exit 2
fi

${python} tools/patch_litex_sim_macos.py --venv ${soc_dir}/.venv
export PATH=${soc_dir}/.venv/bin:${riscv_dir}/bin:${conda_env_dir}/bin:/usr/bin:/bin:/usr/sbin:/sbin
export CFLAGS=-I${conda_env_dir}/include
export LDFLAGS=-L${conda_env_dir}/lib
unset DYLD_LIBRARY_PATH 2>/dev/null || true
# Conda's compiler activation exports target-prefixed CC/CXX values. LiteX
# interprets CC as a boolean CPU option, so do not leak host compiler overrides
# into its RISC-V software-toolchain selection.
unset CC CXX CPP AR AS LD NM RANLIB STRIP OBJCOPY OBJDUMP \
  CLANG CLANGXX CC_FOR_BUILD CXX_FOR_BUILD CXXFLAGS DEBUG_CXXFLAGS \
  DEBUG_CFLAGS CMAKE_ARGS 2>/dev/null || true

# Let LiteX produce its complete Vsim.mk, then rebuild it with the Apple
# compiler/SDK matching this macOS host. Non-system libraries stay isolated in
# tvm_py310.
software_freshness_marker=$(mktemp /tmp/vta-soc-software.XXXXXX)
litex_log=$(mktemp /tmp/vta-soc-litex.XXXXXX)
trap 'rm -f ${software_freshness_marker} ${litex_log}' EXIT
set +e
${python} litex/vta_soc.py "${args[@]}" >${litex_log} 2>&1
litex_status=$?
set -e
gateware=${build_dir}/gateware
makefile=${gateware}/obj_dir/Vsim.mk
software_bin=${build_dir}/software/bios/bios.bin
if [[ ! -f ${makefile} || ! -f ${software_bin} || ! ${software_bin} -nt ${software_freshness_marker} ]]; then
  cat ${litex_log}
  echo "LiteX generation did not produce fresh software/Vsim.mk (status ${litex_status})" >&2
  exit ${litex_status}
fi
echo "LiteX software and simulator sources generated; compiling with the macOS host ABI."

make -C ${gateware}/obj_dir -f Vsim.mk -j4 \
  CXX=${apple_cxx} LINK=${apple_cxx} AR=${apple_ar} \
  "VM_USER_CFLAGS=-nostdinc++ -isystem ${sdk_cxx_headers} -isysroot ${sdk_root} -I${conda_env_dir}/include -I${litex_sim_core}" \
  "VM_USER_LDLIBS=libdylib.o modules.o pads.o parse.o sim.o -isysroot ${sdk_root} -L${conda_env_dir}/lib -lpthread -ljson-c -lz -lm -lc++ -ldl -levent"

test -x ${gateware}/obj_dir/Vsim
echo "SoC simulator built: ${gateware}/obj_dir/Vsim"
