# Production Readiness Checklist

Use before merging generated tests into your main branch.

## CLI one-shot

```bash
forge assert-quality --project-dir ./my_tests
forge golden verify --project-dir ./my_tests
forge build --project-dir ./my_tests --profile production
```

## Checklist

| Item | Pass criteria |
|------|----------------|
| No `// AGENT:` / `// TODO:` | `assert-quality` score ≥ 80, zero agent markers |
| No weak tests | No `SUCCEED()`-only or `EXPECT_TRUE(true)` bodies |
| No tautology | No `EXPECT_EQ(expr, expr)` self-comparisons |
| Golden coverage | `forge golden verify` — core APIs have expected values |
| Tests compile & run | `build_tests status=ok` |
| Coverage (production) | Line coverage ≥ 80% or documented gap |
| HTML report | Open `.forge/cache/report.html` — Assertion Quality section green |

## `.forge.yaml` production profile

```yaml
forge_profile: production
# or use CLI: forge build --profile production
```

## Multi-agent flow

```
forge-enrich (parallel batches)
  → forge-review (readiness checklist)
  → forge-build (--profile production)
```

## When blocked

1. Read `assertion_gate.block_reasons` or HTML **断言质量** section
2. Fix listed tests or add `.forge/golden.yaml` cases
3. Re-run `forge assert-quality` until score ≥ 80
4. Retry `forge build --profile production`
