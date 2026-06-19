---
name: test-forge
description: Scan C/C++ SDK headers, generate GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill

## Workflow

### Step 0: Probe SDK (required)

```
probe_sdk: /path/to/sdk
```

Or CLI: `forge probe /path/to/sdk`

### Step 1: Scan Headers

```
scan_headers:
  sdk_root: /path/to/sdk
  include_dirs: [...]
  use_cache: true
```

Review `conditional: true` symbols — they may need `-D` flags to test.

### Step 2: Mock Generation (optional)

If scan shows `virtual: true` methods:

```
generate_mocks:
  sdk_root: /path/to/sdk
  class_name: Calculator
```

Or: `forge mocks --sdk-root /path/to/sdk --output mocks.hpp`

### Step 3–4: Analyze & Design Tests

Cover normal, boundary, error, resource-pairing scenarios.

### Step 5: Delete Old Tests

```
delete_tests: /path/to/tests
```

### Step 6: Compile

```
compile_tests:
  source_dir: /path/to/tests
  build_dir: /path/to/build
  gtest_source: cached
  coverage: false   # set true if user asks for coverage
```

**Failure recovery:** read `output` from cmake_error responses; fix include/lib/pkg-config paths from probe_sdk.

### Step 7: Run

```
run_tests: /path/to/build
```

### Step 8: Coverage (optional, Linux)

```
collect_coverage:
  build_dir: /path/to/build
  source_dir: /path/to/tests
```

### Step 9: Report

Summarize passed/failed/skipped and coverage percentage if collected.

## Rules

1. Probe and scan before guessing SDK layout
2. Always compile and run generated tests
3. Use `forge` CLI when MCP is unavailable
4. Portable C++17 in tests

## Samples

- [`test_sdk/`](../../test_sdk/) — C library
- [`test_sdk_cpp/`](../../test_sdk_cpp/) — C++ with virtual methods and pkg-config
