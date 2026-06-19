# SDK Test Forge Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/weininghui/TestAgent)](https://github.com/weininghui/TestAgent/releases)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

OpenCode plugin and **standalone CLI** (`forge`) for scanning C/C++ SDK headers, generating GTest suites, compiling, and running tests against real SDK binaries.

**Current release: v3.1.1** — project workflow (`.forge` config, doctor/init/build) + toolchain-aware GTest auto-download.

## What it does

1. **Probe** an SDK layout (include/lib/pkg-config)
2. **Scan** headers with libclang (optional) + regex fallback
3. **Generate** GTest / GMock test code (via Agent or manually)
4. **Download** googletest matched to your compiler (v3.1.1)
5. **Compile & run** tests with CMake, returning structured JSON + CMake hints on failure

Works as an **OpenCode MCP plugin** (`sdk-test-forge`) or a **CLI** you can call from scripts and CI.

## Install

```bash
git clone https://github.com/weininghui/TestAgent.git
cd TestAgent
pip install -r requirements.txt
pip install -e .

# optional
pip install "sdk-test-forge[clang]"   # libclang header parsing
pip install "sdk-test-forge[yaml]"    # .forge.yaml support (JSON works without it)
```

Requirements: **Python 3.10+**, **CMake 3.14+**, **C++ compiler** (g++/clang++/MSVC). **git** recommended for GTest prefetch.

## Quick Start (recommended)

```bash
# 1. Check environment (cmake, compiler, GTest cache)
forge doctor

# 2. Scaffold a test project
forge init ./my_tests --sdk-root ./test_sdk_cpp

# 3. Edit my_tests/.forge.yaml and tests/*.cpp, then one-shot build
forge build --project-dir ./my_tests
```

`forge build` runs: load `.forge` config → `probe_sdk` → download GTest → `compile_tests` → `run_tests`.

### Sample `.forge.yaml`

```yaml
sdk_root: ../test_sdk_cpp
tests_dir: tests
build_dir: build

sdk_include_dirs:
  - ../test_sdk_cpp/include
sdk_lib_dirs:
  - ../test_sdk_cpp/build
link_libraries:
  - my_sdk

gtest_source: auto      # auto | cached | fetch | system
gtest_version: auto     # auto or pin: 1.14.0 / v1.13.0

# optional
# pkg_config_packages: [my_sdk]
# coverage: true
# coverage_tool: gcov
```

JSON config is also supported: see [`examples/forge_test_sdk/.forge.json`](examples/forge_test_sdk/.forge.json).

`compile_tests` walks up from `source_dir` to find `.forge.yaml` / `.forge.yml` / `.forge.json`. Skip with `forge compile --no-config`.

## GTest auto-download (v3.1.1)

Default `gtest_source: auto`:

1. Detect compiler / platform
2. Pick a googletest git tag
3. `git clone` into forge cache (or CMake `FetchContent` fallback)
4. Compile tests via `add_subdirectory`

| Toolchain | Tag |
|-----------|-----|
| GCC ≥ 12, Clang ≥ 15, MSVC 2019+ | `v1.14.0` |
| GCC 9–11, Clang 10–14, MSVC 2017 | `v1.13.0` |
| Older / unknown on Windows | `v1.14.0` (safe default) |
| Very old GCC/Clang | `v1.12.0` |

Cache locations:

- Linux: `~/.cache/sdk-test-forge/gtest/`
- Windows: `%LOCALAPPDATA%\sdk-test-forge\gtest\`
- Override: `FORGE_GTEST_CACHE=/path`

`forge doctor` pre-downloads the recommended tag. Compile JSON includes `gtest_tag`, `gtest.method` (`git` / `cache` / `cmake_fetch`).

```bash
forge compile ./tests ./build --gtest-source auto --gtest-version auto
forge compile ./tests ./build --gtest-version 1.13.0   # pin version
forge compile ./tests ./build --gtest-source system    # use system GTest
```

## CLI reference

| Command | Description |
|---------|-------------|
| `forge doctor` | Check cmake, compiler, pkg-config, caches, GTest |
| `forge init <dir>` | Create `tests/`, `build/`, `.forge.yaml`, sample test |
| `forge build` | Probe + compile + run from `.forge` config |
| `forge probe <sdk>` | Suggest include/lib/link settings |
| `forge scan <sdk>` | Parse headers (`--no-cache`, `--no-clang`) |
| `forge mocks` | Generate GMock templates (`--sdk-root`, `--output`) |
| `forge compile <src> <build>` | Build tests (`--from-probe`, `--no-config`) |
| `forge run <build>` | Run `run_tests` binary (`--filter`) |
| `forge coverage <build>` | Collect gcov/lcov (Linux) |
| `forge clean <dir>` | Delete `*_test.cpp` files |

All commands emit JSON to stdout. Exit codes: `0` ok, `1` test failures, `2` error.

## MCP tools (OpenCode / Cursor)

| MCP tool | CLI equivalent |
|----------|----------------|
| `forge_doctor` | `forge doctor` |
| `init_forge_project` | `forge init` |
| `build_tests` | `forge build` |
| `probe_sdk` | `forge probe` |
| `scan_headers` | `forge scan` |
| `generate_mocks` | `forge mocks` |
| `compile_tests` | `forge compile` |
| `run_tests` | `forge run` |
| `collect_coverage` | `forge coverage` |
| `delete_tests` | `forge clean` |

Open this repo in OpenCode — `plugin.yaml` auto-registers MCP + skill. For global use across projects, see [REGISTER_AGENT.md](REGISTER_AGENT.md).

Agent prompt: [`.opencode/agents/forge.md`](.opencode/agents/forge.md)  
Skill workflow: [`.opencode/skills/test-forge/SKILL.md`](.opencode/skills/test-forge/SKILL.md)

## Legacy step-by-step workflow

```bash
forge probe ./test_sdk_cpp
forge scan ./test_sdk_cpp/include
# write tests/*.cpp
forge compile ./tests ./build --from-probe ./test_sdk_cpp
forge run ./build
```

On compile failure, read the `hints` array first, then `output` (CMake log).

## libclang (optional, better C++ parsing)

```bash
pip install libclang>=16.0.0
```

Windows: set `LIBCLANG_PATH` to LLVM `bin`, e.g. `C:\Program Files\LLVM\bin`.

## Fixtures

| Directory | Description |
|-----------|-------------|
| [`test_sdk/`](test_sdk/) | C library (`calc`) |
| [`test_sdk_cpp/`](test_sdk_cpp/) | C++ namespace, virtual methods, pkg-config |
| [`test_sdk_medium/`](test_sdk_medium/) | Multi-module, `#ifdef`, pkg-config |
| [`examples/forge_test_sdk/`](examples/forge_test_sdk/) | Sample `.forge.json` |

## Capability matrix

| Feature | MCP | CLI | Since |
|---------|-----|-----|-------|
| Environment doctor | `forge_doctor` | `forge doctor` | v3.1 |
| Project scaffold | `init_forge_project` | `forge init` | v3.1 |
| One-shot build | `build_tests` | `forge build` | v3.1 |
| GTest auto-download | `gtest_tag` in JSON | `--gtest-source auto` | v3.1.1 |
| GTest version pin | `gtest_version` | `--gtest-version` | v3.1.1 |
| `.forge` project config | auto in `compile_tests` | `--no-config` | v3.1 |
| Header scan (libclang + regex) | `scan_headers` | `forge scan` | v2.5 |
| Scan cache | `use_cache` | `--no-cache` | v3.0.1 |
| `#ifdef` conditional flag | scan JSON | — | v3.0.1 |
| SDK probe | `probe_sdk` | `forge probe` | v2.5 |
| Compile + link | `compile_tests` | `forge compile` | v2.5 |
| Compile from probe | — | `--from-probe` | v3.0.3 |
| CMake error hints | `hints` | JSON output | v3.0.3 |
| Run tests | `run_tests` | `forge run` | v2.0 |
| Coverage (Linux) | `collect_coverage` | `forge coverage` | v3.0.4 |
| GMock templates | `generate_mocks` | `forge mocks` | v3.0.5 |
| Compile timing | `compile_duration_sec` | same | v3.0.8 |

## Development

```bash
# fast unit tests (no cmake required)
python -m pytest test_mcp_server.py -v -k "not TestCompileAndRun and not TestCliIntegration"

# full suite (needs cmake + compiler)
python -m pytest test_mcp_server.py -v
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `cmake not found` | Install CMake, add to `PATH` |
| `undefined reference` | Add `link_libraries` / check `probe_sdk` |
| `No such file ... .h` | Add `sdk_include_dirs` |
| GTest download fails | Install git; run `forge doctor`; pin `gtest_version: 1.14.0` |
| Windows binary not found | Check `build/x64/Debug/run_tests.exe` |
| Coverage unsupported | gcov/lcov is Linux-only; MSVC not supported |
| libclang scan misses symbols | Set `LIBCLANG_PATH`; add `compile_args: ["-DFEATURE_X"]` |

## Releases

- [All releases](https://github.com/weininghui/TestAgent/releases)
- [CHANGELOG](CHANGELOG.md)
- Latest notes: [RELEASE_NOTES_v3.1.1.md](RELEASE_NOTES_v3.1.1.md)

## License

MIT — see [LICENSE](LICENSE).
