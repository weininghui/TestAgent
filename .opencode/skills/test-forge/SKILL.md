---
name: test-forge
description: Scan C/C++ SDK headers, generate smart GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill (v4.6.0)

## Communication / 交流语言

- **Reply in Chinese by default** when talking to the user.
- Switch to English only when the user explicitly asks in the chat.

## Multi-Agent (v4.6, preferred)

Select **forge** orchestrator agent. It delegates via OpenCode `task()`:

```
get_session_context → read orchestration.next_actions
task(agent="forge-env") → task(agent="forge-scan") → task(agent="forge-scaffold")
→ parallel task(agent="forge-enrich", batch=...) → task(agent="forge-build")
record_agent_run after each sub-agent
```

Configure parallel enrich batch size in `.forge.yaml`:

```yaml
multi_agent_batch_size: 4   # 1 = serial enrich batches
```

## Single-Agent Fallback

When sub-agents unavailable, run MCP tools directly:

### 1. Environment + Scan + Plan

```
ensure_forge_environment
scan_headers: { sdk_root: /path/to/sdk }
suggest_test_plan: { scan_json: ..., project_dir: ./my_tests, max_targets: 20 }
```

### 2. Smart Scaffold + Enrich

```
generate_test_skeleton: { fidelity: smart, overwrite: true, ... }
enrich_test_cases: { project_dir: ./my_tests, test_files: "foo_test.cpp,bar_test.cpp" }
analyze_scaffold_quality: { project_dir: ./my_tests }
```

### 3. Build + Auto Report

```
build_tests: { project_dir: ./my_tests, max_retries: 3, auto_setup_toolchain: true }
```

Only claim all tests passed when `status: ok` and `run.passed` is set. Open `html_path` for the user.

### 4. Failures

```
analyze_test_failures → propose_test_fixes → apply_test_fixes(confirm=true)
```

## Rules

- Agent configures toolchain — not the user
- Never infer PASS from generated .cpp files alone
- Never auto-edit SDK source without confirm
