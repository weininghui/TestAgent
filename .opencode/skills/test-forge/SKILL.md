---
name: test-forge
description: Scan C/C++ SDK headers, generate smart GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill (v4.5.2)

## Communication / 交流语言

- **Reply in Chinese by default** when talking to the user.
- Switch to English only when the user explicitly asks in the chat.

## Autonomous environment (Agent-first)

Always start with:

```
ensure_forge_environment: {}
```

This runs doctor and **auto-installs** MSVC/MinGW/g++ via winget/apt when missing. Do not ask the user to install Build Tools manually unless auto-install fails.

Fallback: `setup_cxx_toolchain: { agent_mode: true, method: auto }`

## Workflow

### 1. Environment + Scan + Plan

```
ensure_forge_environment
scan_headers: { sdk_root: /path/to/sdk }
suggest_test_plan: { scan_json: ..., project_dir: ./my_tests, max_targets: 20 }
```

### 2. Smart Scaffold + Enrich

```
generate_test_skeleton: { fidelity: smart, overwrite: true, ... }
enrich_test_cases: { project_dir: ./my_tests }
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
