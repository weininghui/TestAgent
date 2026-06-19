# Release Notes — v3.2.0 (Agent Intelligence)

Turns SDK Test Forge from a toolchain into an **autonomous agent workflow**.

## Highlights

### Structured test plans (`suggest_test_plan`)
- Scan → scenarios (normal / boundary / error)
- Flags `needs_mock`, `conditional`, `suggested_compile_args`
- MCP + `forge plan <sdk>`

### Executable hint actions
- `compile_tests` / `build_tests` failures return `actions[]` alongside `hints[]`
- Types: `merge_link_libraries`, `merge_sdk_include_dirs`, `merge_sdk_lib_dirs`, etc.
- `apply_actions_to_params()` merges fixes into compile config

### Auto-retry build (`build_with_retry`)
- `build_tests(max_retries=3, auto_fix_config=true)`
- `forge build --retry 3 --auto-fix-config`
- Regenerates CMake, retries with merged probe + hint actions
- Returns `attempts[]`, `auto_fixed` trace

### Build reports
- `forge_report` / `forge report` → Markdown for PRs
- State cached in `.forge/cache/last_build.json`

## v3.2 Agent workflow

1. `forge_doctor`
2. `scan_headers` → `suggest_test_plan`
3. Write / refine tests
4. `build_tests(max_retries=3, auto_fix_config=true)`
5. `forge_report`

---

Release title: **v3.2.0 — Agent Intelligence**
