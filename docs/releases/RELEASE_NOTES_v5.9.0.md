# Release Notes — v5.9.0

Align forge with **OpenCode GUI Task cards** — same mechanism as Hephaestus dispatching Explore.

## Highlights

| Feature | Description |
|---------|-------------|
| **`get_task_dispatch_plan`** | Ready-to-invoke OMO `task()` blocks for GUI Task cards |
| **`validate_forge_delegation_tool`** | Rejects `call_omo_agent`, `task(agent=)`, `title=` |
| **forge `call_omo_agent: deny`** | OMO config matches Hephaestus — forces `task()` path |
| **Single-turn parallel fire** | All `parallel_dispatches` in one response turn |

## Why v5.9

OpenCode GUI renders **Explore-style Task cards** only for OMO **`task()`**. `call_omo_agent` always shows as plain text ("调用了 call_omo_agent"). v5.9 enforces the `task()` path end-to-end.

## Usage

```yaml
delegation_mode: omo   # or: task
delegation_concurrency: 4
```

```
plan = get_task_dispatch_plan(project_dir=...)
# Fire all plan.parallel_dispatches with task() in ONE turn
```

## Fallback modes (no GUI Task card)

- `delegation_mode: cli` — `dispatch_forge_delegate`
- `delegation_mode: inline` — sync task fallback

See [docs/DELEGATION.md](../DELEGATION.md).
