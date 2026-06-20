"""Semantic assertion quality analysis for production-grade test gates.
语义断言质量分析（弱断言 / 自比 / AGENT 残留）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sdk_forge.domain.test_files import match_test_file, parse_test_files_filter, resolve_tests_dir

_RE_TEST_BLOCK = re.compile(
    r"TEST(?:_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*\{",
    re.MULTILINE,
)
_RE_AGENT = re.compile(r"//\s*AGENT:", re.IGNORECASE)
_RE_TODO = re.compile(r"//\s*TODO", re.IGNORECASE)
_RE_SUCCEED = re.compile(r"\bSUCCEED\s*\(\s*\)")
_RE_EXPECT_TRUE = re.compile(r"EXPECT_TRUE\s*\(\s*true\s*\)")
_RE_EXPECT_ASSERT = re.compile(r"\b(EXPECT|ASSERT)_[A-Z0-9_]+\s*\(")
_RE_TAUTOLOGY = re.compile(
    r"(EXPECT|ASSERT)_EQ\s*\(\s*([^,()]+(?:\([^)]*\))?)\s*,\s*\2\s*\)",
    re.IGNORECASE,
)


def _extract_test_blocks(content: str) -> list[dict[str, Any]]:
    """Split source into TEST/TEST_F/TEST_P bodies by brace matching."""
    blocks: list[dict[str, Any]] = []
    for match in _RE_TEST_BLOCK.finditer(content):
        suite, case = match.group(1), match.group(2)
        start = match.end() - 1
        depth = 0
        end = start
        for i in range(start, len(content)):
            ch = content[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = content[start + 1 : end]
        line = content[: match.start()].count("\n") + 1
        blocks.append(
            {
                "suite": suite,
                "case": case,
                "name": f"{suite}.{case}",
                "line": line,
                "body": body,
            }
        )
    return blocks


def _analyze_body(body: str) -> dict[str, Any]:
    stripped = re.sub(r"//[^\n]*", "", body)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
    stripped_no_ws = re.sub(r"\s+", "", stripped)

    agent = bool(_RE_AGENT.search(body))
    todo = bool(_RE_TODO.search(body))
    succeed = bool(_RE_SUCCEED.search(body))
    expect_true = bool(_RE_EXPECT_TRUE.search(body))
    assertions = _RE_EXPECT_ASSERT.findall(body)
    real_count = len(assertions)
    tautologies = []
    for m in _RE_TAUTOLOGY.finditer(body):
        tautologies.append(m.group(0).strip())

    trivial_only = (
        real_count == 0
        or (real_count == 1 and (succeed or expect_true))
        or (real_count <= 1 and not stripped_no_ws.replace(";", ""))
    )
    weak = trivial_only or succeed or expect_true or (real_count == 0 and not stripped_no_ws)

    issues: list[str] = []
    if agent:
        issues.append("agent_remaining")
    if todo:
        issues.append("todo_remaining")
    if weak:
        issues.append("weak")
    if tautologies:
        issues.append("tautology")

    score = 100
    if agent:
        score -= 40
    if weak:
        score -= 35
    if tautologies:
        score -= 25
    if todo:
        score -= 10
    if real_count == 0:
        score -= 20
    score = max(0, min(100, score))

    return {
        "agent_remaining": agent,
        "todo_remaining": todo,
        "weak": weak,
        "tautology": bool(tautologies),
        "tautology_examples": tautologies[:3],
        "real_assertions": real_count,
        "issues": issues,
        "score": score,
    }


def analyze_assertion_quality_impl(
    project_dir: str = "",
    tests_dir: str = "",
    test_files: list[str] | str = "",
) -> dict[str, Any]:
    root = Path(project_dir or Path.cwd()).resolve()
    tests_path = resolve_tests_dir(str(root), tests_dir)
    file_filter = parse_test_files_filter(test_files)

    if not tests_path or not tests_path.is_dir():
        return {"status": "error", "error": f"Tests directory not found under {root}"}

    per_file: list[dict[str, Any]] = []
    all_tests: list[dict[str, Any]] = []
    weak_tests: list[dict[str, Any]] = []

    for path in sorted(tests_path.glob("*_test.cpp")):
        if not match_test_file(path, file_filter):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        blocks = _extract_test_blocks(content)
        file_tests: list[dict[str, Any]] = []
        file_score_sum = 0
        for block in blocks:
            analysis = _analyze_body(block["body"])
            entry = {
                "name": block["name"],
                "line": block["line"],
                **analysis,
            }
            file_tests.append(entry)
            all_tests.append({**entry, "file": path.name})
            file_score_sum += analysis["score"]
            if analysis["issues"]:
                weak_tests.append({**entry, "file": path.name})

        avg_score = round(file_score_sum / max(len(blocks), 1), 1) if blocks else 100
        per_file.append(
            {
                "file": path.name,
                "path": str(path.resolve()),
                "test_count": len(blocks),
                "score": avg_score,
                "tests": file_tests,
            }
        )

    overall = (
        round(
            sum(f["score"] for f in per_file) / max(len(per_file), 1),
            1,
        )
        if per_file
        else 100
    )

    result = {
        "status": "ok",
        "project_dir": str(root),
        "tests_dir": str(tests_path.resolve()),
        "file_count": len(per_file),
        "test_count": len(all_tests),
        "score": overall,
        "weak_test_count": len(weak_tests),
        "weak_tests": weak_tests[:50],
        "files": per_file,
    }

    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    out_path = cache / "assertion_quality.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["saved_to"] = str(out_path)
    return result


def load_assertion_quality(project_dir: str = "") -> dict[str, Any]:
    path = Path(project_dir or Path.cwd()) / ".forge" / "cache" / "assertion_quality.json"
    if not path.exists():
        return {"status": "error", "error": "No assertion quality analysis found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "ok"
        return data
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}
