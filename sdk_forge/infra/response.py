"""JSON response helpers with run_id injection.
带 run_id 注入的 JSON 响应辅助。
"""

from __future__ import annotations

import json
from typing import Any

from sdk_forge.infra.trace import ensure_run_id, inject_run_id


def forge_json(result: Any, *, indent: int = 2, **kwargs: Any) -> str:
    """Serialize dict response with run_id. / 序列化 JSON 并注入 run_id。"""
    ensure_run_id()
    if isinstance(result, dict):
        inject_run_id(result)
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(result, indent=indent, **kwargs)
