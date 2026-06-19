# Release Notes — v3.1.1 (GTest Auto-Download)

Builds on v3.1.0 project workflow with toolchain-aware googletest download before compile.

## Highlights

### GTest auto-download
- Default `gtest_source: auto` — detect compiler, pick tag (`v1.14.0` / `v1.13.0` / `v1.12.0`)
- `git clone` into forge cache, then `add_subdirectory` in generated CMake
- Fallback to CMake `FetchContent` when git prefetch fails
- `forge doctor` reports recommended tag and cache path

### Config keys
```yaml
gtest_source: auto
gtest_version: auto   # or pin: 1.14.0
```

Compile JSON returns `gtest_tag`, `gtest.method`.

## Also in this release line (v3.1.0)
- `.forge.yaml` / `.forge.json` project config
- `forge doctor` / `forge init` / `forge build`
- MCP: `forge_doctor`, `init_forge_project`, `build_tests`

---

Release title: **v3.1.1 — GTest Auto-Download**
