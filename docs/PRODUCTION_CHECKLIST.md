# Production Readiness Checklist

Use before merging generated tests into your main branch.

## Autopilot one-shot (v5.1)

```bash
forge autopilot /path/to/sdk --profile production
# Agent executes returned next_actions until merge_ready
```

Or step-by-step:

```bash
forge assert-quality --project-dir ./my_tests
forge golden verify --project-dir ./my_tests
forge build --project-dir ./my_tests --profile production
forge golden snapshot --project-dir ./my_tests --confirm
```

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
| Reliability | `forge health --project-dir ./my_tests` — no unhealthy pending delegations; see [RELIABILITY.md](RELIABILITY.md) |
| Audit trail | `.forge/cache/audit.jsonl` exists after autopilot; `run_id` in CLI/MCP JSON for correlation |

## Reliability (v5.12+)

```bash
forge health --project-dir ./my_tests
forge health --project-dir ./my_tests --auto-recover   # force retry stalled sub-agents
forge session --project-dir ./my_tests                 # includes recent_audit
```

See [RELIABILITY.md](RELIABILITY.md) for logging, auto-recovery, and error codes.

## `.forge.yaml` production profile

```yaml
forge_profile: production
max_enrich_rounds: 3
autopilot_profile: production
auto_golden_snapshot: true
delegation_auto_recovery: true
# or use CLI: forge build --profile production
```

## Multi-agent / autopilot flow

```
run_forge_autopilot(sdk_root)
  → forge-enrich (parallel batches, auto-retry on assertion fail)
  → forge-review (readiness checklist)
  → forge-build (--profile production)
  → golden snapshot (optional)
```

## When blocked

1. Read `assertion_gate.block_reasons` or HTML **断言质量** section
2. Fix listed tests or add `.forge/golden.yaml` cases
3. Re-run `forge assert-quality` until score ≥ 80
4. Retry `forge build --profile production` or re-run `forge autopilot`
