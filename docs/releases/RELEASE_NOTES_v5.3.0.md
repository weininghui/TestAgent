# Release Notes — v5.3.0

Multi-agent speed: Autopilot step loop, parallel scan, dynamic enrich batch, oracle pipeline.

## Highlights

| Feature | Description |
|---------|-------------|
| **`advance_forge_workflow`** | Record sub-agent + return next step in one call — fewer primary Agent decisions |
| **Parallel scan** | `scan_batch_size: 8` splits headers into parallel `forge-scan` batches, auto-merge plan |
| **Dynamic batch** | `multi_agent_batch_size: auto` scales enrich parallelism by file count |
| **Oracle pipeline** | `auto_oracle_draft: true` runs forge-oracle before first enrich (production) |
| **Stage timeline** | `orchestration.stage_timeline` from `agent_runs` for debugging |

## Primary forge loop (v5.3)

```
run_forge_autopilot(profile=production)
while status == "needs_agent":
  task(agent=next_agent, prompt=prompt_hint)
  advance_forge_workflow(last_agent=..., last_status=ok)
```

## Config (production preset)

```yaml
multi_agent_batch_size: auto
scan_batch_size: 8
auto_oracle_draft: true
max_enrich_rounds: 3
max_agent_retries: 2
```

## Upgrade

```powershell
cd $env:APPDATA\OpenCode\plugins\sdk-test-forge
git fetch --tags; git checkout v5.3.0
pip install -e .
```

Restart OpenCode. Verify: `python -c "import sdk_forge; print(sdk_forge.__version__)"` → `5.3.0`.

## Backward compatibility

- `scan_batch_size: 0` (default in non-production) keeps single forge-scan
- `multi_agent_batch_size: 4` still works; `auto` is opt-in via production preset
- `advance_forge_workflow` is additive; `record_agent_run` still supported
