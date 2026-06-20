"""Persistent audit trail (JSONL) for forge operations.
Forge 操作持久化审计流（JSONL）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdk_forge.infra.trace import get_run_id

AUDIT_FILENAME = "audit.jsonl"


def _audit_path(project_dir: str) -> Path:
    root = Path(project_dir or Path.cwd()).resolve()
    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache / AUDIT_FILENAME


def audit_log(
    event: str,
    project_dir: str = "",
    stage: str = "",
    agent: str = "",
    task_id: str = "",
    detail: dict[str, Any] | None = None,
) -> Path | None:
    """Append one audit event. / 追加一条审计事件。"""
    try:
        path = _audit_path(project_dir)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": get_run_id() or "",
            "event": event,
            "stage": stage,
            "agent": agent,
            "task_id": task_id,
            "detail": detail or {},
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path
    except OSError:
        return None


def read_audit_log(project_dir: str = "", last_n: int = 50) -> dict[str, Any]:
    """Read last N audit events. / 读取最近 N 条审计事件。"""
    path = _audit_path(project_dir)
    if not path.is_file():
        return {"status": "ok", "events": [], "path": str(path), "count": 0}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {"status": "error", "error": str(exc), "events": []}
    events: list[dict[str, Any]] = []
    for line in lines[-max(1, last_n) :]:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {
        "status": "ok",
        "path": str(path),
        "count": len(events),
        "events": events,
    }
