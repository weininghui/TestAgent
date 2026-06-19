# SDK Test Forge Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/weininghui/TestAgent)](https://github.com/weininghui/TestAgent/releases)

OpenCode plugin **and standalone CLI** for generating GoogleTest suites from C/C++ SDK headers.

## What's New in v3.0

- **`forge` CLI** — `scan`, `probe`, `compile`, `run`, `clean`, `coverage`, `mocks`
- **`sdk_forge/` package** — shared core for MCP and CLI
- **Scan cache** — `FORGE_SCAN_CACHE`, `use_cache` on `scan_headers`
- **`conditional` flag** — symbols inside `#ifdef` blocks marked in scan JSON
- **`collect_coverage`** — gcov/lcov summary (Linux)
- **`generate_mocks`** — GMock `MOCK_METHOD` templates for virtual methods

See [v2.5 notes](RELEASE_NOTES_v2.5.0.md) for libclang, pkg-config, GTest cache.

## CLI Quick Start

```bash
pip install -r requirements.txt
forge probe ./test_sdk_cpp
forge scan ./test_sdk_cpp --include test_sdk_cpp/include
forge compile ./tests ./build --include test_sdk_cpp/include --link my_sdk
forge run ./build
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `scan_headers` | libclang/regex scan with cache |
| `probe_sdk` | Suggest compile parameters |
| `compile_tests` | CMake build + optional `coverage` |
| `run_tests` | Execute GTest binary |
| `collect_coverage` | gcov/lcov report |
| `generate_mocks` | GMock templates from scan |
| `delete_tests` | Remove old test files |

## Real SDK Checklist

1. `forge probe <sdk_root>` or `probe_sdk`
2. `forge scan <sdk_root> --include ...` — check `conditional: true` symbols
3. Link via pkg-config / find_package / manual include+lib
4. `forge compile` with `gtest_source=cached`
5. `forge run` then optional `forge coverage`

## Development

```bash
python -m pytest test_mcp_server.py -v -k "not TestCompileAndRun"
python mcp_server.py
forge scan test_sdk
```

## License

MIT — see [LICENSE](LICENSE).
