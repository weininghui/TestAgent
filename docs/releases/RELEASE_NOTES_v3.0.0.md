# Release Notes — v3.0.0

## Highlights

### Standalone CLI
```bash
forge scan ./sdk
forge compile ./tests ./build --link my_sdk
forge run ./build
forge mocks --sdk-root ./test_sdk_cpp
forge coverage ./build
```

### Core refactor
- Logic moved to `sdk_forge/` package
- `mcp_server.py` is a thin MCP wrapper — CLI and MCP share behavior

### v2.5.1 polish (included)
- `#ifdef` symbols tagged with `"conditional": true`
- Scan JSON cache with mtime-based invalidation

### Quality tools
- **Coverage:** `compile_tests(coverage=true)` + `collect_coverage` (Linux gcov/lcov)
- **Mocks:** `generate_mocks` / `forge mocks` for virtual methods

## Upgrade

```bash
git pull && pip install -r requirements.txt
```

Sync `forge.md` and skill to `~/.config/opencode/` if using global registration.

## Breaking changes

None for existing MCP parameters. New tools and CLI are additive.
