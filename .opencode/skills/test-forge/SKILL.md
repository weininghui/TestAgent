---
name: test-forge
description: Scan C/C++ SDK headers, generate GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill (v3.3)

## Workflow

### 1. Doctor + Scan + Plan

```
forge_doctor
scan_headers: { sdk_root: /path/to/sdk }
suggest_test_plan: { scan_json: ..., project_dir: ./my_tests }
```

### 2. Scaffold (new in v3.3)

```
generate_test_skeleton:
  output_dir: ./my_tests/tests
  plan_json: <from suggest_test_plan>
```

Or CLI: `forge scaffold /path/to/sdk --output tests/`

Edit generated TODO/EXPECT sections only where needed.

### 3. Smart Build + Learn

```
build_tests:
  project_dir: ./my_tests
  max_retries: 3
  auto_fix_config: true
```

Successful builds save compile params to `.forge/cache/learned/`.

### 4. Analyze Failures (if test_failures)

```
analyze_test_failures: { build_dir: ./my_tests/build }
```

Apply `review_assertion` actions via Edit — do not blindly rewrite all tests.

### 5. Report + Session

```
forge_report: { project_dir: ./my_tests }
get_session_context: { project_dir: ./my_tests }
```

## CLI map

| MCP | CLI |
|-----|-----|
| generate_test_skeleton | `forge scaffold` |
| analyze_test_failures | `forge analyze` |
| get_session_context | (MCP only) |
| get_learned_config | (MCP only) |

## Rules

1. scaffold before freehand coding
2. build_tests with retry before manual compile loops
3. analyze_test_failures before guessing assertion fixes
4. get_session_context when resuming a prior session
