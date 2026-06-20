# Background Delegation (v5.5+) / 后台委托模式

SDK Forge v5.5+ adds **background delegation**. v5.6 adds **session navigation** and **CLI runtime**.

## Delegation modes

| Mode | When to use |
|------|-------------|
| `omo` | oh-my-openagent installed (default production) |
| `cli` | Spawn `opencode run --agent forge-*` subprocesses (no OMO UI) |
| `inline` | Sync `task(subagent_type=...)` fallback (v5.3) |

## OMO-native task() — required for clickable sub-sessions (v5.7)

oh-my-openagent publishes `metadata.sessionId` via `publishToolMetadata` when you use its **`task`** tool correctly:

```
task(
  subagent_type="forge-enrich",
  load_skills=[],
  description="Enrich batch 0",
  prompt="...",
  run_in_background=true,
)
register_from_omo_task_result(omo_result_text=result, agent="forge-enrich", ...)
```

**Do NOT use** `task(agent=...)` or `title=` — OpenCode native task skips OMO metadata; TUI entries won't be clickable.

`call_omo_agent` is only for `explore` / `librarian`. Forge sub-agents use `task(subagent_type="forge-*")`.

```yaml
delegation_mode: omo          # omo | cli | inline
delegation_concurrency: 4
```

## Sub-agent navigation (v5.6)

OpenCode **TUI** (not all GUI builds) supports parent/child session keys:

- **Down** — enter first child sub-agent session
- **Right / Left** — cycle child sessions
- **Up** — return to forge primary

When OMO returns a `sessionId`, primary forge should call:

```
update_forge_delegation_session(task_id=..., session_id=ses_xxx, project_dir=...)
```

Then `poll_forge_delegations` returns `navigation.pending[].cli_resume`:

```
opencode run --session ses_xxx --continue
```

Or list sessions: `opencode session list`

## MCP tools

| Tool | Role |
|------|------|
| `get_delegation_plan` | Dispatch list |
| `register_forge_delegation` | Track task_id (+ optional session_id) |
| `update_forge_delegation_session` | Bind session_id after OMO dispatch |
| `dispatch_forge_delegate` | CLI mode: background `opencode run` |
| `poll_forge_delegations` | Pending + navigation hints |
| `advance_forge_workflow` | Step workflow |

## OMO setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/merge-omo-forge-agents.ps1
```

## OMO open-source reference (借鉴)

Upstream: [code-yeongyu/oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent)

SDK Forge **does not fork OMO** — it reuses OMO as the **delegation runtime** and mirrors key contracts:

| OMO source (packages/omo-opencode) | What it does | SDK Forge equivalent |
|-----------------------------------|--------------|----------------------|
| `tools/delegate-task/` | `task(subagent_type, run_in_background, load_skills=[])` | `forge.md` dispatch loop |
| `tools/call-omo-agent/` | `call_omo_agent` for explore/librarian | forge primary (research only) |
| `features/tool-metadata-store/publish-tool-metadata.ts` | `metadata.sessionId` → clickable child session | `register_from_omo_task_result` |
| `features/tool-metadata-store/task-metadata-contract.ts` | `<task_metadata>` block in tool output | `parse_omo_task_result_impl` (v5.8+) |
| `tools/background-task/` | `background_output(task_id)` poll + notify | forge waits for `<system-reminder>` then `background_output` |
| `features/background-manager/` | Parallel spawn + concurrency | `.forge.yaml` `delegation_concurrency` + OMO `background_task.defaultConcurrency` |
| `plugin-handlers/tool-config-handler.ts` | Primary agents get `task: allow` | `oh-my-openagent.json` forge `permission.task` |

**OMO-native sub-agent loop** (same as Sisyphus):

1. Fire all `task(..., run_in_background=true)` in one turn
2. Do **not** call `background_output` immediately — wait for system notification
3. `background_output(task_id=..., block=false)` → parse Session ID
4. `get_subagent_dashboard` → user sees live_preview + jump hints

**Sub-agent observability (v5.8):**

| Tool | Role |
|------|------|
| `get_subagent_dashboard` | session_id + live_preview + GUI/TUI/CLI jump hints |
| `peek_subagent_session` | Single session activity |
| `sync_delegation_sessions` | Auto-bind from `opencode session list` |

---

# 后台委托模式（简体中文）

## v5.6 子 agent 可观测性

GUI 里工具调用**不一定可点击**进子窗口——这是 OpenCode/OMO UI 限制。v5.6 提供：

1. **`update_forge_delegation_session`** — 绑定 `ses_xxx` 后用户可 `opencode session list` 或 TUI **Down** 进入
2. **`poll_forge_delegations`** — 返回 `navigation` 块（task_id、session_id、快捷键提示）
3. **`delegation_mode: cli`** — 用 `dispatch_forge_delegate` 后台跑 `opencode run`，不依赖 OMO 分窗

## 配置

```yaml
delegation_mode: omo   # 或 cli / inline
delegation_concurrency: 4
multi_agent_batch_size: auto
```

## 使用

选 **forge** primary，输入 SDK 路径。编排器派发后会汇报 `navigation` 信息，便于你手动进入子 session。
