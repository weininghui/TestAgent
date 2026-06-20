"""Run ID (correlation_id) propagation via contextvars.
运行 ID（correlation_id）上下文传播。
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

_run_id_var: ContextVar[str] = ContextVar("forge_run_id", default="")


def new_run_id() -> str:
    """Generate a new forge run id. / 生成新的 forge 运行 ID。"""
    return f"forge_{uuid.uuid4().hex[:8]}"


def set_run_id(run_id: str) -> None:
    """Set current run id in context. / 设置当前上下文 run_id。"""
    _run_id_var.set(run_id or "")


def get_run_id() -> str:
    """Return current run id or empty string. / 返回当前 run_id。"""
    return _run_id_var.get()


def ensure_run_id() -> str:
    """Ensure a run id exists; create if missing. / 确保存在 run_id。"""
    rid = get_run_id()
    if not rid:
        rid = new_run_id()
        set_run_id(rid)
    return rid


def inject_run_id(result: dict[str, Any]) -> dict[str, Any]:
    """Add run_id to a JSON response dict. / 向 JSON 响应注入 run_id。"""
    if isinstance(result, dict) and "run_id" not in result:
        result["run_id"] = ensure_run_id()
    return result
