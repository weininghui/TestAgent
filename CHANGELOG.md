# Changelog

## [2.5.0] - 2026-06-19

### Added
- libclang-based header parsing with regex fallback (`scan_headers` `include_dirs`, `compile_args`, `use_clang`)
- `probe_sdk` MCP tool for SDK / pkg-config discovery
- `compile_tests` extensions: `cmake_prefix_path`, `find_packages`, `pkg_config_packages`, `extra_cmake_snippet`, `gtest_source`
- GTest FetchContent cache (`FORGE_GTEST_CACHE`, default under `~/.cache/sdk-test-forge/gtest`)
- `test_sdk_cpp/` C++ fixture with namespace, class, templates, and `.pc` file
- Linux + Windows MSVC CI integration jobs with GTest cache
- Optional `[clang]` dependency (`libclang>=16.0.0`)

### Fixed
- Subprocess output decoding uses UTF-8 with `errors=replace` on all platforms
- `run_tests` binary discovery for Windows MSVC output directories

## [2.0.0] - 2026-06-19

### Added
- SDK linking parameters for `compile_tests`
- `test_sdk/` sample project
- 22 pytest cases including CMake generation and test_sdk integration

### Fixed
- Invalid OpenCode agent mode (`edit` → `all`)
- Broken GitHub Actions CI configuration

### Removed
- Tracked `.omo/` development artifacts

## [1.0.0] - Initial release

- MCP server with scan/delete/compile/run tools
- OpenCode forge agent and test-forge skill
- plugin.yaml project-level registration
