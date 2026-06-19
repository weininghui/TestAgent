"""Markdown report generation from build results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdk_forge.plan_gap import load_plan_gap
from sdk_forge.retry import load_build_state
from sdk_forge.test_fix import load_proposals, parse_test_failures


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


def report_impl(
    project_dir: str = "",
    build_state_json: str = "",
    output_format: str = "markdown",
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
    gap = load_plan_gap(root)
    if gap.get("status") == "ok":
        state = dict(state)
        state["plan_gap"] = gap

    props = load_proposals(root)
    if props.get("status") == "ok":
        state = dict(state)
        state["proposals"] = props

    cov_path = Path(root) / ".forge" / "cache" / "coverage.json"
    if cov_path.exists():
        try:
            state = dict(state)
            state["coverage"] = json.loads(cov_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    if output_format == "json":
        return {"status": "ok", "report": state, "format": "json"}

    markdown = format_report_markdown(state)
    return {
        "status": "ok",
        "format": "markdown",
        "markdown": markdown,
        "summary": {
            "status": state.get("status"),
            "passed": state.get("passed", state.get("run", {}).get("passed", 0)),
            "failed": state.get("failed", state.get("run", {}).get("failed", 0)),
            "auto_fixed": state.get("auto_fixed", False),
            "retries_used": state.get("retries_used", 0),
            "plan_gap_missing": len((state.get("plan_gap") or {}).get("missing_targets") or []),
            "proposal_count": len((state.get("proposals") or {}).get("proposals") or []),
        },
    }
