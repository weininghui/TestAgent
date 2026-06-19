"""Parse GTest failures into structured fix suggestions."""

from __future__ import annotations

import re
from typing import Any

from sdk_forge.run import run_tests_impl


_RE_RUN = re.compile(r"\[ RUN      \]\s+(\S+)")
_RE_FAIL = re.compile(r"\[  FAILED  \]\s+(\S+)")
_RE_FILE_LINE = re.compile(r"^\s*(.+?):(\d+): Failure", re.MULTILINE)
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

    for line in output.splitlines():
        run_m = _RE_RUN.match(line.strip())
        if run_m:
            current_test = run_m.group(1)
            continue
        fail_m = _RE_FAIL.match(line.strip())
        if fail_m:
            current_test = fail_m.group(1)
            continue
        file_m = _RE_FILE_LINE.match(line)
        if file_m:
            if current:
                failures.append(current)
            current = {
                "test": current_test,
                "file": file_m.group(1).strip(),
                "line": int(file_m.group(2)),
            }
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
        if which_m and current and "actual" not in current:
            current["actual"] = which_m.group(1).strip()

    if current:
        failures.append(current)

    if not failures:
        for name in run_result.get("failed_tests") or []:
            failures.append({"test": name.strip(), "suggestion": "See GTest output for details"})

    actions: list[dict[str, Any]] = []
    for item in failures:
        test_name = item.get("test", "")
        if item.get("expected") is not None or item.get("actual") is not None:
            actions.append({
                "type": "review_assertion",
                "test": test_name,
                "hint": f"EXPECT mismatch — expected {item.get('expected')!r}, actual {item.get('actual')!r}",
                "file": item.get("file"),
                "line": item.get("line"),
            })
            item["suggestion"] = "Review test inputs and SDK behavior; update EXPECT_* in source"
        else:
            actions.append({
                "type": "review_test",
                "test": test_name,
                "hint": "Test failed — inspect output section for this RUN block",
            })
            item.setdefault("suggestion", "Read GTest output near [ RUN ] / [ FAILED ] for this test")

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
