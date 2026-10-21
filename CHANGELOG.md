# 今日改动与交付记录 (2026-09-23)

## 一、目标

让 ASIC 版 VTA_Top（blockIn=blockOut=8，SRAM 黑盒封装）的 bc_npu case 在精简 SoC
（CPU + AXI + VTA + Boot ROM/SRAM/DDR）上，通过 LiteX + Verilator 仿真，make sim
与 make run 都通过，并且整套环境能在断网的 CentOS 7 / glibc 2.17 服务器上离线复现。

## 二、本地仓库（tinyvta-simple-soc）主要改动

架构（已完成并验证）：

- 存储：Boot ROM 128 KiB @ 0x00000000，片上 SRAM 128 KiB @ 0x01000000，
  片外 DDR 160 KiB @ 0x40000000，UART/CSR 0xf0000000，VTA VCR 0xf0001000。
- 热数据（指令/uop/输入/权重/累加/输出）走 SRAM，golden 对照数据 expected 放 DDR。
  mlperf_resnet8_qconv 从纯 DDR 的 367641 cycle 降到 78012（约 -79%）。

仿真脚本：

- soc/scripts/sim_build.sh：构建前自动修复 verilated.mk，并剥离
  CFLAGS/CXXFLAGS/CPPFLAGS 里的 -std=，避免把 C++ 编译退回 C++98。
- soc/scripts/sim_run.sh：运行 Vsim 前把工具链里的 host 库目录加入
  LD_LIBRARY_PATH，解决 libjson-c.so.4 / libevent-2.1.so.7 找不到。
- 新增 soc/scripts/fix_verilator_cxxstd.sh：幂等修复脚本，可单独调用。

工具链：

- verilated.mk 修复到 v4：CXX = /usr/bin/g++ -std=gnu++11，并清空
  -faligned-new / -Wno-bool-operation 等 GCC 4.8 不认识的选项。

ASIC RTL：

- generated/.../rtl/vta.v 为 ASIC 版 VTA_Top 改名；rtl/mem_sim/ 放入 6 个
  Verilator 兼容的 SRAM 行为模型；filelist.f / manifest.json 同步更新。
- rtl/mem_wrap/ 的 6 个 SRAM 黑盒封装属正式代码，以 README 占位，需手动拷贝。

## 三、服务器环境适配（离线，CentOS 7 / glibc 2.17）

- RISC-V GCC 包装脚本：把 gcc-runtime/lib 的 libstdc++/libmpfr 注入 LD_LIBRARY_PATH，
  且只在 RISC-V 工具链内部生效，不污染宿主机 g++。
- tinyvta_env.csh：清空 LD_PRELOAD/LIBRARY_PATH/LD_LIBRARY_PATH，CC/CXX 挂上
  各自的 C/C++ 标准，且不导出 PYTHON（避免与 Makefile 的 PYTHON ?= .venv/bin/python 冲突）。
- 缺 cc1plus / C++ 头文件时用 tinyvta-gcc-cxx-centos7.tar.gz（需 sudo）补齐。
- 上传大文件被截断：改用 30 MB 分片 + sha256sum 校验后 cat 合并。

环境脚本 consolidation（本轮）：把之前分散在 sim_build.sh / sim_run.sh 里的
主机侧配置尽量收进 tinyvta_env.csh，source 一次即可，后续无需手工修复：

- VERILATOR_ROOT / VERILATOR_DEB_ROOT / RISCV_DEB_ROOT / VERILATOR 全部落进脚本。
- CPATH（host 头文件）/ LIBRARY_PATH（host 链接库）/ LD_LIBRARY_PATH（host 运行库，
  只含 json-c/libevent，无 libstdc++，不会影响宿主 g++）也收进脚本。
- 清空 CFLAGS/CXXFLAGS/CPPFLAGS，杜绝 -std= 泄漏覆盖 C++11。
- source 时顺带幂等执行 fix_verilator_cxxstd.sh，把 verilated.mk 的 C++ 标准修好；
  make sim 仍会再兜底一次，双重保险。

setup_env.csh 健壮性（本轮）：之前它只认继承来的 TINYVTA_ROOT，如果 shell 里
残留了旧值（例如改名前的 .../zvslab_tinyVTA/SoC），就会去错误的目录找安装包，
报「tinyvta-tools-all.tar.gz 不存在」但其实文件就在当前目录。现在改成：只要当前
目录有安装包就优先用当前目录，并在 TINYVTA_ROOT 下没有 soc/ 时报错退出；工具链包
既不存在又没有已解压的 tools/ 时也直接报错，不再静默跳过。

同一处还有第二个坑：TOOLS_TAR / WHEELHOUSE_TAR 一旦被上一次 source 导出到 shell，
再 source 就不会重新计算，于是目录改名后仍然指着旧路径（表现为 TINYVTA_ROOT 已经
是对的、报错却还是 .../SoC/...）。现在只有在继承值确实存在时才沿用，否则从
TINYVTA_ROOT 重新推导，并打印一行 note 说明忽略了哪个旧值。

路径基准改成 VTA_PATH（本轮）：包统一部署在 $VTA_PATH/soc，脚本里所有路径都
以 TINYVTA_ROOT（= $VTA_PATH/soc）为基准，不再写死 /project/research/... 这类
绝对路径。解析顺序是：已导出的 TINYVTA_ROOT > $VTA_PATH/soc > 当前目录；
TINYVTA_ROOT 与 VTA_PATH 会互相补全。README 的复现步骤也改成先 setenv VTA_PATH，
并把工具链解压 + venv + 依赖安装合并成一条 ./setup_env.csh。

安装包与工具链移到 $HOME（本轮）：tinyvta-tools-all.tar.gz 和
tinyvta-python310-offline.tar.gz 现在放 TINYVTA_BUNDLE_DIR（默认 $HOME，即
/home/wangshu），setup_env.csh 把两个包解压到同一目录，得到 tools/、gcc-runtime/、
wheelhouse/；项目目录只保留源码，不再放 113 MB 的工具链。tinyvta_env.csh 会自动
把 TINYVTA_TOOLS_DIR 设成 $TINYVTA_BUNDLE_DIR/tools 并导出，sim_build.sh /
sim_run.sh / check_env.py 都读这个变量，所以工具链放在项目外也能正常构建。
兼容旧布局：TINYVTA_BUNDLE_DIR 下没有安装包时会回退到项目目录，tools/ 落在项目里
时也仍然可用。

## 四、交付物与校验

tinysoc_wangshu.tar.gz（清版环境，约 212 KB）：校验值见交付目录的 SHA256SUMS.txt
（该包自身包含本文档，把自身哈希写进去会自相矛盾，故单独列出）。

tinyvta-tools-all.tar.gz（工具链整合包，90 MB）：
  sha256 f33d802daaf670073a58473b98e7b67d68f57bdbb9c7e4378497510e7669f44e

tinyvta-python310-offline.tar.gz（wheelhouse，23 MB）：
  sha256 6ee0128456b6080e3c0f4aafd6cad5b6cb554ecb3b7724db2213706bf4c592b7

## 五、服务器完整运行包组成

需要用户额外提供（正式代码，不随包分发）：

- nobist/VTA_Top.v 复制为 generated/vta-ip/apb32-axi64/rtl/vta.v
- nobist/mem_wrap/*.v（6 个）复制到 generated/vta-ip/apb32-axi64/rtl/mem_wrap/
- BC 数据头 bc_npu_model.h / bc_npu_code.h / bc_npu_data.h / bc_npu_params.h /
  bc_test_data.h 复制到 soc/cases/bc_npu/，然后跑
  bash soc/patch_bc_case.sh soc/cases/bc_npu（把 VTA_BADDR 改到 0xf0001000）。

## 六、问题与对策

- veril.cpp 报 nullptr was not declared：verilated.mk 的 CXX= 覆盖了环境变量，g++ 退回 C++98。
  用 v4 修复包，或手动给 CXX 加 -std=gnu++11。
- 报 cannot execute cc1plus：残留 conda 的 LD_PRELOAD/LIBRARY_PATH，重新 source tinyvta_env.csh。
- 报 libmpfr.so.6 / GLIBC_2.27 / GLIBCXX_3.4.21 找不到：RISC-V 运行库没走 gcc-runtime/lib，
  用包装脚本注入，不全局 export。
- 报 error while loading shared libraries: libjson-c.so.4（sim 过、run 不行）：运行时
  LD_LIBRARY_PATH 漏了 tools/linux-host，更新 sim_run.sh 或 setenv 到 host lib 目录。
- 报 invalid -march= rv32im：PATH 里其他汇编器覆盖了 RISC-V 工具，检查 PATH 顺序。
- 仿真长时间不出结果（CPU 100% 无输出）：RTL 参数与 case 指令流不匹配（如用 ASIC 版跑
  resnet8），改用 bc_npu 对 ASIC RTL，并检查 blockIn/blockOut 配置。
