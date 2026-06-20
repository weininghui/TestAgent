"""Sub-agent timeout / stall detection and recovery (v5.11)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sdk_forge.infra.config import load_forge_config
from sdk_forge.delegation.core import list_delegations_impl
from sdk_forge.delegation.session_nav import export_session_preview_impl

DEFAULT_STALE_SEC = 900
DEFAULT_EXPORT_TIMEOUT_SEC = 120

TIMEOUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"upstream idle timeout", re.IGNORECASE),
    re.compile(r"idle timeout exceeded", re.IGNORECASE),
    re.compile(r"tool execution aborted", re.IGNORECASE),
    re.compile(r"request timed out", re.IGNORECASE),
    re.compile(r"connection timed out", re.IGNORECASE),
    re.compile(r"deadline exceeded", re.IGNORECASE),
)

TOOL_FAILURE_STATUSES = frozenset({"failed", "error", "aborted", "cancelled", "timeout", "denied"})
TOOL_FAILURE_TITLE = re.compile(r"失败|failed|abort|timeout|denied|error", re.IGNORECASE)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _age_seconds(ts: str | None) -> float | None:
    dt = _parse_iso(ts)
    if not dt:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())


def _delegation_stale_sec(project_dir: str) -> int:
    cfg = load_forge_config(start=project_dir or ".")
    raw = cfg.get("delegation_stale_sec", DEFAULT_STALE_SEC)
    try:
        return max(60, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_STALE_SEC


def _scan_text_for_issues(text: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for pat in TIMEOUT_PATTERNS:
        if pat.search(text or ""):
            issues.append(
                {
                    "kind": "timeout",
                    "pattern": pat.pattern,
                    "message": pat.search(text or "").group(0),
                }
            )
            break
    return issues


def scan_message_parts(parts: list[Any]) -> list[dict[str, Any]]:
    """Detect tool failures / timeout strings in one assistant message."""
    issues: list[dict[str, Any]] = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "text":
            issues.extend(_scan_text_for_issues(str(part.get("text") or "")))
            continue
        if ptype != "tool":
            continue
        tool_name = str(part.get("tool") or part.get("name") or "tool")
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        status = str(state.get("status") or part.get("status") or "").lower()
        title = str(state.get("title") or part.get("title") or "")
        error = str(state.get("error") or part.get("error") or state.get("message") or "")
        blob = " ".join(x for x in (title, error, status) if x)
        if status in TOOL_FAILURE_STATUSES or TOOL_FAILURE_TITLE.search(title):
            issues.append(
                {
                    "kind": "tool_failure",
                    "tool": tool_name,
                    "status": status or "failed",
                    "title": title,
                    "error": error or title,
                }
            )
        issues.extend(_scan_text_for_issues(blob))
    return issues


def analyze_session_export(data: dict[str, Any]) -> dict[str, Any]:
    """Summarize health from opencode export JSON."""
    messages = data.get("messages") or []
    all_issues: list[dict[str, Any]] = []
    last_assistant_at: str | None = None
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        info = message.get("info") or {}
        role = str(info.get("role") or "")
        parts = message.get("parts") or []
        if role == "assistant":
            msg_issues = scan_message_parts(parts)
            if msg_issues and not all_issues:
                all_issues = msg_issues
            if not last_assistant_at:
                t = info.get("time") or {}
                if isinstance(t, dict):
                    last_assistant_at = str(t.get("updated") or t.get("created") or "")
    health = "ok"
    if any(i.get("kind") == "timeout" for i in all_issues):
        health = "timeout"
    elif all_issues:
        health = "tool_failure"
    return {
        "health": health,
        "issues": all_issues,
        "message_count": len(messages),
        "last_assistant_at": last_assistant_at,
        "idle_sec": _age_seconds(last_assistant_at),
    }


def _entry_health(entry: dict[str, Any], project_dir: str, include_preview: bool) -> dict[str, Any]:
    stale_sec = _delegation_stale_sec(project_dir)
    registered_at = str(entry.get("registered_at") or "")
    session_id = str(entry.get("session_id") or "")
    age = _age_seconds(registered_at)

    row: dict[str, Any] = {
        "task_id": entry.get("task_id"),
        "agent": entry.get("agent"),
        "batch_id": entry.get("batch_id"),
        "title": entry.get("title"),
        "status": entry.get("status"),
        "session_id": session_id,
        "registered_at": registered_at,
        "age_sec": round(age, 1) if age is not None else None,
        "stale_threshold_sec": stale_sec,
        "health": "pending",
        "issues": [],
        "recovery": None,
    }

    if entry.get("status") != "pending":
        row["health"] = str(entry.get("status") or "done")
        return row

    if not session_id:
        if age is not None and age > stale_sec:
            row["health"] = "stale"
            row["issues"] = [{"kind": "no_session", "message": "session_id still missing"}]
            row["recovery"] = _recovery_hint(entry, "no_session")
        return row

    if not include_preview:
        if age is not None and age > stale_sec:
            row["health"] = "stale"
            row["issues"] = [{"kind": "stale", "message": f"pending for {int(age)}s"}]
            row["recovery"] = _recovery_hint(entry, "stale")
        return row

    preview = export_session_preview_impl(session_id, max_chars=2000)
    if preview.get("status") != "ok":
        row["health"] = "unknown"
        row["issues"] = [{"kind": "export_error", "message": preview.get("error") or "export failed"}]
        return row

    analyzed = {
        "health": preview.get("health") or "ok",
        "issues": list(preview.get("issues") or []),
        "idle_sec": _age_seconds(str(preview.get("updated_at") or "")),
    }

    row["issues"] = analyzed.get("issues") or []
    row["idle_sec"] = analyzed.get("idle_sec")
    row["live_preview"] = preview.get("live_preview")
    row["health"] = analyzed.get("health") or "ok"

    idle = analyzed.get("idle_sec")
    if row["health"] == "ok" and idle is not None and idle > stale_sec:
        row["health"] = "stale"
        row["issues"].append({"kind": "stale", "message": f"no assistant activity for {int(idle)}s"})
    if row["health"] in ("timeout", "tool_failure", "stale"):
        row["recovery"] = _recovery_hint(entry, row["health"])
    return row


def _recovery_hint(entry: dict[str, Any], reason: str) -> dict[str, Any]:
    agent = str(entry.get("agent") or "")
    batch_id = entry.get("batch_id")
    task_id = str(entry.get("task_id") or "")
    session_id = str(entry.get("session_id") or "")
    return {
        "reason": reason,
        "recommended": [
            "recover_stalled_subagent(project_dir=..., task_id=..., action=retry)",
            f"opencode run --session {session_id} --continue  # resume sub-agent manually",
            "Split large writes into smaller files / shorter prompts to avoid idle timeout",
        ],
        "advance_workflow": {
            "tool": "sdk-forge_advance_forge_workflow",
            "last_agent": agent,
            "last_status": "error",
            "batch_id": batch_id,
            "detail_json": '{"failure":"upstream_idle_timeout","recoverable":true}',
        },
        "redispatch": {
            "tool": "task",
            "note": "After advance_forge_workflow(error), get_task_dispatch_plan may emit retry action",
            "run_in_background": True,
        },
        "task_id": task_id,
        "session_id": session_id,
    }


def check_subagent_health_impl(
    project_dir: str = "",
    include_preview: bool = True,
) -> dict[str, Any]:
    """Scan pending delegations for timeouts, tool failures, and stale sessions."""
    listing = list_delegations_impl(project_dir)
    pending = listing.get("pending") or []
    rows = [_entry_health(entry, project_dir, include_preview) for entry in pending]
    unhealthy = [r for r in rows if r.get("health") not in ("ok", "pending")]
    return {
        "status": "ok",
        "pending_count": len(pending),
        "unhealthy_count": len(unhealthy),
        "stale_threshold_sec": _delegation_stale_sec(project_dir),
        "subagents": rows,
        "needs_recovery": unhealthy,
        "user_hint_zh": (
            "若 live_preview 含「Upstream idle timeout」或 write 失败："
            "调用 recover_stalled_subagent(action=retry) 或手动 resume 子 session 后继续。"
        ),
    }


def recover_stalled_subagent_impl(
    project_dir: str = "",
    task_id: str = "",
    action: str = "retry",
    failure_reason: str = "upstream_idle_timeout",
) -> dict[str, Any]:
    """Mark a stalled delegation as error and advance workflow for orchestration retry."""
    from sdk_forge.orchestration.workflow_advance import advance_forge_workflow_impl

    listing = list_delegations_impl(project_dir)
    entry: dict[str, Any] | None = None
    for item in listing.get("pending") or []:
        if task_id and item.get("task_id") == task_id:
            entry = item
            break
    if not entry and (listing.get("pending") or []):
        entry = listing["pending"][0]
    if not entry:
        return {"status": "not_found", "error": "no pending delegation matched"}

    act = (action or "retry").strip().lower()
    if act == "skip":
        from sdk_forge.delegation.core import complete_delegation_impl

        complete_delegation_impl(
            project_dir,
            agent=str(entry.get("agent") or ""),
            batch_id=entry.get("batch_id"),
            task_id=str(entry.get("task_id") or ""),
            status="skipped",
        )
        return {"status": "ok", "action": "skip", "delegation": entry}

    advance = advance_forge_workflow_impl(
        project_dir=project_dir,
        last_agent=str(entry.get("agent") or ""),
        last_status="error",
        batch_id=entry.get("batch_id"),
        task_id=str(entry.get("task_id") or ""),
        detail={"failure": failure_reason, "recover_action": act, "timeout_recovery": True},
    )
    return {
        "status": "ok",
        "action": act,
        "delegation": entry,
        "failure_reason": failure_reason,
        "workflow": advance,
        "next_step": (
            "get_task_dispatch_plan(project_dir=...) then tool-call task for retry dispatch"
            if advance.get("status") == "needs_agent"
            else advance.get("status")
        ),
        "user_hint_zh": (
            "已记录子 agent 超时/失败。若 orchestration 允许重试，将出现在 next_actions；"
            "否则请缩小单次 write 范围或 opencode run --session <id> --continue 手动续跑。"
        ),
    }
