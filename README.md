# 🔨 SDK Test Forge Agent

An AI-powered test-forging agent that analyses C/C++ SDK header files and
automatically produces comprehensive GoogleTest (GTest) test suites with
CMake build integration.

Built on **LangChain** — all 6 pipeline stages are driven by LLM agents,
eliminating the need for local parsers, templates, or build tooling.

## Architecture

The agent runs a **6-stage LangChain pipeline**:

```
SDK Headers (.h)
      │
      ▼
┌─────────────────┐
│    Scanner      │  Discovers .h files, reads them, invokes LLM to extract
│                 │  a structured APIInventory (functions, classes, enums).
├─────────────────┤
│   Analysis      │  Analyses the inventory for complexity, design patterns,
│                 │  memory safety, thread safety & testing priorities.
├─────────────────┤
│  Test Design    │  Designs up to 100 targeted test cases covering normal
│                 │  paths, edge cases, error handling & boundary conditions.
├─────────────────┤
│  Code Gen       │  Writes compilable C++ GoogleTest source files (.cpp).
├─────────────────┤
│   CI Gen        │  Generates CMakeLists.txt (FetchContent GTest) & a
│                 │  GitHub Actions workflow for automated build & test.
├─────────────────┤
│    Report       │  Synthesises a Markdown report & JSON summary of all
│                 │  pipeline stages.
└─────────────────┘
      │
      ▼
  Output: GTest .cpp + CMake + CI + Report
```

### Key Features

- **Pure LLM-driven** — No libclang, no Jinja2 templates, no custom parsers
- **LangChain pipeline** — Modular, reusable, extensible
- **MCP server integration** — Full pipeline access via Model Context Protocol
- **Config-driven model selection** — Single config file, any OpenAI-compatible provider
- **Cross-stage memory** — Each stage knows what previous stages produced
- **Disk-persisted cache** — SHA-256 content-hash based, avoids redundant LLM calls
- **OpenCode skill** — Designed for seamless use as an OpenCode skill via MCP

## Quick Start

### Prerequisites

- Python 3.10+
- An OpenAI-compatible API key (set as `OPENAI_API_KEY` environment variable)

### Install

```bash
pip install -r requirements.txt
```

### MCP Server

This project is a pure OpenCode MCP plugin. It runs as an MCP server and is
auto-started by OpenCode when invoked as a skill. The only entry points are
`mcp_server.py` (MCP server) and `agent.py` (autonomous goal-driven agent).

```bash
# stdio transport (default, used by OpenCode skills)
python mcp_server.py

# SSE transport (for remote setups)
python mcp_server.py --transport sse --port 8080
```

Once running, any MCP client can call these tools:

| Tool | Description |
|------|-------------|
| `scan_headers` | Discover and parse SDK `.h` files |
| `analyze_api` | Analyse API complexity and patterns |
| `design_test_cases` | Design test cases (scan + analyse + design) |
| `generate_gtest_code` | Write C++ GTest source files |
| `generate_ci_config` | Write CMake + GitHub Actions workflow |
| `generate_report` | Generate Markdown + JSON report |
| `generate_tests` | **End-to-end**: all 6 stages |

### Usage as an OpenCode Skill

The agent is designed to be invoked as an OpenCode skill:

```
task(category="deep", load_skills=["test-agent"], prompt="generate tests for /path/to/sdk")
```

This invokes the MCP server, which runs the full pipeline and produces output
in the configured output directory.

Example MCP client usage:

```json
{
  "tool": "generate_tests",
  "arguments": {
    "sdk_root": "/path/to/sdk",
    "model_preset": "longcat"
  }
}
```

## Model Configuration

The project uses a configuration file at `~/.sdk-test-agent/config.json` to
define the LLM endpoint. There are no hardcoded model presets — all model
settings (URL, model name, API key) are configured at runtime.

### Configuration System

Two layers of configuration are supported:

1. **Environment variables**:
   - `OPENAI_API_KEY` — API key for the LLM provider
   - `SDK_ROOT` — Default SDK root directory
   - `SDK_OUTPUT_ROOT` — Default output directory
   - `SDK_MODEL` — Default model name

2. **Configuration file** (`~/.sdk-test-agent/config.json`):
   - Persistent settings across runs
   - Model URL, model name, and API key management
   - Pipeline defaults and preferences

## Project Structure

```
.
├── agents/                  # LangChain pipeline agents
│   ├── __init__.py
│   ├── llm.py              # LLMWrapper — ChatOpenAI + tenacity retry
│   ├── cache.py            # LLMCache — SHA-256 disk-persisted cache
│   ├── memory.py           # PipelineMemory — cross-stage state
│   ├── config.py           # PipelineConfig dataclass
│   ├── models.py           # Model config helpers & save_config()
│   ├── keychain.py         # In-memory API key management
│   ├── pipeline.py         # Pipeline orchestrator (6 stages)
│   ├── chains/             # 6 LangChain chains (one per stage)
│   │   ├── scanner_chain.py
│   │   ├── analysis_chain.py
│   │   ├── test_design_chain.py
│   │   ├── code_gen_chain.py
│   │   ├── ci_gen_chain.py
│   │   └── report_chain.py
│   ├── tools/              # LangChain @tool definitions
│   │   ├── sdk_tools.py
│   │   ├── code_gen_tools.py
│   │   └── file_tools.py
│   └── prompts/            # LangChain PromptTemplate files
│       ├── scanner_prompt.py
│       ├── analysis_prompt.py
│       ├── test_design_prompt.py
│       ├── code_gen_prompt.py
│       ├── ci_gen_prompt.py
│       ├── report_prompt.py
│       ├── builder.py      # Prompt builder utilities
│       └── techniques.py   # Prompt technique helpers
├── schemas/                 # Data schemas
│   ├── api_schema.py       # APIInventory, FunctionInfo, etc.
│   ├── testcase_schema.py  # TestCaseCollection
│   └── contract_schema.py  # ContractInfo
├── mcp_server.py           # MCP server entry point
├── agent.py                # Autonomous goal-driven agent
├── plugin.yaml             # OpenCode skill configuration
├── tests/                  # Integration tests
├── .github/workflows/      # CI workflow
└── requirements.txt        # Python dependencies
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | API key for the LLM provider |
| `SDK_ROOT` | No | Default SDK root directory |
| `SDK_OUTPUT_ROOT` | No | Default output directory (default: `./output`) |
| `SDK_MODEL` | No | Default model name |

### Configuration File

A persistent configuration file at `~/.sdk-test-agent/config.json` stores your settings:

```json
{
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o",
  "sdk_root": "/path/to/sdk",
  "output_root": "./output"
}
```

- `base_url` — OpenAI-compatible API endpoint
- `model` — Model name
- `sdk_root` / `output_root` — Pipeline directory defaults

## Development

### Running Tests

```bash
# All integration tests
python -m pytest tests/ -v

# Specific test
python -m pytest tests/test_integration.py::TestIntegration::test_pipeline_init -v
```

### Configuring a Custom Model

Use the `save_config()` helper in `agents/models.py` or write directly to
`~/.sdk-test-agent/config.json`:

```python
from agents.models import save_config

# Set a custom OpenAI-compatible endpoint
save_config(
    url="https://api.custom-provider.com/v1",
    model="my-model-name",
    api_key="sk-...",  # stored in keychain, never written to disk in plaintext
)
```

Or manually create `~/.sdk-test-agent/config.json`:

```json
{
  "base_url": "https://api.custom-provider.com/v1",
  "model": "my-model-name"
}
```

### MCP Server Development

When developing with the MCP server:

```bash
# Run the MCP server in stdio mode (for OpenCode skills)
python mcp_server.py

# Run the MCP server in SSE mode
python mcp_server.py --transport sse --port 8080

# Test MCP server tools
python -c "from mcp_server import main; main()"
```

### Cache

LLM responses are cached by SHA-256 hash of `(model + prompt + temperature)`
in `<output_root>/cache/`. The pipeline handles caching automatically.

## Output Structure

```
<output_root>/
├── cache/                  # LLM response cache
├── generated/              # Generated test files
│   ├── *.cpp               # GTest source files
│   └── CMakeLists.txt      # CMake build config
├── .github/workflows/      # CI/CD workflows
├── report.md               # Markdown report
├── report.json             # JSON summary
└── pipeline_memory.json    # Cross-stage context snapshot
```

### Generated Files

The pipeline generates:

- **GTest source files** (`.cpp`) — Complete test suites for SDK APIs
- **CMake configuration** — Build system for compiling and running tests
- **GitHub Actions workflows** — CI/CD pipelines for automated testing
- **Reports** — Markdown and JSON summaries of the test generation process
- **Memory snapshots** — Cross-stage context for debugging and analysis

## License

This project is provided for internal use. No license is specified.
