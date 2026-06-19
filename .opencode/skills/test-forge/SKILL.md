---
name: test-forge
description: Scan C/C++ SDK headers, generate smart GTest code, compile and run tests with SDK linking (SDK Test Forge v5.1)
---

# SDK Test Forge Skill (v5.1.0)

## Version — do not guess

When the user asks **forge / Test Forge version**:

1. Call MCP **`forge_doctor`**
2. Read top-level **`forge_version`** or check **`sdk_test_forge`** in `checks[]`
3. **Do not** use this skill title, old release notes, or sanitizer hint text as the version

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"
```

## Communication / 交流语言

- **Reply in Chinese by default** when talking to the user.
- Switch to English only when the user explicitly asks in the chat.

## Autopilot (v5.1, preferred)

Select **forge** orchestrator. Start with **`run_forge_autopilot`** or **`get_session_context`**:

```
run_forge_autopilot(sdk_root=..., profile=production)
→ execute orchestration.next_actions via task()
→ assertion gate auto-retries enrich; then forge-review → forge-build
```

## Multi-Agent (v4.6+)

Orchestrator delegates via OpenCode `task()`:

```
get_session_context → read orchestration.next_actions
task(agent="forge-env") → task(agent="forge-scan") → task(agent="forge-scaffold")
→ parallel task(agent="forge-enrich", batch=...) → task(agent="forge-review") → task(agent="forge-build")
record_agent_run after each sub-agent
```

Configure parallel enrich batch size in `.forge.yaml`:

```yaml
multi_agent_batch_size: 4   # 1 = serial enrich batches
max_enrich_rounds: 3          # assertion-driven enrich retries (v5.1)
```

## Single-Agent Fallback

When sub-agents unavailable, run MCP tools directly:

### 1. Environment + Scan + Plan

```
ensure_forge_environment
scan_headers: { sdk_root: /path/to/sdk }
suggest_test_plan: { scan_json: ..., project_dir: ./my_tests, max_targets: 20 }
```

### 2. Scaffold + Enrich

```
generate_test_skeleton: { fidelity: smart, overwrite: true, ... }
enrich_test_cases: { project_dir: ..., test_files: ... }
analyze_assertion_quality
```

### 3. Build + Report

```
build_tests: { project_dir: ..., profile: production }
```

Only claim all tests passed when `status: ok` and `run.passed` is set. Open `html_path` for the user.
