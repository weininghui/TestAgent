# Release Notes — v3.1.0 (Real SDK Workflow)

v3.1 focuses on **agent-ready project workflow** for real SDKs: config file, environment checks, scaffolding, and one-shot build.

## Highlights

### Project config (`.forge.yaml` / `.forge.json`)
- Place config at project root; `compile_tests` walks up from `source_dir` to find it
- Keys: `sdk_root`, `tests_dir`, `build_dir`, `sdk_include_dirs`, `sdk_lib_dirs`, `link_libraries`, `pkg_config_packages`, `gtest_source`, `coverage`
- CLI override: `forge compile --no-config` skips config loading
- YAML requires optional `pip install sdk-test-forge[yaml]` (or `pyyaml`)

### `forge doctor`
Checks cmake, compiler (`g++`/`cl`), pkg-config, forge cache dirs, libclang, and `LIBCLANG_PATH` on Windows.

### `forge init <dir>`
Creates `tests/`, `build/`, sample `*_test.cpp`, and `.forge.yaml` template.

### `forge build`
One-shot: load config → `probe_sdk` → `compile_tests` → `run_tests`. Use `--no-run` to compile only.

## MCP tools (new)

| Tool | CLI equivalent |
|------|----------------|
| `forge_doctor` | `forge doctor` |
| `init_forge_project` | `forge init` |
| `build_tests` | `forge build` |

## Quick start

```bash
forge doctor
forge init ./my_sdk_tests --sdk-root /path/to/sdk
cd my_sdk_tests
# edit tests/*.cpp and .forge.yaml
forge build
```

## Example config

See `examples/forge_test_sdk/.forge.json`.

---

Release title: **v3.1.0 — Real SDK Workflow**
