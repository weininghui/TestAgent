"""Parse GTest failures into structured fix suggestions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sdk_forge.pipeline.run import run_tests_impl

_RE_RUN = re.compile(r"\[ RUN      \]\s+(\S+)")
_RE_FAIL = re.compile(r"\[  FAILED  \]\s+(\S+)")
_RE_FILE_LINE = re.compile(
    r"^\s*(?:(.+?):(\d+)|(.+?)\((\d+)\)):\s*(?:Failure|error(?:\s|$|:))",
    re.MULTILINE,
)
_RE_EXPECTED = re.compile(r"Expected:\s*(.+)")
_RE_ACTUAL = re.compile(r"Actual:\s*(.+)")
_RE_WHICH = re.compile(r"Which is:\s*(.+)")


def parse_test_failures(run_result: dict[str, Any]) -> dict[str, Any]:
    if run_result.get("status") not in ("test_failures", "ok"):
        return {
            "status": "error",
            "error": run_result.get("error", "No test output to analyze"),
        }

    output = run_result.get("output") or ""
    if run_result.get("status") == "ok":
        return {"status": "ok", "failures": [], "actions": [], "failure_count": 0}

    failures: list[dict[str, Any]] = []
    current_test = ""
    current: dict[str, Any] = {}
    msvc_values = False

    for line in output.splitlines():
        run_m = _RE_RUN.match(line.strip())
        if run_m:
            current_test = run_m.group(1)
            continue
        fail_m = _RE_FAIL.match(line.strip())
        if fail_m and not fail_m.group(1).endswith("test,"):
            current_test = fail_m.group(1)
            continue
        file_m = _RE_FILE_LINE.match(line)
        if file_m:
            if current:
                failures.append(current)
            file_path = file_m.group(1) or file_m.group(3) or ""
            line_no = file_m.group(2) or file_m.group(4) or "0"
            current = {
                "test": current_test,
                "file": file_path.strip(),
                "line": int(line_no),
            }
            msvc_values = "Expected equality" in line
            continue
        exp_m = _RE_EXPECTED.search(line)
        if exp_m and current:
            current["expected"] = exp_m.group(1).strip()
            continue
        act_m = _RE_ACTUAL.search(line)
        if act_m and current:
            current["actual"] = act_m.group(1).strip()
            continue
        which_m = _RE_WHICH.search(line)
        if which_m and current:
            current["actual"] = which_m.group(1).strip()
            continue
        if msvc_values and current:
            stripped = line.strip()
            if not stripped or stripped.startswith("Which is"):
                continue
            if "expected_expr" not in current:
                current["expected_expr"] = stripped
            elif "expected" not in current:
                current["expected"] = stripped
                msvc_values = False

    if current:
        failures.append(current)

    if not failures:
        for line in output.splitlines():
            fail_m = _RE_FAIL.match(line.strip())
            if fail_m and not re.search(r"\d+\s+test", fail_m.group(1)):
                name = fail_m.group(1)
                if name and name not in {f.get("test") for f in failures}:
                    failures.append({"test": name, "suggestion": "See GTest output for details"})
        for name in run_result.get("failed_tests") or []:
            failures.append({"test": name.strip(), "suggestion": "See GTest output for details"})

    actions: list[dict[str, Any]] = []
    for item in failures:
        test_name = item.get("test", "")
        if item.get("expected") is not None or item.get("actual") is not None:
            actions.append(
                {
                    "type": "review_assertion",
                    "test": test_name,
                    "hint": f"EXPECT mismatch — expected {item.get('expected')!r}, actual {item.get('actual')!r}",
                    "file": item.get("file"),
                    "line": item.get("line"),
                }
            )
            item["suggestion"] = "Review test inputs and SDK behavior; update EXPECT_* in source"
        else:
            actions.append(
                {
                    "type": "review_test",
                    "test": test_name,
                    "hint": "Test failed — inspect output section for this RUN block",
                }
            )
            item.setdefault(
                "suggestion", "Read GTest output near [ RUN ] / [ FAILED ] for this test"
            )

    return {
        "status": "ok",
        "failure_count": len(failures),
        "failures": failures,
        "actions": actions,
    }


def analyze_test_failures_impl(
    build_dir: str = "",
    run_json: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    import json

    if run_json:
        if isinstance(run_json, str):
            try:
                run_result = json.loads(run_json)
            except json.JSONDecodeError as exc:
                return {"status": "error", "error": f"Invalid run JSON: {exc}"}
        else:
            run_result = run_json
    elif build_dir:
        run_result = run_tests_impl(build_dir)
    else:
        return {"status": "error", "error": "Provide build_dir or run_json"}

    if run_result.get("status") == "error":
        return run_result

    parsed = parse_test_failures(run_result)
    parsed["run_status"] = run_result.get("status")
    parsed["total"] = run_result.get("total", 0)
    parsed["passed"] = run_result.get("passed", 0)
    parsed["failed"] = run_result.get("failed", 0)
    return parsed


_RE_EXPECT_MACRO = re.compile(
    r"(EXPECT_\w+|ASSERT_\w+)\s*\([^)]+\)",
)


def _read_line_context(file_path: Path, line_no: int, radius: int = 5) -> list[str]:
    if not file_path.is_file():
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    start = max(0, line_no - radius - 1)
    end = min(len(lines), line_no + radius)
    return lines[start:end]


def _suggest_assertion_line(current_line: str, expected: str, actual: str) -> str | None:
    if not current_line.strip():
        return None
    match = _RE_EXPECT_MACRO.search(current_line)
    if not match:
        return None
    macro = match.group(0)
    if actual in macro:
        return current_line.replace(actual, expected, 1)
    if expected not in macro:
        return f"{current_line.rstrip()}  // suggested: use expected value {expected}"
    return None


def propose_test_fixes_impl(
    build_dir: str = "",
    analysis_json: str | dict[str, Any] | None = None,
    project_dir: str = "",
    tests_dir: str = "",
) -> dict[str, Any]:
    if analysis_json:
        if isinstance(analysis_json, str):
            try:
                analysis = json.loads(analysis_json)
            except json.JSONDecodeError as exc:
                return {"status": "error", "error": f"Invalid analysis JSON: {exc}"}
        else:
            analysis = analysis_json
    elif build_dir:
        analysis = analyze_test_failures_impl(build_dir)
    else:
        return {"status": "error", "error": "Provide build_dir or analysis_json"}

    if analysis.get("status") == "error":
        return analysis

    root = Path(project_dir or Path.cwd()).resolve()
    tests_path = Path(tests_dir) if tests_dir else root / "tests"
    if not tests_path.is_dir():
        tests_path = root / "tests"

    proposals: list[dict[str, Any]] = []
    for failure in analysis.get("failures") or []:
        file_name = failure.get("file") or ""
        line_no = failure.get("line")
        expected = failure.get("expected")
        actual = failure.get("actual")
        if not file_name or not line_no:
            continue

        file_path = Path(file_name)
        if not file_path.is_file():
            file_path = tests_path / Path(file_name).name
        if not file_path.is_file():
            continue

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
            current = lines[int(line_no) - 1]
        except (OSError, IndexError, ValueError):
            continue

        suggested = None
        reason = "Inspect assertion near failure line"
        if expected is not None and actual is not None:
            suggested = _suggest_assertion_line(current, str(expected), str(actual))
            reason = "Expected/Actual mismatch from GTest"

        proposals.append(
            {
                "type": "propose_assertion_fix",
                "requires_confirmation": True,
                "test": failure.get("test"),
                "file": str(file_path.name),
                "path": str(file_path.resolve()),
                "line": line_no,
                "current": current.strip(),
                "suggested": (suggested or current).strip(),
                "reason": reason,
                "context": _read_line_context(file_path, int(line_no)),
            }
        )

    result = {
        "status": "ok",
        "proposal_count": len(proposals),
        "proposals": proposals,
        "requires_confirmation": True,
    }

    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "last_proposals.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["saved_to"] = str(path)
    return result


def load_proposals(project_dir: str = "") -> dict[str, Any]:
    path = Path(project_dir or Path.cwd()) / ".forge" / "cache" / "last_proposals.json"
    if not path.exists():
        return {"status": "error", "error": "No proposals found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "ok"
        return data
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}


def apply_proposed_fixes_impl(
    project_dir: str = "",
    confirm: bool | str = False,
    indices: list[int] | str | None = None,
) -> dict[str, Any]:
    """Apply cached proposals to source files. Requires explicit confirm=true."""
    from sdk_forge.domain.util import parse_bool

    if not parse_bool(confirm, default=False):
        return {
            "status": "error",
            "error": "confirm=true required — proposals never apply without explicit user confirmation",
        }

    root = Path(project_dir or Path.cwd()).resolve()
    cached = load_proposals(str(root))
    if cached.get("status") == "error":
        return cached

    proposals = cached.get("proposals") or []
    if indices is not None:
        if isinstance(indices, str):
            selected = {int(x.strip()) for x in indices.split(",") if x.strip().isdigit()}
        else:
            selected = set(indices)
        proposals = [p for i, p in enumerate(proposals) if i in selected]

    applied: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, prop in enumerate(proposals):
        file_path = Path(prop.get("path") or prop.get("file") or "")
        if not file_path.is_file():
            file_path = root / "tests" / Path(str(prop.get("file", ""))).name
        if not file_path.is_file():
            errors.append(f"Missing file for proposal {idx}: {prop.get('file')}")
            continue

        line_no = int(prop.get("line") or 0)
        current = str(prop.get("current") or "")
        suggested = str(prop.get("suggested") or "")
        if not line_no or not current or not suggested or current == suggested:
            errors.append(f"Skipped invalid proposal {idx}: {prop.get('test')}")
            continue

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
            if line_no < 1 or line_no > len(lines):
                errors.append(f"Line {line_no} out of range in {file_path.name}")
                continue
            if lines[line_no - 1].strip() != current:
                errors.append(
                    f"Line {line_no} changed since proposal for {prop.get('test')} — re-run propose_test_fixes"
                )
                continue
            indent = lines[line_no - 1][
                : len(lines[line_no - 1]) - len(lines[line_no - 1].lstrip())
            ]
            new_line = suggested if suggested.endswith("\n") else suggested + "\n"
            if not new_line.startswith(indent) and indent:
                new_line = indent + new_line.lstrip()
            lines[line_no - 1] = new_line
            file_path.write_text("".join(lines), encoding="utf-8")
            applied.append(
                {
                    "index": idx,
                    "test": prop.get("test"),
                    "file": str(file_path),
                    "line": line_no,
                }
            )
        except OSError as exc:
            errors.append(f"{file_path.name}: {exc}")

    result = {
        "status": "ok" if applied else "error",
        "applied_count": len(applied),
        "applied": applied,
        "errors": errors,
    }
    if not applied:
        result["error"] = errors[0] if errors else "No proposals applied"
    return result
