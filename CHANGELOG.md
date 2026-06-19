# Changelog

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
