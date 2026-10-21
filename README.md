# TY1B-simple SoC 服务器环境复现指南

本文说明如何在一台 CentOS 7 x86_64 服务器上复现 tinyvta-simple-soc 的完整
仿真环境，包括 Python 环境、RISC-V 工具链、Verilator、ASIC 版 VTA RTL 和
bc_npu case。

今日（2026-09-23）的改动与交付记录见 [CHANGELOG.md](CHANGELOG.md)。

### 写在前面:极简上手指南(修改于2026/9/24)

1. `cd $VTA_PATH/soc` 进入soc路径

2. `./setup.csh` 解压conda依赖包

3. `source tinyvta_env.csh` 配置环境

4. `cd $VTA_PATH/soc/generate/vta-ip/apb32-axi64/rtl` 使用正式版代码VTA_Top.v替换vta.v并保持vta.v命名。memory cell的.v放入/rtl/mem_wrap。完善/filelist.f。

5. 若vta.v接口或模块名存在更新，请执行步骤5：`cd $VTA_PATH/soc/soc` ,按照步骤二中log提示执行make rtl,之后执行`make generate`更新整个SOC代码。若无接口或模块名更新，跳过步骤5。

6. `cd $VTA_PATH/soc/soc`,按照步骤二中log提示执行make rtl,更新cases/内容,在$VTA_PATH/soc/soc下执行`make sim CASE=<case的路径名>`,`make run CASE=<case的路径名>`  或 在case的Makefile路径下直接执行`make sim`进行编译,`make run`进行soc级case仿真。

## 1. 目标架构

CPU: VexRiscv RV32 @200 MHz
总线: AXI
存储: Boot ROM 128 KiB + 片上 SRAM 128 KiB + 片外 DDR 160 KiB
NPU: ASIC 版 VTA_Top（blockIn=blockOut=8，SRAM 黑盒）
UART: case 结果输出

地址映射:

ROM       0x00000000  128 KiB
SRAM      0x01000000  128 KiB
DDR       0x40000000  160 KiB
UART/CSR  0xf0000000
VTA VCR   0xf0001000

## 2. 前置条件

服务器: CentOS 7 x86_64, glibc 2.17。

必须存在:

/usr/bin/gcc
/usr/bin/g++
python3.10 或 conda/miniforge
make / perl / bash

## 3. 离线包清单

本适配包:

tinysoc_wangshu.tar.gz

它包含:

soc/ 源码与配置修改（SRAM/DDR、APB4 适配、BC case）
generated/.../mem_sim/ Verilator 兼容 SRAM 行为模型
tinyvta_env.csh 环境脚本

工具链与运行库包:

tinyvta-tools-all.tar.gz      工具链整合包（Verilator/RISC-V GCC 修复/运行库/头文件/库）
tinyvta-python310-offline.tar.gz  Python 依赖（可选）
tinyvta-gcc-cxx-centos7.tar.gz  cc1plus + C++ 头文件（需 sudo，可选）

前两个放在 TINYVTA_BUNDLE_DIR（默认 $HOME，即 /home/wangshu）下，由
setup_env.csh 解压；项目目录里不放它们。

用户提供的正式代码文件（不随包分发）:

ASIC 版 VTA_Top.v
mem_wrap/*.v
BC case 数据头（bc_npu_*.h, bc_test_data.h）

## 4. 复现步骤

约定一个上层目录 VTA_PATH，本包解压后位于 $VTA_PATH/soc：

  VTA_PATH=/project/research/wangshu/project/zvslab_tinyVTA
  TINYVTA_ROOT=$VTA_PATH/soc

脚本里所有路径都以 TINYVTA_ROOT（即 $VTA_PATH/soc）为基准，不需要写死绝对
路径；只要设置 VTA_PATH，TINYVTA_ROOT 会自动推导出来。

### 4.1 解压适配包

setenv VTA_PATH /project/research/wangshu/project/zvslab_tinyVTA
mkdir -p "$VTA_PATH/soc"
cd "$VTA_PATH/soc"
tar -xzf /path/to/tinysoc_wangshu.tar.gz --strip-components=1

### 4.2 一键准备工具链与 Python 环境

两个安装包放在 TINYVTA_BUNDLE_DIR（默认 $HOME，即 /home/wangshu）下：

  /home/wangshu/tinyvta-tools-all.tar.gz
  /home/wangshu/tinyvta-python310-offline.tar.gz

然后执行（用 ./ 执行，不要 source）：

cd "$VTA_PATH/soc"
./setup_env.csh

它会把两个包解压到同一个目录 /home/wangshu 下，得到 tools/、gcc-runtime/、
wheelhouse/，再创建 soc/.venv 并离线安装 requirements.txt，最后打印
python deps ok。项目目录里不再需要放这些大文件。

如果安装包放在别处，先 setenv TINYVTA_BUNDLE_DIR <目录> 再跑。

### 4.3 确认 verilated.mk 已修正

解压出来的 verilated.mk 应该已经把 C++ 标准绑到 CXX 上：

grep -E '^(PERL|CXX|LINK|CFG_CXXFLAGS)' \
  "$TINYVTA_ROOT/tools/linux/usr/share/verilator/include/verilated.mk"

正确输出:

PERL = perl
CXX = /usr/bin/g++ -std=gnu++11
LINK = /usr/bin/g++
CFG_CXXFLAGS_STD_NEWEST = -std=gnu++11
CFG_CXXFLAGS_NO_UNUSED =

如果 CXX 只有 /usr/bin/g++（没有 -std=gnu++11），说明用的是旧的 v3 修复包。
soc/scripts/sim_build.sh 会在 make sim 时调用 soc/scripts/fix_verilator_cxxstd.sh
自动修正这个文件（幂等，已修好时静默跳过），也可以单独执行：

cd "$TINYVTA_ROOT/soc"
bash scripts/fix_verilator_cxxstd.sh "$TINYVTA_ROOT/tools/linux/usr/share/verilator"

或者手工修改：

cd "$TINYVTA_ROOT/tools/linux/usr/share/verilator/include"
sed -i 's|^CXX = .*|CXX = /usr/bin/g++ -std=gnu++11|' verilated.mk
sed -i 's|^LINK = .*|LINK = /usr/bin/g++|' verilated.mk
sed -i 's|^CFG_CXXFLAGS_STD_NEWEST = .*|CFG_CXXFLAGS_STD_NEWEST = -std=gnu++11|' verilated.mk
sed -i 's|^CFG_CXXFLAGS_NO_UNUSED = .*|CFG_CXXFLAGS_NO_UNUSED =|' verilated.mk

### 4.4 系统头文件与 C++ 前端

如果 cc1plus 或 C++ 头文件缺失，用 tinyvta-gcc-cxx-centos7.tar.gz:

cd /tmp
tar -xzf tinyvta-gcc-cxx-centos7.tar.gz
sudo cp -a usr/libexec/gcc/x86_64-redhat-linux/4.8.5/cc1plus /usr/libexec/gcc/x86_64-redhat-linux/4.8.5/cc1plus
sudo chmod 755 /usr/libexec/gcc/x86_64-redhat-linux/4.8.5/cc1plus
sudo mkdir -p /usr/include/c++
sudo cp -a usr/include/c++/4.8.5 /usr/include/c++

验证:

/usr/bin/gcc -c -x c /dev/null -o /tmp/t.o
/usr/bin/g++ -c -x c++ /dev/null -o /tmp/t2.o

### 4.5 加载环境

cd "$VTA_PATH/soc"
source tinyvta_env.csh
echo "VERILATOR=[$VERILATOR]"
echo "TINYVTA_TOOLS_DIR=[$TINYVTA_TOOLS_DIR]"
echo "LD_LIBRARY_PATH=[$LD_LIBRARY_PATH]"
env | grep -E 'LD_PRELOAD|CFLAGS|CXXFLAGS|CPPFLAGS'

VERILATOR 应指向 $TINYVTA_TOOLS_DIR/linux/usr/bin/verilator（默认即
/home/wangshu/tools/...）；LD_LIBRARY_PATH 应指向 linux-host/usr/lib/x86_64-linux-gnu
（Vsim 运行时要找 libjson-c/libevent）。env 那条应无输出（LD_PRELOAD 和各
-std= 标志都被清掉）。

### 4.6 放置 ASIC 版 RTL

cd "$TINYVTA_ROOT/generated/vta-ip/apb32-axi64/rtl"
cp /path/to/src_rtl/nobist/VTA_Top.v vta.v
cp -r /path/to/src_rtl/nobist/mem_wrap .
ls -l vta.v mem_wrap/

更新 filelist.f:

cd "$TINYVTA_ROOT/generated/vta-ip/apb32-axi64"
printf -- 'rtl/vta.v\nrtl/mem_wrap/mem_ext.v\nrtl/mem_wrap/mem_0_ext.v\nrtl/mem_wrap/tensorFile_0_ext.v\nrtl/mem_wrap/tensorFile_0_0_ext.v\nrtl/mem_wrap/tensorFile_0_1_ext.v\nrtl/mem_wrap/vmeTag_array_ext.v\nrtl/mem_sim/SZFA55_8X128X1CM2.v\nrtl/mem_sim/SZFA55_64X128X1CM2.v\nrtl/mem_sim/SYFA55_128X32X1CM2.v\nrtl/mem_sim/SZFA55_512X64X1CM2.v\nrtl/mem_sim/SZFA55_128X64X1CM2.v\nrtl/mem_sim/SZFA55_16X40X1CM2.v\n' > filelist.f

### 4.7 更新 RTL 接口

cd "$TINYVTA_ROOT/soc"
make rtl INTERFACE_ARGS="--map clock=clock --map host.psel=io_host_PSELx"

### 4.8 准备 BC NPU case

setenv BC_SRC /path/to/case/BC
cp $BC_SRC/bc_npu_model.h "$TINYVTA_ROOT/soc/cases/bc_npu/"
cp $BC_SRC/bc_npu_code.h "$TINYVTA_ROOT/soc/cases/bc_npu/"
cp $BC_SRC/bc_npu_data.h "$TINYVTA_ROOT/soc/cases/bc_npu/"
cp $BC_SRC/bc_npu_params.h "$TINYVTA_ROOT/soc/cases/bc_npu/"
cp $BC_SRC/bc_test_data.h "$TINYVTA_ROOT/soc/cases/bc_npu/"
cd "$TINYVTA_ROOT/soc/cases/bc_npu"
bash "$TINYVTA_ROOT/soc/patch_bc_case.sh" "$PWD"

确认 VTA_BADDR 变成 0xf0001000。

### 4.9 编译并运行

cd "$TINYVTA_ROOT/soc"
make sim CASE=bc_npu
make run CASE=bc_npu

预期输出:

VTA case bc_npu: start
VTA case PASS

## 5. 常见问题

报 NEEDTIMINGOPT:
终端没加载环境，重新 source tinyvta_env.csh。

报 cannot execute cc1plus:
环境残留 conda 的 LD_PRELOAD / LIBRARY_PATH，重新 source 环境脚本。

报 invalid -march= rv32im / rv64imafdc:
RISC-V 汇编器被 PATH 里其他工具覆盖，检查环境脚本。

报 error while loading shared libraries: libjson-c.so.4 (make sim 能过、make run 不行):
simulator 链接的 libjson-c.so.4 / libevent-2.1.so.7 来自
tools/linux-host/usr/lib/x86_64-linux-gnu，运行时没有把它加到 LD_LIBRARY_PATH。
soc/scripts/sim_run.sh 现在会自动加；老版本可以先确认再手工补：

ldd build/case-bc_npu/gateware/obj_dir/Vsim | grep -E 'json-c|event'

若显示 not found，更新 soc/scripts/sim_run.sh，或临时这样跑：

setenv LD_LIBRARY_PATH "$TINYVTA_TOOLS_DIR/linux-host/usr/lib/x86_64-linux-gnu"
cd "$TINYVTA_ROOT/soc"
make run CASE=bc_npu

报 libmpfr / libstdc++ / GLIBC_2.27:
运行库未放到 gcc-runtime/lib 或路径不对。

报 veril.cpp: 'nullptr' was not declared in this scope:
verilated.mk 里的 CXX 覆盖了环境变量，g++ 退回了 C++98。见 4.3 节，
把 CXX 改成 /usr/bin/g++ -std=gnu++11 后重跑。

仿真长时间不出结果:
bc_npu_model.h 的等待循环没有超时，CPU 100% 但无输出说明 VTA 未完成，
检查 RTL 参数与 case 指令流是否匹配。

## 6. 目录结构

$VTA_PATH/
  soc/                   = TINYVTA_ROOT，本包解压根目录
    soc/                 LiteX SoC 源码与 case
      cases/bc_npu/      BC NPU case
      config/            地址与硬件配置
      firmware/          固件模板与镜像规则
      linker/            链接脚本
      litex/             LiteX SoC 集成
      scripts/           构建与运行脚本
      tools/             Python 工具（check_env.py 等）
      .venv/             Python 虚拟环境（setup_env.csh 创建）
    generated/vta-ip/apb32-axi64/
      rtl/vta.v          ASIC 版顶层 RTL
      rtl/mem_wrap/      SRAM 黑盒封装
      rtl/mem_sim/       SRAM 行为模型
      filelist.f         RTL 文件清单
    setup_env.csh        一键准备工具链与 Python 环境
    tinyvta_env.csh      环境脚本

$TINYVTA_BUNDLE_DIR/     默认 $HOME，即 /home/wangshu
  tinyvta-tools-all.tar.gz        工具链安装包
  tinyvta-python310-offline.tar.gz  Python 离线包
  tools/                  = TINYVTA_TOOLS_DIR，工具链解压结果
  gcc-runtime/lib/        RISC-V 运行库
  wheelhouse/             Python 离线依赖

## 7. 离线包校验（v4 工具链）

tinyvta-python310-offline.tar.gz
  sha256 6ee0128456b6080e3c0f4aafd6cad5b6cb554ecb3b7724db2213706bf4c592b7  (23 MB)

tinyvta-tools-all.tar.gz
  sha256 f33d802daaf670073a58473b98e7b67d68f57bdbb9c7e4378497510e7669f44e  (90 MB)

v4 修复内容:
  旧的 v3 修复包里 verilated.mk 写的是 CXX = /usr/bin/g++。makefile 用 "="
  赋值会覆盖环境变量，CentOS 7 的 g++ 因此退回 C++98，编译 LiteX 的 veril.cpp
  (用到 nullptr) 就报 "'nullptr' was not declared in this scope"。
  v4 改成 CXX = /usr/bin/g++ -std=gnu++11，并把 CFG_CXXFLAGS_NO_UNUSED 清空
  （gcc 4.8 不认识 -faligned-new / -Wno-bool-operation 之类的新选项）。
  另外 soc/scripts/sim_build.sh 现在会在 make sim 时自动检查并修正该文件，
  所以旧环境只要更新这一个脚本也能自愈。

  注意: 该修复只作用于 C/C++ 的编译标准。CFLAGS 里如果带 -std=gnu99 也会被
  LiteX 透传到 Verilator 的 -CFLAGS 并覆盖 C++11，所以 sim_build.sh 会先
  从 CFLAGS/CXXFLAGS/CPPFLAGS 里剥掉所有 -std= 选项，C 标准请挂在 CC 上。

## 8. 通用综合（Yosys）

已提供独立的 Yosys 0.70 综合环境和本地 VTA 配置。在 WSL 中执行：

```sh
cd /mnt/d/VSCode/tinysoc_wangshu/soc
make synth-setup
make synth
make synth SYNTH_STAGE=gates
```

流程保留 RAM 阵列，输出网表、资源统计、输入哈希和完整日志。
这是本地 NPU 的通用综合，不代表完整 SoC、ASIC 工艺映射或 FPGA 实现已完成。
配置、结果和器件/工艺综合所需条件见 [综合说明](soc/synth/README.md)。

## 9. Synopsys Design Compiler

DC 后端直接读取与 Yosys 共用 profile 中的 RTL，支持展开检查和指定库/SDC 后的工艺映射。在服务器的 `soc/` 目录执行：

```sh
make synth-dc-prepare                                  # 仅生成脚本
make synth-dc SYNTH_PROFILE=vcr                        # 先验证小模块
make synth-dc SYNTH_PROFILE=vta-local                  # 展开本地 VTA
make synth-dc SYNTH_PROFILE=vcr DC_STAGE=map DC_CONFIG=/path/to/dc.json
```

服务器需提供 Python >=3.10、DC 和许可证；映射另需真实 `.db` 库及 SDC。
本地已验证生成器、Tcl 控制流程和源码视图回归，尚未进行真实 DC 综合。
配置模板、产物、SRAM 映射限制及执行方式见 [DC 使用说明](soc/synth/dc/README.md)。

CentOS 7 的 Yosys 离线环境和本次项目增量包使用独立安装目录及 `soc/synth/server.mk`，安装与同步方法见 [服务器离线部署说明](soc/synth/SERVER_BUNDLE.md)。
