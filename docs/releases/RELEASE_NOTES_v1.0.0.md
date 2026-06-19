# Release v1.0.0 - SDK Test Forge Plugin for OpenCode

First stable release of the SDK Test Forge plugin.

## Features

- MCP server with 4 tools: scan_headers, delete_tests, compile_tests, run_tests
- OpenCode Agent (AGENTS.md) using built-in model for test generation
- Skill (test-forge) with 8-step workflow
- Auto-registration via plugin.yaml
- 17/17 tests passing (16 unit + 1 integration)
- C/C++ header parsing with regex (functions, classes, enums, typedefs, using aliases)
- Cross-platform: Windows (.exe detection), Linux, macOS
- No external LLM dependencies - uses OpenCode's built-in model

## Installation

```bash
cd $env:APPDATA/opencode
mkdir plugins -ErrorAction SilentlyContinue
git clone https://github.com/weininghui/TestAgent.git plugins/sdk-test-forge
```

## MCP Config (mcp.json)

```json
{
  "mcpServers": {
    "sdk-test-forge": {
      "command": "python",
      "args": ["$env:APPDATA/opencode/plugins/sdk-test-forge/mcp_server.py"],
      "env": {}
    }
  }
}
```