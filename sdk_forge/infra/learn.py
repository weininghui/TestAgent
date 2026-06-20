"""Persist and reuse successful compile fixes across sessions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdk_forge.infra.config import merge_compile_params


def _sdk_hash(sdk_root: str) -> str:
    normalized = str(Path(sdk_root).resolve()).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _learned_dir(project_dir: str = "") -> Path:
    root = Path(project_dir or Path.cwd())
    return root / ".forge" / "cache" / "learned"


def learned_config_path(sdk_root: str, project_dir: str = "") -> Path:
    return _learned_dir(project_dir) / f"{_sdk_hash(sdk_root)}.json"


def load_learned_params(sdk_root: str, project_dir: str = "") -> dict[str, Any]:
    if not sdk_root.strip():
        return {}
    path = learned_config_path(sdk_root, project_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get("compile_params") or {}


def load_learned_config(sdk_root: str, project_dir: str = "") -> dict[str, Any]:
    if not sdk_root.strip():
        return {"status": "error", "error": "sdk_root required"}
    path = learned_config_path(sdk_root, project_dir)
    if not path.exists():
        return {"status": "ok", "found": False, "sdk_root": sdk_root}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "ok", "found": True, "path": str(path), **data}


def forget_learned_config(sdk_root: str, project_dir: str = "") -> dict[str, Any]:
    path = learned_config_path(sdk_root, project_dir)
    if path.exists():
        path.unlink(missing_ok=True)
        return {"status": "ok", "removed": str(path)}
    return {"status": "ok", "removed": None, "message": "No learned config found"}


def learn_from_build(state: dict[str, Any], project_dir: str = "") -> dict[str, Any]:
    sdk_root = state.get("sdk_root") or ""
    if not sdk_root:
        return {"status": "skipped", "reason": "no sdk_root in build state"}

    compile_ok = (state.get("compile") or {}).get("status") == "ok"
    run = state.get("run") or {}
    run_ok = state.get("status") == "ok" or run.get("status") == "ok"
    if not compile_ok or not run_ok:
        return {"status": "skipped", "reason": "build or run not successful"}

    params = {}
    for key in (
        "sdk_include_dirs",
        "sdk_lib_dirs",
        "link_libraries",
        "cmake_prefix_path",
        "pkg_config_packages",
    ):
        val = state.get(key)
        if val:
            params[key] = val

    if not params and state.get("compile"):
        pass

    fix_history: list[dict[str, Any]] = []
    for att in state.get("attempts") or []:
        applied = att.get("actions_applied") or []
        if applied:
            fix_history.append(
                {
                    "attempt": att.get("attempt"),
                    "result": att.get("result"),
                    "actions": applied,
                }
            )

    payload = {
        "sdk_root": sdk_root,
        "last_success": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "compile_params": _extract_params_from_state(state),
        "fix_history": fix_history[-10:],
    }

    path = learned_config_path(sdk_root, project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "ok", "path": str(path.resolve()), "sdk_root": sdk_root}


def _extract_params_from_state(state: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "sdk_include_dirs",
        "sdk_lib_dirs",
        "link_libraries",
        "cmake_prefix_path",
        "pkg_config_packages",
        "find_packages",
        "gtest_source",
        "gtest_version",
    )
    result: dict[str, Any] = {}
    for key in keys:
        if state.get(key):
            result[key] = state[key]
    compile_block = state.get("compile") or {}
    if compile_block.get("config_file"):
        result["_source_config"] = compile_block["config_file"]
    return result


def merge_learned_into_params(
    params: dict[str, Any], sdk_root: str, project_dir: str = ""
) -> dict[str, Any]:
    learned = load_learned_params(sdk_root, project_dir)
    if not learned:
        return params
    return merge_compile_params(learned, params)
