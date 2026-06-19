# Release Notes — v5.1.0

**Hands-Off Autopilot** — provide an SDK path and let the orchestrator drive enrich retries, review, production build, and optional golden snapshot.

## Highlights

| Feature | Description |
|---------|-------------|
| **`forge autopilot`** | One command / MCP `run_forge_autopilot` — init, env, scan, scaffold, then `next_actions` for Agent |
| **Assertion loop** | After enrich batches complete, assertion gate auto-retries weak files up to `max_enrich_rounds` |
| **Golden snapshot** | `forge golden snapshot --confirm` extracts `EXPECT_EQ(call, N)` from test sources into `.forge/golden.yaml` |
| **`merge_ready`** | Orchestration reports when build passed and no pending actions remain |

## Quick start

```bash
forge autopilot ./examples/test_sdk_cpp --profile production
```

OpenCode Agent: call `run_forge_autopilot(sdk_root=..., profile=production)` then execute returned `next_actions` via `task()`.

## Configuration (`.forge.yaml`)

```yaml
max_enrich_rounds: 3          # default 1 preserves v5.0 single-round behavior
autopilot_profile: production
auto_golden_snapshot: true
```

## Backward compatibility

- Default `max_enrich_rounds: 1` — same as v5.0 when not using autopilot or production preset
- Existing MCP/CLI tools unchanged; autopilot is additive
- `golden snapshot` defaults to merge mode; existing cases are not overwritten

## v5.2 (planned)

- `forge-oracle` subagent for golden drafts from headers
- Runtime golden capture (test harness instrumentation)
- Windows coverage gate alternative
