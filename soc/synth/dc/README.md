# TinySoC 的 Design Compiler 后端

已提供可在服务器运行的 DC 脚本、配置和 Makefile 入口。**本地没有 DC 可执行程序、许可证及工艺库，因此尚未完成真实 DC 运行验证。** 本地验证覆盖脚本生成、Tcl 语法与控制流程、配置检查、失败传播，以及生成源码的 Yosys 回归；Tcl 测试中的命令替身不代表 Synopsys 工具验证。

## 输入与范围

DC 直接读取 RTL，复用上一级 `profiles.json` 的顶层、文件清单和宏，不经过 Yosys 网表。当前可选 `vta-local`（`VTA_Top`）和 `vcr`（`VCRRegisters`）；前者是本地自包含的 APB32/AXI64 VTA，并非完整 SoC 或服务器 BIST 版本。流程不引入 `soc/sim/models/` 的 SRAM 仿真替代模型。

| 阶段 | 行为 | 主要产物 |
|---|---|---|
| `elaborate`，默认 | analyze、elaborate、link、check_design，使用 DC 自带 GTECH | `elaborated.ddc`、展开后的资源及设计检查报告 |
| `map` | 上述检查后读入用户 SDC，执行 compile/compile_ultra，检查未映射叶单元 | `mapped.v`、`mapped.ddc`、`mapped.sdc`，面积、时序、QoR 报告 |

展开通过不表示工艺映射通过。映射通过也不表示时序收敛；必须审阅 `check_timing.rpt`、`timing.rpt` 和约束完整性。GTECH 资源报告与 Yosys 的统计口径不同，不能直接比较门数。

## 服务器执行

在服务器复制整个项目，并按服务器已有方式加载 Synopsys 环境和许可证。需要 Python >=3.10；本后端仅使用标准库，不需要安装 Yosys 或 LiteX。

```sh
cd tinysoc_wangshu/soc

# 只生成脚本，不查找/执行 DC
make synth-dc-prepare

# 先用小模块验证工具环境，再展开整个本地 VTA
make synth-dc SYNTH_PROFILE=vcr
make synth-dc SYNTH_PROFILE=vta-local

# 工具不在 PATH 或需选择指定 Python 时
make synth-dc DC_SHELL=/tools/synopsys/dc/bin/dc_shell DC_PYTHON=/path/to/python3
```

本机 PowerShell 中可用已有独立 Python 环境生成脚本：

```powershell
wsl.exe -d Ubuntu-20.04 -- make -C /mnt/d/VSCode/tinysoc_wangshu/soc synth-dc-prepare DC_PYTHON=/home/wangshu/.local/share/tinysoc-synth/venv/bin/python
```

建议在服务器重新生成脚本以记录服务器路径及库哈希。默认输出 `soc/build/synthesis-dc/<profile>/<stage>/`；`settings.tcl` 的源码视图采用相对路径，原始源码目录的 include 搜索路径也相对项目定位。若搬运已生成的输出目录，应保留它与项目的相对位置；工艺库和 SDC 路径是生成环境中的绝对路径，搬运后需要重新生成。Windows 自定义输出目录与源码不在同一盘符时，include 搜索路径会使用绝对路径，也需到服务器重新生成。

也可以在输出目录执行 `dc_shell -f run_dc.tcl`。这会产生工具报告及 `result.json`，但不会更新 Python 管理的 `summary.json`；建议使用 Makefile 入口，让状态和报告一起校验。

## 工艺映射配置

复制 `config.example.json` 到自己的配置文件，填写真实的库与约束，例如：

```json
{
  "target_libraries": ["/pdk/lib/standard_cells_tt.db"],
  "link_libraries": ["/pdk/sram/sram2p8x128_tt.db"],
  "search_paths": ["/pdk/include"],
  "sdc": "./tinysoc.sdc",
  "compile_command": "compile"
}
```

上面的路径仅为示例。`target_libraries` 放标准单元库；`link_libraries` 放设计实际例化的 SRAM/IP 库。所有库必须是已存在的 DC `.db` 文件，不自动编译 Liberty。JSON 中的相对路径以该 JSON 所在目录为基准，支持环境变量及 `~`。`compile_command` 仅允许 `compile` 或 `compile_ultra`，后者需要相应许可证。

```sh
# 建议先映射小模块；SDC 须对应所选顶层的端口
make synth-dc SYNTH_PROFILE=vcr DC_STAGE=map DC_CONFIG=/project/config/dc.json

# 仅检查配置并生成映射脚本
make synth-dc-prepare SYNTH_PROFILE=vcr DC_STAGE=map DC_CONFIG=/project/config/dc.json
```

`map` 阶段缺少标准单元库或显式 SDC 会立即报错。`constraints.example.sdc` 只展示 clock 端口的写法，**不会自动选用**；其中周期 5.0 以目标库的时间单位解释，不是 200 MHz 已收敛的承诺。需根据目标补齐时钟、I/O 延迟、负载、驱动、复位例外等约束。

完整 VTA 的 RTL 含约 375 万位推断存储器。DC 的存储推断/映射方式取决于工具和库，本后端没有自动把这些数组替换为 SRAM 宏；直接对完整 VTA 执行 `map` 可能展开成大量寄存器。实际 ASIC 流程应先完成 SRAM wrapper/宏例化及对应 `.db` 绑定，再评估完整设计的面积和时序。只在 link_library 中加入 SRAM 库不会自动替换数组。

当前脚本针对常规逻辑综合；没有配置物理库、floorplan 或 topographical 流程。使用 DC NXT 时选择服务器安装对应的 `dc_shell` 和许可证环境；是否支持当前命令选项仍需以服务器版本的实际运行结果为准。

## 源码视图与结果可信度

本地 `vta.v` 有 62 条未受 `SYNTHESIS` 保护的独立单行 immediate assertion。两个现有 profile 显式启用了 `dc.guard_simple_immediate_assertions`：生成器仅在构建目录 `rtl/` 的副本中给这些断言加 `synopsys translate_off/on`。字符串和注释中的 assert 保持原样；遇到多行、并发断言或带 else 等其他形式会拒绝自动处理，要求明确的 RTL 综合保护。原始 RTL、仿真断言及 IP 校验文件不改动。

`summary.json` 记录原始源码与 DC 视图的 SHA256、隔离断言数量、库/SDC 哈希、阶段、命令和状态。`prepared` 仅表示脚本已生成；只有真实执行入口完成且校验通过才写 `passed`。工具输出保存在 `console.log`，详细报告在 `reports/`。

每次调用会使旧结果失效，并用新的 token 和独立 WORK 子目录避免读到旧展开结果。执行成功需同时满足：进程返回 0、匹配本次 token/顶层/阶段的完成记录、所需报告和产物存在且非空、控制台无 Error/Fatal。许可证启动失败、工具未执行 Tcl、link/check_design/compile 失败及残留未映射单元均不能沿用旧成功结果。工具警告保留在日志中，需要结合设计审阅。

其他选项：

```sh
python3 tools/run_dc_synthesis.py --help
python3 tools/run_dc_synthesis.py --profile vcr --prepare-only --build-dir build/my-dc
# 额外的 dc_shell 参数使用 --dc-arg=...，可重复；不会作为 Tcl 命令求值
```

## 本地验证记录（2026-10-20）

- DC 后端 10 项自动检查通过，其中 Tcl 分支使用真实 Tcl 8.6 解析器与命令替身执行；覆盖展开、映射以及 link/check_design/compile/未映射单元失败。
- 现有 Yosys runner 的 4 项测试通过；共享 profile 新增的 DC 配置不改变 Yosys 输入。
- DC 源码视图的 Yosys coarse 综合通过，资源结构统计与原始 RTL 完全一致：4860 个叶单元、82 个存储数组、3747479 位存储、11841 位阵列外寄存器。`vcr/gates` 回归仍为 1615 个叶单元、320 位寄存器。
- 真实 Synopsys DC、工艺库解析和许可证尚未验证；服务器首次运行应先使用 `vcr`。

测试命令：`python3 -m unittest discover -s tests -p 'test_dc_synthesis.py' -v`。默认没有 Tcl 时会跳过 Tcl 部分；设置 `DC_TEST_TCL=/path/to/tclsh` 可启用，并按该 Tcl 的安装位置配置运行库。
