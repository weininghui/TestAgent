# 安装与更新 — OpenCode 插件与 CLI

[English](INSTALL.md) | **简体中文**

本文把三件事分开说明：

| 章节 | 适用场景 |
|------|----------|
| [1. 仅安装 CLI](#1-仅安装-cli不用-opencode-插件) | 终端、CI 脚本，不用 OpenCode |
| [2. OpenCode 插件 — 首次安装](#2-opencode-插件--首次安装) | 第一次配置 MCP + Agent |
| [3. 更新到最新版本](#3-更新到最新版本) | 已安装但版本过旧 |

**当前 Release：** [v5.10.0](releases/RELEASE_NOTES_v5.10.0.md) — 最新 tag 见 [GitHub Releases](https://github.com/weininghui/TestAgent/releases)。

## 最省事怎么用（推荐）

| 你的习惯 | 做法 | 更新时要做的事 |
|----------|------|----------------|
| **只测某一个 SDK 项目** | OpenCode **直接打开 SDK Forge 仓库**（方式 A） | `git pull` + **重启 OpenCode**（`run_mcp.py` 会自动 pip） |
| **所有项目都要用 forge** | 全局插件目录 + 一键脚本 | 运行 `scripts/update-opencode-plugin.ps1` + **重启 OpenCode** |

`plugin.yaml` 已改为 `python run_mcp.py`：OpenCode 启动 MCP 时会**自动**检查 `mcp`/`pydantic` 依赖和 `sdk_forge` 版本，必要时静默 `pip install -e .`。  
你仍需要 **重启 OpenCode**（MCP 子进程不会热更新），但通常**不必再手动 pip**。

### 想「GitHub 有新版就自动兜底」？

**一键启用（推荐）：**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/enable-auto-update.ps1
```

会做三件事：

| 机制 | 何时运行 | 作用 |
|------|----------|------|
| **`FORGE_AUTO_UPDATE=1`** | 每次 OpenCode 启动 MCP | 最多每 6 小时 `git pull` + 自动 `pip` + 同步 Agent/Skill |
| **计划任务** `SDKTestForge-PluginAutoUpdate` | 每天凌晨 3:00（默认） | 即使用户没开 OpenCode 也拉 GitHub |
| **`run_mcp.py` pip 自检** | MCP 启动 | 依赖/版本不对时静默重装 |

手动等价设置：

```powershell
[System.Environment]::SetEnvironmentVariable("FORGE_AUTO_UPDATE", "1", "User")
```

**前提：** 插件目录必须是 **git 克隆**（`%APPDATA%\OpenCode\plugins\sdk-forge`），不能是 zip 拷贝。

**仍须知道：** 拉完新代码后，**完全退出再打开 OpenCode** 才会加载新 MCP（同一次会话不会热更新）。若自动更新拉了新提交，`.forge/cache/pending_opencode_restart.json` 会提示需要重启。

### 想「尽量自动」更新 GitHub 代码？（手动环境变量）

设置环境变量 **`FORGE_AUTO_UPDATE=1`** 后，每次 OpenCode 启动 MCP（`run_mcp.py`）时会：

1. 每 **6 小时最多一次** `git fetch` + 若落后则 `reset` 到 `origin/main`
2. 再自动 `pip install -e .`（已有逻辑）

**Windows（用户环境变量，永久生效）：**

```powershell
[System.Environment]::SetEnvironmentVariable(
  "FORGE_AUTO_UPDATE", "1", "User"
)
```

或在 OpenCode 的 MCP 配置里为 `sdk-forge` 增加 `env`（若你的 OpenCode 版本支持）：

```json
"env": { "FORGE_AUTO_UPDATE": "1" }
```

**注意：** 自动拉代码需要网络；仅适用于 **git 克隆的插件目录**（全局 `plugins/sdk-forge`）。  
**不会**在运行中热更新 — 拉完新代码后，下次 **重启 OpenCode** 才会加载新 MCP 逻辑；同一次会话内仍是旧进程。

**Windows 一键更新（全局插件目录）：**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/update-opencode-plugin.ps1
```

---

## 版本号该看哪里？

| 来源 | 显示内容 | 能否代表功能版本？ |
|------|----------|-------------------|
| `python -c "import sdk_forge; print(sdk_forge.__version__)"` | **运行时代码版本** | **是（最可靠）** |
| `plugin.yaml` 里的 `version:` | OpenCode 插件清单 | 是 |
| `pip show sdk-forge` → `Version` | `pyproject.toml` 包元数据 | 仅当发布时同步更新了 `pyproject.toml` |
| GitHub Release tag | 官方发布版本 | 是 |

若 `pip show` 仍是 `4.0.0`，但 `sdk_forge.__version__` 已是 `5.2.0`，说明 **代码已更新、pip 元数据未重装** — 在插件目录再执行一次 `pip install -e .`。

**v5.10+ 安装自检：**

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"   # 应为 5.10.0
forge autopilot --help                                         # 必须有 autopilot 子命令
python -c "import sdk_forge.task_dispatch"                     # task 派发模块
```

OpenCode MCP 工具列表中应有 **`get_task_dispatch_plan`**、**`validate_forge_delegation_tool`**、**`get_subagent_dashboard`**、**`run_forge_autopilot`**、**`advance_forge_workflow`**。  
**v5.10 已移除：** `dispatch_forge_delegate`（仅使用 OpenCode `task` tool call）。

---

## 1. 仅安装 CLI（不用 OpenCode 插件）

只在命令行或 CI 里用 `forge`，不需要 OpenCode。

### 环境要求

- Python 3.10+
- CMake 3.14+
- C++ 编译器（g++/clang++/MSVC）
- 建议安装 `git`（预拉取 GTest）

### 安装

```bash
git clone https://github.com/weininghui/sdk-forge.git`ncd sdk-forge
pip install -r requirements.txt
pip install -e .

# 可选
pip install "sdk-forge[clang]"   # libclang 头文件解析
pip install "sdk-forge[yaml]"    # .forge.yaml
```

### 验证

```bash
forge doctor
forge --help
```

---

## 2. OpenCode 插件 — 首次安装

本仓库是 **Python MCP 插件**（`sdk-forge`），**不会**出现在 OpenCode 的 npm 插件市场里。请在 MCP 列表找 `sdk-forge`，在 Agent 下拉框找 `forge`。

任选 **一种** 方式：

### 方式 A — 直接打开本仓库（最简单）

1. 克隆：

   ```bash
   git clone https://github.com/weininghui/sdk-forge.git`n   cd sdk-forge
   ```

2. 安装 Python 包（可编辑模式）：

   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

3. 用 OpenCode **打开 SDK Forge 根目录**。

4. OpenCode 自动加载根目录 `plugin.yaml` → 启动 `python mcp_server.py`。

5. Agent 提示词在仓库 `.opencode/agents/forge.md` 及 `forge-*.md`。

   若要在 **所有项目** 里用 forge，再复制到全局目录：

   ```
   %APPDATA%\OpenCode\agents\          # Windows
   ~/.config/opencode/agents/          # Linux / macOS
   ```

6. OpenCode 聊天窗口选择 Agent **`forge`**；确认 MCP **`sdk-forge`** 已启用。

### 方式 B — 全局插件目录（任意项目都能用）

Windows 标准路径：

```
%APPDATA%\OpenCode\plugins\sdk-forge
```

示例完整路径：

```
C:\Users\<你的用户名>\AppData\Roaming\OpenCode\plugins\sdk-forge
```

**步骤（Windows PowerShell）：**

```powershell
$PluginDir = "$env:APPDATA\OpenCode\plugins\sdk-forge"
New-Item -ItemType Directory -Force -Path (Split-Path $PluginDir) | Out-Null

# 首次安装：克隆指定 release tag
git clone --branch v5.1.0 --depth 1 https://github.com/weininghui/sdk-forge.git $PluginDir

cd $PluginDir
pip install -r requirements.txt
pip install -e .

# 全局 Agent 提示词
$AgentsDir = "$env:APPDATA\OpenCode\agents"
New-Item -ItemType Directory -Force -Path $AgentsDir | Out-Null
Copy-Item -Force ".opencode\agents\forge*.md" $AgentsDir
```

**Linux / macOS：**

```bash
PLUGIN_DIR="$HOME/.config/opencode/plugins/sdk-forge"
mkdir -p "$(dirname "$PLUGIN_DIR")"
git clone --branch v5.1.0 --depth 1 https://github.com/weininghui/sdk-forge.git "$PLUGIN_DIR"
cd "$PLUGIN_DIR"
pip install -r requirements.txt
pip install -e .
mkdir -p "$HOME/.config/opencode/agents"
cp .opencode/agents/forge*.md "$HOME/.config/opencode/agents/"
```

**可选** — 在 `opencode.json` 里手动注册 MCP（未使用项目级 `plugin.yaml` 时）：

```json
{
  "mcp": {
    "sdk-forge": {
      "command": ["python", "C:/Users/YOU/AppData/Roaming/OpenCode/plugins/sdk-forge/mcp_server.py"],
      "enabled": true,
      "type": "local"
    }
  }
}
```

7. **完全退出并重启 OpenCode**（不是只关聊天窗口）。

8. 按上文 [版本号该看哪里？](#版本号该看哪里) 做自检。

---

## 3. 更新到最新版本

适用于：OpenCode 里没有 `run_forge_autopilot`、或 `sdk_forge.__version__` 低于 [最新 Release](https://github.com/weininghui/sdk-forge/releases)。

> **注意：** 只 `git pull` 不够，必须 **`pip install -e .`** 并 **重启 OpenCode**（MCP 是子进程，不会热更新）。

### 路径 A — 全局插件目录安装的用户

将 `v5.1.0` 换成 GitHub 上最新 tag。

**Windows PowerShell：**

```powershell
$PluginDir = "$env:APPDATA\OpenCode\plugins\sdk-forge"
cd $PluginDir

# 若是 git 仓库
git fetch --tags
git checkout v5.1.0

# 若不是 git：删除目录后按「方式 B 首次安装」重新克隆

pip install -r requirements.txt
pip install -e . --force-reinstall

# 更新 Agent 提示词
Copy-Item -Force ".opencode\agents\forge*.md" "$env:APPDATA\OpenCode\agents\"

# 完全重启 OpenCode
```

**Linux / macOS：**

```bash
PLUGIN_DIR="$HOME/.config/opencode/plugins/sdk-forge"
cd "$PLUGIN_DIR"
git fetch --tags
git checkout v5.1.0
pip install -r requirements.txt
pip install -e . --force-reinstall
cp .opencode/agents/forge*.md "$HOME/.config/opencode/agents/"
# 重启 OpenCode
```

### 路径 B — 直接打开 SDK Forge 仓库的用户

```bash
cd /path/to/sdk-forge
git fetch --tags
git checkout v5.1.0
pip install -r requirements.txt
pip install -e . --force-reinstall
# 重启 OpenCode 或重新打开项目
```

### 路径 C — 从本地开发目录同步到 OpenCode 插件目录

开发在 `E:\vs_test\AINew\aiagent-main` 等目录，希望 OpenCode 用这份代码：

**Windows：**

```powershell
$Src = "E:\vs_test\AINew\aiagent-main"
$Dst = "$env:APPDATA\OpenCode\plugins\sdk-forge"
robocopy $Src $Dst /MIR /XD .git build .forge __pycache__ .pytest_cache
cd $Dst
pip install -e . --force-reinstall
Copy-Item -Force ".opencode\agents\forge*.md" "$env:APPDATA\OpenCode\agents\"
```

### 每次更新后 — 验证

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"
forge autopilot --help
pip show sdk-forge
```

| 检查项 | v5.2.0 预期 |
|--------|-------------|
| `sdk_forge.__version__` | `5.2.0` |
| `forge autopilot --help` | 有 `autopilot` 子命令 |
| MCP 工具 | `run_forge_autopilot`、`draft_golden_cases`、`record_agent_run` + `review_verdict` |
| `pip show` Version | `5.2.0`（`pip install -e .` 之后） |

若版本仍不对：

1. 看 `pip show` 里 `Editable project location` 是否指向你刚更新的目录。
2. 在该目录执行 `pip install -e . --force-reinstall`。
3. **完全重启 OpenCode**。

---

## 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| AI 说 forge 是 `4.0.0` | 旧的 `pyproject.toml` 或未重装 pip 包 | 更新代码 + `pip install -e . --force-reinstall` |
| MCP 没有 `run_forge_autopilot` | 插件目录未更新到 v5.1 | 见 [第 3 节](#3-更新到最新版本) |
| `forge` 没有 `autopilot` | CLI 未从新代码重装 | 在插件目录 `pip install -e .` |
| 只在某个项目能用 | 仅项目级 `plugin.yaml` | 改用 [方式 B 全局插件目录](#方式-b--全局插件目录任意项目都能用) |
| `git pull` 后功能没变 | MCP 子进程未重启 | 退出 OpenCode 再打开 |

---

## 相关文档

- [REGISTER_AGENT.md](REGISTER_AGENT.md) — Agent 下拉框、`opencode.json`、Skill
- [README.zh-CN.md](../README.zh-CN.md) — 功能与 CLI 说明
- [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) — 生产级流程
