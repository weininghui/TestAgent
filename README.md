# SDK Test Forge Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/weininghui/TestAgent)](https://github.com/weininghui/TestAgent/releases)

OpenCode plugin and **standalone CLI** (`forge`) for C/C++ GTest generation.

## Capability Matrix

| Feature | MCP | CLI | Since |
|---------|-----|-----|-------|
| Environment doctor | `forge_doctor` | `forge doctor` | v3.1 |
| Project scaffold | `init_forge_project` | `forge init` | v3.1 |
| One-shot build | `build_tests` | `forge build` | v3.1 |
| GTest auto-download | `gtest_tag` in compile JSON | `--gtest-source auto` | v3.1.1 |
| GTest version pin | `gtest_version` | `--gtest-version` | v3.1.1 |
| `.forge.yaml` config | auto in `compile_tests` | `--no-config` | v3.1 |
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

## Quick Start (v3.1)

```bash
pip install -r requirements.txt
pip install -e .

forge doctor
forge init ./my_tests --sdk-root ./test_sdk_cpp
# edit my_tests/.forge.yaml and tests/*.cpp
forge build --project-dir ./my_tests
```

Legacy step-by-step:

```bash
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

## GTest auto-download (v3.1.1)

Default `gtest_source: auto` — forge detects compiler/cmake, picks a googletest tag (e.g. `v1.14.0` for GCC 12+/Clang 15+), downloads to cache via `git clone`, then compiles tests.

```yaml
# .forge.yaml
gtest_source: auto      # auto | cached | fetch | system
gtest_version: auto     # or pin: 1.14.0 / v1.13.0
```

- `forge doctor` pre-downloads the recommended tag and reports cache path
- `compile_tests` returns `gtest_tag`, `gtest.method` (`git` / `cache` / `cmake_fetch`)
- Without git, CMake `FetchContent` downloads during configure

## Fixtures

- `test_sdk/` — C library
- `test_sdk_cpp/` — C++ namespace/class/virtual
- `test_sdk_medium/` — multi-module + `#ifdef MEDIUM_NET` + pkg-config
- `examples/forge_test_sdk/` — sample `.forge.json` for v3.1 workflow

## Development

```bash
python -m pytest test_mcp_server.py -v -k "not TestCompileAndRun and not TestCliIntegration"
```

## License

MIT
