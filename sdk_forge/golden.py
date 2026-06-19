"""Golden oracle cases for production-grade assertion generation.
Golden 预期值 — 驱动 codegen / enrich oracle。
"""

from __future__ import annotations

import json
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
