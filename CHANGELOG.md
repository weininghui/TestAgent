# Changelog

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
