# SDK Test Forge Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/weininghui/TestAgent)](https://github.com/weininghui/TestAgent/releases)

OpenCode plugin and **standalone CLI** (`forge`) for C/C++ GTest generation.

## v3.0.x Capability Matrix

| Feature | MCP | CLI | Since |
|---------|-----|-----|-------|
| Header scan (libclang + regex) | `scan_headers` | `forge scan` | v2.5 |
| Scan cache | `use_cache` | `--no-cache` | v3.0.1 |
| `#ifdef` conditional flag | scan JSON | scan JSON | v3.0.1 |
| SDK probe | `probe_sdk` | `forge probe` | v2.5 |
| Compile + link | `compile_tests` | `forge compile` | v2.5 |
| Compile from probe | — | `--from-probe` | v3.0.3 |
| CMake error hints | `hints` field | JSON output | v3.0.3 |
| Run tests | `run_tests` | `forge run` | v2.0 |
| Coverage (Linux) | `collect_coverage` | `forge coverage` | v3.0.4 |
| GMock templates | `generate_mocks` | `forge mocks` | v3.0.5 |
| Compile timing | `compile_duration_sec` | same | v3.0.8 |

## Quick Start

```bash
pip install -r requirements.txt
pip install -e .

forge probe ./test_sdk_cpp
forge scan ./test_sdk_cpp/include
forge compile ./tests ./build --from-probe ./test_sdk_cpp
forge run ./build
```

## libclang (optional)

```bash
pip install libclang>=16.0.0
```

Windows: set `LIBCLANG_PATH` to LLVM `bin` (e.g. `C:\Program Files\LLVM\bin`).

## Fixtures

- `test_sdk/` — C library
- `test_sdk_cpp/` — C++ namespace/class/virtual
- `test_sdk_medium/` — multi-module + `#ifdef MEDIUM_NET` + pkg-config

## Development

```bash
python -m pytest test_mcp_server.py -v -k "not TestCompileAndRun and not TestCliIntegration"
```

## License

MIT
