# test_sdk — Sample C SDK for SDK Test Forge

Minimal C library used to validate scan → compile → run with SDK linking.

## Layout

```
test_sdk/
├── include/calc.h    # Public API
├── src/calc.c        # Implementation (static lib calc)
└── CMakeLists.txt
```

## Build the SDK library

```bash
cmake -S test_sdk -B test_sdk/build
cmake --build test_sdk/build
```

## Use with forge / MCP

1. `scan_headers("<repo>/test_sdk")`
2. Generate `calc_test.cpp` that includes `calc.h` and tests `calc_add`, etc.
3. `compile_tests` with:
   - `sdk_include_dirs`: `["<repo>/test_sdk/include"]`
   - `sdk_lib_dirs`: `["<repo>/test_sdk/build"]` (or `Debug`/`Release` subdir on Windows)
   - `link_libraries`: `["calc"]`
4. `run_tests(build_dir)`

## Example prompt (OpenCode)

```
用 forge 测试 test_sdk，SDK 路径是 E:/vs_test/AINew/aiagent-main/test_sdk
```
