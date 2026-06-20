"""Draft golden oracle cases from plan/scan (forge-oracle subagent).
从 plan/scan 生成 golden 草稿（forge-oracle）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdk_forge.pipeline.golden import _dump_yaml, find_golden_path, init_golden_template, load_golden_cases
from sdk_forge.domain.plan_gap import _load_plan_state as load_plan_state


def _default_expect_for_scenario(scenario: str, symbol: str) -> Any:
    name = (scenario or "").lower()
    if "error" in name or "invalid" in name or "null" in name:
        return None
    if "zero" in name:
        return 0
    if "negative" in name:
        return -1
    if "float" in name or "double" in name:
        return 1.0
    if "string" in name or "str" in name:
        return "expected"
    if "bool" in name:
        return True
    return 0


def draft_golden_from_plan_impl(
    project_dir: str = "",
    merge: bool = True,
    confirm: bool = False,
) -> dict[str, Any]:
    """Build golden.yaml draft from last_plan.json scenarios (heuristic expects)."""
    root = Path(project_dir or Path.cwd()).resolve()
    plan = load_plan_state(str(root))
    if plan.get("status") == "error" or not plan.get("targets"):
        return {"status": "error", "error": "No saved plan with targets"}

    existing: dict[str, Any] = {}
    if merge:
        loaded = load_golden_cases(str(root))
        existing = dict(loaded.get("golden") or {})

    drafted: dict[str, Any] = {}
    added = 0
    skipped = 0

    for target in plan.get("targets") or []:
        symbol = str(target.get("symbol") or "")
        if not symbol:
            continue
        cases: list[dict[str, Any]] = []
        for scenario in target.get("scenarios") or []:
            sname = str(scenario.get("name") or "Case")
            args = scenario.get("args")
            if args is None:
                args = []
            expect = scenario.get("expect")
            if expect is None:
                expect = _default_expect_for_scenario(sname, symbol)
            entry: dict[str, Any] = {"name": sname, "args": args}
            if scenario.get("expect_error"):
                entry["expect_error"] = True
                entry["comment"] = scenario.get("comment") or "verify SDK error behavior"
            elif expect is not None:
                entry["expect"] = expect
            else:
                entry["comment"] = "TODO: set expect from SDK docs or runtime"
            cases.append(entry)

        if not cases:
            cases.append({
                "name": "Normal",
                "args": [],
                "comment": f"TODO: oracle draft for {symbol}",
            })

        entry = drafted.setdefault(symbol, {"cases": []})
        if not isinstance(entry, dict):
            entry = {"cases": []}
            drafted[symbol] = entry
        existing_cases = entry.setdefault("cases", [])
        existing_names = {str(c.get("name")) for c in existing_cases if isinstance(c, dict)}

        merged_entry = existing.setdefault(symbol, {"cases": []})
        if not isinstance(merged_entry, dict):
            merged_entry = {"cases": []}
            existing[symbol] = merged_entry
        merged_cases = merged_entry.setdefault("cases", [])
        merged_names = {str(c.get("name")) for c in merged_cases if isinstance(c, dict)}

        for case in cases:
            name = str(case.get("name"))
            if name in merged_names:
                skipped += 1
                continue
            merged_cases.append(case)
            merged_names.add(name)
            added += 1

    if not confirm:
        return {
            "status": "ok",
            "dry_run": True,
            "symbols": list(drafted.keys()),
            "added_count": added,
            "skipped_count": skipped,
            "draft": drafted,
            "hint": "Re-run with confirm=true to write .forge/golden.yaml",
        }

    init_golden_template(str(root))
    golden_path = find_golden_path(str(root)) or root / ".forge" / "golden.yaml"
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    golden_path.write_text(_dump_yaml(existing if merge else drafted), encoding="utf-8")
    return {
        "status": "ok",
        "golden_file": str(golden_path.resolve()),
        "symbols": list(drafted.keys()),
        "added_count": added,
        "skipped_count": skipped,
    }
