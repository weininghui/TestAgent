---
name: test-forge
description: Scan C/C++ SDK headers, generate GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill

## Workflow (v3.2 — Agent Autonomy)

### Step 0: Doctor

```
forge_doctor
```

### Step 1: Scan + Plan

```
scan_headers: { sdk_root: /path/to/sdk }
suggest_test_plan: { scan_json: <scan result> }
```

Review `targets[].scenarios` and `needs_mock` / `conditional` flags.

### Step 2: Probe + Init (if new project)

```
init_forge_project: { target_dir: ./my_tests, sdk_root: /path/to/sdk }
probe_sdk: { sdk_root: /path/to/sdk }
```

Merge probe suggestions into `.forge.yaml`.

### Step 3: Mocks (if plan shows needs_mock)

```
generate_mocks: { sdk_root: /path/to/sdk, class_name: MyClass }
```

### Step 4: Write Tests

Use plan scenarios as checklist. Write `.cpp` under `tests/`.

### Step 5: Smart Build (with retry)

```
build_tests:
  project_dir: ./my_tests
  max_retries: 3
  auto_fix_config: true
```

On failure inspect `attempts[].actions_applied` and `compile.actions`.

### Step 6: Report

```
forge_report: { project_dir: ./my_tests }
```

Paste `markdown` into PR or chat summary.

## compile_tests actions reference

When not using `build_tests`, read `actions` from `compile_tests` errors:

| type | Config key |
|------|------------|
| merge_link_libraries | link_libraries |
| merge_sdk_include_dirs | sdk_include_dirs |
| merge_sdk_lib_dirs | sdk_lib_dirs |
| merge_cmake_prefix_path | cmake_prefix_path |
| merge_pkg_config_packages | pkg_config_packages |

## CLI equivalents

| MCP | CLI |
|-----|-----|
| suggest_test_plan | `forge plan <sdk>` |
| build_tests | `forge build --retry 3 --auto-fix-config` |
| forge_report | `forge report --project-dir .` |

## Rules

1. Always `suggest_test_plan` before writing tests
2. Prefer `build_tests(max_retries=3)` over manual compile loops
3. Read `actions` before `hints` on compile failure
4. Portable C++17 in tests

## Samples

- [`test_sdk/`](../../test_sdk/) — C library
- [`test_sdk_cpp/`](../../test_sdk_cpp/) — C++ virtual + pkg-config
- [`examples/forge_test_sdk/`](../../examples/forge_test_sdk/) — `.forge.json`
