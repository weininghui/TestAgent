"""Background delegation state for multi-agent orchestration (v5.5+).
后台委托状态跟踪 — .forge/cache/delegations.json
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdk_forge.orchestration import delegation_concurrency, delegation_mode, get_orchestration_context

_TASK_ID_RE = re.compile(
    r"(?:Background Task ID|Task ID|task_id|background_task_id)[:\s]+([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
_SESSION_ID_RE = re.compile(
    r"(?:Session ID|session_id|sessionId)[:\s]+(ses_[a-zA-Z0-9_-]+|pending)",
    re.IGNORECASE,
)
_TASK_METADATA_RE = re.compile(
    r"<task_metadata>([\s\S]*?)</task_metadata>",
    re.IGNORECASE,
)


def _parse_task_metadata_block(text: str) -> dict[str, str]:
    """Parse OMO <task_metadata> block (packages/omo-opencode task-metadata-contract)."""
    match = _TASK_METADATA_RE.search(text or "")
    if not match:
        return {}
    parsed: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key in ("session_id", "sessionid"):
            parsed["session_id"] = value
        elif key in ("task_id", "taskid"):
            parsed["task_id"] = value
        elif key == "background_task_id":
            parsed["background_task_id"] = value
        elif key in ("subagent", "agent"):
            parsed["agent"] = value
    return parsed


def parse_omo_task_result_impl(text: str) -> dict[str, Any]:
    """Parse OMO task() / call_omo_agent text output for task_id and session_id."""
    raw = text or ""
    meta = _parse_task_metadata_block(raw)
    task_match = _TASK_ID_RE.search(raw)
    session_match = _SESSION_ID_RE.search(raw)
    task_id = meta.get("background_task_id") or meta.get("task_id") or (
        task_match.group(1) if task_match else ""
    )
    session_id = meta.get("session_id") or ""
    if session_match and not session_id:
        sid = session_match.group(1)
        if sid.lower() != "pending":
            session_id = sid
    return {
        "status": "ok",
        "task_id": task_id or None,
        "session_id": session_id or None,
        "clickable": bool(session_id),
        "hint": (
            "TUI: press Down to enter child session when session_id is set"
            if session_id
            else "Wait for session_id in background_output(block=false), then update_forge_delegation_session"
        ),
    }


def register_from_omo_result_impl(
    project_dir: str,
    omo_result_text: str,
    agent: str,
    batch_id: int | None = None,
    title: str = "",
) -> dict[str, Any]:
    """Parse OMO task output and register delegation + session binding."""
    parsed = parse_omo_task_result_impl(omo_result_text)
    task_id = parsed.get("task_id")
    if not task_id:
        return {
            "status": "error",
            "error": "Could not parse task_id from OMO result",
            "parsed": parsed,
        }
    reg = register_delegation_impl(
        project_dir,
        str(task_id),
        agent,
        batch_id=batch_id,
        title=title,
        session_id=str(parsed["session_id"]) if parsed.get("session_id") else "",
        runtime="omo",
    )
    reg["parsed"] = parsed
    return reg


def _delegations_path(project_dir: str) -> Path:
    root = Path(project_dir or Path.cwd())
    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache / "delegations.json"


def _load_state(project_dir: str) -> dict[str, Any]:
    path = _delegations_path(project_dir)
    if not path.is_file():
        return {"delegations": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"delegations": []}
        data.setdefault("delegations", [])
        return data
    except (OSError, json.JSONDecodeError):
        return {"delegations": []}


def _save_state(project_dir: str, state: dict[str, Any]) -> Path:
    path = _delegations_path(project_dir)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _navigation_hint(entry: dict[str, Any]) -> dict[str, Any]:
    session_id = entry.get("session_id") or ""
    task_id = entry.get("task_id") or ""
    agent = entry.get("agent") or ""
    hints: dict[str, Any] = {
        "task_id": task_id,
        "agent": agent,
        "title": entry.get("title"),
        "runtime": entry.get("runtime", "omo"),
    }
    if session_id:
        hints["session_id"] = session_id
        hints["tui"] = "Press Down (session_child_first) to enter this sub-agent session"
        hints["cli_resume"] = f"opencode run --session {session_id} --continue"
        hints["gui"] = (
            f"OpenCode 桌面版：左侧 Session 列表 → 点击 session_id `{session_id}` "
            f"或标题含「{entry.get('title') or agent}」的会话"
        )
        hints["open_chat"] = f"opencode run --session {session_id} --continue"
        hints["peek"] = f"peek_subagent_session(session_id={session_id})"
    else:
        hints["tui"] = (
            "If sub-agent entry spins without click: wait for session_id, then "
            "call sync_delegation_sessions or get_subagent_dashboard"
        )
        hints["cli_resume"] = "opencode session list"
        hints["gui"] = "先调用 get_subagent_dashboard 自动匹配 session_id，再到左侧 Session 列表点击"
        hints["sync"] = "sync_delegation_sessions(project_dir=...)"
    if entry.get("pid"):
        hints["pid"] = entry["pid"]
    return hints


def register_delegation_impl(
    project_dir: str,
    task_id: str,
    agent: str,
    batch_id: int | None = None,
    title: str = "",
    session_id: str = "",
    runtime: str = "omo",
    pid: int | None = None,
) -> dict[str, Any]:
    if not task_id or not agent:
        return {"status": "error", "error": "task_id and agent required"}
    state = _load_state(project_dir)
    entry: dict[str, Any] = {
        "task_id": str(task_id),
        "agent": agent,
        "batch_id": batch_id,
        "title": title or agent,
        "status": "pending",
        "runtime": runtime or "omo",
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    if session_id:
        entry["session_id"] = str(session_id)
    if pid is not None:
        entry["pid"] = int(pid)
    delegations = [d for d in state.get("delegations") or [] if d.get("task_id") != task_id]
    delegations.append(entry)
    state["delegations"] = delegations
    path = _save_state(project_dir, state)
    return {
        "status": "ok",
        "delegation": entry,
        "navigation": _navigation_hint(entry),
        "path": str(path),
    }


def update_delegation_session_impl(
    project_dir: str,
    task_id: str,
    session_id: str,
) -> dict[str, Any]:
    if not task_id or not session_id:
        return {"status": "error", "error": "task_id and session_id required"}
    state = _load_state(project_dir)
    updated = False
    entry: dict[str, Any] | None = None
    for item in state.get("delegations") or []:
        if item.get("task_id") == task_id:
            item["session_id"] = str(session_id)
            item["session_updated_at"] = datetime.now(timezone.utc).isoformat()
            entry = item
            updated = True
            break
    if not updated:
        return {"status": "not_found", "error": f"No delegation for task_id={task_id}"}
    _save_state(project_dir, state)
    assert entry is not None
    return {
        "status": "ok",
        "delegation": entry,
        "navigation": _navigation_hint(entry),
    }


def poll_cli_delegate_processes(project_dir: str = "") -> dict[str, Any]:
    """Mark CLI delegations complete when their subprocess exits."""
    state = _load_state(project_dir)
    updated: list[str] = []
    for entry in state.get("delegations") or []:
        if entry.get("runtime") != "cli" or entry.get("status") != "pending":
            continue
        pid = entry.get("pid")
        if pid is None:
            continue
        try:
            import os

            os.kill(int(pid), 0)
        except OSError:
            entry["status"] = "ok"
            entry["completed_at"] = datetime.now(timezone.utc).isoformat()
            entry["exit_reason"] = "process_exited"
            updated.append(str(entry.get("task_id")))
    if updated:
        _save_state(project_dir, state)
    return {"status": "ok", "completed_task_ids": updated}


def complete_delegation_impl(
    project_dir: str,
    agent: str,
    batch_id: int | None = None,
    task_id: str = "",
    status: str = "ok",
) -> dict[str, Any]:
    state = _load_state(project_dir)
    updated = False
    for entry in state.get("delegations") or []:
        if task_id and entry.get("task_id") != task_id:
            continue
        if not task_id:
            if entry.get("agent") != agent:
                continue
            eb = entry.get("batch_id")
            if batch_id is not None and eb != batch_id:
                continue
            if entry.get("status") != "pending":
                continue
        entry["status"] = status
        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        updated = True
        if task_id:
            break
    if updated:
        _save_state(project_dir, state)
    return {"status": "ok" if updated else "not_found", "updated": updated}


def list_delegations_impl(project_dir: str = "") -> dict[str, Any]:
    poll_cli_delegate_processes(project_dir)
    state = _load_state(project_dir)
    delegations = state.get("delegations") or []
    pending = [d for d in delegations if d.get("status") == "pending"]
    done = [d for d in delegations if d.get("status") != "pending"]
    return {
        "status": "ok",
        "pending": pending,
        "completed": done,
        "pending_count": len(pending),
    }


def poll_forge_delegations_impl(project_dir: str = "") -> dict[str, Any]:
    """Return pending vs completed delegations for primary forge polling."""
    listing = list_delegations_impl(project_dir)
    orch = get_orchestration_context(project_dir)
    completed_agents = orch.get("completed_agents") or {}
    pending_nav = [_navigation_hint(d) for d in listing["pending"]]
    return {
        "status": "ok",
        "pending_delegations": listing["pending"],
        "completed_delegations": listing["completed"],
        "pending_count": listing["pending_count"],
        "completed_agents": completed_agents,
        "stage_timeline": orch.get("stage_timeline"),
        "navigation": {
            "pending": pending_nav,
            "tui_parent_child": "Down=enter child session, Up=return to forge primary",
            "session_list": "opencode session list",
        },
    }


def all_parallel_done_impl(
    project_dir: str,
    agent: str,
    batch_ids: list[int],
) -> dict[str, Any]:
    orch = get_orchestration_context(project_dir)
    completed = orch.get("completed_agents") or {}
    done_batches = set(completed.get(agent) or [])
    missing = [bid for bid in batch_ids if bid not in done_batches]
    return {
        "status": "ok",
        "all_done": not missing,
        "missing_batch_ids": missing,
        "completed_batch_ids": sorted(done_batches),
    }


def get_delegation_plan_impl(project_dir: str = "") -> dict[str, Any]:
    """Build dispatch plan from orchestration next_actions."""
    from sdk_forge.task_dispatch import build_task_dispatches_impl

    orch = get_orchestration_context(project_dir)
    actions = orch.get("next_actions") or []
    mode = orch.get("delegation_mode") or delegation_mode(project_dir)
    concurrency = orch.get("delegation_concurrency") or delegation_concurrency(project_dir)
    dispatchable = [a for a in actions if not a.get("blocked")]
    background = [a for a in dispatchable if a.get("run_in_background")]
    foreground = [a for a in dispatchable if not a.get("run_in_background")]
    task_plan = build_task_dispatches_impl(project_dir)
    gui_modes = mode in ("omo", "task")
    return {
        "status": "ok",
        "delegation_mode": mode,
        "delegation_concurrency": concurrency,
        "actions": dispatchable,
        "background_actions": background,
        "foreground_actions": foreground,
        "blocked_actions": [a for a in actions if a.get("blocked")],
        "merge_ready": bool(orch.get("merge_ready")),
        "orchestration_status": "needs_agent" if dispatchable else ("ok" if orch.get("merge_ready") else "idle"),
        "dispatch_protocol": task_plan.get("dispatch_protocol"),
        "gui_task_card": gui_modes,
        "task_dispatches": task_plan.get("task_dispatches"),
        "forbidden_tools": task_plan.get("forbidden_tools"),
        "forbidden_params": task_plan.get("forbidden_params"),
        "dispatch_hint": (
            "OMO task(): subagent_type + load_skills=[] + description + run_in_background — "
            "renders OpenCode GUI Task card. NEVER call_omo_agent or task(agent=)."
            if gui_modes
            else "cli: dispatch_forge_delegate — no GUI Task card"
            if mode == "cli"
            else "inline: sync task — no OMO GUI Task card"
        ),
        "omo_task_template": {
            "load_skills": [],
            "note": "Use OMO task tool with subagent_type + description + run_in_background",
        } if gui_modes else None,
    }


def clear_delegations_impl(project_dir: str = "") -> dict[str, Any]:
    path = _delegations_path(project_dir)
    state = {"delegations": [], "cleared_at": datetime.now(timezone.utc).isoformat()}
    _save_state(project_dir, state)
    return {"status": "ok", "path": str(path)}
