# Release Notes — v4.6.0 (Multi-Agent Orchestration)

Split the v4.5 single-agent pipeline into **1 orchestrator + 5 subagents** with **parallel enrich batches**.

## Highlights

### Multi-Agent architecture
- **forge** (`mode: primary`) — reads `orchestration.next_actions`, dispatches via OpenCode `task()`
- **forge-env** — `ensure_forge_environment`
- **forge-scan** — `scan_headers` + `suggest_test_plan`
- **forge-scaffold** — smart skeleton + quality check
- **forge-enrich** — batch AGENT marker completion (**parallel** when `multi_agent_batch_size > 1`)
- **forge-build** — compile, run, fix loop

### Orchestration MCP
- `get_session_context` → `orchestration.enrich_batches`, `next_actions`
- `record_agent_run(agent, batch_id)` — workflow state for orchestrator
- `enrich_test_cases(test_files=...)` — per-batch file filter

### Configuration

```yaml
multi_agent_batch_size: 4   # 1 = serial enrich batches
```

## Upgrade from v4.5.2

```bash
pip install -e .
# Copy new .opencode/agents/forge-*.md to OpenCode plugin dir
# Optional: merge docs/examples/oh-my-openagent.multi-agent.json
forge doctor
```

Select **forge** in OpenCode — orchestrator handles sub-agent dispatch automatically.

## Fallback

If `task()` subagents unavailable, forge.md includes v4.5 single-agent MCP fallback.

---

Release title: **v4.6.0 — Multi-Agent Orchestration**
