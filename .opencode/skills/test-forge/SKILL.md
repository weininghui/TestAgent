---
name: test-forge
description: Scan C/C++ SDK headers, generate GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill

## Workflow (v3.1)

### Step 0: Doctor (recommended)

```
forge_doctor
```

Or CLI: `forge doctor` — verify cmake, compiler, caches before long compile loops.

### Step 1: Init project (new SDKs)

```
init_forge_project:
  target_dir: /path/to/my_sdk_tests
  sdk_root: /path/to/sdk
```

Creates `tests/`, `build/`, `.forge.yaml`. Edit config with probe results.

### Step 2: Probe SDK

```
probe_sdk: /path/to/sdk
```

Or CLI: `forge probe /path/to/sdk`

### Step 3: Scan Headers

```
scan_headers:
  sdk_root: /path/to/sdk
  include_dirs: [...]
  use_cache: true
```

Review `conditional: true` symbols — they may need `-D` flags to test.

### Step 4: Mock Generation (optional)

If scan shows `virtual: true` methods:

```
generate_mocks:
  sdk_root: /path/to/sdk
  class_name: Calculator
```

### Step 5–6: Analyze, Design, Write Tests

Cover normal, boundary, error, resource-pairing scenarios. Write `.cpp` under `tests/`.

### Step 7: Build (one-shot)

```
build_tests:
  project_dir: /path/to/my_sdk_tests
```

Or step-by-step:

```
compile_tests:
  source_dir: /path/to/tests
  build_dir: /path/to/build
  use_config: true
```

`compile_tests` auto-loads `.forge.yaml` / `.forge.json` from project root.

**Failure recovery:** read `hints` first, then `output`.

### Step 8: Run (if not using build_tests)

```
run_tests: /path/to/build
```

### Step 9: Coverage (optional, Linux)

Set `coverage: true` in `.forge.yaml`, then `collect_coverage`.

### Step 10: Report

Summarize passed/failed/skipped and coverage percentage if collected.

## `.forge.yaml` keys

- `sdk_root`, `tests_dir`, `build_dir`
- `sdk_include_dirs`, `sdk_lib_dirs`, `link_libraries`
- `pkg_config_packages`, `cmake_prefix_path`, `find_packages`
- `gtest_source`, `coverage`, `coverage_tool`

See `examples/forge_test_sdk/.forge.json`.

## Rules

1. Run `forge_doctor` on unfamiliar machines
2. Probe and scan before guessing SDK layout
3. Prefer `build_tests` when `.forge.yaml` exists
4. Portable C++17 in tests

## Samples

- [`test_sdk/`](../../test_sdk/) — C library
- [`test_sdk_cpp/`](../../test_sdk_cpp/) — C++ with virtual methods and pkg-config
- [`examples/forge_test_sdk/`](../../examples/forge_test_sdk/) — sample `.forge.json`
