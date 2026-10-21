# 将 TinySoC 上传到 GitHub

以下命令在本地 Windows PowerShell 执行，项目根目录为 `D:\VSCode\tinysoc_wangshu`。本地已安装 Git，尚未初始化此目录为 Git 仓库。

## 1. 提交范围

`.gitignore` 已修正：只忽略根目录 `/tools/` 工具链，保留 `soc/tools/` 中的项目脚本。虚拟环境、构建结果、运行库、离线包和 `deliverables/` 不纳入源码提交。

服务器原始快照 `generated/vta-ip/server-memory-*/` 和 `syncore_be_ram_sdp_en.v` 暂不提交。后者文件头有明确的 Synopsys 保密/专有条款，需要根据实际许可决定是否可以上传。私有仓库的可见性设置本身不授予第三方代码的上传许可。

建议初始仓库设为 Private。准备公开时，再核对剩余 RTL、文档和数据的发布范围与许可证；此仓库尚未自动添加统一的开源许可证。

`.gitattributes` 保护 `generated/vta-ip/` 下文件的原始字节，避免跨平台换行转换使 RTL SHA256 失效；shell 和 Makefile 使用 LF 换行。

默认的本地 VTA 综合配置使用自包含的 `rtl/vta.v`，不依赖被排除的服务器快照。服务器 wrapper 绑定测试、服务器源码归档及重新制作包含归档的离线增量包，仍需在本地另行提供这些文件。

## 2. 初始化并完成本地提交

```powershell
cd D:\VSCode\tinysoc_wangshu
git init -b main
git config core.autocrlf false
```

如果尚未设置提交身份，使用你的姓名/昵称和 GitHub 邮箱配置。也可以使用 GitHub Settings → Emails 中的 noreply 地址：

```powershell
git config user.name "你的姓名或昵称"
git config user.email "你的GitHub邮箱"

git add .
git status --short
git diff --cached --stat
```

确认 `soc/tools/` 中的脚本已暂存，同时没有离线工具链、构建目录及被排除的服务器 RTL。Windows 文件系统通常不携带 Linux 执行位，首次提交时为入口脚本设置：

```powershell
git update-index --chmod=+x setup_env.csh soc/scripts/setup_synth_env.sh soc/scripts/sim_build.sh soc/scripts/sim_run.sh soc/scripts/fix_verilator_cxxstd.sh soc/scripts/riscv_deb_compat/riscv64-unknown-elf-gcc soc/scripts/verilator_deb_compat/verilator
git commit -m "Initial import of TinySoC verification platform"
```

## 3. 创建 GitHub 仓库并推送

打开 https://github.com/new ，仓库名例如 `tinysoc_wangshu`，选择 Private。创建空仓库，初始化选项中的 README、gitignore 和 license 留空，避免与已有本地内容产生两套初始提交。

把下面地址替换为新建仓库的实际 HTTPS 地址：

```powershell
git remote add origin https://github.com/你的用户名/tinysoc_wangshu.git
git push -u origin main
```

首次 HTTPS 推送按 Git 的提示完成 GitHub 身份认证；Git for Windows 的凭据管理器通常会引导浏览器登录。若使用 PAT，请在凭据提示中输入，不要将 token 写入 remote URL、脚本或仓库文件。

## 4. 后续更新

```powershell
git status
git add .
git diff --cached --stat
git commit -m "Describe the change"
git push
```

服务器需要独立克隆时，可使用新目录，例如：

```sh
git clone https://github.com/你的用户名/tinysoc_wangshu.git /project/research/wangshu/project/tinysoc_git
```

现有 `/home/wangshu/` 工具依赖继续通过环境变量/绝对路径引用。服务器已部署目录中若有未提交的正式 RTL 或配置，先保留这些差异，再决定迁移方式。
