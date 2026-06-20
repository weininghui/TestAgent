# Release Notes — v5.6.0

Sub-agent **observability** — session binding, navigation hints, and CLI delegation runtime.

## Highlights

| Feature | Description |
|---------|-------------|
| **Session binding** | `update_forge_delegation_session(task_id, session_id)` |
| **Navigation hints** | `poll_forge_delegations` → `navigation.pending[].cli_resume` |
| **CLI runtime** | `delegation_mode: cli` + `dispatch_forge_delegate` |
| **Forge protocol** | Primary reports task_id / session_id after each dispatch |

## Why v5.6

v5.5 added background delegation protocol but OpenCode GUI may not show clickable sub-agent windows. v5.6 lets forge **record session IDs** and tell users how to navigate (TUI Down/Up, `opencode session list`, `opencode run --session ses_xxx --continue`).

## New MCP tools

- `update_forge_delegation_session`
- `dispatch_forge_delegate`

## Config

```yaml
delegation_mode: omo   # default | cli | inline
```

See [docs/DELEGATION.md](../DELEGATION.md).
