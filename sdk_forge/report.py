"""Markdown and HTML report generation from build results.
从构建结果生成 Markdown / HTML 测试报告。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdk_forge.enrich import load_scaffold_quality
from sdk_forge.plan_gap import load_plan_gap
from sdk_forge.report_html import format_report_html
from sdk_forge.retry import load_build_state
from sdk_forge.test_fix import load_proposals, parse_test_failures
from sdk_forge.workflow import load_workflow_state


def _enrich_report_state(project_dir: str, state: dict[str, Any]) -> dict[str, Any]:
    root = project_dir or str(Path.cwd())
    enriched = dict(state)

    gap = load_plan_gap(root)
    if gap.get("status") == "ok":
        enriched["plan_gap"] = gap

    props = load_proposals(root)
    if props.get("status") == "ok":
        enriched["proposals"] = props

    cov_path = Path(root) / ".forge" / "cache" / "coverage.json"
    if cov_path.exists():
        try:
            enriched["coverage"] = json.loads(cov_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    quality = load_scaffold_quality(root)
    if quality.get("status") == "ok":
        enriched["scaffold_quality"] = quality
    elif gap.get("scaffold_quality"):
        enriched["scaffold_quality"] = gap.get("scaffold_quality")

    if enriched.get("quality_gate"):
        pass
    elif state.get("quality_gate"):
        enriched["quality_gate"] = state.get("quality_gate")

    workflow = load_workflow_state(root)
    if workflow.get("status") == "ok":
        enriched["workflow"] = workflow

    bench_path = Path(root) / ".forge" / "cache" / "bench_last.json"
    if bench_path.is_file():
        try:
            enriched["bench"] = json.loads(bench_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    enriched["project_dir"] = root
    return enriched


def _build_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": state.get("status"),
        "passed": state.get("passed", state.get("run", {}).get("passed", 0)),
        "failed": state.get("failed", state.get("run", {}).get("failed", 0)),
        "auto_fixed": state.get("auto_fixed", False),
        "retries_used": state.get("retries_used", 0),
        "plan_gap_missing": len((state.get("plan_gap") or {}).get("missing_targets") or []),
        "proposal_count": len((state.get("proposals") or {}).get("proposals") or []),
    }


def format_report_markdown(state: dict[str, Any]) -> str:
    lines = ["# SDK Test Forge Report", ""]
    status = state.get("status", "unknown")
    lines.append(f"**Status:** {status}")
    lines.append("")

    if state.get("sdk_root"):
        lines.append(f"- SDK: `{state['sdk_root']}`")
    if state.get("source_dir"):
        lines.append(f"- Tests: `{state['source_dir']}`")
    if state.get("build_dir"):
        lines.append(f"- Build: `{state['build_dir']}`")
    lines.append("")

    run = state.get("run") or {}
    if run:
        lines.append("## Test Results")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total | {run.get('total', 0)} |")
        lines.append(f"| Passed | {run.get('passed', 0)} |")
        lines.append(f"| Failed | {run.get('failed', 0)} |")
        lines.append("")

    coverage_pct = run.get("line_coverage_pct")
    compile_info = state.get("compile") or {}
    if coverage_pct is None:
        coverage_pct = state.get("line_coverage_pct") or compile_info.get("line_coverage_pct")
    cached_cov = state.get("coverage") or {}
    if coverage_pct is None and cached_cov.get("line_coverage_pct") is not None:
        coverage_pct = cached_cov.get("line_coverage_pct")
    if coverage_pct is not None:
        lines.append("## Coverage")
        lines.append("")
        lines.append(f"- Line coverage: **{coverage_pct}%**")
        if cached_cov.get("html_report_dir"):
            lines.append(f"- HTML report: `{cached_cov['html_report_dir']}`")
        lines.append("")

    quality = state.get("scaffold_quality") or {}
    if quality.get("placeholder_ratio") is not None:
        lines.append("## 用例质量")
        lines.append("")
        lines.append(f"- Placeholder ratio: **{quality.get('placeholder_ratio')}**")
        lines.append(f"- Placeholder total: {quality.get('placeholder_total', 0)}")
        if quality.get("needs_enrichment"):
            lines.append("- **Needs Agent enrichment** (ratio > 50%)")
        lines.append("")

    run = state.get("run") or {}
    if run.get("status") == "test_failures":
        analysis = parse_test_failures(run)
        if analysis.get("failures"):
            lines.append("## Failed Tests")
            lines.append("")
            for item in analysis["failures"][:20]:
                lines.append(f"- **{item.get('test', '?')}**")
                if item.get("file"):
                    lines.append(f"  - `{item['file']}:{item.get('line', '?')}`")
                if item.get("expected") is not None:
                    lines.append(f"  - expected `{item.get('expected')}`, actual `{item.get('actual')}`")
                if item.get("suggestion"):
                    lines.append(f"  - {item['suggestion']}")
            lines.append("")

    plan_gap = state.get("plan_gap") or {}
    if plan_gap.get("missing_targets") or plan_gap.get("partial_targets"):
        lines.append("## Plan Gap")
        lines.append("")
        for item in (plan_gap.get("missing_targets") or [])[:15]:
            lines.append(f"- Missing tests for **{item.get('symbol')}** ({item.get('kind')})")
        for item in (plan_gap.get("partial_targets") or [])[:15]:
            missing = ", ".join(item.get("missing_scenarios") or [])
            lines.append(f"- Partial **{item.get('symbol')}** — missing scenarios: {missing}")
        lines.append("")

    proposals = state.get("proposals") or {}
    proposal_items = proposals.get("proposals") or []
    if proposal_items:
        lines.append("## Proposed Fixes (needs confirmation)")
        lines.append("")
        for item in proposal_items[:10]:
            lines.append(f"- **{item.get('test', '?')}** `{item.get('file')}:{item.get('line')}`")
            lines.append(f"  - current: `{item.get('current', '')}`")
            lines.append(f"  - suggested: `{item.get('suggested', '')}`")
        lines.append("")

    attempts = state.get("attempts") or []
    if attempts:
        lines.append("## Build Attempts")
        lines.append("")
        for att in attempts:
            lines.append(f"- Attempt {att.get('attempt')}: **{att.get('result')}**"
                         + (f" ({att.get('stage')})" if att.get("stage") else ""))
            applied = att.get("actions_applied") or []
            if applied:
                for action in applied:
                    lines.append(f"  - applied `{action.get('type')}`: {action.get('values')}")
        if state.get("auto_fixed"):
            lines.append("")
            lines.append("*Config auto-fixed during retry.*")
        lines.append("")

    if compile_info.get("gtest_tag"):
        lines.append("## GTest")
        lines.append("")
        lines.append(f"- Tag: `{compile_info['gtest_tag']}`")
        gtest = compile_info.get("gtest") or {}
        if gtest.get("method"):
            lines.append(f"- Method: `{gtest['method']}`")
        lines.append("")

    if compile_info.get("sanitizer") and compile_info.get("sanitizer") not in ("none", ""):
        lines.append("## Sanitizer")
        lines.append("")
        lines.append(f"- Mode: `{compile_info['sanitizer']}`")
        lines.append("")

    learned = state.get("learned") or {}
    if learned.get("path"):
        lines.append("## Learned Config")
        lines.append("")
        lines.append(f"- Saved to `{learned['path']}`")
        lines.append("")

    if status not in ("ok",):
        hints = compile_info.get("hints") or []
        if hints:
            lines.append("## Hints")
            lines.append("")
            for hint in hints:
                lines.append(f"- {hint}")
            lines.append("")

    return "\n".join(lines)


def build_auto_summary(state: dict[str, Any]) -> str:
    """Plain-text summary for testers (Chinese, no Agent required).
    为测试同学生成中文纯文本摘要（无需 Agent 手写）。
    """
    lines: list[str] = []
    status = state.get("status", "unknown")
    run = state.get("run") or {}
    passed = state.get("passed", run.get("passed", 0))
    failed = state.get("failed", run.get("failed", 0))
    total = run.get("total", passed + failed)

    if status == "ok" and run:
        lines.append(f"全部 {total} 个测试通过。")
    elif status == "test_failures":
        lines.append(f"共 {total} 个测试：通过 {passed}，失败 {failed}。")
        analysis = parse_test_failures(run)
        for item in (analysis.get("failures") or [])[:10]:
            name = item.get("test", "?")
            lines.append(f"- 失败：{name}")
            if item.get("expected") is not None:
                lines.append(f"  期望 {item.get('expected')}，实际 {item.get('actual', '?')}")
    elif status == "compiler_not_found":
        tc = state.get("toolchain") or {}
        lines.append("未检测到 C++ 编译器，测试源码已生成但未编译、未运行。")
        lines.append("请安装 Visual Studio Build Tools（含 C++ 工作负载）或 MinGW-w64 后重新 build_tests。")
        if tc.get("hint"):
            lines.append(f"详情：{tc['hint']}")
    elif not run and status not in ("ok",):
        lines.append("测试未运行：仅生成了 GTest 源码或构建失败，不能以用例数量推断 PASS。")
    elif status != "ok":
        stage = (state.get("compile") or {}).get("stage", "build")
        lines.append(f"构建未成功（阶段：{stage}）。")
        for hint in ((state.get("compile") or {}).get("hints") or [])[:5]:
            lines.append(f"- {hint}")

    proposals = (state.get("proposals") or {}).get("proposals") or []
    if proposals:
        lines.append(f"有 {len(proposals)} 条修复建议，需确认后再 apply。")

    gap = state.get("plan_gap") or {}
    missing = len(gap.get("missing_targets") or [])
    if missing:
        lines.append(f"测试计划缺口：{missing} 个 API 尚未覆盖。")

    if not lines:
        lines.append("构建已完成，详见下方各章节。")
    return "\n".join(lines)


def auto_generate_report(project_dir: str, state: dict[str, Any]) -> dict[str, Any]:
    """Write HTML report after build with auto summary.
    构建结束后写入 HTML 报告（含自动摘要）。
    """
    summary_text = build_auto_summary(state)
    enriched = _enrich_report_state(project_dir, state)
    html_content = format_report_html(enriched, agent_summary=summary_text)
    root = project_dir or str(Path.cwd())
    html_path = Path(root) / ".forge" / "cache" / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_content, encoding="utf-8")
    return {
        "status": "ok",
        "format": "html",
        "html_path": str(html_path.resolve()),
        "html": html_content,
        "summary": _build_summary(enriched),
        "auto_summary": summary_text,
    }


def report_impl(
    project_dir: str = "",
    build_state_json: str = "",
    output_format: str = "markdown",
    agent_summary: str = "",
    output_path: str = "",
) -> dict[str, Any]:
    if build_state_json.strip():
        try:
            state = json.loads(build_state_json)
        except json.JSONDecodeError as exc:
            return {"status": "error", "error": f"Invalid build state JSON: {exc}"}
    else:
        state = load_build_state(project_dir)
        if state.get("status") == "error":
            return state

    root = project_dir or str(Path.cwd())
    state = _enrich_report_state(root, state)
    summary = _build_summary(state)

    if output_format == "json":
        return {"status": "ok", "report": state, "format": "json", "summary": summary}

    if output_format == "html":
        html_content = format_report_html(state, agent_summary=agent_summary)
        html_path = Path(output_path) if output_path else Path(root) / ".forge" / "cache" / "report.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html_content, encoding="utf-8")
        return {
            "status": "ok",
            "format": "html",
            "html_path": str(html_path.resolve()),
            "html": html_content,
            "summary": summary,
        }

    markdown = format_report_markdown(state)
    return {
        "status": "ok",
        "format": "markdown",
        "markdown": markdown,
        "summary": summary,
    }
