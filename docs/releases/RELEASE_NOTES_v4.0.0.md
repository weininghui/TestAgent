# Release Notes — v4.0.0 (Smart Test Codegen)

Consolidates the v3.7–v4.0 roadmap: rule-based assertions + Agent enrichment + coverage expand.

## Highlights

### v3.7 — Smart scaffold (`fidelity=smart`)
- `sdk_forge/codegen.py` generates real `EXPECT_EQ` / `EXPECT_DOUBLE_EQ` for int/float/string APIs
- Infers add/sub/mul/div from symbol names (e.g. `calc_add(2, 3) == 5`)
- Unknown types get `// AGENT:` markers for OpenCode Agent to fill

```bash
forge scaffold ./sdk --fidelity smart --overwrite
```

### v3.8 — Full dimensions
- Plan: enum targets, overflow, empty_input, lifecycle scenarios, TEST_P flag
- Codegen: parameterized tests, enum member assertions, class construction/copy/destructor
- Gap analysis reports placeholder counts per file

### v3.9 — Agent enrichment loop
- `enrich_test_cases` — header excerpts, compile macros, AGENT marker line numbers
- `analyze_scaffold_quality` — `placeholder_ratio`; block build if > 50% without enrichment
- Session includes `scaffold_quality`

```bash
forge enrich --project-dir .
forge quality --project-dir .
```

### v4.0 — Complex scenarios
- `coverage_expand` — append TEST_P blocks for low-coverage symbols
- `group_by_header` — TEST_F fixture smoke tests per header
- HTML report **用例质量** section

## v4.0 workflow

```
scan → plan → scaffold(smart) → enrich → Agent Edit → quality check
→ build_tests → html_path → (optional) coverage_expand → rebuild
```

---

Release title: **v4.0.0 — Smart Test Codegen**
