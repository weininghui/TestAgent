# SDK Test Forge Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/weininghui/TestAgent)](https://github.com/weininghui/TestAgent/releases)

An OpenCode plugin that automatically generates GoogleTest (GTest) test suites
from C/C++ SDK header files. Uses **OpenCode's built-in model** for all
intelligence — no external LLM API keys required.

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
- **MCP server** (`mcp_server.py`) — pure Python tools for file operations:
  scanning headers, deleting tests, compiling with CMake, running tests
- **OpenCode Agent** (`AGENTS.md`) — uses OpenCode's built-in model for
  API analysis, test case design, and C++ GTest code generation

**No LangChain, no ChatOpenAI, no OPENAI_API_KEY needed.**

## Quick Start

### Prerequisites

- Python 3.10+
- OpenCode (with built-in model)
- CMake 3.14+ (for compiling tests)
- C++ compiler with C++17 support

### Install

```bash
pip install -r requirements.txt
```

### Usage in OpenCode

Simply tell the agent:

```
帮我测试 /path/to/sdk 的接口
```

Or via `task()`:

```
task(category="deep", load_skills=["test-forge"], prompt="generate tests for /path/to/sdk")
```

The agent will:
1. Scan all `.h` files in the SDK directory
2. Analyze the API surface
3. Design targeted test cases
4. Write GTest `.cpp` files
5. Delete any existing test files
6. Compile with CMake
7. Run tests and report results

### MCP Server (standalone)

```bash
# stdio transport (default, used by OpenCode)
python mcp_server.py

# SSE transport (for remote setups)
python mcp_server.py --transport sse --port 8080
```

#### Available MCP Tools

| Tool | Description |
|------|-------------|
| `scan_headers` | Scan `.h` files, extract API structures |
| `delete_tests` | Remove existing test files in a directory |
| `compile_tests` | Compile GTest files with CMake (auto-creates CMakeLists.txt) |
| `run_tests` | Run compiled test binary, parse results |

## Project Structure

```
.
├── mcp_server.py                # MCP server (file-operation tools)
├── AGENTS.md                    # Test Forge Agent definition
├── plugin.yaml                  # OpenCode plugin manifest
├── .opencode/
│   └── skills/test-forge/
│       └── SKILL.md             # Skill workflow instructions
├── requirements.txt             # Python dependencies (mcp + pydantic only)
├── pyproject.toml               # Project metadata
└── README.md
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run MCP server in dev mode
python mcp_server.py

# Lint check
python -m py_compile mcp_server.py
```

## Plugin Files

| File | Purpose |
|------|---------|
| `plugin.yaml` | Auto-registers MCP server + skill in OpenCode |
| `AGENTS.md` | Defines the Test Forge Agent behavior |
| `.opencode/skills/test-forge/SKILL.md` | Skill instructions for task delegation |

## Red Lines

- ❌ **No external LLM API calls** — must use OpenCode's built-in model
- ❌ No scanning = no guessing SDK structure
- ❌ Generated code must be compiled and run before reporting
- ❌ No hardcoded SDK paths

## License

MIT License — see [LICENSE](LICENSE) for details.
