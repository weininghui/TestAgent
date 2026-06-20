---
name: sdk-forge
description: Scan C/C++ SDK headers, generate smart GTest code, compile and run tests with SDK linking (SDK Forge)
---

# SDK Forge Skill

## Version — do not guess

When the user asks **forge / SDK Forge version**:

1. Call MCP **`forge_doctor`**
2. Read top-level **`forge_version`** or check **`sdk_test_forge`** in `checks[]`
3. **Do not** use this skill title, old release notes, or sanitizer hint text as the version

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"
```

## Communication / 交流语言

- **Reply in Chinese by default** when talking to the user.
- Switch to English only when the user explicitly asks in the chat.

## Autopilot (preferred)

Select **forge** orchestrator. Start with **`run_forge_autopilot`** then **background delegation** (v5.5):

```
run_forge_autopilot(sdk_root=..., profile=production)
plan = get_delegation_plan(project_dir=...)
# OMO: task(run_in_background=true/false, subagent_type=..., prompt=..., title=...)
# register_forge_delegation → update_forge_delegation_session (if sessionId) → background_output
# poll_forge_delegations → navigation.pending (TUI Down / opencode session list)
```

## Multi-Agent (v5.5 background)

Orchestrator delegates via OMO `task()` with explicit `run_in_background`:

```
get_delegation_plan → dispatch background_actions (parallel enrich/scan)
→ foreground_actions (env/scaffold/review/build)
→ background_output(task_id) → advance_forge_workflow
```

Configure in `.forge.yaml`:

```yaml
delegation_mode: omo
delegation_concurrency: 4
multi_agent_batch_size: auto
scan_batch_size: 8
auto_oracle_draft: true
max_enrich_rounds: 3
```

See [docs/DELEGATION.md](../../docs/DELEGATION.md).

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
