# Changelog

## [3.0.0] - 2026-06-19

### Added
- `sdk_forge/` core package shared by MCP and CLI
- `forge` CLI: scan, probe, compile, run, clean, coverage, mocks
- Scan result cache (`FORGE_SCAN_CACHE`, `use_cache` parameter)
- `conditional: true/false` on symbols inside `#ifdef` blocks
- `collect_coverage` MCP tool and `forge coverage` (gcov/lcov, Linux)
- `generate_mocks` MCP tool and `forge mocks` for virtual methods
- `compile_tests` `coverage` and `coverage_tool` parameters

## [2.5.0] - 2026-06-19

### Added
- libclang parsing, probe_sdk, pkg-config/find_package, GTest cache
- test_sdk_cpp fixture, Linux + Windows CI

## [2.0.0] - 2026-06-19

- SDK linking, test_sdk sample, CI fixes

## [1.0.0] - Initial release

- MCP server with scan/delete/compile/run tools
