# Release v2.0.0 - SDK Test Forge

## Added

- `compile_tests` SDK linking parameters:
  - `sdk_include_dirs` — SDK header search paths
  - `sdk_lib_dirs` — library search paths
  - `link_libraries` — libraries to link (e.g. `calc`)
- `scan_headers` now scans `.hpp` files
- `delete_tests` recursively removes test files in subdirectories
- `test_sdk/` sample C library with example GTest (`examples/calc_test.cpp`)
- Global OpenCode registration docs in README and REGISTER_AGENT.md

## Fixed

- OpenCode agent `mode: edit` → `mode: all` (valid in current OpenCode)
- CI workflow: runs `pytest test_mcp_server.py` instead of missing `tests/` and `cli.py`
- Removed tracked `.omo/` development artifacts from repository

## Changed

- Extracted `_generate_cmake_content()` for testable CMake generation
- Production `requirements.txt` contains only `mcp` + `pydantic`
- Dev dependencies (`pytest`, `pytest-asyncio`) moved to `pyproject.toml` optional `[dev]`

## Upgrade

1. Pull latest `main` or checkout tag `v2.0.0`
2. Update `~/.config/opencode/opencode.json` MCP path if needed
3. Sync `~/.config/opencode/agents/forge.md` from `.opencode/agents/forge.md`
4. Restart OpenCode

## Verification

```bash
pip install -r requirements.txt pytest pytest-asyncio
python -m pytest test_mcp_server.py -v
```
