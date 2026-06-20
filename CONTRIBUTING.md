# Contributing to SDK Forge

Thank you for improving SDK Forge.

## Setup

```bash
git clone https://github.com/weininghui/TestAgent.git
cd TestAgent
pip install -r requirements.txt
pip install -e ".[dev]"
pre-commit install
```

## Before opening a PR

```bash
# Fast tests
python -m pytest tests/ -v -k "not TestCompileAndRun and not TestCoveragePipeline and not TestCliIntegration"

# Lint (optional but recommended)
ruff check sdk_forge mcp_server.py run_mcp.py tests
ruff format --check sdk_forge mcp_server.py run_mcp.py tests
```

## Conventions

- Read [docs/CONVENTIONS.md](docs/CONVENTIONS.md) — bilingual docstrings, default 中文 for user-facing agent replies
- v5.11+ layered imports — see [docs/MIGRATION_v5.11.md](docs/MIGRATION_v5.11.md)
- Sync OpenCode docs when changing MCP tools or forge orchestration (see [docs/CONVENTIONS.md](docs/CONVENTIONS.md#文档同步--doc-sync))

## Releases

Maintainers: [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md)

## Repo rename note

Canonical GitHub name is `sdk-forge`; live repo may still be `TestAgent`. See [docs/GITHUB_REPO_RENAME.md](docs/GITHUB_REPO_RENAME.md).
