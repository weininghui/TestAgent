# Release Notes — v5.11.0

**Layered package layout** + **sub-agent timeout recovery** for multi-agent workflows.

## Added

| Feature | Description |
|---------|-------------|
| **`sdk_forge/delegation/health.py`** | Detect `Upstream idle timeout`, tool failures, stale pending delegations |
| MCP **`check_subagent_health`** | Scan pending sub-agents for health issues |
| MCP **`recover_stalled_subagent`** | Mark error → `advance_forge_workflow` → orchestration retry via `max_agent_retries` |
| **`delegation_stale_sec`** | Optional `.forge.yaml` key (default 900s) |
| Dashboard **`health` / `issues` / `recovery`** | On `get_subagent_dashboard` and `poll_forge_delegations` |

## Changed — layered package (breaking for flat imports)

`sdk_forge/` root now keeps only entry points:

```
cli.py | __init__.py | __main__.py
domain/ | orchestration/ | delegation/ | pipeline/ | infra/
```

All root **`sys.modules` shims removed** (e.g. `sdk_forge/scan.py`).

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

## Timeout recovery playbook

When a sub-agent shows `write 失败` or **Upstream idle timeout exceeded**:

1. `get_subagent_dashboard(include_preview=true)` — check `health` / `issues`
2. `check_subagent_health(project_dir=...)`
3. `recover_stalled_subagent(task_id=..., action=retry)`
4. `get_task_dispatch_plan` → tool-call `task` for retry dispatch
5. Or manual: `opencode run --session ses_xxx --continue`

**Prevention:** split large writes; smaller enrich batches; avoid oversized parallel batches.

## Upgrade

```powershell
cd $env:APPDATA\OpenCode\plugins\sdk-forge
git fetch --tags
git checkout v5.11.0
pip install -e . -q
# Copy forge agent if using custom path:
# Copy-Item .opencode\agents\forge.md $env:USERPROFILE\.config\opencode\agents\forge.md -Force
# Fully restart OpenCode
python -c "import sdk_forge; print(sdk_forge.__version__)"   # 5.11.0
```

Or from repo:

```powershell
cd E:\vs_test\AINew\aiagent-main\scripts
.\update-opencode-plugin.ps1 -Ref v5.11.0
```

## Tests

176 passed, 5 skipped (`tests/test_mcp_server.py`).
