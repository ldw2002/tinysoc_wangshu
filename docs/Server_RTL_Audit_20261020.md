# 服务器 NPU 存储 RTL 核验

日期：2026-10-20。输入为用户提供的 22 个文件。核验范围为存储包装层、分支依赖和局部行为，不代表完整 NPU 或 SoC 已通过仿真。

后续进展：已新增 `soc/sim/models/npu_sram_behavioral.sv`，覆盖七类 SRAM 宏，可替代大型宏模型用于当前约定下的 RTL 功能仿真。
Icarus 四态测试已通过七类宏全地址检查、13 个异常场景和七组 ASIC 包装层端口绑定；尚未与厂商模型做等价验证。
下文原始依赖清单中的厂商 SRAM 模型仍适用于真实宏行为/时序验证；使用自建功能模型时可暂不获取。

## 已完成的整理

- 原始文件按字节归档到 `generated/vta-ip/server-memory-20261020/`，没有修改源文件。
- 七个 `*_ext.v` 放入 `rtl/mem_wrap/`，其余十五个文件放入 `rtl/bist_rtl/`；来源和 SHA256 记录在 `source_inventory.json`。
- 当前 `apb32-axi64` 活动目录的 RTL、filelist、manifest、interface 未替换。
- 使用 Icarus Verilog 10.3 做局部编译和四态读写测试，并使用 pyslang 12.0.0 交叉检查展开依赖。工具保存在 `soc/build/server_rtl_audit/`，没有安装到系统路径。

## 存储实例与选择关系

```text
七个 *_ext
  -> NPU_sram_wrap_2p / NPU_sram_wrap_sp
     -> ASIC: NPU_sram_asic_* -> SRAM 宏
     -> 非 ASIC 且 FPGA: NPU_sram_fpga_* -> syncore_be_ram_sdp_en
     -> 两宏均未定义: 行为分支，当前代码不完整
     + NPU_sram_bist、NPU_sram_xor、时钟门控和 MUX
```

ASIC 分支优先于 FPGA；不能同时定义两者来混用 SRAM 与门控实现。
所有七个外层封装均显式设置 `HAS_BIST=1`，写使能宽度均为 1。

| 外层模块 | 类型 | 深度 × 位宽 | 对应 ASIC 宏模块 |
|---|---|---|---|
| mem_ext | 一写一读 | 8 × 128 | sram2p8x128 |
| mem_0_ext | 一写一读 | 64 × 128 | sram2p64x128 |
| tensorFile_0_ext | 一写一读 | 1024 × 32 | sram2p1024x32 |
| tensorFile_0_0_ext | 一写一读 | 256 × 64 | sram2p256x64 |
| tensorFile_0_0_0_ext | 单端口 | 128 × 32 | sram1p128x32 |
| tensorFile_1_0_ext | 单端口 | 32 × 32 | sram1p32x32 |
| vmeTag_array_ext | 一写一读 | 16 × 59 | sram2p32x59，仅使用低 16 个地址 |

单端口外层封装在读写同时有效时选择写地址，并只使用 `W0_clk` 驱动底层；`R0_clk` 未用于底层时钟。因此需要配套顶层确认其同钟、读写互斥约束。

## 已确认的问题

### 1. 新版 syncore 的 A 口寄存读路径没有生成

位置：`rtl/bist_rtl/syncore_be_ram_sdp_en.v:129`。

```systemverilog
if (READ_WRITE_A == 3) begin
```

`NPU_sram_fpga_sp` 实际配置为 `READ_WRITE_A=1`、`RADDR_LTNCY_A=0`、`RDATA_LTNCY_A=1`。
因此其输出选择 `RdDataA_reg0`，但更新该寄存器的逻辑没有生成。

局部测试向地址 3 写入 `0x12345678` 后读取，实际得到 `xxxxxxxx`。
仅在诊断副本中把该条件改为 `READ_WRITE_A != 3`，同一个测试读回 `0x12345678`。
这项诊断修改未应用到原始快照或活动 RTL。

项目原有的另一份 syncore 具有不同内容；本次 Icarus 编译还在其部分 `generate begin` 结构发现未配对的 `end`，因此也不能直接将旧文件作为已验证替代版本。

### 2. FPGA 双口包装层没有将写片选合入写入条件

位置：`NPU_sram_fpga_2p.v:92`，`EnA` 和 `WenA` 都接 `we`，`wce_n` 没有进入底层写入门控。
实际选择的是 A 写、B 读，读地址不寄存、读数据寄存。

局部测试正常写入和读回通过；随后设置 `wce_n=1、we=1`，存储仍被改写为 `0xdeadbeef`。
这违反独立片选接口的一般约定。
外层功能路径将 `wce_n=~W0_en`、`we=W0_en` 绑定，能约束掉这组输入组合；故不能据此直接断言正常 NPU 路径已经出现误写。

### 3. MUX 条件编译存在工具兼容性问题

位置：`NPU_mux_cell.v:78` 存在未在同一行填写宏名的 `` `ifdef ``。
Icarus 10.3 预处理 FPGA 分支时报告末尾 `endif` 未匹配，预处理结果中普通 MUX 赋值被丢失。
这是上层包装测试不能直接按“编译进程返回 0”认定成功的原因之一。
pyslang 对该段处理不同，必须以明确且合法的条件编译重建一致行为。
已有 `NO_MUX_CELL` 宏可选择普通逻辑 MUX，但本次不把该配置视为完整 BIST 验收结论。

### 4. ASIC 双口宏的 RMEB 连接拼写不一致

位置：`NPU_sram_asic_2p.v:89`，其他四个宏分支也相同。
模块输入声明为 `RMBE`，实例化却写为 `.RMEB(RMEB)`。
右侧 `RMEB` 没有声明，成为未驱动的隐式线网，没有使用外部输入 `RMBE`。
宏端口左侧名称是否正确，仍需真实宏模型确认；右侧信号不一致已能从源码确认。

### 5. 行为模型分支尚不完整

- `NPU_sram_wrap_2p.v:97` 的 `NPU_sram_beh_2p` 模块名被注释，留下独立的参数化实例语句，无法解析。
- 即使恢复模块名，当前实例还连接低功耗、RM 等端口，而提供的 `NPU_sram_beh_2p` 没有这些端口，需同步适配。
- `NPU_sram_wrap_sp.v:81` 引用 `NPU_sram_beh`，本批没有对应模块。
- 双口行为模型在写使能有效时禁止读，并在其他未读周期输出 Z；不能默认为其与 FPGA/ASIC 路径具有相同并发和保持语义。

### 6. SIM 不代表完整 X 检查已启用

`NPU_xchecker.v:22` 把被检查的 `data` 声明为 output，检查语句全部被注释。
因此定义 `SIM` 不会自动获得有效 X 监测；`SIM` 还会改变 BIST 比较运算语义。

## 测试记录与限制

测试脚本和日志在 `soc/build/server_rtl_audit/`：

| 测试 | 结果 |
|---|---|
| FPGA 单口包装写后读，使用服务器原文件 | 失败，读回 X |
| 相同测试，仅修正诊断副本中的 A 口生成条件 | 通过 |
| FPGA 双口包装正常写后读 | 通过 |
| FPGA 双口包装禁用片选时尝试写入 | 未抑制写入，接口测试失败 |
| 七个 FPGA 外层封装展开 | 两工具可展开；Icarus 另有 MUX 预处理异常，不能视为行为通过 |
| ASIC 分支展开 | 缺少七类 SRAM 宏模型和所选工艺标准单元模型 |
| 无 ASIC/FPGA 宏的行为分支展开 | 失败，行为分支不完整 |
| 上层 mem_ext/BIST 冒烟 | 原配置功能读回失败；增加 NO_MUX_CELL 的探索配置未完成，未给出 BIST 通过结论 |

Icarus 10.3 本次运行中部分 `$fatal` 仍返回进程码 0，测试结论同时检查日志中的 FAIL/FATAL，不能只读进程返回值。
本次未运行完整 NPU 计算、TinySoC CPU 固件、ASIC 宏时序仿真或 FPGA 板级仿真。

## 仍需从服务器补充

1. 与这七个外层封装匹配的 `SHAOCHONG_Top_bist.v`、内部计算核心和其他被实例化模块；如有正常功能独立顶层，也一并提供。
2. 上表七类 SRAM 宏的 Verilog 功能模型、递归头文件和端口说明。本地旧的六个 SZFA/SYFA 模型不能直接代替这些模块。
3. 实际选用的工艺和完整编译宏。代码中 SRAM 宏实例至少需要 `ASIC + SMIC40LL + SYNOPSYS_MEM`；门控和 MUX 还取决于标准单元选择。
4. 对应门控/MUX 的 Verilog 单元模型。若采用代码中的 SYNOPSYS 分支，为 `STN_CKGTPLT_V5_1` 和 `STN_MUX2_1`；其他工艺选择需换成对应模型，不能根据文件名猜实际选择。
5. 已跑通的 ASIC/FPGA 编译和仿真脚本、filelist、include 路径、顶层参数、正常/BIST 测试平台、通过日志及各测试端口的正常配置。
6. 与该硬件版本一致的配置、指令、uOp、权重、输入和 golden；若使用 BC 用例，需要其五个配套头文件及递归依赖。

本地旧清单引用 `tensorFile_0_1_ext.v`，本批提供的是另一组名称和规格。
不应改名凑清单，也不应简单拼接新存储层与本地内嵌数组版本的 `vta.v`。
应在取得配套顶层后按真实实例关系重新生成清单及接口元数据。
