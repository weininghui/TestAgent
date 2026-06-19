# Release Notes — v2.5.0

**Theme:** Real large SDK usable — libclang parsing, pkg-config/find_package linking, GTest cache, Windows CI.

## Highlights

### libclang header parsing
- `scan_headers` uses libclang AST when available (`pip install libclang>=16.0.0`)
- Falls back to regex parsing automatically
- New scan fields: namespaces, static/virtual method flags, parser metadata

### Real SDK linking
- `pkg_config_packages` — link via `pkg_check_modules`
- `find_packages` — CMake `find_package` with optional components/target
- `cmake_prefix_path` — locate installed SDK prefixes
- `extra_cmake_snippet` — inject advanced CMake fragments

### GTest cache
- Default cache: `~/.cache/sdk-test-forge/gtest` (Linux) or `%LOCALAPPDATA%\sdk-test-forge\gtest` (Windows)
- Override with `FORGE_GTEST_CACHE`
- `gtest_source`: `cached` (default), `fetch`, or `system`

### probe_sdk tool
- Input: SDK root directory or `.pc` file path
- Output: suggested `include_dirs`, `lib_dirs`, `link_libraries`, `pkg_config_packages`

### Fixtures & CI
- New `test_sdk_cpp/` — C++ SDK with namespace, templates, enum class, pkg-config
- CI: Linux integration (incl. pkg-config) + Windows MSVC integration
- GTest cache in GitHub Actions

## Upgrade

```bash
git pull
pip install -r requirements.txt
# Optional
pip install libclang>=16.0.0
```

Sync `.opencode/agents/forge.md` and skill to your `~/.config/opencode/` if using global registration.

## Breaking changes

None — v2.0 parameters remain supported; new parameters are optional.
