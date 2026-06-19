# Release Notes — v3.6.1 (Auto HTML Report)

Simpler workflow for testers — no manual `forge_report` call.

## Highlights

### Auto report after build
- `build_tests` / `forge build` now auto-generates `.forge/cache/report.html`
- Response includes `html_path` — tell testers to open it in a browser
- Summary section **测试摘要** is filled automatically (pass/fail counts, failure names)

### Opt out
```yaml
auto_report: false   # in .forge.yaml
```

### Optional manual report
`forge_report` still works when you need to regenerate or add extra notes via `agent_summary`.

---

Release title: **v3.6.1 — Auto HTML Report**
