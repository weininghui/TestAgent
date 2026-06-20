# Release Notes — v5.2.0

Multi-agent orchestration maturity: failure recovery, review hard gate, build↔enrich loop, forge-oracle.

## Highlights

| Feature | Description |
|---------|-------------|
| **Agent error retry** | `record_agent_run(status=error)` → orchestration emits retry `next_actions` until `max_agent_retries` (default 2) |
| **Review hard gate** | `forge-review` sets `review_verdict=pass\|block`; build only when `pass` |
| **Build→enrich loop** | Build blocked on assertion/scaffold quality → clear enrich runs, increment round, re-dispatch weak files |
| **forge-oracle** | Optional subagent + `draft_golden_cases` MCP — golden drafts from plan scenarios |

## Config

```yaml
max_agent_retries: 2      # sub-agent error retries before blocked
max_enrich_rounds: 3      # unchanged from v5.1
multi_agent_batch_size: 4 # parallel enrich batch size
```

## MCP / workflow

- `record_agent_run(..., review_verdict="pass"|"block")` for forge-review
- `get_orchestration_context` → `review_verdict`, `build_blocked_status`, `max_agent_retries`
- `draft_golden_cases(project_dir, confirm=false|true)` — draft golden from `last_plan.json`

## Sub-agents (8 total)

Primary **forge** + `forge-env`, `forge-scan`, `forge-scaffold`, `forge-enrich`, `forge-review`, `forge-build`, **`forge-oracle`** (optional).

## Upgrade

```powershell
cd $env:APPDATA\OpenCode\plugins\sdk-test-forge
git fetch --tags && git checkout v5.2.0
pip install -e .
```

Restart OpenCode. Verify: `python -c "import sdk_forge; print(sdk_forge.__version__)"` → `5.2.0`.

## Backward compatibility

- Default `max_agent_retries: 2` — only affects agents that report `status=error`
- Review gate requires explicit `review_verdict=pass` before build in production flow
- v5.1 autopilot and assertion enrich loop unchanged
