#!/bin/csh -f
# Offline environment bootstrap for the TY1B-simple SoC (csh/tcsh).
#
# 自动完成（断网环境）:
#   1. 解压工具链包 tinyvta-tools-all.tar.gz
#   2. 解压 Python 离线包 tinyvta-python310-offline.tar.gz
#   3. 创建 soc/.venv
#   4. 离线安装 requirements.txt
#   5. 自检 Python 依赖
#
# 两个安装包默认放在 TINYVTA_BUNDLE_DIR（默认 $HOME，即 /home/wangshu）。
# 解压出来的 tools/ gcc-runtime/ wheelhouse/ 也落在同一个目录，供
# tinyvta_env.csh 通过 TINYVTA_TOOLS_DIR 引用，项目目录本身不再需要放这些
# 大文件。
#
# RTL（ASIC vta.v + mem_wrap）和 BC case 数据头仍需手动拷贝。

# The package is deployed as $VTA_PATH/soc.  Resolve the project root the same
# way tinyvta_env.csh does: explicit TINYVTA_ROOT, then $VTA_PATH/soc, then the
# current directory.
if (! $?TINYVTA_ROOT) then
    if ($?VTA_PATH) then
        setenv TINYVTA_ROOT "$VTA_PATH/soc"
    else
        setenv TINYVTA_ROOT `pwd`
    endif
endif
if (! $?VTA_PATH) then
    setenv VTA_PATH `dirname "$TINYVTA_ROOT"`
endif

if (! -d "$TINYVTA_ROOT/soc") then
    echo "error: TINYVTA_ROOT=[$TINYVTA_ROOT] 下没有 soc/ 目录"
    echo "       请先 cd 到解压好的项目根目录，再运行 ./setup_env.csh"
    echo '       或 setenv VTA_PATH <上层目录>（本包位于 $VTA_PATH/soc）'
    exit 2
endif

# Where the two release tarballs live.  Defaults to $HOME (/home/wangshu on
# this server); the older layout that kept them inside the project directory is
# still accepted, and an explicit TINYVTA_BUNDLE_DIR always wins.
if (! $?TINYVTA_BUNDLE_DIR) then
    setenv TINYVTA_BUNDLE_DIR "$HOME"
endif
if (! -f "$TINYVTA_BUNDLE_DIR/tinyvta-tools-all.tar.gz" && -f "$TINYVTA_ROOT/tinyvta-tools-all.tar.gz") then
    echo "note: $TINYVTA_BUNDLE_DIR 下没有安装包，改用项目目录 $TINYVTA_ROOT"
    setenv TINYVTA_BUNDLE_DIR "$TINYVTA_ROOT"
endif
if (! -d "$TINYVTA_BUNDLE_DIR") then
    echo "error: TINYVTA_BUNDLE_DIR=[$TINYVTA_BUNDLE_DIR] 不存在"
    echo "       请 setenv TINYVTA_BUNDLE_DIR <存放两个 tar.gz 的目录>"
    exit 2
endif

# An earlier run exported TOOLS_TAR / WHEELHOUSE_TAR into this shell, so
# re-running would otherwise keep using those old paths even after the bundles
# moved.  Honour an explicit override only while it still resolves.
if (! $?TOOLS_TAR) then
    setenv TOOLS_TAR "$TINYVTA_BUNDLE_DIR/tinyvta-tools-all.tar.gz"
else if (! -f "$TOOLS_TAR" && -f "$TINYVTA_BUNDLE_DIR/tinyvta-tools-all.tar.gz") then
    echo "note: 忽略继承的 TOOLS_TAR=[$TOOLS_TAR]，改用 $TINYVTA_BUNDLE_DIR 下的安装包"
    setenv TOOLS_TAR "$TINYVTA_BUNDLE_DIR/tinyvta-tools-all.tar.gz"
endif
if (! $?WHEELHOUSE_TAR) then
    setenv WHEELHOUSE_TAR "$TINYVTA_BUNDLE_DIR/tinyvta-python310-offline.tar.gz"
else if (! -f "$WHEELHOUSE_TAR" && -f "$TINYVTA_BUNDLE_DIR/tinyvta-python310-offline.tar.gz") then
    echo "note: 忽略继承的 WHEELHOUSE_TAR=[$WHEELHOUSE_TAR]，改用 $TINYVTA_BUNDLE_DIR 下的安装包"
    setenv WHEELHOUSE_TAR "$TINYVTA_BUNDLE_DIR/tinyvta-python310-offline.tar.gz"
endif
# NOTE: do not export "PYTHON" here.  The SoC Makefile uses
# PYTHON ?= .venv/bin/python, and an inherited PYTHON environment variable
# would override it with a bare command name and fail env-check.
if (! $?TINYVTA_PYTHON) then
    setenv TINYVTA_PYTHON python3.10
endif
set PYTHON_BIN = "$TINYVTA_PYTHON"

cd "$TINYVTA_BUNDLE_DIR"

echo "== 0. 检查 python =="
which "$PYTHON_BIN" > /dev/null
if ($status != 0) then
    echo "error: $PYTHON_BIN not found; install Python 3.10 or setenv TINYVTA_PYTHON /path/to/python3.10"
    exit 2
endif
"$PYTHON_BIN" --version

echo "== 1. 解压工具链 =="
if (-f "$TOOLS_TAR") then
    tar -xzf "$TOOLS_TAR"
    echo "tools/ 与 gcc-runtime/ 已解压到 $TINYVTA_BUNDLE_DIR"
else if (-d "$TINYVTA_BUNDLE_DIR/tools") then
    echo "warning: $TOOLS_TAR 不存在，但 $TINYVTA_BUNDLE_DIR/tools 已存在，跳过解压"
else
    echo "error: 找不到工具链包 $TOOLS_TAR"
    echo "       请把它放到 $TINYVTA_BUNDLE_DIR，或 setenv TOOLS_TAR /path/to/该文件"
    exit 2
endif

echo "== 2. 准备 Python 离线包 =="
if (-d "$TINYVTA_BUNDLE_DIR/wheelhouse") then
    echo "$TINYVTA_BUNDLE_DIR/wheelhouse 已存在，跳过解压"
else if (-f "$WHEELHOUSE_TAR") then
    tar -xzf "$WHEELHOUSE_TAR"
    echo "wheelhouse/ 已解压到 $TINYVTA_BUNDLE_DIR"
else
    echo "error: 断网环境需要 Python 离线包"
    echo "       请把 tinyvta-python310-offline.tar.gz 放到 $TINYVTA_BUNDLE_DIR"
    echo "       或设置 WHEELHOUSE_TAR 指向该文件，然后重新运行"
    exit 2
endif

echo "== 3. 创建虚拟环境 =="
cd "$TINYVTA_ROOT/soc"
"$PYTHON_BIN" -m venv .venv

echo "== 4. 安装依赖 =="
./.venv/bin/python -m pip install \
    --no-index --find-links="$TINYVTA_BUNDLE_DIR/wheelhouse" \
    -r requirements.txt

echo "== 5. 自检 =="
./.venv/bin/python -c "import litex,litedram,migen,serial,packaging; print('python deps ok')"

echo ""
echo "自动配置完成。"
echo "  项目目录  : $TINYVTA_ROOT"
echo "  安装包目录: $TINYVTA_BUNDLE_DIR  (tools/ gcc-runtime/ wheelhouse/)"
echo ""
echo "接下来手动完成:"
echo "  1. 放 ASIC 版 VTA_Top.v:"
echo "     cp /path/to/VTA_Top.v $TINYVTA_ROOT/generated/vta-ip/apb32-axi64/rtl/vta.v"
echo "     cp -r /path/to/mem_wrap $TINYVTA_ROOT/generated/vta-ip/apb32-axi64/rtl/"
echo "  2. 拷贝 BC 数据头并打补丁:"
echo "     cp /path/to/BC/bc_npu_*.h $TINYVTA_ROOT/soc/cases/bc_npu/"
echo "     cp /path/to/BC/bc_test_data.h $TINYVTA_ROOT/soc/cases/bc_npu/"
echo "     bash $TINYVTA_ROOT/soc/patch_bc_case.sh $TINYVTA_ROOT/soc/cases/bc_npu"
echo ""
echo "然后执行:"
echo "  source $TINYVTA_ROOT/tinyvta_env.csh"
echo "  cd $TINYVTA_ROOT/soc"
echo '  make rtl INTERFACE_ARGS="--map clock=clock --map host.psel=io_host_PSELx"'
echo "  make sim CASE=bc_npu"
echo "  make run CASE=bc_npu"
