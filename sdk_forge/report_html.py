"""HTML report generation from build results."""

from __future__ import annotations

import html
from typing import Any

from sdk_forge.test_fix import parse_test_failures

_CSS = """
body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 2rem; color: #1a1a1a; line-height: 1.5; }
h1 { margin-bottom: 0.25rem; }
.meta { color: #555; margin-bottom: 1.5rem; }
.badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 999px; font-weight: 600; font-size: 0.9rem; }
.badge-ok { background: #d1fae5; color: #065f46; }
.badge-fail { background: #fee2e2; color: #991b1b; }
.badge-warn { background: #fef3c7; color: #92400e; }
section { margin: 1.5rem 0; }
table { border-collapse: collapse; width: 100%; max-width: 40rem; }
th, td { border: 1px solid #ddd; padding: 0.5rem 0.75rem; text-align: left; }
th { background: #f3f4f6; }
ul { padding-left: 1.25rem; }
li { margin: 0.35rem 0; }
code { background: #f3f4f6; padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.9em; }
.agent-analysis { background: #eff6ff; border-left: 4px solid #3b82f6; padding: 1rem 1.25rem; border-radius: 4px; }
.agent-analysis p { margin: 0.5rem 0; }
.footer { margin-top: 2rem; color: #888; font-size: 0.85rem; }
@media print { body { margin: 1rem; } }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _badge_class(status: str) -> str:
    if status == "ok":
        return "badge-ok"
    if status == "test_failures":
        return "badge-warn"
    return "badge-fail"


def _section(title: str, body: str) -> str:
    if not body.strip():
        return ""
    return f"<section><h2>{_esc(title)}</h2>{body}</section>"


def _agent_analysis_html(agent_summary: str) -> str:
    text = (agent_summary or "").strip()
    if not text:
        return ""
    paragraphs = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        paragraphs.append("<p>" + "<br>".join(_esc(ln) for ln in lines) + "</p>")
    if not paragraphs:
        return ""
    return _section("Agent Analysis", f'<div class="agent-analysis">{"".join(paragraphs)}</div>')


def format_report_html(state: dict[str, Any], agent_summary: str = "") -> str:
    status = state.get("status", "unknown")
    run = state.get("run") or {}
    compile_info = state.get("compile") or {}

    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>SDK Test Forge Report</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        "<h1>SDK Test Forge Report</h1>",
        f'<p class="meta"><span class="badge {_badge_class(status)}">{_esc(status)}</span></p>',
    ]

    meta_items = []
    for key, label in (("sdk_root", "SDK"), ("source_dir", "Tests"), ("build_dir", "Build")):
        if state.get(key):
            meta_items.append(f"<li><strong>{label}:</strong> <code>{_esc(state[key])}</code></li>")
    if meta_items:
        parts.append(f"<ul>{''.join(meta_items)}</ul>")

    parts.append(_agent_analysis_html(agent_summary))

    if run:
        results = (
            "<table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
            f"<tr><td>Total</td><td>{_esc(run.get('total', 0))}</td></tr>"
            f"<tr><td>Passed</td><td>{_esc(run.get('passed', 0))}</td></tr>"
            f"<tr><td>Failed</td><td>{_esc(run.get('failed', 0))}</td></tr>"
            "</tbody></table>"
        )
        parts.append(_section("Test Results", results))

    coverage_pct = run.get("line_coverage_pct")
    if coverage_pct is None:
        coverage_pct = state.get("line_coverage_pct") or compile_info.get("line_coverage_pct")
    cached_cov = state.get("coverage") or {}
    if coverage_pct is None and cached_cov.get("line_coverage_pct") is not None:
        coverage_pct = cached_cov.get("line_coverage_pct")
    if coverage_pct is not None:
        cov_body = f"<p>Line coverage: <strong>{_esc(coverage_pct)}%</strong></p>"
        if cached_cov.get("html_report_dir"):
            cov_body += f'<p>Coverage HTML: <code>{_esc(cached_cov["html_report_dir"])}</code></p>'
        parts.append(_section("Coverage", cov_body))

    if run.get("status") == "test_failures":
        analysis = parse_test_failures(run)
        if analysis.get("failures"):
            items = []
            for item in analysis["failures"][:20]:
                line = f"<li><strong>{_esc(item.get('test', '?'))}</strong>"
                if item.get("file"):
                    line += f" — <code>{_esc(item['file'])}:{_esc(item.get('line', '?'))}</code>"
                if item.get("expected") is not None:
                    line += f"<br>expected <code>{_esc(item.get('expected'))}</code>, actual <code>{_esc(item.get('actual'))}</code>"
                if item.get("suggestion"):
                    line += f"<br>{_esc(item['suggestion'])}"
                items.append(line + "</li>")
            parts.append(_section("Failed Tests", f"<ul>{''.join(items)}</ul>"))

    plan_gap = state.get("plan_gap") or {}
    if plan_gap.get("missing_targets") or plan_gap.get("partial_targets"):
        items = []
        for item in (plan_gap.get("missing_targets") or [])[:15]:
            items.append(
                f"<li>Missing tests for <strong>{_esc(item.get('symbol'))}</strong> ({_esc(item.get('kind'))})</li>"
            )
        for item in (plan_gap.get("partial_targets") or [])[:15]:
            missing = ", ".join(item.get("missing_scenarios") or [])
            items.append(
                f"<li>Partial <strong>{_esc(item.get('symbol'))}</strong> — missing scenarios: {_esc(missing)}</li>"
            )
        parts.append(_section("Plan Gap", f"<ul>{''.join(items)}</ul>"))

    proposal_items = (state.get("proposals") or {}).get("proposals") or []
    if proposal_items:
        items = []
        for item in proposal_items[:10]:
            items.append(
                f"<li><strong>{_esc(item.get('test', '?'))}</strong> "
                f"<code>{_esc(item.get('file'))}:{_esc(item.get('line'))}</code>"
                f"<br>current: <code>{_esc(item.get('current', ''))}</code>"
                f"<br>suggested: <code>{_esc(item.get('suggested', ''))}</code></li>"
            )
        parts.append(_section("Proposed Fixes (needs confirmation)", f"<ul>{''.join(items)}</ul>"))

    attempts = state.get("attempts") or []
    if attempts:
        items = []
        for att in attempts:
            line = f"<li>Attempt {_esc(att.get('attempt'))}: <strong>{_esc(att.get('result'))}</strong>"
            if att.get("stage"):
                line += f" ({_esc(att['stage'])})"
            applied = att.get("actions_applied") or []
            for action in applied:
                line += f"<br>applied <code>{_esc(action.get('type'))}</code>: {_esc(action.get('values'))}"
            items.append(line + "</li>")
        body = f"<ul>{''.join(items)}</ul>"
        if state.get("auto_fixed"):
            body += "<p><em>Config auto-fixed during retry.</em></p>"
        parts.append(_section("Build Attempts", body))

    if compile_info.get("gtest_tag"):
        gtest = compile_info.get("gtest") or {}
        body = f"<p>Tag: <code>{_esc(compile_info['gtest_tag'])}</code></p>"
        if gtest.get("method"):
            body += f"<p>Method: <code>{_esc(gtest['method'])}</code></p>"
        parts.append(_section("GTest", body))

    if compile_info.get("sanitizer") and compile_info.get("sanitizer") not in ("none", ""):
        parts.append(_section("Sanitizer", f"<p>Mode: <code>{_esc(compile_info['sanitizer'])}</code></p>"))

    learned = state.get("learned") or {}
    if learned.get("path"):
        parts.append(_section("Learned Config", f"<p>Saved to <code>{_esc(learned['path'])}</code></p>"))

    if status not in ("ok",):
        hints = compile_info.get("hints") or []
        if hints:
            parts.append(_section("Hints", f"<ul>{''.join(f'<li>{_esc(h)}</li>' for h in hints)}</ul>"))

    parts.append('<p class="footer">Generated by SDK Test Forge</p>')
    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)
