"""OpenCode session discovery + sub-agent live preview (v5.8)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdk_forge.delegation import (
    _load_state,
    _navigation_hint,
    _save_state,
    list_delegations_impl,
)

_SUBAGENT_TITLE_RE = re.compile(r"@([a-zA-Z0-9_-]+)\s+subagent", re.IGNORECASE)


def _opencode_exe() -> str:
    return shutil.which("opencode") or "opencode"


def _run_opencode_json(args: list[str], timeout: int = 90) -> tuple[Any | None, str | None]:
    cmd = [_opencode_exe(), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    raw = (proc.stdout or "").strip()
    if not raw:
        err = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
        return None, err
    start_candidates = [i for i in (raw.find("{"), raw.find("[")) if i >= 0]
    if not start_candidates:
        return None, "opencode output is not JSON"
    start = min(start_candidates)
    try:
        return json.loads(raw[start:]), None
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error: {exc}"


def list_opencode_sessions_impl(max_count: int = 100) -> dict[str, Any]:
    data, err = _run_opencode_json(
        ["session", "list", "--format", "json", "-n", str(max_count)]
    )
    if err:
        return {"status": "error", "error": err, "sessions": []}
    sessions = data if isinstance(data, list) else []
    return {"status": "ok", "sessions": sessions, "count": len(sessions)}


def _extract_message_text(message: dict[str, Any]) -> str:
    chunks: list[str] = []
    for part in message.get("parts") or []:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype in ("text", "reasoning") and part.get("text"):
            chunks.append(str(part["text"]))
        elif ptype == "tool":
            tool_name = part.get("tool") or part.get("name") or "tool"
            state = part.get("state") or {}
            status = state.get("status") or part.get("status") or ""
            title = state.get("title") or part.get("title") or ""
            label = f"[{tool_name}]"
            if title:
                label = f"[{tool_name}: {title}]"
            if status:
                label = f"{label} ({status})"
            chunks.append(label)
    return "\n".join(chunks).strip()


def export_session_preview_impl(session_id: str, max_chars: int = 500) -> dict[str, Any]:
    if not session_id or not session_id.startswith("ses_"):
        return {"status": "error", "error": "valid session_id required"}
    data, err = _run_opencode_json(["export", session_id])
    if err or not isinstance(data, dict):
        return {"status": "error", "error": err or "export failed", "session_id": session_id}
    info = data.get("info") or {}
    messages = data.get("messages") or []
    last_user = ""
    last_assistant = ""
    last_activity = ""
    last_role = ""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        role = (message.get("info") or {}).get("role") or ""
        text = _extract_message_text(message)
        if not text:
            continue
        if role == "assistant" and not last_assistant:
            last_assistant = text
        elif role == "user" and not last_user:
            last_user = text
        if not last_activity:
            last_activity = text
            last_role = role
        if last_assistant and last_user:
            break
    preview = last_assistant or last_activity or ""
    if len(preview) > max_chars:
        preview = preview[: max_chars - 3] + "..."
    return {
        "status": "ok",
        "session_id": session_id,
        "title": info.get("title") or "",
        "parent_id": info.get("parentID") or info.get("parentId") or "",
        "agent": (messages[-1].get("info") or {}).get("agent") if messages else "",
        "message_count": len(messages),
        "last_role": last_role,
        "last_user_snippet": (last_user[:200] + "...") if len(last_user) > 200 else last_user,
        "live_preview": preview,
        "updated_at": info.get("time", {}).get("updated") if isinstance(info.get("time"), dict) else None,
    }


def _session_matches_delegation(session: dict[str, Any], entry: dict[str, Any]) -> bool:
    title = str(session.get("title") or "")
    agent = str(entry.get("agent") or "")
    task_title = str(entry.get("title") or "")
    if task_title and task_title.lower() in title.lower():
        return True
    if agent and f"(@{agent} subagent)".lower() in title.lower():
        return True
    m = _SUBAGENT_TITLE_RE.search(title)
    if m and agent and m.group(1).lower() == agent.lower():
        return True
    return False


def sync_delegation_sessions_impl(
    project_dir: str = "",
    parent_session_id: str = "",
) -> dict[str, Any]:
    """Bind pending delegations to OpenCode sessions by title / subagent pattern."""
    listing = list_opencode_sessions_impl(max_count=200)
    if listing.get("status") != "ok":
        return listing
    sessions = listing.get("sessions") or []
    if parent_session_id:
        parent_exports: dict[str, dict[str, Any]] = {}
        for session in sessions:
            sid = session.get("id")
            if not sid:
                continue
            preview = export_session_preview_impl(str(sid), max_chars=1)
            if preview.get("status") == "ok" and preview.get("parent_id") == parent_session_id:
                parent_exports[str(sid)] = session
        if parent_exports:
            sessions = list(parent_exports.values())

    state = _load_state(project_dir)
    bound: list[dict[str, Any]] = []
    used_session_ids: set[str] = set()
    for entry in state.get("delegations") or []:
        if entry.get("session_id"):
            used_session_ids.add(str(entry["session_id"]))
            continue
        if entry.get("status") != "pending":
            continue
        for session in sessions:
            sid = str(session.get("id") or "")
            if not sid or sid in used_session_ids:
                continue
            if not _session_matches_delegation(session, entry):
                continue
            entry["session_id"] = sid
            entry["session_updated_at"] = datetime.now(timezone.utc).isoformat()
            entry["session_title"] = session.get("title")
            used_session_ids.add(sid)
            bound.append(
                {
                    "task_id": entry.get("task_id"),
                    "agent": entry.get("agent"),
                    "session_id": sid,
                    "title": session.get("title"),
                    "navigation": _navigation_hint(entry),
                }
            )
            break
    if bound:
        _save_state(project_dir, state)
    return {"status": "ok", "bound": bound, "bound_count": len(bound)}


def get_subagent_dashboard_impl(
    project_dir: str = "",
    parent_session_id: str = "",
    include_preview: bool = True,
    max_preview_chars: int = 400,
) -> dict[str, Any]:
    """Unified view: pending sub-agents, session ids, live preview, jump hints."""
    sync = sync_delegation_sessions_impl(project_dir, parent_session_id=parent_session_id)
    listing = list_delegations_impl(project_dir)
    pending = listing.get("pending") or []
    completed = listing.get("completed") or []

    rows: list[dict[str, Any]] = []
    for entry in pending + completed:
        nav = _navigation_hint(entry)
        row: dict[str, Any] = {
            "task_id": entry.get("task_id"),
            "agent": entry.get("agent"),
            "batch_id": entry.get("batch_id"),
            "title": entry.get("title"),
            "status": entry.get("status"),
            "session_id": entry.get("session_id") or "",
            "session_title": entry.get("session_title") or "",
            "navigation": nav,
        }
        sid = entry.get("session_id")
        if include_preview and sid:
            preview = export_session_preview_impl(str(sid), max_chars=max_preview_chars)
            if preview.get("status") == "ok":
                row["live_preview"] = preview.get("live_preview") or ""
                row["message_count"] = preview.get("message_count")
                row["session_title"] = preview.get("title") or row["session_title"]
                if not row["session_title"]:
                    row["session_title"] = preview.get("title")
        rows.append(row)

    pending_rows = [r for r in rows if r.get("status") == "pending"]
    return {
        "status": "ok",
        "sync": sync,
        "pending_count": len(pending_rows),
        "subagents": rows,
        "how_to_open": {
            "gui": (
                "OpenCode 桌面版：左侧 Session 列表 → 找标题含 (@forge-xxx subagent) 或下方 session_id → 点击进入聊天"
            ),
            "tui": "在 forge 主 session 按 Down 进入第一个子 session，Left/Right 切换，Up 回主 session",
            "terminal": "opencode run --session <session_id> --continue  （在新终端打开该子 agent 聊天）",
            "peek": "peek_subagent_session(session_id=...) 或本工具的 live_preview 字段",
        },
        "user_report_hint": (
            "派发后用中文向用户展示表格：agent | batch | session_id | live_preview | 如何打开"
        ),
    }
