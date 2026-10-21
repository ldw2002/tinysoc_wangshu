# TinySoC 综合环境

当前提供独立的 **Yosys 通用综合** 流程，用于本地 VTA 的综合检查和资源统计。
它不依赖 LiteX、Verilator、RISC-V 工具链或商业工具许可。
默认使用固定版本的 YoWASP Yosys 0.70；也可以显式选择本机原生 Yosys。

另有独立的 **Synopsys Design Compiler 后端**，复用同一份 RTL profile，支持展开检查和指定库/SDC 后的工艺映射。
入口为 `make synth-dc-prepare` / `make synth-dc`，服务器配置与当前验证范围见 [DC 使用说明](dc/README.md)。
本地尚未安装或真实运行 DC；脚本准备完成不等于 DC 综合通过。

CentOS 7 服务器使用独立的 Yosys 0.40 离线组合和 `synth/server.mk`，不要直接搬运当前 Wasmtime 47 环境（需要 GLIBC 2.28）。
离线包安装、参考项目和带备份的增量同步见 [服务器离线部署说明](SERVER_BUNDLE.md)。

## 当前机器运行

在 WSL Ubuntu-20.04 中，从项目的 `soc/` 目录执行：

```sh
make synth-setup
make synth
make synth SYNTH_STAGE=gates
make synth SYNTH_PROFILE=vcr SYNTH_STAGE=gates
```

PowerShell 中可以直接执行：

```powershell
wsl.exe -d Ubuntu-20.04 -- make -C /mnt/d/VSCode/tinysoc_wangshu/soc synth
```

安装位置为 `$HOME/.local/share/tinysoc-synth/venv`，依赖版本在本目录 `requirements.txt` 固定。
安装脚本复用现有 Python >=3.10 创建独立 venv，不改变项目的 LiteX Python 环境和系统 Python。
自定义位置使用 `SYNTH_ENV_DIR`；自定义创建环境的 Python 使用 `SYNTH_BOOTSTRAP_PYTHON`。
`installed-requirements.txt` 记录安装结果。首次运行需下载依赖并缓存 WebAssembly 编译结果。

## 选择综合对象和阶段

`profiles.json` 中目前有两个配置，源码路径相对于仓库根目录：

| 配置 | 顶层 | 范围 |
|---|---|---|
| vta-local | VTA_Top | 本地自包含 16×16、APB32/AXI64 VTA |
| vcr | VCRRegisters | 小规模寄存器块，验证综合/ABC 工具链 |

- `coarse`：层次检查、过程转换、逻辑/FSM/算术优化、存储收集和结构检查；保留字级算术与 RAM。
- `gates`：在上述基础上通过 techmap/ABC 的 strash/map 流程将逻辑映射为通用门；仍保留 RAM 阵列。

默认保留 RAM，避免把数百万位存储直接映射成触发器。报告中的 RAM 位数是逻辑容量，不是 ASIC SRAM 面积或 FPGA BRAM 使用量。
通用门数量也不是某工艺的面积或某 FPGA 的 LUT 数量。
两个阶段都显式定义 `SYNTHESIS`，不引入随机初始化逻辑。
综合视图显式移除仅用于验证的断言单元，不改变原 RTL 中的仿真断言。
触发器位数仅统计存储阵列之外的寄存器单元；合并到 RAM 读端口的寄存器不另计。

默认输入只包含本地 `rtl/vta.v`，因为该版本已内嵌其存储数组，属于自包含 RTL。
当前活动 IP 的旧 filelist 仍引用缺失的服务器封装，不能作为这一配置的输入。
这不是忽略综合错误：`hierarchy -check` 和 `check -assert` 会检查实际所选设计；输入源文件和 SHA256 会记录到报告。
服务器 BIST 发布包仍需配套顶层后建立单独配置，不能把这次结果当作服务器版 NPU 已通过。

## 产物

默认路径：`soc/build/synthesis/<配置>/<阶段>/`。

| 文件 | 内容 |
|---|---|
| summary.json | 通过/失败状态、工具版本、输入 SHA256、层次展开后的资源计数 |
| report.md | 综合范围、统计和限制 |
| stat.json | Yosys 原始统计 |
| netlist.v / netlist.json | 优化后 Verilog / JSON 网表 |
| run.ys | 可重放的完整 Yosys 脚本 |
| yosys.log / console.log | 完整日志和错误信息 |

资源统计按每个实例的实际出现次数计算，复用模块不会只统计一次。
新运行开始时会使旧成功报告失效；执行失败时记录失败状态，不沿用旧成功指标。

更多控制选项：

```sh
python3 tools/run_synthesis.py --help
make synth SYNTH_ARGS="--yosys /path/to/yosys --timeout 600"
```

可通过 `--profiles` 使用其他配置文件，通过 `--top` 覆盖顶层、`--build-dir` 指定产物目录。
也可用 `SYNTH_YOSYS=/path/to/yosys` 显式覆盖 Makefile 的工具选择。
`soc/sim/models/` 中的自建 SRAM 功能替代模型会被拒绝作为综合输入；ASIC 综合应使用宏的黑盒/综合视图及实际工艺映射。

## 后续器件/工艺综合

当前 SoC 入口是 SimPlatform，含 DDR 仿真 PHY/存储模型和仿真接口；本流程没有声称综合整个 SoC。
SoC 综合需要明确硬件边界，并替换仿真模型或提供宏黑盒。

- FPGA：确定器件/板卡、硬件顶层、BRAM/DDR 实现、时钟复位和约束，再配置目标器件综合及实现工具。
- ASIC：提供标准单元 Liberty、SRAM 综合视图/Liberty、工艺配置和时序约束，再建立实际库映射、STA 及后端流程。
- Design Compiler 已提供脚本后端，但工具、许可证和工艺库仍需服务器提供；本地没有真实 DC 运行结果。
- Vivado、Quartus、Genus 等商业工具尚未在本环境配置或验证。

200 MHz 是现有仿真配置，本流程没有据此验证 Fmax、时序收敛、功耗、PPA 或 bitstream。

## 已验证基线（2026-10-20）

本地 VTA 输入 SHA256：`c63e432318179bd8e8ef8192a6954d20a1c0664274f226b4103ccb2cb31b4771`。

| 配置/阶段 | 层次展开后的叶单元 | 存储阵列 | 存储位数 | 阵列外寄存器位数 |
|---|---:|---:|---:|---:|
| vta-local / coarse | 4860 | 82 | 3747479 | 11841 |
| vta-local / gates | 387868 | 82 | 3747479 | 11785 |
| vcr / gates | 1615 | 0 | 0 | 320 |

三个配置均通过 `check -assert`，没有推断锁存器或遗留 RTL 过程。
叶单元统计包含对应阶段的算术/逻辑、寄存器和未映射存储单元，不能直接称为物理门数。
精确工具版本、源码哈希、警告和运行耗时以各次 `summary.json` 为准。
