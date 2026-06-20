"""Shared utilities."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def parse_bool(value: bool | str | None, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    stripped = str(value).strip().lower()
    if stripped in ("", "true", "1", "yes", "on"):
        return True
    if stripped in ("false", "0", "no", "off"):
        return False
    return default


def normalize_str_list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            return [stripped]
        return []
    return [str(item) for item in value if str(item).strip()]


def normalize_json_list(value: list[Any] | str | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            return []
        return []
    return list(value)


def cmake_path(path: str) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def run_subprocess(
    cmd: list[str], cwd: str | None = None, timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
