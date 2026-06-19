# Changelog

## [3.6.2] - 2026-06-19

Conventions: bilingual code comments and Chinese-first Agent replies.

### Added
- `docs/CONVENTIONS.md` — communication language + bilingual comment guidelines
- Agent docs: default Chinese; English only when user asks in chat

### Changed
- Updated `docs/AGENTS.md`, `forge.md`, `SKILL.md` with language policy
- Bilingual module docstrings on report/pipeline/session/workflow modules

## [3.6.1] - 2026-06-19

Auto-generate HTML test report after `build_tests` — no manual `forge_report` for testers.

### Added
- `build_auto_summary` / `auto_generate_report` — tester-friendly Chinese summary
- `build_pipeline_impl` attaches `html_path` and `report` after every build (default on)
- `.forge.yaml` `auto_report: false` to disable

### Changed
- HTML summary section title: **测试摘要** (was Agent Analysis)
- Agent docs: testers only need `build_tests` → open `html_path`

## [3.6.0] - 2026-06-19

HTML test reports with Agent analysis section.

### Added
- `sdk_forge/report_html.py` — single-file HTML report with embedded CSS
- `forge_report(output_format=html, agent_summary=..., output_path=...)` — MCP + CLI
- CLI: `forge report --format html`, `--agent-summary`, `--agent-summary-file`
- Session context: `last_report_html` when `.forge/cache/report.html` exists
- Report state enrichment refactored via `_enrich_report_state` (shared markdown/html)

### Changed
- `forge_report` advances workflow stage to `report` on successful HTML generation

## [3.5.0] - 2026-06-19

Real SDK adaptations and confirmation-gated apply loop.

### Added
- CMake `add_library` parsing in `probe_sdk` (fixes wrong link name when clone dir ≠ project name)
- Plan noise filter (`YAML_CPP_API`, macro-like symbols) and `max_targets` limit
- `apply_test_fixes` / `forge apply-fix --confirm` — write proposals after explicit confirmation
- `sdk_forge/workflow.py` — stage tracking in `.forge/cache/workflow.json`
- MCP: `apply_test_fixes`; `suggest_test_plan(max_targets=...)`

### Fixed
- Probe no longer suggests `link_libraries: ["test"]` for SDKs cloned into arbitrary folders

## [3.4.0] - 2026-06-19

Plan gap analysis, confirmation-gated fix proposals, sanitizers, compile_commands.

### Added
- `sdk_forge/plan_gap.py` — `analyze_plan_gap` / `forge gap`
- `propose_test_fixes` — assertion edit proposals with `requires_confirmation: true`
- `sdk_forge/compdb.py` — export/read `compile_commands.json` cache
- MCP: `analyze_plan_gap`, `propose_test_fixes`, `get_compile_commands`, `export_compile_commands`
- CLI: `forge gap`, `forge propose-fix`, `forge compdb`, `forge session`
- `sanitizer` compile param (asan/ubsan; graceful degrade on MSVC)
- Report: coverage, plan gap, proposed fixes sections
- Session context: `plan_gap`, `last_proposals`, `compile_commands`
- CI: E2E scaffold→analyze pipeline, ASan smoke on Linux

## [3.3.1] - 2026-06-19

Project layout cleanup — no functional API changes.

### Changed
- Sample SDK fixtures moved to `examples/` (`test_sdk`, `test_sdk_cpp`, `test_sdk_medium`)
- Release notes moved to `docs/releases/`
- Agent docs moved to `docs/` (`AGENTS.md`, `REGISTER_AGENT.md`)
- Tests moved to `tests/`; pytest `testpaths` configured in `pyproject.toml`
- README: project layout section and updated fixture paths

## [3.3.0] - 2026-06-19

Agent continuation — test scaffolding, failure learning, GTest analyze, session context.

### Added
- `sdk_forge/templates.py` — `generate_test_skeleton` / `forge scaffold`
- `sdk_forge/learn.py` — persist successful compile params; merge on next build
- `sdk_forge/test_fix.py` — `analyze_test_failures` / `forge analyze`
- `sdk_forge/session.py` — `get_session_context`, `last_plan.json` cache
- MCP: `generate_test_skeleton`, `analyze_test_failures`, `get_session_context`, `get_learned_config`, `forget_learned_config`
- Report: failed test summary + learned config section

## [3.2.0] - 2026-06-19

Agent intelligence — structured test plans, executable hint actions, and auto-retry build.

### Added
- `sdk_forge/hint_actions.py` — CMake errors → machine-readable `actions`
- `sdk_forge/plan.py` — `suggest_test_plan` with per-symbol scenarios
- `sdk_forge/retry.py` — `build_with_retry_impl` with auto-fix loop
- `sdk_forge/report.py` — `forge report` Markdown summaries
- MCP: `suggest_test_plan`, `forge_report`, `get_build_state`
- CLI: `forge plan`, `forge report`, `forge build --retry N --auto-fix-config`
- `compile_tests` cmake_error responses include `actions`
- `apply_actions_to_params` / `save_forge_config` in config.py
- Build state cache at `.forge/cache/last_build.json`

## [3.1.1] - 2026-06-19

### Added
- GTest auto-download with toolchain-based version selection (`sdk_forge/gtest.py`)
- `gtest_source: auto` (default) — git clone to cache, then compile
- `gtest_version: auto` or pin (`1.14.0`, `v1.13.0`, …)
- `forge doctor` checks/prepares googletest cache
- Compile JSON includes `gtest_tag`, `gtest.method`

## [3.1.0] - 2026-06-19

Real SDK workflow — project config, environment diagnostics, and one-shot build.

### Added
- `.forge.yaml` / `.forge.yml` / `.forge.json` project config (`sdk_forge/config.py`)
- `compile_tests` auto-loads forge config from parent walk (`use_config` flag)
- `forge doctor` / `forge_doctor` — cmake, compiler, cache, libclang checks
- `forge init` / `init_forge_project` — scaffold `tests/`, `build/`, `.forge.yaml`
- `forge build` / `build_tests` — probe + compile + run pipeline
- Example `examples/forge_test_sdk/.forge.json`
- Optional `pyyaml` extra for YAML config

## [3.0.9] - 2026-06-19

v3.0 stable — aggregates v3.0.1 through v3.0.8 patch improvements.

### Added (v3.0.1–v3.0.8)
- CLI integration tests; Windows `x64/Debug/run_tests.exe` discovery
- Scan cache mtime invalidation; conditional class/enum tests; optional libclang CI
- `sdk_forge/errors.py` CMake hints; `forge compile --from-probe`
- Linux coverage pipeline + lcov CI artifact
- Mock e2e for `test_sdk_cpp`; `mock_<Class>.hpp` naming
- `test_sdk_medium/` fixture (multi-namespace, virtual, `#ifdef`, pkg-config)
- Agent failure-recovery docs; compile `compile_duration_sec` timing
- README v3.0.x capability matrix

## [3.0.0] - 2026-06-19

- `sdk_forge/` package, `forge` CLI, coverage, mocks, scan cache, conditional flags

## [2.5.0] - 2026-06-19

- libclang, probe_sdk, pkg-config, GTest cache, test_sdk_cpp, Windows CI

## [2.0.0] - 2026-06-19

- SDK linking, test_sdk, CI fixes

## [1.0.0] - Initial release
