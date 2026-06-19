"""Session context: plan, build state, learned config."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdk_forge.learn import load_learned_config
from sdk_forge.plan_gap import load_plan_gap
from sdk_forge.report import report_impl
from sdk_forge.retry import load_build_state
from sdk_forge.test_fix import load_proposals


def save_plan_state(project_dir: str, plan: dict[str, Any]) -> Path:
    root = Path(project_dir or Path.cwd())
    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "last_plan.json"
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_plan_state(project_dir: str) -> dict[str, Any]:
    path = Path(project_dir or Path.cwd()) / ".forge" / "cache" / "last_plan.json"
    if not path.exists():
        return {"status": "error", "error": "No saved plan found"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}


def get_session_context_impl(project_dir: str = "") -> dict[str, Any]:
    root = Path(project_dir or Path.cwd())
    plan_path = root / ".forge" / "cache" / "last_plan.json"
    build_state = load_build_state(str(root))
    plan = load_plan_state(str(root)) if plan_path.exists() else None

    sdk_root = ""
    if isinstance(build_state, dict) and build_state.get("sdk_root"):
        sdk_root = build_state["sdk_root"]
    elif isinstance(plan, dict) and plan.get("sdk_root"):
        sdk_root = plan["sdk_root"]

    learned = load_learned_config(sdk_root, str(root)) if sdk_root else {"status": "ok", "found": False}

    report_summary = {}
    if isinstance(build_state, dict) and build_state.get("status") != "error":
        rep = report_impl(project_dir=str(root), output_format="json")
        if rep.get("status") == "ok":
            report_summary = rep.get("summary") or {}

    plan_gap = load_plan_gap(str(root))
    proposals = load_proposals(str(root))

    compdb_path = root / ".forge" / "cache" / "compile_commands.json"

    return {
        "status": "ok",
        "project_dir": str(root.resolve()),
        "plan": plan if plan and plan.get("status") != "error" else None,
        "build_state": build_state if build_state.get("status") != "error" else None,
        "learned_config": learned if learned.get("found") else None,
        "plan_gap": plan_gap if plan_gap.get("status") == "ok" else None,
        "last_proposals": proposals if proposals.get("status") == "ok" else None,
        "compile_commands": str(compdb_path) if compdb_path.is_file() else None,
        "last_report_summary": report_summary or None,
    }
