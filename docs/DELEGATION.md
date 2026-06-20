# Sub-agent delegation — OpenCode `task()` only (v5.10)

Forge dispatches sub-agents **only** via OpenCode/OMO **`task` tool call** (function calling). This renders **Explore-style Task cards** in the GUI.

Reference: [anomalyco/opencode](https://github.com/anomalyco/opencode) — `packages/opencode/src/tool/task.ts`

## Dispatch loop

```
sdk-forge_get_task_dispatch_plan(project_dir=...)
→ tool-call task(subagent_type=..., load_skills=[], description=..., prompt=..., run_in_background=...)
→ sdk-forge_register_from_omo_task_result(...)
→ sdk-forge_sync_delegation_sessions + sdk-forge_get_subagent_dashboard
→ background_output(task_id) when notified
→ sdk-forge_advance_forge_workflow(...)
```

**Critical:** Writing `task(...)` in a markdown code block does **not** execute. You must use a native **tool call**.

## Forbidden

| Do not use | Why |
|------------|-----|
| `call_omo_agent` | No GUI Task card; removed from forge path |
| `task(agent=...)` | Wrong parameter — use `subagent_type` |
| `title=` | Use `description=` (GUI card label) |
| `dispatch_forge_delegate` | Removed in v5.10 |
| `delegation_mode: cli` / `inline` | Removed — always `task()` |

## Config (`.forge.yaml`)

```yaml
delegation_concurrency: 4
multi_agent_batch_size: auto
```

## MCP tools

| Tool | Role |
|------|------|
| `get_task_dispatch_plan` | Executable `task()` args for each next_action |
| `validate_forge_delegation_tool` | Reject bad syntax in agent text |
| `register_from_omo_task_result` | Parse OMO output + bind session_id |
| `get_subagent_dashboard` | live_preview + jump hints |
| `poll_forge_delegations` | Pending/completed + navigation |
| `advance_forge_workflow` | Step workflow |

## OMO setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/merge-omo-forge-agents.ps1
```

Forge OMO permissions: `task: allow`, `call_omo_agent: deny`

## Enter sub-agent chat

1. **GUI Task card** — click Explore-style card
2. **Session sidebar** — `(@forge-xxx subagent)` or `ses_xxx`
3. **TUI** — Down into child, Up to parent
4. **CLI** — `opencode run --session ses_xxx --continue`

---

# 简体中文

Forge **只**通过 OpenCode **`task` 工具调用**派发子 agent，GUI 显示 **Task 卡片**。

- **禁止**在回复里写 `task(...)` 代码块 — 必须用 tool call
- **禁止** `call_omo_agent`、`delegation_mode: cli/inline`（v5.10 已移除）
- 配置只需 `delegation_concurrency`，无需 `delegation_mode`
