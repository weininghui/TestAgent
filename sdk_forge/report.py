"""Markdown report generation from build results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdk_forge.retry import load_build_state
from sdk_forge.test_fix import parse_test_failures


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

    compile_info = state.get("compile") or {}
    if compile_info.get("gtest_tag"):
        lines.append("## GTest")
        lines.append("")
        lines.append(f"- Tag: `{compile_info['gtest_tag']}`")
        gtest = compile_info.get("gtest") or {}
        if gtest.get("method"):
            lines.append(f"- Method: `{gtest['method']}`")
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
        },
    }
