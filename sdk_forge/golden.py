"""Golden oracle cases for production-grade assertion generation.
Golden 预期值 — 驱动 codegen / enrich oracle。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

GOLDEN_FILENAMES = (".forge/golden.yaml", ".forge/golden.yml", "golden.yaml")


def _parse_yaml(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("PyYAML required for golden.yaml") from exc
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def find_golden_path(project_dir: str) -> Path | None:
    root = Path(project_dir or Path.cwd()).resolve()
    for name in GOLDEN_FILENAMES:
        path = root / name if name.startswith(".forge") else root / ".forge" / name
        if path.is_file():
            return path
    golden_dir = root / ".forge" / "golden"
    if golden_dir.is_dir():
        files = sorted(golden_dir.glob("*.yaml")) + sorted(golden_dir.glob("*.yml"))
        if files:
            return files[0]
    return None


def load_golden_cases(project_dir: str = "", symbol: str = "") -> dict[str, Any]:
    root = Path(project_dir or Path.cwd()).resolve()
    golden_dir = root / ".forge" / "golden"
    merged: dict[str, Any] = {}

    main = find_golden_path(str(root))
    if main and main.parent.name != "golden":
        try:
            text = main.read_text(encoding="utf-8")
            merged.update(_parse_yaml(text) if main.suffix in (".yaml", ".yml") else json.loads(text))
        except (OSError, json.JSONDecodeError, RuntimeError):
            pass

    if golden_dir.is_dir():
        for path in sorted(golden_dir.glob("*.yaml")) + sorted(golden_dir.glob("*.yml")):
            try:
                data = _parse_yaml(path.read_text(encoding="utf-8"))
                sym = path.stem
                if isinstance(data, dict) and "cases" in data:
                    merged[sym] = data
                elif isinstance(data, dict):
                    merged.update(data)
            except (OSError, RuntimeError):
                continue

    if symbol:
        key = symbol.lower().replace("-", "_")
        for k, v in merged.items():
            if k.lower().replace("-", "_") == key:
                return {"status": "ok", "symbol": k, "cases": (v.get("cases") if isinstance(v, dict) else v) or []}
        return {"status": "ok", "symbol": symbol, "cases": []}

    return {"status": "ok", "project_dir": str(root), "symbols": list(merged.keys()), "golden": merged}


def golden_to_enrich_hints(symbol: str, cases: list[dict[str, Any]]) -> list[str]:
    hints: list[str] = []
    for case in cases or []:
        name = case.get("name", "?")
        args = case.get("args")
        expect = case.get("expect")
        if expect is not None:
            hints.append(f"golden[{name}]: args={args} expect={expect}")
        elif case.get("expect_error"):
            hints.append(f"golden[{name}]: expect error for args={args}")
        elif case.get("comment"):
            hints.append(f"golden[{name}]: {case['comment']}")
    return hints


def verify_golden_in_tests(project_dir: str = "") -> dict[str, Any]:
    """Check golden cases appear referenced in test sources (best-effort)."""
    root = Path(project_dir or Path.cwd()).resolve()
    loaded = load_golden_cases(str(root))
    golden = loaded.get("golden") or {}
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return {"status": "error", "error": "tests/ not found"}

    all_content = ""
    for path in tests_dir.glob("*_test.cpp"):
        try:
            all_content += path.read_text(encoding="utf-8") + "\n"
        except OSError:
            continue

    covered: list[str] = []
    missing: list[dict[str, Any]] = []
    for sym, data in golden.items():
        cases = (data.get("cases") if isinstance(data, dict) else []) or []
        sym_ref = sym.lower().replace("-", "_")
        if sym_ref not in all_content.lower() and sym not in all_content:
            missing.append({"symbol": sym, "reason": "symbol not referenced in tests"})
            continue
        for case in cases:
            expect = case.get("expect")
            if expect is not None and str(expect) in all_content:
                covered.append(f"{sym}.{case.get('name')}")
            else:
                missing.append({"symbol": sym, "case": case.get("name"), "expect": expect})

    return {
        "status": "ok",
        "project_dir": str(root),
        "covered_count": len(covered),
        "missing_count": len(missing),
        "covered": covered[:50],
        "missing": missing[:50],
    }


GOLDEN_TEMPLATE = """# Golden oracle cases (v4.8)
# Per-symbol expected values for production-grade assertions.
#
# calc_add:
#   cases:
#     - name: normal
#       args: [2, 3]
#       expect: 5
#     - name: error
#       args: [1, 0]
#       expect_error: true
#       comment: division by zero — verify SDK behavior

calc_add:
  cases:
    - name: normal
      args: [2, 3]
      expect: 5
"""


def init_golden_template(project_dir: str) -> Path:
    root = Path(project_dir or Path.cwd()).resolve()
    forge_dir = root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    path = forge_dir / "golden.yaml"
    if not path.exists():
        path.write_text(GOLDEN_TEMPLATE, encoding="utf-8")
    return path


def _dump_yaml(data: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("PyYAML required for golden.yaml") from exc
    return yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


_RE_TEST_BLOCK = re.compile(
    r"TEST(?:_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*\{",
    re.MULTILINE,
)
_RE_EXPECT_EQ = re.compile(
    r"EXPECT_EQ\s*\(\s*([^,()]+(?:\([^)]*\))?)\s*,\s*([^)]+)\s*\)",
)
_RE_CALL = re.compile(r"(?:([\w:]+)::)?(\w+)\s*\(([^)]*)\)")


def _parse_literal(value: str) -> Any:
    value = value.strip()
    if not value:
        return None
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_call_args(args_str: str) -> list[Any]:
    if not args_str.strip():
        return []
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in args_str:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [_parse_literal(p) for p in parts if p.strip()]


def _extract_expect_eq_cases(content: str, default_symbol: str = "") -> list[dict[str, Any]]:
    """Extract EXPECT_EQ(call, expect) cases grouped by TEST scenario name."""
    cases: list[dict[str, Any]] = []
    for match in _RE_TEST_BLOCK.finditer(content):
        _suite, scenario = match.group(1), match.group(2)
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
        for eq in _RE_EXPECT_EQ.finditer(body):
            call_expr = eq.group(1).strip()
            expect_expr = eq.group(2).strip()
            call_match = _RE_CALL.match(call_expr)
            symbol = default_symbol
            args: list[Any] = []
            if call_match:
                symbol = call_match.group(2) or default_symbol
                args = _parse_call_args(call_match.group(3) or "")
            expect = _parse_literal(expect_expr)
            if expect is None or (isinstance(expect, str) and expect == call_expr):
                continue
            cases.append({
                "name": scenario,
                "args": args,
                "expect": expect,
                "symbol": symbol,
            })
    return cases


def _symbol_from_test_file(path: Path) -> str:
    name = path.stem
    if name.endswith("_test"):
        return name[: -len("_test")]
    return name


def snapshot_golden_from_plan_impl(
    project_dir: str = "",
    merge: bool = True,
    confirm: bool = False,
    from_last_build: bool = False,
) -> dict[str, Any]:
    """Extract EXPECT_EQ cases from generated tests and merge into .forge/golden.yaml."""
    root = Path(project_dir or Path.cwd()).resolve()
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return {"status": "error", "error": "tests/ not found"}

    if from_last_build:
        build_path = root / ".forge" / "cache" / "last_build.json"
        if not build_path.is_file():
            return {"status": "error", "error": "No last_build.json; run build first"}

    plan_path = root / ".forge" / "cache" / "last_plan.json"
    plan_symbols: dict[str, str] = {}
    if plan_path.is_file():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            for target in plan.get("targets") or []:
                sym = str(target.get("symbol") or "")
                if sym:
                    plan_symbols[sym.lower()] = sym
        except (OSError, json.JSONDecodeError):
            pass

    existing: dict[str, Any] = {}
    golden_path = root / ".forge" / "golden.yaml"
    if merge and golden_path.is_file():
        try:
            existing = _parse_yaml(golden_path.read_text(encoding="utf-8"))
        except (OSError, RuntimeError):
            existing = {}

    extracted: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(tests_dir.glob("*_test.cpp")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        file_symbol = _symbol_from_test_file(path)
        sym_key = plan_symbols.get(file_symbol.lower(), file_symbol)
        for case in _extract_expect_eq_cases(content, default_symbol=sym_key):
            symbol = case.pop("symbol", sym_key) or sym_key
            extracted.setdefault(symbol, []).append(case)

    if not extracted:
        return {"status": "ok", "added_count": 0, "message": "No EXPECT_EQ cases found in tests"}

    merged = dict(existing) if merge else {}
    added = 0
    skipped = 0
    for symbol, cases in extracted.items():
        entry = merged.setdefault(symbol, {"cases": []})
        if not isinstance(entry, dict):
            entry = {"cases": []}
            merged[symbol] = entry
        existing_cases = entry.setdefault("cases", [])
        existing_names = {str(c.get("name")) for c in existing_cases if isinstance(c, dict)}
        for case in cases:
            name = str(case.get("name", ""))
            if name in existing_names:
                skipped += 1
                continue
            existing_cases.append({
                "name": name,
                "args": case.get("args", []),
                "expect": case.get("expect"),
            })
            existing_names.add(name)
            added += 1

    if not confirm and added > 0:
        return {
            "status": "ok",
            "dry_run": True,
            "added_count": added,
            "skipped_count": skipped,
            "symbols": list(extracted.keys()),
            "hint": "Re-run with confirm=true to write .forge/golden.yaml",
        }

    golden_path.parent.mkdir(parents=True, exist_ok=True)
    golden_path.write_text(_dump_yaml(merged), encoding="utf-8")
    return {
        "status": "ok",
        "golden_file": str(golden_path.resolve()),
        "added_count": added,
        "skipped_count": skipped,
        "symbols": list(extracted.keys()),
    }
