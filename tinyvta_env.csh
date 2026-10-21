# TinyVTA SoC simulation environment (tcsh/csh)
#
# Usage (from the package root, i.e. the directory holding soc/ and generated/):
#   source tinyvta_env.csh
#
# Everything the offline toolchain needs is set here, so after sourcing this
# script the SoC Makefile targets (make rtl / sim / run) work without further
# manual environment fixes.
#
# Layout: the project tree lives in TINYVTA_ROOT (= $VTA_PATH/soc) and stays
# small.  The offline toolchain and the Python wheelhouse are unpacked
# separately into TINYVTA_BUNDLE_DIR (default $HOME, i.e. /home/wangshu);
# TINYVTA_TOOLS_DIR points at the tools/ subtree inside it and is exported for
# soc/scripts/sim_build.sh, soc/scripts/sim_run.sh and tools/check_env.py.

# ---------------------------------------------------------------------------
# 0. Project location.
#
# The package is deployed as $VTA_PATH/soc, so one VTA_PATH is enough to anchor
# the whole tree: TINYVTA_ROOT is derived from it, and every other path in this
# script (tools/, gcc-runtime/, generated/, soc/) is relative to TINYVTA_ROOT.
#
# Resolution order:
#   1. an already exported TINYVTA_ROOT        (explicit override)
#   2. $VTA_PATH/soc                           (server layout)
#   3. the current directory                   (source from the package root)
# ---------------------------------------------------------------------------
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

if (! -d "$TINYVTA_ROOT/soc" || ! -d "$TINYVTA_ROOT/generated") then
    echo "warning: TINYVTA_ROOT=[$TINYVTA_ROOT] 下没有 soc/ 或 generated/"
    echo '         请先 setenv VTA_PATH <上层目录>（本包位于 $VTA_PATH/soc），'
    echo "         或 cd 到包根目录后再 source 本脚本。"
endif

# ---------------------------------------------------------------------------
# 1. Offline bundles.
#
# TINYVTA_BUNDLE_DIR holds the two release tarballs and the trees unpacked from
# them (tools/, gcc-runtime/, wheelhouse/).  It defaults to $HOME, so the ~113
# MB of toolchain never has to live inside the project tree.
#
# TINYVTA_TOOLS_DIR is what the build scripts consume.  An explicit export
# always wins; otherwise the bundle directory is preferred and the older
# in-project tools/ layout is kept as a fallback.
# ---------------------------------------------------------------------------
if (! $?TINYVTA_BUNDLE_DIR) then
    setenv TINYVTA_BUNDLE_DIR "$HOME"
endif
if (! $?TINYVTA_TOOLS_DIR) then
    if (-d "$TINYVTA_BUNDLE_DIR/tools") then
        setenv TINYVTA_TOOLS_DIR "$TINYVTA_BUNDLE_DIR/tools"
    else if (-d "$TINYVTA_ROOT/tools") then
        setenv TINYVTA_TOOLS_DIR "$TINYVTA_ROOT/tools"
    else
        setenv TINYVTA_TOOLS_DIR "$TINYVTA_BUNDLE_DIR/tools"
    endif
endif

if (! -d "$TINYVTA_TOOLS_DIR") then
    echo "warning: TINYVTA_TOOLS_DIR=[$TINYVTA_TOOLS_DIR] 不存在"
    echo "         请先运行 ./setup_env.csh，它会把工具链解压到 $TINYVTA_BUNDLE_DIR"
endif

# ---------------------------------------------------------------------------
# 2. Clear anything a login profile or an earlier attempt may have leaked.
#    Stale LD_PRELOAD / LIBRARY_PATH shims break the host g++ (cc1plus), and a
#    leaked -std= in CFLAGS/CXXFLAGS/CPPFLAGS is forwarded into Verilator's
#    generated C++ build where it can force C++98.
# ---------------------------------------------------------------------------
unsetenv LD_PRELOAD
unsetenv LIBRARY_PATH
unsetenv CPATH
unsetenv CFLAGS
unsetenv CXXFLAGS
unsetenv CPPFLAGS
unsetenv LD_LIBRARY_PATH

# ---------------------------------------------------------------------------
# 3. Toolchain roots.  Point them at the bundled (offline) tools so nothing
#    depends on a distro RISC-V / Verilator install.  VERILATOR pins 4.028,
#    which tolerates the RTL timing delays; Verilator 5.x would reject them.
# ---------------------------------------------------------------------------
setenv RISCV_DEB_ROOT     "$TINYVTA_TOOLS_DIR/linux/usr"
setenv VERILATOR_DEB_ROOT "$TINYVTA_TOOLS_DIR/linux/usr"
setenv VERILATOR_ROOT     "$TINYVTA_TOOLS_DIR/linux/usr/share/verilator"
setenv VERILATOR          "$TINYVTA_TOOLS_DIR/linux/usr/bin/verilator"

# ---------------------------------------------------------------------------
# 4. Host (x86_64) compiler used to build the LiteX simulator modules.
#    CentOS 7 gcc 4.8 defaults to C89/C++98; LiteX needs C99 and C++11.  The
#    standard is attached to CC/CXX rather than CFLAGS because Verilator
#    reuses CFLAGS for its generated C++ code.
#
#    The bundled host headers/libs provide json-c and libevent (LiteX links
#    against them) plus the missing GCC internal headers.  The host lib dir
#    contains no libstdc++/libc, so adding it to LD_LIBRARY_PATH does not
#    disturb the host g++/cc1plus; it only lets Vsim find libjson-c.so.4 and
#    libevent-2.1.so.7 at run time.
# ---------------------------------------------------------------------------
setenv CC  "/usr/bin/gcc -std=gnu99"
setenv CXX "/usr/bin/g++ -std=gnu++11"

if (-d "$TINYVTA_TOOLS_DIR/linux-host/usr/include") then
    setenv CPATH "$TINYVTA_TOOLS_DIR/linux-host/usr/include"
endif
if (-d "$TINYVTA_TOOLS_DIR/linux-host/usr/lib/x86_64-linux-gnu") then
    setenv LIBRARY_PATH   "$TINYVTA_TOOLS_DIR/linux-host/usr/lib/x86_64-linux-gnu"
    setenv LD_LIBRARY_PATH "$TINYVTA_TOOLS_DIR/linux-host/usr/lib/x86_64-linux-gnu"
endif

# The RISC-V cc1/ld runtime (a newer libstdc++/libmpfr) must NOT enter the
# global LD_LIBRARY_PATH: it is injected by
# soc/scripts/riscv_deb_compat/riscv64-unknown-elf-gcc only while the RISC-V
# toolchain runs, so it can never shadow the host g++.

# ---------------------------------------------------------------------------
# 5. Repair the bundled verilated.mk so it builds C++ as C++11.  Idempotent;
# a no-op when the tools bundle is not extracted yet or already repaired.
# make sim performs the same repair as a belt-and-braces fallback.
# ---------------------------------------------------------------------------
if (-f "$TINYVTA_ROOT/soc/scripts/fix_verilator_cxxstd.sh") then
    bash "$TINYVTA_ROOT/soc/scripts/fix_verilator_cxxstd.sh" "$VERILATOR_ROOT" >& /dev/null
endif

echo "TinyVTA environment ready: $TINYVTA_ROOT"
echo "  tools   : $TINYVTA_TOOLS_DIR"
echo "  bundles : $TINYVTA_BUNDLE_DIR"
