# Release Notes — v3.6.0 (HTML Test Report)

Browser-openable test reports with an Agent-written analysis section.

## Highlights

### HTML report
- `forge_report(output_format=html)` generates a single static HTML file
- Default path: `.forge/cache/report.html` (override with `output_path`)
- Sections mirror markdown report: status badge, test results, coverage, failures, gap, proposals, etc.

### Agent analysis
- Pass `agent_summary` (Markdown or plain text) when calling `forge_report`
- Rendered as escaped paragraphs in an **Agent Analysis** section (no XSS)
- Agent workflow: build → analyze → write summary → `forge_report(format=html)` → tell user to open `html_path`

### CLI
```bash
forge report --format html --output ./report.html
forge report --format html --agent-summary-file analysis.md
```

### Session
- `get_session_context` returns `last_report_html` when the file exists

## v3.6 workflow

```
plan → scaffold → gap → build → analyze → propose → confirm → apply
→ Agent writes analysis → forge_report(format=html) → open html_path
```

---

Release title: **v3.6.0 — HTML Test Report**
