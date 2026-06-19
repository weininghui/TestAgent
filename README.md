# SDK Test Forge Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/weininghui/TestAgent)](https://github.com/weininghui/TestAgent/releases)

An OpenCode plugin that automatically generates GoogleTest (GTest) test suites
from C/C++ SDK header files. Uses **OpenCode's built-in model** for all
intelligence — no external LLM API keys required.

## What's New in v2.0

- **`compile_tests` SDK linking** — pass `sdk_include_dirs`, `sdk_lib_dirs`, `link_libraries`
- **`scan_headers` scans `.hpp`** in addition to `.h`
- **`delete_tests` recursive** — cleans nested test directories
- **`test_sdk/` sample** — minimal C library for end-to-end validation
- **Fixed CI** — pytest on `test_mcp_server.py`, no broken `cli.py` references
- **OpenCode config** — `mode: all` for forge agent (not `edit`)

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
- **MCP server** (`mcp_server.py`) — file operations: scan, delete, compile, run
- **OpenCode Agent (`forge`)** — API analysis, test design, C++ code generation

**No external LLM API keys needed.**

## Quick Start

### Prerequisites

- Python 3.10+
- OpenCode (with built-in model)
- CMake 3.14+
- C++ compiler with C++17 support

### Install

```bash
pip install -r requirements.txt
```

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

Optionally configure model in `oh-my-openagent.json`:

```json
{
  "agents": {
    "forge": {
      "model": "opencode/deepseek-v4-flash-free",
      "fallback_models": ["opencode/mimo-v2.5-free"]
    }
  }
}
```

### Project-level registration

Open the TestAgent repo (or any project with `plugin.yaml`) in OpenCode — MCP + skill auto-register.

### Usage

Select **forge** in the Agent dropdown, then:

```
帮我测试 /path/to/sdk 的接口
```

Try the bundled sample:

```
帮我测试 <repo>/test_sdk 的接口
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `scan_headers` | Scan `.h` / `.hpp`, extract API structures |
| `delete_tests` | Recursively remove existing GTest files |
| `compile_tests` | Compile with CMake; optional SDK include/lib/link params |
| `run_tests` | Run compiled binary, parse GTest output |

### compile_tests SDK parameters (v2.0)

| Parameter | Example | Purpose |
|-----------|---------|---------|
| `sdk_include_dirs` | `["/sdk/include"]` | SDK header search paths |
| `sdk_lib_dirs` | `["/sdk/build"]` | Library search paths |
| `link_libraries` | `["calc"]` | Libraries to link besides gtest |

## Project Structure

```
.
├── mcp_server.py
├── test_mcp_server.py
├── AGENTS.md
├── plugin.yaml
├── test_sdk/                  # Sample C SDK
├── .opencode/
│   ├── agents/forge.md
│   └── skills/test-forge/
├── REGISTER_AGENT.md          # Detailed registration guide
└── README.md
```

## Development

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio
python -m pytest test_mcp_server.py -v
python mcp_server.py
```

## Documentation

See [REGISTER_AGENT.md](REGISTER_AGENT.md) for full OpenCode registration options.

## License

MIT License — see [LICENSE](LICENSE) for details.
