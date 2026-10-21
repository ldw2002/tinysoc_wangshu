#!/usr/bin/env bash
set -eu

gateware=${1:?usage: $0 build-dir/gateware}
simulator=${gateware}/obj_dir/Vsim
if [[ ! -x ${simulator} ]]; then
  echo "case simulator not found: ${simulator}" >&2
  echo "build it first with: make sim CASE=case-name-or-path" >&2
  exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
soc_dir=$(cd -- "${script_dir}/.." && pwd)
project_dir=$(cd -- "${soc_dir}/.." && pwd)
python=${SOC_PYTHON:-${soc_dir}/.venv/bin/python}
conda_env_dir=${CONDA_ENV_DIR:-${CONDA_PREFIX:-}}
if [[ -z ${conda_env_dir} ]]; then
  conda_env_dir=$(${python} -c 'import sys; print(sys.base_prefix)')
fi

# The simulator links against libjson-c / libevent that ship inside the tools
# bundle, so running it needs the same library search path that sim_build.sh
# used.  Without this, starting Vsim fails with
# "error while loading shared libraries: libjson-c.so.4".
if [[ -n ${TINYVTA_TOOLS_DIR:-} ]]; then
  tools_dir=${TINYVTA_TOOLS_DIR}
else
  tools_dir=${project_dir}/tools
fi
if [[ -d ${tools_dir} ]]; then
  tools_dir=$(cd -- "${tools_dir}" && pwd)
fi
linux_host_lib=${tools_dir}/linux-host/usr/lib/x86_64-linux-gnu

if [[ $(uname -s) == Darwin ]]; then
  export DYLD_LIBRARY_PATH=${conda_env_dir}/lib${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}
else
  export LD_LIBRARY_PATH=${conda_env_dir}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
  if [[ -d ${linux_host_lib} ]]; then
    export LD_LIBRARY_PATH=${linux_host_lib}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
  fi
fi

cd ${gateware}
exec ${python} ${soc_dir}/tools/run_case_firmware.py ./obj_dir/Vsim sim_config.js
