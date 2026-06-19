# test_sdk — Sample C SDK for SDK Test Forge

Minimal C library used to validate scan → compile → run with SDK linking.

## Layout

```
examples/test_sdk/
├── include/calc.h    # Public API
├── src/calc.c        # Implementation (static lib calc)
└── CMakeLists.txt
```

## Build the SDK library

From the repository root:

```bash
cmake -S examples/test_sdk -B examples/test_sdk/build
cmake --build examples/test_sdk/build
```

## Use with forge / MCP

1. `scan_headers("<repo>/examples/test_sdk")`
2. Generate `calc_test.cpp` that includes `calc.h` and tests `calc_add`, etc.
3. `compile_tests` with:
   - `sdk_include_dirs`: `["<repo>/examples/test_sdk/include"]`
   - `sdk_lib_dirs`: `["<repo>/examples/test_sdk/build"]` (or `Debug`/`Release` subdir on Windows)
   - `link_libraries`: `["calc"]`
4. `run_tests(build_dir)`

## Example prompt (OpenCode)

```
用 forge 测试 test_sdk，SDK 路径是 <repo>/examples/test_sdk
```
