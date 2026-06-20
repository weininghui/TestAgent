# SDK Forge

**English** | [简体中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/weininghui/sdk-forge)](https://github.com/weininghui/sdk-forge/releases)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

OpenCode plugin and **standalone CLI** (`forge`) for scanning C/C++ SDK headers, generating GTest suites, compiling, and running tests against real SDK binaries.

**Current release: [v5.6.0](docs/releases/RELEASE_NOTES_v5.6.0.md)** — Sub-agent observability (session binding + CLI delegation).

Previous: [v5.3.0](docs/releases/RELEASE_NOTES_v5.3.0.md) — Autopilot step loop, parallel scan, dynamic enrich batch.

## What it does

1. **Probe** SDK layout (include / lib / pkg-config)
2. **Scan** headers (libclang optional + regex fallback)
3. **Plan & generate** GTest / GMock code (smart scaffold + Agent enrich)
4. **Quality gates** — placeholder ratio, assertion score, golden oracle
5. **Compile & run** with CMake; HTML report + structured JSON on failure

Works as an **OpenCode MCP plugin** (`sdk-forge`) or a **CLI** for scripts and CI.

## Installation & updates

**Three separate guides** (do not mix CLI install with OpenCode plugin update):

| Guide | Document |
|-------|----------|
| CLI only (terminal / CI) | [docs/INSTALL.md §1](docs/INSTALL.md#1-cli-only-no-opencode-plugin) |
| OpenCode plugin — **first install** | [docs/INSTALL.md §2](docs/INSTALL.md#2-opencode-plugin-first-install) |
| **Update** to latest release | [docs/INSTALL.md §3](docs/INSTALL.md#3-update-to-the-latest-release) |

简体中文：[docs/INSTALL.zh-CN.md](docs/INSTALL.zh-CN.md)

**Check version (use runtime, not only `pip show`):**

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"   # should match latest release
forge autopilot --help                                       # v5.1+ must list autopilot
```

OpenCode plugin directory (Windows): `%APPDATA%\OpenCode\plugins\sdk-forge`

After any update: `pip install -e .` in that directory, then **restart OpenCode completely**.

## Quick start (CLI)

```bash
git clone https://github.com/weininghui/sdk-forge.git`ncd sdk-forge
pip install -r requirements.txt
pip install -e .
```

Full CLI setup: [docs/INSTALL.md §1](docs/INSTALL.md#1-cli-only-no-opencode-plugin).

**Requirements:** Python 3.10+, CMake 3.14+, C++ compiler (g++/clang++/MSVC). `git` recommended for GTest prefetch.

Optional extras:

```bash
pip install "sdk-forge[clang]"   # libclang header parsing
pip install "sdk-forge[yaml]"    # .forge.yaml (JSON works without PyYAML)
```

## Quick start (OpenCode Agent)

1. **Install the plugin** — [docs/INSTALL.md §2](docs/INSTALL.md#2-opencode-plugin-first-install) (first time) or [§3](docs/INSTALL.md#3-update-to-the-latest-release) (update).
2. Select Agent **`forge`** in the chat dropdown.
3. Ask: *"Test `./examples/test_sdk_cpp` and give me the HTML report."*

Or use v5.1 autopilot: *"Run forge autopilot on `./examples/test_sdk_cpp` with production profile."*

Agent registration details: [docs/REGISTER_AGENT.md](docs/REGISTER_AGENT.md).

The orchestrator runs: `forge-env` → `forge-scan` → `forge-scaffold` → parallel `forge-enrich` → `forge-review` → `forge-build`.

Agent docs: [`.opencode/agents/forge.md`](.opencode/agents/forge.md) · Skill: [`.opencode/skills/test-forge/SKILL.md`](.opencode/skills/test-forge/SKILL.md)

## Autopilot (v5.1)

Provide only an SDK path — the orchestrator runs the full pipeline with automatic enrich retries:

```bash
forge autopilot ./examples/test_sdk_cpp --profile production
# or MCP: run_forge_autopilot(sdk_root=..., profile=production)
```

| Phase | Behavior |
|-------|----------|
| init / env / scan / scaffold | Programmatic (no LLM) |
| enrich | Agent executes `next_actions`; **assertion gate auto-retries** weak files up to `max_enrich_rounds` |
| review → build | `forge-review` then `forge-build --profile production` |
| post-build | Optional `golden snapshot` from generated `EXPECT_EQ` |

```yaml
# .forge.yaml autopilot options (v5.1)
max_enrich_rounds: 3          # default 1 = v5.0 single-round behavior
autopilot_profile: production
auto_golden_snapshot: true
```

## Production workflow (v5.0+)

For merge-ready tests, use the **production profile**:

```bash
forge golden init --project-dir ./my_tests    # create .forge/golden.yaml template
# edit golden.yaml with expected values for core APIs
forge assert-quality --project-dir ./my_tests
forge build --project-dir ./my_tests --profile production
```

| Gate | What it checks |
|------|----------------|
| Scaffold quality | Placeholder / AGENT ratio |
| Assertion quality | Weak tests, tautology, remaining `// AGENT:` |
| Golden oracle | Expected values in `.forge/golden.yaml` |
| Coverage (production) | Line coverage ≥ 80% (Linux gcov) |

Checklist: [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md)

### Sample `.forge.yaml`

```yaml
sdk_root: ../examples/test_sdk_cpp
tests_dir: tests
build_dir: build

sdk_include_dirs:
  - ../examples/test_sdk_cpp/include
sdk_lib_dirs:
  - ../examples/test_sdk_cpp/build
link_libraries:
  - my_sdk

gtest_source: auto
gtest_version: auto

# Multi-agent enrich batch size (v4.6)
multi_agent_batch_size: 4

# Production merge gate (v5.0) — or: forge build --profile production
# forge_profile: production
# min_assertion_score: 80
# block_weak_tests: true
# block_agent_markers: true
```

JSON config: [`examples/forge_test_sdk/.forge.json`](examples/forge_test_sdk/.forge.json)

## CLI reference

| Command | Description |
|---------|-------------|
| `forge doctor` | Check cmake, compiler, caches, GTest |
| `forge setup-toolchain --confirm` | Auto-install MSVC / MinGW / g++ (Agent: MCP `ensure_forge_environment`) |
| `forge init <dir>` | Scaffold `tests/`, `build/`, `.forge.yaml`, golden template |
| `forge plan <sdk>` | Structured test plan from scan |
| `forge scaffold <sdk>` | Generate tests (`--fidelity smart`) |
| `forge enrich` | Agent enrichment briefs (`--test-files`) |
| `forge quality` | Scaffold placeholder ratio |
| `forge assert-quality` | Semantic assertion score (v5.0) |
| `forge golden init\|verify\|snapshot` | Golden oracle template / verify / snapshot from tests (v5.1) |
| `forge autopilot <sdk>` | Hands-off orchestration entry (v5.1) |
| `forge build` | Probe + compile + run + HTML report (`--profile production`, `--retry 3`) |
| `forge bench` | Benchmark plan→scaffold→quality→build |
| `forge gap` | Plan vs tests / coverage gap |
| `forge analyze` / `propose-fix` / `apply-fix` | Failure analysis and fixes |
| `forge report` | Markdown / HTML / JSON report |
| `forge session` | Session + orchestration context JSON |
| `forge scan` / `probe` / `compile` / `run` / `coverage` / `mocks` / `clean` | Lower-level steps |

All commands emit JSON to stdout. Exit codes: `0` ok, `1` test failures, `2` error.

## MCP tools (OpenCode / Cursor)

| MCP tool | CLI equivalent |
|----------|----------------|
| `ensure_forge_environment` | `forge setup-toolchain` + doctor |
| `scan_headers` | `forge scan` |
| `suggest_test_plan` | `forge plan` |
| `generate_test_skeleton` | `forge scaffold` |
| `enrich_test_cases` | `forge enrich` |
| `analyze_assertion_quality` | `forge assert-quality` |
| `load_golden_cases` / `verify_golden_coverage` / `snapshot_golden_cases` | `forge golden` |
| `run_forge_autopilot` | `forge autopilot` |
| `build_tests` | `forge build` |
| `get_session_context` | `forge session` (includes `orchestration`) |
| `record_agent_run` | Multi-agent completion tracking |
| `forge_report` | `forge report` |

Full list and registration: [REGISTER_AGENT.md](docs/REGISTER_AGENT.md)

## Multi-agent architecture (v4.6+, v5.5 background delegation)

Primary **forge** dispatches sub-agents via oh-my-openagent `task(run_in_background=true)` for parallel enrich/scan batches, then `background_output` → `advance_forge_workflow`. See [docs/DELEGATION.md](docs/DELEGATION.md).

| Agent | Role |
|-------|------|
| `forge` (primary) | Orchestrator — dispatches sub-agents via `task()` |
| `forge-env` | Toolchain + doctor |
| `forge-scan` | Scan + plan |
| `forge-scaffold` | Smart skeleton |
| `forge-enrich` | Parallel AGENT marker completion |
| `forge-review` | Production readiness checklist (v5.0) |
| `forge-build` | Compile, run, fix loop |

Sub-agents live in [`.opencode/agents/`](.opencode/agents/).

## Example SDKs

| Directory | Description |
|-----------|-------------|
| [`examples/test_sdk/`](examples/test_sdk/) | C library (`calc`) |
| [`examples/test_sdk_cpp/`](examples/test_sdk_cpp/) | C++ namespace, virtual methods |
| [`examples/test_sdk_medium/`](examples/test_sdk_medium/) | Multi-module, `#ifdef`, pkg-config |
| [`examples/yaml_cpp_bench/`](examples/yaml_cpp_bench/) | Benchmark fixture |
| [`examples/forge_test_sdk/`](examples/forge_test_sdk/) | Sample `.forge.json` |

Build a fixture SDK: see [examples/README.md](examples/README.md).

## Project layout

```
sdk-forge/
├── sdk_forge/          # Python package (CLI + core)
├── mcp_server.py       # OpenCode MCP entry
├── tests/              # pytest suite
├── examples/           # Sample SDKs
├── docs/               # Agent docs, release notes, checklists
├── .opencode/          # Agent prompts + skill
├── plugin.yaml         # OpenCode plugin manifest
└── README.md / README.zh-CN.md
```

## Capability matrix

| Feature | MCP | CLI | Since |
|---------|-----|-----|-------|
| Production profile | `build_tests(profile=production)` | `forge build --profile production` | v5.0 |
| Assertion quality gate | `analyze_assertion_quality` | `forge assert-quality` | v5.0 |
| Golden oracle | `load_golden_cases` | `forge golden` | v5.0 |
| Multi-agent orchestration | `get_session_context` | — | v4.6 |
| Parallel enrich batches | `enrich_test_cases(test_files=...)` | `forge enrich --test-files` | v4.6 |
| Auto toolchain | `ensure_forge_environment` | `forge setup-toolchain --confirm` | v4.5 |
| Quality gate | `build_tests` | `forge build --skip-quality-gate` | v4.1 |
| Smart codegen + enrich | `generate_test_skeleton` / `enrich_test_cases` | `forge scaffold` / `forge enrich` | v4.0 |
| Session / plan gap / fixes | `get_session_context` / `analyze_plan_gap` | `forge session` / `forge gap` | v3.4 |
| HTML report | `forge_report` | `forge report --format html` | v3.6 |
| GTest auto-download | compile JSON `gtest_tag` | `--gtest-source auto` | v3.1 |

Full matrix: previous releases in [CHANGELOG.md](CHANGELOG.md).

## Conventions

- **Agent replies:** Chinese by default; say "reply in English" in chat to switch.
- **Code comments:** bilingual for public APIs — [docs/CONVENTIONS.md](docs/CONVENTIONS.md).

## Development

```bash
# Unit tests (no cmake required)
python -m pytest tests/ -v -k "not TestCompileAndRun and not TestCliIntegration"

# Full suite (cmake + compiler)
python -m pytest tests/ -v
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `cmake not found` | Install CMake, add to `PATH` |
| `compiler_not_found` | Run `forge setup-toolchain --confirm` or MCP `ensure_forge_environment` |
| `assertion_quality_blocked` | Run `forge assert-quality`; fix weak tests / AGENT markers |
| `undefined reference` | Add `link_libraries`; run `forge probe` |
| GTest download fails | Install git; `forge doctor`; pin `gtest_version: 1.14.0` |
| Coverage unsupported | gcov is Linux-only |
| libclang misses symbols | Set `LIBCLANG_PATH`; add `compile_args: ["-DFEATURE_X"]` |

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/INSTALL.md](docs/INSTALL.md) | **Install & update** OpenCode plugin + CLI |
| [docs/INSTALL.zh-CN.md](docs/INSTALL.zh-CN.md) | 安装与更新（中文） |
| [docs/REGISTER_AGENT.md](docs/REGISTER_AGENT.md) | OpenCode / MCP registration |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent prompt source |
| [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) | Pre-merge checklist |
| [docs/releases/](docs/releases/) | Release notes |
| [CHANGELOG.md](CHANGELOG.md) | Full changelog |

## Releases

- [All releases](https://github.com/weininghui/sdk-forge/releases)
- Latest: [RELEASE_NOTES_v5.3.0.md](docs/releases/RELEASE_NOTES_v5.3.0.md)

## License

MIT — see [LICENSE](LICENSE).
