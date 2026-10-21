# TinySoC 服务器离线综合包（2026-10-21）

本包面向此前记录中的 **CentOS 7 / Linux x86_64 / GLIBC 2.17** 服务器，使用服务器已有的 **Python >=3.10**。不包含 Python 解释器，不需要 sudo，不依赖外部 `which` 程序，不联网安装，也不修改系统 glibc 或现有 SoC Python 环境。

包内有：

- `offline_yosys/`：固定版本 wheelhouse、离线安装器和 SHA256 清单。
- `reference_project/`：独立的本地 VTA 参考 RTL 与新增的综合/DC/SRAM 工具，可先在这里试跑。
- `project_update/`：可以同步到现有项目的新增文件，不含活动 `vta.v` 和 SoC Makefile。
- `review/soc.Makefile`：本地完整 Makefile，仅供对照合并。
- `apply_server_synth_update.py`：校验、预览和带备份的增量同步工具。
- `validation/`：本包依赖及参考设计的验证结果；不含工具缓存或大型网表。
- `manifest.json`、`SHA256SUMS`：包内各文件的哈希和来源范围。

## 1. 上传并解压

将 `tinysoc_server_synth_20261021.tar.gz` 与旁边的 `.sha256` 文件一起上传。Linux bash/csh 均可执行：

```sh
sha256sum -c tinysoc_server_synth_20261021.tar.gz.sha256
tar -xzf tinysoc_server_synth_20261021.tar.gz
cd tinysoc_server_synth_20261021
```

下面使用 `python3.10`，请替换为服务器已有 Python 3.10 或更高版本的实际命令/绝对路径。可以先执行 `python3.10 --version`；不需要 `which`。

```sh
python3.10 apply_server_synth_update.py --verify-only
python3.10 offline_yosys/install_synth_offline.py
```

默认安装位置是 `$HOME/.local/share/tinysoc-synth-centos7/venv`，原有 LiteX 环境保持独立。也可用 `--prefix /path/to/new-prefix` 指定位置，后面的 make 命令相应增加 `SYNTH_ENV_DIR=/path/to/new-prefix`。安装目录已有其他内容且不属于此安装器时会拒绝覆盖。

安装器从随包附带的 pip wheel 引导，不要求现有 Python 安装 pip/ensurepip，但需要标准库的 venv 和 Python 本身正常工作。安装后会执行依赖检查和 `yowasp-yosys -V`。首次启动会在用户缓存目录编译 WebAssembly，耗时可能较长，无需联网。

## 2. 先运行包内参考项目

```sh
cd reference_project/soc
make -f synth/server.mk synth SYNTH_PROFILE=vcr SYNTH_STAGE=gates
make -f synth/server.mk synth SYNTH_PROFILE=vta-local SYNTH_STAGE=coarse
```

结果默认保存在 `reference_project/soc/build/synthesis/<profile>/<stage>/`，包括 `report.md`、`summary.json`、网表和日志。存储数组保持未映射状态。Yosys `run.ys` 的固定输出文件名相对构建目录，手动重放时应先进入该输出目录。

这里的参考 RTL 是本地自包含的 16×16、APB32/AXI64 VTA，不能据此认定服务器另一版 ASIC/BIST NPU 或完整 SoC 已通过。原始 RTL SHA256 为：

```text
c63e432318179bd8e8ef8192a6954d20a1c0664274f226b4103ccb2cb31b4771
```

## 3. 同步新增内容到服务器现有项目

回到解压包顶层，`--project-root` 必须指向同时包含 `soc/` 和 `generated/` 的项目根目录，不是其内部的 `soc/`。

```sh
# 先只校验和预览
python3.10 apply_server_synth_update.py --project-root /path/to/tinysoc

# 应用更新，旧文件会自动备份
python3.10 apply_server_synth_update.py --project-root /path/to/tinysoc --apply
```

备份和更新报告保存在目标项目 `soc/build/server-synth-backups/<本次编号>/`。同步程序不复制活动 `vta.v`，不替换现有 Makefile；使用独立的 `soc/synth/server.mk` 运行新增流程。

如果服务器活动 RTL 的哈希与参考 RTL 不同，程序会跳过 `soc/synth/profiles.json`，保留服务器原配置。此时请从 `profiles.server.example.json` 建立自己的 profile，核对顶层名、全部源码/宏、include 路径及 SRAM 实现后，再通过 `SYNTH_ARGS="--profiles synth/profiles.server.json"` 或 `DC_ARGS="--profiles synth/profiles.server.json"` 指定。示例不包含完整服务器 BIST 源码清单，不能直接当作完整配置。

同步内容包括综合/DC 脚本、相关测试、SRAM 功能模型与测试脚本，以及服务器 memory/BIST 文件的独立快照和审计说明。`generated/vta-ip/server-memory-20261020/` 是归档，未自动加入当前综合清单。SRAM 仿真功能模型不会作为综合输入。
SRAM 模型测试需要 Icarus Verilog，本综合离线包未包含 Icarus；这不影响 Yosys 和 DC 入口。

## 4. 使用服务器已有的 DC

DC 本体、许可证和工艺库不随包分发。路径 `/tools/eda1/` 是工具安装区域，不一定就是可执行文件目录，可以使用 `find` 定位：

```sh
find /tools/eda1 -name dc_shell 2>/dev/null
```

按服务器已有方式加载 Synopsys 环境和许可证后，在包内参考项目的 `soc/` 目录试跑。下面路径是示例，替换为实际结果：

```sh
make -f synth/server.mk synth-dc-prepare SYNTH_PROFILE=vcr
make -f synth/server.mk synth-dc SYNTH_PROFILE=vcr DC_SHELL=/tools/eda1/实际目录/bin/dc_shell
```

映射需要自行准备真实 `.db` 和对应顶层的完整 SDC，参考 `soc/synth/dc/config.example.json` 和 DC README。当前只验证了生成器和 Tcl 控制流程，没有本地真实 DC 运行结果。完整 VTA 的推断数组尚未自动替换成 SRAM 宏，只添加 SRAM `.db` 不会完成宏适配。

## 5. 版本与验证边界

离线包固定使用 Yosys **0.40**、yowasp-runtime **1.60**、Wasmtime **20.0.0**；本地原有环境仍为 Yosys **0.70**。选择旧版本是为了兼容服务器 glibc。不同版本优化结果不必相同，报告必须连同工具版本比较。

本地已实际完成：离线安装与依赖检查、Yosys 启动、小模块 gates 综合、完整 VTA coarse 综合、综合/DC 自动检查。Wasmtime ELF 导入的最高 GLIBC 符号版本为 **2.14**；完整 CentOS 7 实机及服务器 DC 仍需上传后验证。包内 `validation/` 记录具体结果。

本包不包含新版 Wasmtime 47，不升级系统 glibc，不提供 PPA/时序收敛或 FPGA bitstream 结论。

## 6. HOME 配额用尽时

如果启动时在 `cache_filename.open("wb")` 报 `OSError: [Errno 122] Disk quota exceeded`，说明写 YoWASP 编译缓存时配额不足；总磁盘有空闲也可能出现用户配额不足。可以把缓存和综合输出都移到有可用配额的项目或 scratch 文件系统。

在此前的 csh/tcsh 环境中，例如：

```csh
setenv YOWASP_CACHE_DIR /project/research/wangshu/project/zvslab_tinyVTA/soc/soc/build/yowasp-cache
mkdir -p "$YOWASP_CACHE_DIR"
/home/wangshu/.local/share/tinysoc-synth-centos7/venv/bin/python /home/wangshu/.local/share/tinysoc-synth-centos7/venv/bin/yowasp-yosys -V
```

如果仍从 HOME 中的参考项目运行综合，请同时通过 `SYNTH_ARGS="--build-dir /project/research/wangshu/project/zvslab_tinyVTA/soc/soc/build/synthesis/vcr/gates"` 重定向综合输出，避免网表继续占用 HOME。如果新目录也报配额不足，需要换到有配额的目录或释放相应文件系统的个人配额。无需删除已安装的 Python 依赖。

新版 `server.mk` 默认缓存目录为当前 `soc/` 下的 `build/yowasp-cache`，显式指定的 `YOWASP_CACHE_DIR` 会优先使用。已上传的 20261021 原包可以直接使用上述环境变量，不必重装。
