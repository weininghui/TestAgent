# Release Notes — v3.4.0 (Agent + Engineering)

Closes the v3.3 agent loop with plan/coverage gap analysis, confirmation-gated fix proposals, and build engineering helpers.

## Highlights

### Plan gap (`analyze_plan_gap`)
- Compare `suggest_test_plan` targets vs `tests/*_test.cpp` and TEST scenarios
- Optional coverage cache integration
- CLI: `forge gap --project-dir .`

### Fix proposals (`propose_test_fixes`)
- Builds on `analyze_test_failures` with `current` / `suggested` line pairs
- **`requires_confirmation: true`** — never auto-edits source
- CLI: `forge propose-fix <build_dir>`

### Engineering
- `sanitizer: asan | ubsan | asan+ubsan` in `.forge.yaml` / `forge compile --sanitizer`
- `compile_commands.json` exported to `.forge/cache/` after successful compile
- MCP: `get_compile_commands`, `export_compile_commands`

## v3.4 workflow

```
plan → scaffold → gap → build → analyze → propose → user confirm → Edit → report
```

---

Release title: **v3.4.0 — Plan Gap & Fix Proposals**
