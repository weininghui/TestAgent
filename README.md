# SDK Test Generation Agent

An AI-powered test generation agent that analyses C/C++ SDK header files and
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
- **Dual interface** — CLI (`app.py`) + MCP server (`mcp_server.py`)
- **Multi-model** — Pluggable model presets (LongCat, DashScope, custom)
- **Cross-stage memory** — Each stage knows what previous stages produced
- **Disk-persisted cache** — SHA-256 content-hash based, avoids redundant LLM calls

## Quick Start

### Prerequisites

- Python 3.10+
- An OpenAI-compatible API key (set as `OPENAI_API_KEY` environment variable)

### Install

```bash
pip install -r requirements.txt
```

### Run (CLI)

```bash
# Full pipeline (default model: longcat)
python app.py --sdk-root /path/to/sdk

# With a different model preset
python app.py --sdk-root /path/to/sdk --model dashscope

# Dry-run (validate pipeline without LLM calls)
python app.py --sdk-root /path/to/sdk --dry-run

# Run a single stage
python app.py --sdk-root /path/to/sdk --stage scanner
```

### Run (MCP Server)

The MCP server exposes the pipeline as LLM-callable tools via the
[Model Context Protocol](https://modelcontextprotocol.io/).

```bash
# stdio transport (default — for OpenCode skills)
python mcp_server.py

# SSE transport (for Docker / remote setups)
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

## CLI Reference

```
usage: app.py [-h] [--model {longcat,dashscope,default}]
              [--sdk-root SDK_ROOT] [--output-root OUTPUT_ROOT]
              [--build-dir BUILD_DIR] [--llm-enabled] [--no-cache]
              [--dry-run] [--stage {scanner,analysis,test_design,code_gen,ci_gen,report}]
              [--verbose]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | `longcat` | Model preset name |
| `--sdk-root` | `""` | SDK root directory (required) |
| `--output-root` | `./output` | Output directory |
| `--build-dir` | `build` | Build directory name |
| `--no-cache` | `false` | Disable LLM response caching |
| `--dry-run` | `false` | Validate pipeline without LLM calls |
| `--stage` | — | Run a single pipeline stage only |
| `--verbose` / `-v` | `false` | DEBUG-level logging |

## Model Presets

| Preset | Model | Provider | Endpoint |
|--------|-------|----------|----------|
| `longcat` (default) | LongCat-2.0-Preview | LongCat | `api.longcat.chat` |
| `dashscope` | kimi-k2.5 | Aliyun DashScope | `dashscope.aliyuncs.com` |

Add custom presets in `agents/models.py`. The API key is read from the
`OPENAI_API_KEY` environment variable by default (configurable per preset).

## Project Structure

```
.
├── agents/                  # LangChain pipeline agents
│   ├── __init__.py
│   ├── llm.py              # LLMWrapper — ChatOpenAI + tenacity retry
│   ├── cache.py            # LLMCache — SHA-256 disk-persisted cache
│   ├── memory.py           # PipelineMemory — cross-stage state
│   ├── config.py           # PipelineConfig dataclass
│   ├── models.py           # ModelConfig presets
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
│       └── report_prompt.py
├── ir/                     # Data schemas
│   ├── api_schema.py       # APIInventory, FunctionInfo, etc.
│   ├── testcase_schema.py  # TestCaseCollection
│   └── contract_schema.py  # ContractInfo
├── app.py                  # CLI entry point
├── mcp_server.py           # MCP server entry point
├── tests/                  # Integration tests
├── Dockerfile              # Containerised MCP server
├── .github/workflows/      # CI workflow
└── requirements.txt        # Python dependencies
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | API key for the LLM provider |
| `SDK_ROOT` | No | Default SDK root (can be overridden via CLI) |
| `SDK_OUTPUT_ROOT` | No | Default output directory (default: `./output`) |
| `SDK_LOG_LEVEL` | No | Logging level (default: `INFO`) |
| `SDK_NO_CACHE` | No | Disable caching if set |
| `SDK_MODEL` | No | Default model preset name |

## Development

### Running Tests

```bash
# All integration tests
python -m pytest tests/ -v

# Specific test
python -m pytest tests/test_integration.py::TestIntegration::test_pipeline_init -v
```

### Adding a New Model Preset

```python
# In agents/models.py
from agents.models import ModelConfig, _MODELS

MY_MODEL = ModelConfig(
    model="my-model-name",
    base_url="https://api.example.com/v1",
    api_key_env="MY_API_KEY",
)
_MODELS["my-preset"] = MY_MODEL
```

### Cache

LLM responses are cached by SHA-256 hash of `(model + prompt + temperature)`
in `<output_root>/cache/`. Use `--no-cache` to bypass during development.

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

## License

This project is provided for internal use. No license is specified.
