# AGENTS.md — SDK Forge

Cursor and human contributors: start here for project context.

## What this repo is

**SDK Forge** — OpenCode MCP plugin + standalone CLI (`forge`) for scanning C/C++ SDK headers, generating GTest suites, compiling, and running tests.

- **Package:** `sdk-forge` (import `sdk_forge`)
- **GitHub:** [weininghui/TestAgent](https://github.com/weininghui/TestAgent)
- **Local path (dev):** `E:\vs_test\AINew\aiagent-main`

## Cursor workflow

1. Open this repo as the Cursor workspace
2. Describe the change (feature, fix, docs, release)
3. Agent runs tests, edits code, updates docs as needed
4. User confirms → commit/push on request

Cursor rules: [.cursor/rules/sdk-forge.mdc](.cursor/rules/sdk-forge.mdc)

## Key docs

| Doc | Purpose |
|-----|---------|
| [README.md](README.md) | Project overview (English) |
| [README.zh-CN.md](README.zh-CN.md) | 项目概览（中文） |
| [docs/INSTALL.md](docs/INSTALL.md) | Install & update CLI + OpenCode plugin |
| [docs/REGISTER_AGENT.md](docs/REGISTER_AGENT.md) | OpenCode agent registration |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | Bilingual comments, doc sync |
| [docs/MIGRATION_v5.11.md](docs/MIGRATION_v5.11.md) | v5.11 layered import migration |
| [RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) | Release checklist |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributor guide |
| [docs/GITHUB_REPO_RENAME.md](docs/GITHUB_REPO_RENAME.md) | Rename TestAgent → sdk-forge on GitHub |
| [docs/AGENTS.md](docs/AGENTS.md) | **OpenCode forge agent** system prompt source (not Cursor) |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## Architecture (v5.11+)

```
sdk_forge/
  domain/        # models, util
  orchestration/ # workflow core
  delegation/    # task dispatch, session nav, health
  pipeline/      # scan, build, enrich, scaffold
  infra/         # config, gtest, doctor
  cli.py         # forge CLI entry
mcp_server.py    # MCP tool definitions
.opencode/       # OpenCode agents + sdk-forge skill
```

## Common commands

```bash
pip install -e .
forge doctor
forge autopilot --help
python -m pytest tests/ -v -k "not TestCompileAndRun"
```

## Release (summary)

```powershell
scripts\release.ps1 -Version 5.12.0
# Edit RELEASE_NOTES, CHANGELOG, README links
python -m pytest tests/ -v
git tag v5.12.0
git push origin main --tags
scripts\update-opencode-plugin.ps1 -Ref v5.12.0
```

Full steps: [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md)

## OpenCode forge agent

The **forge** orchestrator agent prompt is maintained in:

- [.opencode/agents/forge.md](.opencode/agents/forge.md) (runtime)
- [docs/AGENTS.md](docs/AGENTS.md) (source copy for registration docs)

Sub-agents: `forge-env`, `forge-scan`, `forge-scaffold`, `forge-oracle`, `forge-enrich`, `forge-review`, `forge-build`.
