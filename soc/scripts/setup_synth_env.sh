#!/usr/bin/env bash
# Install the pinned Yosys WebAssembly distribution into a user-owned venv.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
soc_dir=$(cd -- "${script_dir}/.." && pwd)
python=${SYNTH_BOOTSTRAP_PYTHON:-${SYNTH_PYTHON:-}}
prefix=${SYNTH_ENV_DIR:-${HOME}/.local/share/tinysoc-synth}

if [[ $# -gt 0 ]]; then
    echo "usage: SYNTH_BOOTSTRAP_PYTHON=python3 SYNTH_ENV_DIR=/path $0" >&2
    exit 2
fi
if [[ -z ${python} ]]; then
    for candidate in python3.12 python3.11 python3.10 python3 "${HOME}/miniconda3/envs/tvm_py310/bin/python"; do
        if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" -c 'import sys, venv; assert sys.version_info >= (3, 10)' >/dev/null 2>&1; then
            python=${candidate}
            break
        fi
    done
fi
if [[ -z ${python} ]]; then
    echo "Python >=3.10 is required; set SYNTH_BOOTSTRAP_PYTHON to its executable." >&2
    exit 2
fi
"${python}" -c 'import sys; assert sys.version_info >= (3, 10), "Python >=3.10 is required"'
mkdir -p "${prefix}"
if [[ ! -x "${prefix}/venv/bin/python" ]]; then
    "${python}" -m venv "${prefix}/venv"
fi
"${prefix}/venv/bin/python" -m pip install --disable-pip-version-check -r "${soc_dir}/synth/requirements.txt"
"${prefix}/venv/bin/python" -m pip freeze > "${prefix}/installed-requirements.txt"
"${prefix}/venv/bin/yowasp-yosys" -V
echo "Synthesis environment: ${prefix}/venv"
echo "Yosys: ${prefix}/venv/bin/yowasp-yosys"
