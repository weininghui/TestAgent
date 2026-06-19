# Release Notes — v5.0.0 (Production Quality)

Consolidates **v4.7–v5.0**: semantic assertion gate, golden oracle, codegen depth, coverage loop, forge-review agent.

## v4.7 — Semantic Quality Gate

- `analyze_assertion_quality` — weak / tautology / AGENT detection, score 0–100
- `forge_profile: production` / `forge build --profile production`
- Assertion gate blocks before compile when score too low
- HTML report **断言质量** section

## v4.8 — Golden Oracle

- `.forge/golden.yaml` — expected values per symbol/scenario
- `load_golden_cases`, `verify_golden_coverage` MCP
- `forge golden init|verify` CLI
- enrich briefs include `oracle_hints`; codegen prefers golden `EXPECT_EQ`

## v4.9 — Codegen Depth

- Golden-driven assertions in smart scaffold
- Enum member assertions from scan data
- Improved error paths (sanitizer metadata from plan)
- Reduced `SUCCEED()` / AGENT fallbacks

## v5.0 — Coverage + Review

- Production pipeline: coverage collect → expand → coverage gate
- **`forge-review`** subagent — Production Readiness Checklist (中文)
- Orchestrator: enrich → review → build
- CI: `forge assert-quality` smoke job
- [PRODUCTION_CHECKLIST.md](../PRODUCTION_CHECKLIST.md)

## Upgrade

```bash
pip install -e .
# Copy .opencode/agents/forge-review.md
forge golden init --project-dir ./my_tests
forge build --project-dir ./my_tests --profile production
```

---

Release title: **v5.0.0 — Production Quality**
