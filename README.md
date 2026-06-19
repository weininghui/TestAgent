# SDK Test Forge Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/weininghui/TestAgent)](https://github.com/weininghui/TestAgent/releases)

An OpenCode plugin that automatically generates GoogleTest (GTest) test suites
from C/C++ SDK header files. Uses **OpenCode's built-in model** for all
intelligence — no external LLM API keys required.

## What's New in v2.5

- **libclang header parsing** — `scan_headers` uses libclang AST when available, regex fallback
- **`probe_sdk` tool** — suggest include/lib/pkg-config settings from SDK root or `.pc` file
- **Real SDK linking** — `compile_tests` supports `pkg_config_packages`, `find_packages`, `cmake_prefix_path`
- **GTest cache** — FetchContent cached under `~/.cache/sdk-test-forge/gtest` (Windows: `%LOCALAPPDATA%`)
- **`test_sdk_cpp/`** — C++ fixture with namespaces, classes, templates, pkg-config
- **Cross-platform CI** — Linux + Windows MSVC integration jobs with GTest cache

## Architecture

```
User provides SDK path
         │
         ▼
┌─────────────────────────────────┐
│ OpenCode Agent (built-in model) │  Analyzes APIs, designs tests,
│  + MCP server (file operations) │  generates code, compiles & runs
└─────────────────────────────────┘
         │
         ▼
  Output: GTest .cpp + Build + Test Results
```

The plugin is a hybrid architecture:
- **MCP server** (`mcp_server.py`) — file operations: scan, probe, delete, compile, run
- **OpenCode Agent (`forge`)** — API analysis, test design, C++ code generation

**No external LLM API keys needed.**

## Quick Start

### Prerequisites

- Python 3.10+
- OpenCode (with built-in model)
- CMake 3.14+
- C++ compiler with C++17 support
- Optional: LLVM/libclang for better C++ parsing (`pip install sdk-test-forge[clang]`)

### Install

```bash
pip install -r requirements.txt
# Optional: libclang parsing
pip install libclang>=16.0.0
```

On Windows, set `LIBCLANG_PATH` to your LLVM `bin` directory if libclang is not found.

### Global registration (recommended)

TestAgent is a **Python MCP plugin**, not an npm package — it will **not** appear in OpenCode's npm plugin list.

Add to `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "sdk-test-forge": {
      "command": ["python", "/path/to/TestAgent/mcp_server.py"],
      "enabled": true,
      "type": "local"
    }
  }
}
```

Copy agent definition to `~/.config/opencode/agents/forge.md` (from `.opencode/agents/forge.md`).

### Usage

Select **forge** in the Agent dropdown, then:

```
帮我测试 /path/to/sdk 的接口
```

Try the bundled samples:

```
帮我测试 <repo>/test_sdk 的接口
帮我测试 <repo>/test_sdk_cpp 的接口
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `scan_headers` | Scan `.h` / `.hpp` with libclang (or regex fallback) |
| `probe_sdk` | Suggest compile params from SDK root or `.pc` file |
| `delete_tests` | Recursively remove existing GTest files |
| `compile_tests` | Compile with CMake; SDK/pkg-config/find_package linking |
| `run_tests` | Run compiled binary, parse GTest output |

### scan_headers parameters (v2.5)

| Parameter | Example | Purpose |
|-----------|---------|---------|
| `include_dirs` | `["/sdk/include"]` | `-I` paths for libclang |
| `compile_args` | `["-std=c++17", "-DMYSDK_EXPORT"]` | Extra clang args |
| `use_clang` | `true` | Use libclang when available (default) |

### compile_tests parameters (v2.5)

| Parameter | Example | Purpose |
|-----------|---------|---------|
| `sdk_include_dirs` | `["/sdk/include"]` | SDK header search paths |
| `sdk_lib_dirs` | `["/sdk/build"]` | Library search paths |
| `link_libraries` | `["my_sdk"]` | Libraries to link besides gtest |
| `cmake_prefix_path` | `["/opt/my_sdk"]` | `CMAKE_PREFIX_PATH` for find_package |
| `find_packages` | `[{"name":"OpenSSL","components":["Crypto"],"target":"OpenSSL::Crypto"}]` | CMake find_package |
| `pkg_config_packages` | `["libcurl"]` | pkg-config dependencies |
| `extra_cmake_snippet` | `target_compile_definitions(...)` | Advanced CMake injection |
| `gtest_source` | `cached` / `fetch` / `system` | GTest acquisition strategy |

Environment variable `FORGE_GTEST_CACHE` overrides the GTest cache directory.

## Real SDK Integration Checklist

1. **Probe first** — call `probe_sdk(sdk_root)` or pass a `.pc` file path
2. **Scan with context** — `scan_headers(sdk_root, include_dirs=[...], compile_args=["-std=c++17"])`
3. **Choose linking strategy**:
   - Installed SDK with `.pc` → `pkg_config_packages`
   - CMake package → `cmake_prefix_path` + `find_packages`
   - Prebuilt libs → `sdk_include_dirs` + `sdk_lib_dirs` + `link_libraries`
4. **Use GTest cache** — default `gtest_source=cached` avoids re-downloading on Windows
5. **Compile and run** — `compile_tests` then `run_tests`

### Example: OpenSSL-style library

```json
{
  "cmake_prefix_path": ["/usr/local/openssl"],
  "find_packages": [{"name": "OpenSSL", "components": ["Crypto"], "target": "OpenSSL::Crypto"}]
}
```

### Example: pkg-config library

```json
{
  "pkg_config_packages": ["libcurl"]
}
```

## Project Structure

```
.
├── mcp_server.py
├── test_mcp_server.py
├── test_sdk/                  # Sample C SDK
├── test_sdk_cpp/              # Sample C++ SDK (namespace, templates, .pc)
├── .opencode/
│   ├── agents/forge.md
│   └── skills/test-forge/
├── REGISTER_AGENT.md
└── README.md
```

## Development

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio
python -m pytest test_mcp_server.py -v -k "not TestCompileAndRun"
python mcp_server.py
```

## Documentation

See [REGISTER_AGENT.md](REGISTER_AGENT.md) for full OpenCode registration options.

## License

MIT License — see [LICENSE](LICENSE) for details.
