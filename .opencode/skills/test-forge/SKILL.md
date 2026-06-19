---
name: test-forge
description: Scan C/C++ SDK headers, generate GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill (v3.4)

## Workflow

### 1. Doctor + Scan + Plan

```
forge_doctor
scan_headers: { sdk_root: /path/to/sdk }
suggest_test_plan: { scan_json: ..., project_dir: ./my_tests }
```

### 2. Scaffold + Gap

```
generate_test_skeleton: { output_dir: ./my_tests/tests, plan_json: ... }
analyze_plan_gap: { project_dir: ./my_tests }
```

Fill missing targets/scenarios reported by gap analysis.

### 3. Smart Build + Learn

```
build_tests: { project_dir: ./my_tests, max_retries: 3, auto_fix_config: true }
```

### 4. Test failures (confirmation gate)

```
analyze_test_failures: { build_dir: ./my_tests/build }
propose_test_fixes: { build_dir: ./my_tests/build, project_dir: ./my_tests }
```

Show proposals to user; apply with Edit only after confirmation. Never auto-edit source.

### 5. Report + Session

```
forge_report: { project_dir: ./my_tests }
get_session_context: { project_dir: ./my_tests }
```

## Optional

- `sanitizer: asan` in `.forge.yaml` (Linux/clang)
- `get_compile_commands` after compile for libclang/IDE
