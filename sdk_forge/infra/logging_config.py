"""Centralized logging configuration for SDK Forge.
SDK Forge 集中式日志配置。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sdk_forge.infra.trace import get_run_id

_CONFIGURED = False
_LOG_FORMAT = "%(asctime)s [%(name)s] [run_id=%(run_id)s] %(levelname)-8s %(message)s"
_DATE_FORMAT = "%H:%M:%S"


class _RunIdFilter(logging.Filter):
    """Inject run_id into every log record. / 为每条日志注入 run_id。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = get_run_id() or "-"  # type: ignore[attr-defined]
        return True


def configure_forge_logging(
    level: str | int | None = None,
    log_file: str | Path | None = None,
) -> None:
    """Configure root sdk_forge logging once. / 一次性配置 sdk_forge 日志。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    env_level = os.environ.get("FORGE_LOG_LEVEL", "").strip().upper()
    resolved_level = level or env_level or "INFO"
    if isinstance(resolved_level, str):
        resolved_level = getattr(logging, resolved_level, logging.INFO)

    root = logging.getLogger("sdk_forge")
    root.setLevel(resolved_level)
    root.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    run_filter = _RunIdFilter()

    if not root.handlers:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.addFilter(run_filter)
        root.addHandler(console)

    env_log_file = os.environ.get("FORGE_LOG_FILE", "").strip()
    file_path = log_file or env_log_file
    if file_path:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(formatter)
        fh.addFilter(run_filter)
        root.addHandler(fh)

    mcp_logger = logging.getLogger("mcp_server")
    mcp_logger.setLevel(resolved_level)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a sdk_forge.* logger. / 获取 sdk_forge 子 logger。"""
    if not name.startswith("sdk_forge"):
        name = f"sdk_forge.{name}"
    return logging.getLogger(name)
