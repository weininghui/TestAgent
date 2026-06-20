"""HTML report generation from build results.
从构建结果生成单文件 HTML 测试报告。
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from sdk_forge.pipeline.test_fix import parse_test_failures

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
    if status in ("test_failures", "compiler_not_found"):
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
    return _section("测试摘要", f'<div class="agent-analysis">{"".join(paragraphs)}</div>')


def format_report_html(state: dict[str, Any], agent_summary: str = "") -> str:
    status = state.get("status", "unknown")
    run = state.get("run") or {}
    compile_info = state.get("compile") or {}

    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>SDK Forge Report</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        "<h1>SDK Forge Report</h1>",
        f'<p class="meta"><span class="badge {_badge_class(status)}">{_esc(status)}</span></p>',
    ]

    meta_items = []
    for key, label in (("sdk_root", "SDK"), ("source_dir", "Tests"), ("build_dir", "Build")):
        if state.get(key):
            meta_items.append(f"<li><strong>{label}:</strong> <code>{_esc(state[key])}</code></li>")
    if meta_items:
        parts.append(f"<ul>{''.join(meta_items)}</ul>")

    parts.append(_agent_analysis_html(agent_summary))

    if status == "compiler_not_found" or (compile_info.get("status") == "compiler_not_found"):
        tc = state.get("toolchain") or {}
        body = (
            "<p><strong>Tests were not compiled or executed.</strong> "
            "Generated <code>*_test.cpp</code> files may look clean in the editor, "
            "but GTest requires a C++ toolchain to link and run.</p>"
        )
        if tc.get("hint"):
            body += f"<p>{_esc(tc['hint'])}</p>"
        hints = tc.get("hints") or state.get("hints") or compile_info.get("hints") or []
        if hints:
            body += "<ul>" + "".join(f"<li>{_esc(h)}</li>" for h in hints[:6]) + "</ul>"
        parts.append(_section("Toolchain", body))
    elif not run and status not in ("ok", "test_failures"):
        parts.append(
            _section(
                "Toolchain",
                "<p><em>No test run recorded. Do not infer PASS from generated source files alone — "
                "run <code>build_tests</code> after installing a C++ compiler.</em></p>",
            )
        )

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
            cov_body += f"<p>Coverage HTML: <code>{_esc(cached_cov['html_report_dir'])}</code></p>"
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

    quality = state.get("scaffold_quality") or (
        plan_gap.get("scaffold_quality") if plan_gap else None
    )
    if quality:
        ratio = quality.get("placeholder_ratio")
        body = (
            f"<p>Placeholder ratio: <strong>{_esc(ratio)}</strong> "
            f"(total placeholders: {_esc(quality.get('placeholder_total', 0))})</p>"
        )
        if quality.get("needs_enrichment"):
            body += "<p><em>Needs Agent enrichment before relying on results.</em></p>"
        files = quality.get("files") or []
        if files:
            body += (
                "<ul>"
                + "".join(
                    f"<li><code>{_esc(f.get('file'))}</code> — placeholders: {_esc(f.get('total', 0))}</li>"
                    for f in files[:10]
                )
                + "</ul>"
            )
        parts.append(_section("用例质量", body))

    assertion_q = state.get("assertion_quality") or state.get("assertion_gate")
    if isinstance(assertion_q, dict) and assertion_q.get("quality"):
        assertion_q = assertion_q.get("quality")
    elif state.get("assertion_gate") and not assertion_q:
        assertion_q = state.get("assertion_gate")
    if isinstance(assertion_q, dict) and (
        assertion_q.get("score") is not None or assertion_q.get("weak_tests")
    ):
        score = assertion_q.get(
            "score",
            assertion_q.get("quality", {}).get("score")
            if isinstance(assertion_q.get("quality"), dict)
            else None,
        )
        body = f"<p>Assertion quality score: <strong>{_esc(score)}</strong>/100</p>"
        weak = (
            assertion_q.get("weak_tests")
            or (assertion_q.get("quality") or {}).get("weak_tests")
            or []
        )
        if weak:
            body += (
                "<ul>"
                + "".join(
                    f"<li><code>{_esc(w.get('file', '?'))}</code> {_esc(w.get('name', '?'))} "
                    f"— {_esc(', '.join(w.get('issues') or []))}</li>"
                    for w in weak[:15]
                )
                + "</ul>"
            )
            body += (
                "<p><em>Enrich prompt: fix weak/tautology tests before production merge.</em></p>"
            )
        parts.append(_section("断言质量", body))

    ag = state.get("assertion_gate") or {}
    if ag and not ag.get("skipped") and ag.get("passed") is False:
        parts.append(
            _section(
                "Assertion Gate",
                f"<p class='badge badge-fail'>BLOCKED</p><p>{_esc('; '.join(ag.get('block_reasons') or []))}</p>",
            )
        )

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
        parts.append(
            _section("Sanitizer", f"<p>Mode: <code>{_esc(compile_info['sanitizer'])}</code></p>")
        )

    gate = state.get("quality_gate") or {}
    if gate:
        passed = gate.get("passed")
        label = "passed" if passed else "failed/warn"
        parts.append(
            _section(
                "Quality Gate",
                f"<p>Mode: <code>{_esc(gate.get('mode', 'warn'))}</code> — "
                f"<strong>{label}</strong> "
                f"(ratio: {_esc(gate.get('ratio'))}, max: {_esc(gate.get('max_placeholder_ratio'))})</p>",
            )
        )

    workflow = state.get("workflow") or {}
    history = workflow.get("history") or []
    gate_history = [
        h for h in history if h.get("quality_gate") is not None or h.get("stage") == "quality_gate"
    ]
    if gate_history:
        items = []
        for h in gate_history[-5:]:
            items.append(
                f"<li>{_esc(h.get('stage'))}: quality_gate={_esc(h.get('quality_gate'))}</li>"
            )
        parts.append(_section("Gate History", f"<ul>{''.join(items)}</ul>"))

    bench = state.get("bench") or {}
    bench_path = Path(str(state.get("project_dir") or "")) / ".forge" / "cache" / "bench_last.json"
    if not bench and bench_path.is_file():
        try:
            import json as _json

            bench = _json.loads(bench_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bench = {}
    if bench.get("placeholder_ratio") is not None:
        parts.append(
            _section(
                "Benchmark",
                f"<p>Placeholder ratio: <strong>{_esc(bench.get('placeholder_ratio'))}</strong> — "
                f"build: <code>{_esc(bench.get('build_status'))}</code>, "
                f"pass rate: {_esc(bench.get('test_pass_rate'))}</p>",
            )
        )

    learned = state.get("learned") or {}
    if learned.get("path"):
        parts.append(
            _section("Learned Config", f"<p>Saved to <code>{_esc(learned['path'])}</code></p>")
        )

    if status not in ("ok",):
        hints = compile_info.get("hints") or []
        if hints:
            parts.append(
                _section("Hints", f"<ul>{''.join(f'<li>{_esc(h)}</li>' for h in hints)}</ul>")
            )

    parts.append('<p class="footer">Generated by SDK Forge</p>')
    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)
