"""Agent enrichment briefs and scaffold quality analysis.
为 Agent 生成补全 brief，并分析骨架质量。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sdk_forge.codegen import count_placeholders
from sdk_forge.compdb import get_compile_commands_impl
from sdk_forge.test_files import match_test_file, parse_test_files_filter, resolve_tests_dir
from sdk_forge.plan_gap import _symbol_from_test_file
from sdk_forge.plan_gap import _load_plan_state as load_plan_state

_RE_AGENT = re.compile(r"^\s*//\s*AGENT:", re.MULTILINE)
_RE_TEST = re.compile(r"TEST\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)")


def _read_header_excerpt(sdk_root: str, header_file: str, max_lines: int = 40) -> str:
    if not sdk_root or not header_file:
        return ""
    path = Path(sdk_root) / header_file
    if not path.is_file():
        path = Path(sdk_root) / Path(header_file).name
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[:max_lines])
    except OSError:
        return ""


def _find_agent_markers(content: str) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for i, line in enumerate(content.splitlines(), start=1):
        if "// AGENT:" in line or "// TODO:" in line:
            markers.append({
                "line": i,
                "text": line.strip(),
                "kind": "agent" if "AGENT:" in line else "todo",
            })
    return markers


def enrich_test_cases_impl(
    project_dir: str = "",
    symbol: str = "",
    tests_dir: str = "",
    test_files: list[str] | str = "",
) -> dict[str, Any]:
    """Build enrichment briefs for Agent to fill complex test cases.
    生成 Agent 补全复杂用例所需的 structured brief。
    """
    from sdk_forge.workflow import update_workflow_stage

    root = Path(project_dir or Path.cwd()).resolve()
    plan = load_plan_state(str(root))
    if plan.get("status") == "error":
        return plan

    sdk_root = plan.get("sdk_root") or ""
    tests_path = resolve_tests_dir(str(root), tests_dir)
    file_filter = parse_test_files_filter(test_files)

    compdb = get_compile_commands_impl(str(root))
    compile_macros: list[str] = []
    if compdb.get("status") == "ok":
        for entry in (compdb.get("compile_commands") or [])[:5]:
            if not isinstance(entry, dict):
                continue
            cmd = str(entry.get("command") or "")
            for part in cmd.split():
                if part.startswith("-D"):
                    compile_macros.append(part)

    plan_targets = {str(t.get("symbol", "")).lower(): t for t in (plan.get("targets") or [])}
    briefs: list[dict[str, Any]] = []

    if not tests_path or not tests_path.is_dir():
        return {"status": "error", "error": f"Tests directory not found under {root}"}

    for path in sorted(tests_path.glob("*_test.cpp")):
        if not match_test_file(path, file_filter):
            continue
        sym_key = _symbol_from_test_file(path).lower()
        if symbol and sym_key != symbol.lower().replace("-", "_"):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        target = None
        for key, t in plan_targets.items():
            safe = re.sub(r"[^a-z0-9_]", "_", key).strip("_").lower()
            if safe == sym_key or key.lower() == sym_key:
                target = t
                break

        markers = _find_agent_markers(content)
        counts = count_placeholders(content)
        suites = {}
        for suite, case in _RE_TEST.findall(content):
            suites.setdefault(suite, []).append(case)

        sym_name = target.get("symbol") if target else sym_key
        from sdk_forge.golden import golden_to_enrich_hints, load_golden_cases
        golden = load_golden_cases(str(root), symbol=sym_name or sym_key)
        golden_cases = golden.get("cases") or []
        oracle_hints = golden_to_enrich_hints(sym_name or sym_key, golden_cases)

        briefs.append({
            "symbol": sym_name,
            "test_file": str(path.resolve()),
            "header_file": target.get("file") if target else None,
            "header_excerpt": _read_header_excerpt(sdk_root, target.get("file", "") if target else ""),
            "scenarios": target.get("scenarios") if target else [],
            "golden_cases": golden_cases,
            "oracle_hints": oracle_hints,
            "missing_golden": not golden_cases and bool(markers),
            "compile_macros": compile_macros[:10],
            "markers": markers,
            "placeholder_counts": counts,
            "suites": suites,
            "suggestions": [
                "Replace // AGENT: lines with real EXPECT_* assertions",
                "Use golden_cases / oracle_hints when present",
                "Use header excerpt for valid inputs and return values",
                "Re-run analyze_assertion_quality after edits",
            ],
        })

    result = {
        "status": "ok",
        "project_dir": str(root),
        "sdk_root": sdk_root,
        "brief_count": len(briefs),
        "briefs": briefs,
    }
    if project_dir:
        update_workflow_stage(project_dir, "enrich", {"brief_count": len(briefs)})
    return result


def analyze_scaffold_quality_impl(
    project_dir: str = "",
    tests_dir: str = "",
    test_files: list[str] | str = "",
) -> dict[str, Any]:
    """Analyze TODO/placeholder ratio in generated tests.
    分析生成测试中的占位符比例。
    """
    root = Path(project_dir or Path.cwd()).resolve()
    tests_path = resolve_tests_dir(str(root), tests_dir)
    file_filter = parse_test_files_filter(test_files)

    if not tests_path or not tests_path.is_dir():
        return {"status": "error", "error": f"Tests directory not found under {root}"}

    files: list[dict[str, Any]] = []
    placeholder_total = 0
    line_total = 0
    test_count = 0

    for path in sorted(tests_path.glob("*_test.cpp")):
        if not match_test_file(path, file_filter):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        counts = count_placeholders(content)
        lines = len(content.splitlines()) or 1
        tests = len(_RE_TEST.findall(content))
        placeholder_total += counts["total"]
        line_total += lines
        test_count += tests
        files.append({
            "file": path.name,
            "path": str(path.resolve()),
            "test_count": tests,
            **counts,
        })

    ratio = round(placeholder_total / max(line_total, 1), 4)
    result = {
        "status": "ok",
        "project_dir": str(root),
        "tests_dir": str(tests_path.resolve()),
        "file_count": len(files),
        "test_count": test_count,
        "placeholder_total": placeholder_total,
        "placeholder_ratio": ratio,
        "needs_enrichment": ratio > 0.5,
        "files": files,
    }

    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    out_path = cache / "scaffold_quality.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["saved_to"] = str(out_path)
    return result


def load_scaffold_quality(project_dir: str = "") -> dict[str, Any]:
    path = Path(project_dir or Path.cwd()) / ".forge" / "cache" / "scaffold_quality.json"
    if not path.exists():
        return {"status": "error", "error": "No scaffold quality analysis found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "ok"
        return data
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}
