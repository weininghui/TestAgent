"""Coverage-guided test case expansion.
基于覆盖率缓存扩展低覆盖符号的测试用例。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdk_forge.codegen import render_test_p_block
from sdk_forge.plan_gap import load_plan_gap
from sdk_forge.plan_gap import _load_plan_state as load_plan_state
from sdk_forge.templates import _render_function_target, _safe_test_suite


def coverage_expand_impl(
    project_dir: str = "",
    tests_dir: str = "",
    threshold_pct: float = 80.0,
) -> dict[str, Any]:
    """Append boundary/error TEST_P blocks for low-coverage plan targets.
    为低覆盖 target 追加边界/错误 TEST_P 用例块。
    """
    root = Path(project_dir or Path.cwd()).resolve()
    plan = load_plan_state(str(root))
    if plan.get("status") == "error":
        return plan

    gap = load_plan_gap(str(root))
    cov = (gap.get("coverage") or {}) if gap.get("status") == "ok" else {}
    line_pct = cov.get("line_coverage_pct")
    uncovered = set(cov.get("uncovered_symbols") or [])
    if not uncovered and line_pct is not None and line_pct >= threshold_pct:
        return {
            "status": "ok",
            "message": "Coverage above threshold; no expansion needed",
            "line_coverage_pct": line_pct,
            "files_appended": [],
        }

    if not uncovered:
        for item in gap.get("missing_targets") or []:
            uncovered.add(item.get("symbol"))
        for item in gap.get("partial_targets") or []:
            uncovered.add(item.get("symbol"))

    tests_path = Path(tests_dir) if tests_dir else root / "tests"
    if not tests_path.is_dir():
        tests_path = root / "tests"

    targets_by_sym = {str(t.get("symbol", "")): t for t in (plan.get("targets") or [])}
    appended: list[str] = []

    for sym in uncovered:
        target = targets_by_sym.get(sym)
        if not target or target.get("kind") != "function":
            continue
        safe = sym.lower().replace("-", "_")
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in safe)
        path = tests_path / f"{safe}_test.cpp"
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        if "INSTANTIATE_TEST_SUITE_P" in content and "ForgeExpand" in content:
            continue
        block = render_test_p_block(target, _safe_test_suite(sym))
        if not block:
            continue
        expanded = block.replace("INSTANTIATE_TEST_SUITE_P(Forge,", "INSTANTIATE_TEST_SUITE_P(ForgeExpand,")
        path.write_text(content.rstrip() + "\n\n// coverage_expand\n" + expanded, encoding="utf-8")
        appended.append(str(path.resolve()))

    return {
        "status": "ok",
        "project_dir": str(root),
        "uncovered_symbols": sorted(uncovered),
        "line_coverage_pct": line_pct,
        "files_appended": appended,
        "appended_count": len(appended),
    }
