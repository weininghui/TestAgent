---
name: test-forge
description: Scan C/C++ SDK headers, generate GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill

Generate GoogleTest (GTest) test suites from C/C++ SDK header files.

## When to Use

- User provides an SDK path and asks to test its APIs
- User asks to "generate tests" for a C/C++ library
- User wants to verify SDK API correctness with automated tests

## Workflow

### Step 1: Probe SDK

Call `probe_sdk` to discover suggested compile parameters:

```
sdk_root: /path/to/sdk
```

Or pass a `.pc` file path directly. Use the returned `sdk_include_dirs`, `sdk_lib_dirs`, `pkg_config_packages`, and `cmake_prefix_path` in later steps.

### Step 2: Scan Headers

Call `scan_headers` with include context for complex C++ SDKs:

```
sdk_root: /path/to/sdk
include_dirs: ["/path/to/sdk/include"]
compile_args: ["-std=c++17"]
use_clang: true
```

Returns JSON with functions (namespace, static/virtual flags), classes, enums, typedefs, and parser metadata.

### Step 3: Analyze API (use OpenCode's model)

Review the scan result and analyze:
- API surface size and complexity
- Functions that need parameter validation tests
- Functions with pointer parameters (nullptr tests)
- Error return patterns
- Resource handle patterns (init/close pairs)
- Thread safety candidates

### Step 4: Design Test Cases (use OpenCode's model)

Design targeted test cases covering:
- **Normal path** — typical valid inputs
- **Boundary** — edge values, empty strings, zero sizes
- **Error handling** — null pointers, invalid enums, out-of-range values
- **Resource management** — init/close, open/close pairs, double-free prevention
- **State** — sequence-dependent calls, repeat calls

### Step 5: Write GTest Source Files

Write C++ GTest source files using OpenCode's `Write` tool.

For C libraries linked from C++ tests, wrap includes in `extern "C" { ... }`.

### Step 6: Delete Old Tests

Call `delete_tests`:

```
test_dir: /path/to/output/tests
```

### Step 7: Compile (with SDK linking)

Call `compile_tests` using the strategy from `probe_sdk`:

**Prebuilt library:**
```
source_dir: /path/to/output/tests
build_dir: /path/to/output/build
sdk_include_dirs: ["/path/to/sdk/include"]
sdk_lib_dirs: ["/path/to/sdk/build"]
link_libraries: ["my_sdk"]
gtest_source: cached
```

**pkg-config:**
```
pkg_config_packages: ["my_sdk"]
```

**CMake package:**
```
cmake_prefix_path: ["/opt/my_sdk"]
find_packages: [{"name": "my_sdk", "target": "my_sdk::my_sdk"}]
```

### Step 8: Run Tests

Call `run_tests`:

```
build_dir: /path/to/output/build
```

### Step 9: Report

Summarize total, passed, failed, skipped, and list any failures.

## Rules

1. **No external LLM calls** — use only OpenCode's built-in model
2. **Probe and scan first** — never guess SDK structure
3. **Always compile and run** — generated code must be verified
4. **Use descriptive test names** — `FunctionName_Scenario_ExpectedResult`
5. **Write portable C++17** — avoid platform-specific APIs in tests

## Sample SDKs

- [`test_sdk/`](../../test_sdk/) — minimal C library
- [`test_sdk_cpp/`](../../test_sdk_cpp/) — C++ SDK with namespace, templates, pkg-config
