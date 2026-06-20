# Migrate to v5.11 — Layered `sdk_forge` Package

**English** | [简体中文](#简体中文)

## English

v5.11 reorganizes `sdk_forge` into layered subpackages and **removes all root import shims**.

### Layout

```
sdk_forge/
  cli.py | __init__.py | __main__.py          # entry points only
  domain/ | orchestration/ | delegation/ | pipeline/ | infra/
```

### Import migration

| Old (removed) | New |
|---------------|-----|
| `sdk_forge.scan` | `sdk_forge.pipeline.scan` |
| `sdk_forge.build` | `sdk_forge.pipeline.build` |
| `sdk_forge.delegation` | `sdk_forge.delegation.core` |
| `sdk_forge.orchestration` | `sdk_forge.orchestration.core` |
| `sdk_forge.pipeline` | `sdk_forge.pipeline.core` |
| `sdk_forge.task_dispatch` | `sdk_forge.delegation.task_dispatch` |
| `sdk_forge.session_nav` | `sdk_forge.delegation.session_nav` |
| `sdk_forge.gtest` | `sdk_forge.infra.gtest` |
| `sdk_forge.config` | `sdk_forge.infra.config` |
| `sdk_forge.util` | `sdk_forge.domain.util` |

### New in v5.11

- **`sdk_forge/delegation/health.py`** — sub-agent timeout / stall detection
- MCP **`check_subagent_health`**, **`recover_stalled_subagent`**
- Config **`delegation_stale_sec`** (default 900)

### Upgrade

```powershell
cd $env:APPDATA\OpenCode\plugins\sdk-forge
git fetch --tags
git checkout v5.11.0
pip install -e . -q
# Fully restart OpenCode
python -c "import sdk_forge; print(sdk_forge.__version__)"   # 5.11.0
```

Or: `scripts\update-opencode-plugin.ps1 -Ref v5.11.0`

Full release notes: [RELEASE_NOTES_v5.11.0.md](releases/RELEASE_NOTES_v5.11.0.md)

---

## 简体中文

v5.11 将 `sdk_forge` 重组为分层子包，并 **移除所有根目录 import shim**。

### 目录结构

```
sdk_forge/
  cli.py | __init__.py | __main__.py          # 仅入口
  domain/ | orchestration/ | delegation/ | pipeline/ | infra/
```

### Import 迁移

| 旧（已移除） | 新 |
|-------------|-----|
| `sdk_forge.scan` | `sdk_forge.pipeline.scan` |
| `sdk_forge.build` | `sdk_forge.pipeline.build` |
| `sdk_forge.delegation` | `sdk_forge.delegation.core` |
| `sdk_forge.orchestration` | `sdk_forge.orchestration.core` |
| `sdk_forge.pipeline` | `sdk_forge.pipeline.core` |
| `sdk_forge.task_dispatch` | `sdk_forge.delegation.task_dispatch` |
| `sdk_forge.session_nav` | `sdk_forge.delegation.session_nav` |
| `sdk_forge.gtest` | `sdk_forge.infra.gtest` |
| `sdk_forge.config` | `sdk_forge.infra.config` |
| `sdk_forge.util` | `sdk_forge.domain.util` |

### v5.11 新增

- **`sdk_forge/delegation/health.py`** — 子 agent 超时 / 停滞检测
- MCP **`check_subagent_health`**、**`recover_stalled_subagent`**
- 配置 **`delegation_stale_sec`**（默认 900 秒）

### 升级

```powershell
cd $env:APPDATA\OpenCode\plugins\sdk-forge
git fetch --tags
git checkout v5.11.0
pip install -e . -q
# 完全重启 OpenCode
python -c "import sdk_forge; print(sdk_forge.__version__)"   # 5.11.0
```

或：`scripts\update-opencode-plugin.ps1 -Ref v5.11.0`

完整说明：[RELEASE_NOTES_v5.11.0.md](releases/RELEASE_NOTES_v5.11.0.md)
