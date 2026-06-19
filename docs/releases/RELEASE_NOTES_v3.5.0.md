# Release Notes — v3.5.0 (Real SDK + Apply Loop)

Improvements from OpenCode/yaml-cpp real-world testing.

## Highlights

### Smarter probe
- Parse `add_library()` from CMakeLists.txt (fixes folder named `test` → wrong `link_libraries`)
- yaml-cpp now probes as `yaml-cpp`, not `test`

### Plan filtering for large SDKs
- Filter macro noise (`YAML_CPP_API`, `*_EXPORT`, etc.)
- `max_targets` on `suggest_test_plan` / `forge plan --max-targets N`

### Apply after confirmation
- `apply_test_fixes(confirm=true)` / `forge apply-fix --confirm`
- Writes cached proposals only after explicit user confirmation
- Workflow stage tracked in `.forge/cache/workflow.json`

## v3.5 workflow

```
plan(max_targets=20) → scaffold → gap → build → analyze → propose → user confirm → apply → report
```

---

Release title: **v3.5.0 — Real SDK & Apply Loop**
