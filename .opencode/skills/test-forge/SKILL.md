---
name: test-forge
description: Scan C/C++ SDK headers, generate GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill (v3.6)

## Workflow

### 1. Doctor + Scan + Plan

```
forge_doctor
scan_headers: { sdk_root: /path/to/sdk }
suggest_test_plan: { scan_json: ..., project_dir: ./my_tests, max_targets: 20 }
```

### 2. Scaffold + Gap

```
generate_test_skeleton: { output_dir: ./my_tests/tests, plan_json: ... }
analyze_plan_gap: { project_dir: ./my_tests }
```

### 3. Build — report auto-generated

```
build_tests: { project_dir: ./my_tests, max_retries: 3, auto_fix_config: true }
```

**No manual `forge_report` needed.** After `build_tests`, the JSON response includes:

- `html_path` — open in browser (default `.forge/cache/report.html`)
- `report.summary` — passed/failed counts

Tell the user to open `html_path`. `get_session_context` also returns `last_report_html`.

Set `auto_report: false` in `.forge.yaml` to disable auto-generation.

### 4. Test failures (confirmation gate)

```
analyze_test_failures: { build_dir: ./my_tests/build }
propose_test_fixes: { build_dir: ./my_tests/build, project_dir: ./my_tests }
apply_test_fixes: { project_dir: ./my_tests, confirm: true }
```

Then re-run `build_tests` — a fresh HTML report is generated automatically.

### 5. Optional manual report

Only if you need to regenerate or add extra notes:

```
forge_report: { project_dir: ./my_tests, output_format: html, agent_summary: "..." }
```

## Optional

- `sanitizer: asan` in `.forge.yaml` (Linux/clang)
- `get_compile_commands` after compile for libclang/IDE
