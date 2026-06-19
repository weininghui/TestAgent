# Release Notes — v3.3.0 (Agent Continuation)

Extends v3.2 with scaffolding, cross-session learning, and test-failure analysis.

## Highlights

### Test skeleton (`generate_test_skeleton`)
- Generates compilable `*_test.cpp` from `suggest_test_plan`
- CLI: `forge scaffold <sdk> --output tests/`

### Failure learning
- Successful `build_tests` saves compile params to `.forge/cache/learned/{hash}.json`
- Next build merges learned link/include paths before retry loop
- MCP: `get_learned_config`, `forget_learned_config`

### GTest analyze (`analyze_test_failures`)
- Parses Expected/Actual from GTest output
- Returns `review_assertion` actions for Agent Edit (no auto source rewrite)
- CLI: `forge analyze <build_dir>`

### Session context
- `get_session_context(project_dir)` — plan + build state + learned config + report summary
- `suggest_test_plan(..., project_dir=...)` saves `last_plan.json`

## v3.3 workflow

```
scan → plan → scaffold → build_tests(retry=3) → analyze (if needed) → report
```

---

Release title: **v3.3.0 — Agent Continuation**
