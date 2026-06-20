"""Compare test plan targets against generated test files and coverage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sdk_forge.pipeline.codegen import count_placeholders
from sdk_forge.pipeline.plan import suggest_test_plan_impl
from sdk_forge.pipeline.templates import _safe_scenario, _safe_test_suite

_RE_TEST = re.compile(r"TEST\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)")


def _symbol_from_test_file(path: Path) -> str:
    name = path.stem
    if name.endswith("_test"):
        return name[: -len("_test")]
    return name


def _load_plan_state(project_dir: str) -> dict[str, Any]:
    path = Path(project_dir) / ".forge" / "cache" / "last_plan.json"
    if not path.exists():
        return {"status": "error", "error": "No saved plan found"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}


def _scan_test_files(tests_dir: Path) -> dict[str, dict[str, Any]]:
    """Map symbol -> {file, suites: {suite: [cases]}}."""
    mapping: dict[str, dict[str, Any]] = {}
    if not tests_dir.is_dir():
        return mapping

    for path in sorted(tests_dir.glob("*_test.cpp")):
        symbol = _symbol_from_test_file(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        suites: dict[str, list[str]] = {}
        for suite, case in _RE_TEST.findall(text):
            suites.setdefault(suite, []).append(case)
        mapping[symbol.lower()] = {
            "symbol": symbol,
            "file": str(path.name),
            "path": str(path.resolve()),
            "suites": suites,
        }
    return mapping


def _expected_cases(target: dict[str, Any]) -> list[str]:
    return [_safe_scenario(str(s.get("name", "Case"))) for s in (target.get("scenarios") or [])]


def _load_coverage_summary(project_dir: Path, build_dir: str = "") -> dict[str, Any] | None:
    cache = project_dir / ".forge" / "cache" / "coverage.json"
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("status") == "ok":
                return data
        except (OSError, json.JSONDecodeError):
            pass

    if build_dir:
        info = Path(build_dir) / "coverage.info"
        if info.exists():
            return {"status": "ok", "line_coverage_pct": 0.0, "source": str(info)}

    return None


def analyze_plan_gap_impl(
    project_dir: str = "",
    plan_json: str | dict[str, Any] | None = None,
    tests_dir: str = "",
    sdk_root: str = "",
) -> dict[str, Any]:
    root = Path(project_dir or Path.cwd()).resolve()

    if plan_json:
        if isinstance(plan_json, str):
            try:
                plan = json.loads(plan_json)
            except json.JSONDecodeError as exc:
                return {"status": "error", "error": f"Invalid plan JSON: {exc}"}
        else:
            plan = plan_json
    else:
        plan = _load_plan_state(str(root))
        if plan.get("status") == "error":
            if sdk_root:
                plan = suggest_test_plan_impl(sdk_root=sdk_root)
            else:
                return {"status": "error", "error": "No saved plan; provide plan_json or sdk_root"}

    if plan.get("status") == "error":
        return plan

    tests_path = Path(tests_dir) if tests_dir else root / "tests"
    if not tests_path.is_dir():
        for candidate in ("tests", "test"):
            alt = root / candidate
            if alt.is_dir():
                tests_path = alt
                break

    test_map = _scan_test_files(tests_path)
    plan_symbols = {
        str(t.get("symbol", "")).lower(): t for t in (plan.get("targets") or []) if t.get("symbol")
    }

    missing_targets: list[dict[str, Any]] = []
    partial_targets: list[dict[str, Any]] = []
    covered_targets: list[str] = []

    for key, target in plan_symbols.items():
        entry = test_map.get(key)
        if not entry:
            missing_targets.append(
                {
                    "symbol": target.get("symbol"),
                    "kind": target.get("kind"),
                    "file": target.get("file"),
                }
            )
            continue

        suite = _safe_test_suite(str(target.get("symbol", "")))
        present_cases = set(entry["suites"].get(suite, []))
        missing_scenarios = [
            s.get("name", "")
            for s in (target.get("scenarios") or [])
            if _safe_scenario(str(s.get("name", "Case"))) not in present_cases
        ]
        if missing_scenarios:
            partial_targets.append(
                {
                    "symbol": target.get("symbol"),
                    "kind": target.get("kind"),
                    "test_file": entry["file"],
                    "missing_scenarios": missing_scenarios,
                }
            )
        else:
            covered_targets.append(str(target.get("symbol")))

    unplanned_tests = [info["file"] for key, info in test_map.items() if key not in plan_symbols]

    quality_files: list[dict[str, Any]] = []
    placeholder_total = 0
    line_total = 0
    if tests_path.is_dir():
        for path in sorted(tests_path.glob("*_test.cpp")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            counts = count_placeholders(text)
            lines = len(text.splitlines()) or 1
            placeholder_total += counts["total"]
            line_total += lines
            sym = _symbol_from_test_file(path).lower()
            needs_test_p = any(
                t.get("use_test_p")
                and re.sub(r"[^a-z0-9_]", "_", str(t.get("symbol", "")).lower()).strip("_") == sym
                for t in (plan.get("targets") or [])
            )
            quality_files.append(
                {
                    "file": path.name,
                    "path": str(path.resolve()),
                    **counts,
                    "has_test_p": "TEST_P" in text,
                    "has_instantiate": "INSTANTIATE_TEST_SUITE_P" in text,
                    "missing_test_p": needs_test_p and "TEST_P" not in text,
                }
            )

    placeholder_ratio = round(placeholder_total / max(line_total, 1), 4)

    build_dir = ""
    from sdk_forge.pipeline.retry import load_build_state

    build_state = load_build_state(str(root))
    if isinstance(build_state, dict):
        build_dir = str(build_state.get("build_dir") or "")

    coverage_block: dict[str, Any] | None = None
    cov = _load_coverage_summary(root, build_dir)
    if cov:
        uncovered = [t["symbol"] for t in missing_targets]
        uncovered.extend(t["symbol"] for t in partial_targets)
        coverage_block = {
            "line_coverage_pct": cov.get("line_coverage_pct"),
            "uncovered_symbols": uncovered,
            "html_report_dir": cov.get("html_report_dir"),
        }

    result = {
        "status": "ok",
        "project_dir": str(root),
        "tests_dir": str(tests_path.resolve()) if tests_path.is_dir() else str(tests_path),
        "target_count": len(plan_symbols),
        "test_file_count": len(test_map),
        "missing_targets": missing_targets,
        "partial_targets": partial_targets,
        "covered_targets": covered_targets,
        "unplanned_tests": unplanned_tests,
        "coverage": coverage_block,
        "scaffold_quality": {
            "placeholder_total": placeholder_total,
            "placeholder_ratio": placeholder_ratio,
            "files": quality_files,
        },
    }

    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    gap_path = cache / "plan_gap.json"
    gap_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["saved_to"] = str(gap_path)
    return result


def load_plan_gap(project_dir: str = "") -> dict[str, Any]:
    path = Path(project_dir or Path.cwd()) / ".forge" / "cache" / "plan_gap.json"
    if not path.exists():
        return {"status": "error", "error": "No plan gap analysis found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "ok"
        return data
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}
