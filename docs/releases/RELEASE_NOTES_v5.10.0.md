# Release Notes — v5.10.0

**Single delegation path:** OpenCode/OMO `task()` tool call only.

## Removed

| Removed | Replacement |
|---------|-------------|
| `delegation_mode: cli` | `task()` tool call |
| `delegation_mode: inline` | `task()` tool call |
| MCP `dispatch_forge_delegate` | `task()` tool call |
| `sdk_forge/delegate_runner.py` | — |
| `call_omo_agent` on forge | `task(subagent_type=...)` |

## Kept

- `get_task_dispatch_plan` — returns `task` tool-call args
- `get_subagent_dashboard` — session binding + live preview
- `register_from_omo_task_result` — parse OMO output
- OMO config: forge `task: allow`, `call_omo_agent: deny`

## Why

v5.9 proved GUI Task cards work when forge uses native **tool call** on `task`. Alternate paths (CLI subprocess, inline sync, `call_omo_agent`) were redundant and confused models.

Reference: [OpenCode task tool](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/tool/task.ts)

## Upgrade

```powershell
cd $env:APPDATA\OpenCode\plugins\sdk-forge
git fetch --tags; git checkout v5.10.0
pip install -e . -q
# Fully restart OpenCode
```

Remove from `.forge.yaml` if present:

```yaml
# delegation_mode: omo   # no longer needed
```
