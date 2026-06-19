# SDK Test Forge Skill

Generate GoogleTest (GTest) test suites from C/C++ SDK header files.

## When to Use

- User provides an SDK path and asks to test its APIs
- User asks to "generate tests" for a C/C++ library
- User wants to verify SDK API correctness with automated tests

## Workflow

### Step 1: Scan Headers

Call the `scan_headers` MCP tool with the SDK root path:

```
sdk_root: /path/to/sdk
```

This returns a JSON-structured inventory of all `.h` files with:
- Functions (name, return type, params)
- Classes/structs
- Enums
- Typedefs
- Includes

### Step 2: Analyze API (use OpenCode's model)

Review the scan result and analyze:
- API surface size and complexity
- Functions that need parameter validation tests
- Functions with pointer parameters (nullptr tests)
- Error return patterns
- Resource handle patterns (init/close pairs)
- Thread safety candidates

### Step 3: Design Test Cases (use OpenCode's model)

Design targeted test cases covering:
- **Normal path** — typical valid inputs
- **Boundary** — edge values, empty strings, zero sizes
- **Error handling** — null pointers, invalid enums, out-of-range values
- **Resource management** — init/close, open/close pairs, double-free prevention
- **State** — sequence-dependent calls, repeat calls

### Step 4: Write GTest Source Files

Write C++ GTest source files using OpenCode's `Write` tool:

- One `.cpp` file per SDK module or header
- Each file follows this structure:
  ```cpp
  #include <gtest/gtest.h>
  #include "sdk_header.h"

  TEST(SuiteName, TestName) {
    // Arrange
    // Act
    // Assert
  }
  ```

### Step 5: Delete Old Tests

Call `delete_tests` MCP tool:

```
test_dir: /path/to/output/tests
```

### Step 6: Compile

Call `compile_tests` MCP tool:

```
source_dir: /path/to/output/tests
build_dir: /path/to/output/build
```

### Step 7: Run Tests

Call `run_tests` MCP tool:

```
build_dir: /path/to/output/build
```

### Step 8: Report

Summarize the results:
- Total tests, passed, failed, skipped
- List of failed tests (if any)
- Coverage summary

## Rules

1. **No external LLM calls** — use only OpenCode's built-in model
2. **Always scan first** — never guess SDK structure
3. **Always compile and run** — generated code must be verified
4. **Use descriptive test names** — `FunctionName_Scenario_ExpectedResult`
5. **Write portable C++17** — avoid platform-specific APIs in tests
