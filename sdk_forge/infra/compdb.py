"""Export compile_commands.json for IDE / libclang."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def export_compile_commands_impl(
    build_dir: str,
    project_dir: str = "",
) -> dict[str, Any]:
    build_path = Path(build_dir)
    if not build_path.is_dir():
        return {"status": "error", "error": f"Build directory not found: {build_dir}"}

    candidates = [
        build_path / "compile_commands.json",
        build_path / "Debug" / "compile_commands.json",
        build_path / "Release" / "compile_commands.json",
    ]
    source_file: Path | None = None
    for candidate in candidates:
        if candidate.is_file():
            source_file = candidate
            break
    if source_file is None:
        for found in build_path.rglob("compile_commands.json"):
            if found.is_file():
                source_file = found
                break

    if source_file is None:
        return {
            "status": "error",
            "error": "compile_commands.json not found — rebuild with CMAKE_EXPORT_COMPILE_COMMANDS",
        }

    root = Path(project_dir or Path.cwd()).resolve()
    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / "compile_commands.json"
    shutil.copy2(source_file, dest)

    return {
        "status": "ok",
        "source": str(source_file.resolve()),
        "path": str(dest.resolve()),
        "project_dir": str(root),
    }


def get_compile_commands_impl(project_dir: str = "") -> dict[str, Any]:
    root = Path(project_dir or Path.cwd()).resolve()
    path = root / ".forge" / "cache" / "compile_commands.json"
    if not path.is_file():
        return {
            "status": "error",
            "error": "No cached compile_commands.json — run compile/build first",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}
    return {
        "status": "ok",
        "path": str(path.resolve()),
        "entry_count": len(data) if isinstance(data, list) else 0,
        "compile_commands": data,
    }
