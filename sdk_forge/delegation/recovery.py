"""Auto-recovery state and logic for stalled delegations (v5.13).
子 Agent 自动恢复状态与逻辑。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdk_forge.infra.audit import audit_log
from sdk_forge.infra.config import load_forge_config
from sdk_forge.infra.logging_config import get_logger
from sdk_forge.infra.profile import resolve_forge_config

logger = get_logger("delegation.recovery")

DEFAULT_AUTO_RECOVERY_MAX = 2
DEFAULT_BACKOFF_SEC = 30


def _recovery_state_path(project_dir: str) -> Path:
    root = Path(project_dir or Path.cwd()).resolve()
    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache / "recovery_state.json"


def _load_state(project_dir: str) -> dict[str, Any]:
    path = _recovery_state_path(project_dir)
    if not path.is_file():
        return {"attempts": {}, "last_attempt_at": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("attempts", {})
            data.setdefault("last_attempt_at", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"attempts": {}, "last_attempt_at": {}}


def _save_state(project_dir: str, state: dict[str, Any]) -> None:
    path = _recovery_state_path(project_dir)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _batch_key(agent: str, batch_id: Any) -> str:
    return f"{agent}:{batch_id if batch_id is not None else 'none'}"


def recovery_config(project_dir: str) -> dict[str, Any]:
    """Resolved auto-recovery settings. / 解析后的自动恢复配置。"""
    cfg = resolve_forge_config(load_forge_config(start=project_dir or "."))
    max_raw = cfg.get("delegation_auto_recovery_max", DEFAULT_AUTO_RECOVERY_MAX)
    backoff_raw = cfg.get("delegation_retry_backoff_sec", DEFAULT_BACKOFF_SEC)
    try:
        max_attempts = max(0, int(max_raw))
    except (TypeError, ValueError):
        max_attempts = DEFAULT_AUTO_RECOVERY_MAX
    try:
        backoff = max(5, int(backoff_raw))
    except (TypeError, ValueError):
        backoff = DEFAULT_BACKOFF_SEC
    auto = bool(cfg.get("delegation_auto_recovery", False))
    return {
        "delegation_auto_recovery": auto,
        "delegation_auto_recovery_max": max_attempts,
        "delegation_retry_backoff_sec": backoff,
    }


def retry_count_for_batch(project_dir: str, agent: str, batch_id: Any) -> int:
    """How many auto-recoveries already attempted. / 已尝试的自动恢复次数。"""
    state = _load_state(project_dir)
    key = _batch_key(agent, batch_id)
    raw = state.get("attempts", {}).get(key, 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def should_auto_recover(
    entry: dict[str, Any],
    project_dir: str,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    """Decide if entry qualifies for auto recovery. / 判断是否应自动恢复。"""
    cfg = recovery_config(project_dir)
    if not force and not cfg["delegation_auto_recovery"]:
        return False, "auto_recovery_disabled"

    health = str(entry.get("health") or "")
    if health not in ("timeout", "stale", "tool_failure"):
        return False, "health_ok"

    agent = str(entry.get("agent") or "")
    batch_id = entry.get("batch_id")
    count = retry_count_for_batch(project_dir, agent, batch_id)
    if count >= cfg["delegation_auto_recovery_max"]:
        return False, "circuit_open"

    key = _batch_key(agent, batch_id)
    state = _load_state(project_dir)
    last_at = state.get("last_attempt_at", {}).get(key)
    if last_at and not force:
        try:
            last_ts = datetime.fromisoformat(str(last_at).replace("Z", "+00:00"))
            elapsed = (
                datetime.now(timezone.utc) - last_ts.astimezone(timezone.utc)
            ).total_seconds()
            backoff = cfg["delegation_retry_backoff_sec"] * (2**count)
            if elapsed < backoff:
                return False, "backoff"
        except (TypeError, ValueError):
            pass

    return True, "eligible"


def record_recovery_attempt(
    project_dir: str,
    agent: str,
    batch_id: Any,
    *,
    auto: bool = True,
) -> int:
    """Increment recovery counter; return new count. / 记录恢复尝试并返回新计数。"""
    state = _load_state(project_dir)
    key = _batch_key(agent, batch_id)
    attempts = state.setdefault("attempts", {})
    count = int(attempts.get(key, 0)) + 1
    attempts[key] = count
    state.setdefault("last_attempt_at", {})[key] = datetime.now(timezone.utc).isoformat()
    _save_state(project_dir, state)
    audit_log(
        "recovery",
        project_dir=project_dir,
        stage="delegation",
        agent=agent,
        task_id="",
        detail={"batch_id": batch_id, "attempt": count, "auto": auto},
    )
    logger.info("recovery attempt %s for %s batch=%s auto=%s", count, agent, batch_id, auto)
    return count


def try_auto_recover_all(project_dir: str, *, force: bool = False) -> dict[str, Any]:
    """Attempt auto recovery for all unhealthy pending delegations."""
    from sdk_forge.delegation.health import (
        check_subagent_health_impl,
        recover_stalled_subagent_impl,
    )

    health = check_subagent_health_impl(project_dir, include_preview=not force)
    recovered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    circuit_open: list[dict[str, Any]] = []

    for entry in health.get("needs_recovery") or []:
        ok, reason = should_auto_recover(entry, project_dir, force=force)
        if not ok:
            row = {"task_id": entry.get("task_id"), "reason": reason, "agent": entry.get("agent")}
            if reason == "circuit_open":
                circuit_open.append(row)
            else:
                skipped.append(row)
            continue

        task_id = str(entry.get("task_id") or "")
        agent = str(entry.get("agent") or "")
        batch_id = entry.get("batch_id")
        result = recover_stalled_subagent_impl(
            project_dir,
            task_id=task_id,
            action="retry",
            failure_reason=str(entry.get("health") or "upstream_idle_timeout"),
        )
        record_recovery_attempt(project_dir, agent, batch_id, auto=not force)
        recovered.append(
            {"task_id": task_id, "agent": agent, "result_status": result.get("status")}
        )
        time.sleep(0)  # yield for tests

    return {
        "status": "ok",
        "recovered": recovered,
        "skipped": skipped,
        "circuit_open": circuit_open,
        "auto_recovery_enabled": recovery_config(project_dir)["delegation_auto_recovery"] or force,
    }
