# Release Notes — v5.8.0

Sub-agent **live dashboard** — watch child agents work and open their chat sessions.

## Highlights

| Feature | Description |
|---------|-------------|
| **`get_subagent_dashboard`** | session_id + `live_preview` + GUI/TUI/CLI jump hints |
| **`peek_subagent_session`** | Export session and show latest activity |
| **`sync_delegation_sessions`** | Auto-bind pending delegations from `opencode session list` |
| **`<task_metadata>` parsing** | Align with oh-my-openagent task output contract |

## Sub-agent navigation

After forge dispatches sub-agents:

1. **`get_subagent_dashboard(project_dir=...)`** — table of agents, session IDs, live previews
2. **GUI** — OpenCode left sidebar → click session titled `(@forge-enrich subagent)`
3. **TUI** — Down to enter child session, Up to return
4. **CLI** — `opencode run --session ses_xxx --continue`

## Also in this release series (v5.5–v5.7)

- **v5.5** — OMO background delegation (`delegation_mode: omo`, `get_delegation_plan`)
- **v5.6** — Session binding, CLI runtime (`dispatch_forge_delegate`)
- **v5.7** — OMO-native `task(subagent_type, load_skills=[], description=...)`

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/merge-omo-forge-agents.ps1
```

```yaml
delegation_mode: omo
delegation_concurrency: 4
```

See [docs/DELEGATION.md](../DELEGATION.md).
