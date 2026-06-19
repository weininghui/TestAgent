# Migrate from sdk-test-forge / TestAgent to SDK Forge (v5.4)

**English** | [简体中文](#简体中文)

## English

v5.4 renames the project to **SDK Forge**:

| Item | Old | New |
|------|-----|-----|
| GitHub repo | `weininghui/TestAgent` | `weininghui/sdk-forge` |
| OpenCode plugin ID | `sdk-test-forge` | `sdk-forge` |
| Plugin directory | `plugins/sdk-test-forge` | `plugins/sdk-forge` |
| pip package | `sdk-test-forge` | `sdk-forge` |
| Python module | `sdk_forge` | `sdk_forge` (unchanged) |
| CLI / Agent | `forge` | `forge` (unchanged) |

### Windows (OpenCode global plugin)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/migrate-rename-sdk-forge.ps1
```

Or manually:

```powershell
# 1. Move plugin directory
$Old = "$env:APPDATA\OpenCode\plugins\sdk-test-forge"
$New = "$env:APPDATA\OpenCode\plugins\sdk-forge"
if (Test-Path $Old) { Move-Item $Old $New -Force }

# 2. Update git remote
cd $New
git remote set-url origin https://github.com/weininghui/sdk-forge.git
git fetch --tags
git checkout v5.4.0

# 3. Reinstall pip package
pip uninstall sdk-test-forge -y
pip install -e .

# 4. Restart OpenCode — MCP list should show sdk-forge
```

### Manual MCP config

If you configured MCP manually in `opencode.json`, rename the key:

```json
"sdk-forge": {
  "command": ["python", ".../plugins/sdk-forge/run_mcp.py"]
}
```

### Dev clone

```bash
git remote set-url origin https://github.com/weininghui/sdk-forge.git
```

GitHub redirects `TestAgent` URLs for a while, but update remotes promptly.

---

## 简体中文

v5.4 将项目统一命名为 **SDK Forge**：

| 项 | 旧 | 新 |
|----|-----|-----|
| GitHub 仓库 | `weininghui/TestAgent` | `weininghui/sdk-forge` |
| OpenCode 插件 ID | `sdk-test-forge` | `sdk-forge` |
| 插件目录 | `plugins/sdk-test-forge` | `plugins/sdk-forge` |
| pip 包 | `sdk-test-forge` | `sdk-forge` |
| Python 模块 | `sdk_forge` | `sdk_forge`（不变） |
| CLI / Agent | `forge` | `forge`（不变） |

### Windows 一键迁移

```powershell
powershell -ExecutionPolicy Bypass -File scripts/migrate-rename-sdk-forge.ps1
```

### 手动 MCP 配置

若在 `opencode.json` 里手动配置过 MCP，请将 JSON 键名 `sdk-test-forge` 改为 `sdk-forge`。

迁移后**完全退出并重启 OpenCode**。
