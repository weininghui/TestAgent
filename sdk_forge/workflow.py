"""Workflow stage tracking for Agent sessions.
Agent 会话工作流阶段跟踪（.forge/cache/workflow.json）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGES = (
    "doctor",
    "scan",
    "plan",
    "scaffold",
    "enrich",
    "quality_gate",
    "gap",
    "build",
    "analyze",
    "propose",
    "apply",
    "report",
)


def update_workflow_stage(project_dir: str, stage: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    if stage not in STAGES:
        return {"status": "error", "error": f"Unknown stage: {stage}. Valid: {', '.join(STAGES)}"}

    root = Path(project_dir or Path.cwd())
    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "workflow.json"

    state: dict[str, Any] = {"stage": stage, "updated_at": datetime.now(timezone.utc).isoformat()}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    state["stage"] = stage
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    if detail:
        state.setdefault("history", []).append({"stage": stage, **detail})
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "ok", "workflow": state, "path": str(path)}


def load_workflow_state(project_dir: str = "") -> dict[str, Any]:
    path = Path(project_dir or Path.cwd()) / ".forge" / "cache" / "workflow.json"
    if not path.exists():
        return {"status": "ok", "stage": None, "path": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "ok"
        data["path"] = str(path)
        return data
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}


def record_agent_completion(
    project_dir: str,
    agent: str,
    status: str = "ok",
    batch_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append sub-agent run result to workflow.json agent_runs."""
    root = Path(project_dir or Path.cwd())
    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "workflow.json"

    state: dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}

    entry: dict[str, Any] = {
        "agent": agent,
        "status": status,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if batch_id is not None:
        entry["batch_id"] = batch_id
    if detail:
        entry.update(detail)

    state.setdefault("agent_runs", []).append(entry)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "ok", "recorded": entry, "path": str(path)}


def _workflow_path(project_dir: str) -> Path:
    root = Path(project_dir or Path.cwd())
    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache / "workflow.json"


def _load_state_raw(project_dir: str) -> dict[str, Any]:
    path = _workflow_path(project_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state_raw(project_dir: str, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _workflow_path(project_dir).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def get_enrich_round(project_dir: str = "") -> int:
    state = _load_state_raw(project_dir)
    try:
        return int(state.get("enrich_round", 0))
    except (TypeError, ValueError):
        return 0


def increment_enrich_round(project_dir: str = "") -> int:
    state = _load_state_raw(project_dir)
    n = get_enrich_round(project_dir) + 1
    state["enrich_round"] = n
    _save_state_raw(project_dir, state)
    return n


def clear_agent_runs(project_dir: str = "", agent: str = "") -> dict[str, Any]:
    """Remove completion records for one agent (e.g. forge-enrich) to allow re-dispatch."""
    state = _load_state_raw(project_dir)
    runs = state.get("agent_runs") or []
    if agent:
        state["agent_runs"] = [r for r in runs if str(r.get("agent") or "") != agent]
    else:
        state["agent_runs"] = []
    _save_state_raw(project_dir, state)
    return {"status": "ok", "cleared_agent": agent or "all", "remaining_runs": len(state["agent_runs"])}
