#!/usr/bin/env python3
"""OpenCode MCP entry — bootstrap deps/package then start mcp_server.
OpenCode 插件入口：自动检查依赖与包版本，再启动 MCP。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_AUTO_UPDATE_INTERVAL_SEC = 6 * 3600  # at most once per 6 hours


def _read_project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^version\s*=\s*\"([^\"]+)\"", text, re.MULTILINE)
    return match.group(1) if match else ""


def _pip_install(args: list[str]) -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", *args, "-q"],
        cwd=str(ROOT),
    )


def _auto_update_enabled() -> bool:
    return os.environ.get("FORGE_AUTO_UPDATE", "").strip().lower() in ("1", "true", "yes", "on")


def _opencode_config_root() -> Path | None:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", "")
        if not base:
            return None
        return Path(base) / "OpenCode"
    config = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config) if config else Path.home() / ".config"
    return root / "opencode"


def _sync_opencode_assets() -> None:
    """Copy forge agents + test-forge skill into OpenCode user config."""
    agents_src = ROOT / ".opencode" / "agents"
    skill_src = ROOT / ".opencode" / "skills" / "test-forge" / "SKILL.md"
    base = _opencode_config_root()
    if not base:
        return
    agents_dst = base / "agents"
    agents_dst.mkdir(parents=True, exist_ok=True)
    if agents_src.is_dir():
        for path in agents_src.glob("forge*.md"):
            try:
                shutil.copy2(path, agents_dst / path.name)
            except OSError:
                pass
    if skill_src.is_file():
        skill_dst = base / "skills" / "test-forge"
        skill_dst.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(skill_src, skill_dst / "SKILL.md")
        except OSError:
            pass


def _mark_pending_restart(pulled_commits: int) -> None:
    cache_dir = ROOT / ".forge" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "pulled_commits": pulled_commits,
        "forge_version": _read_project_version(),
        "message": "Plugin updated from GitHub — fully quit and reopen OpenCode to load new MCP code.",
    }
    (cache_dir / "pending_opencode_restart.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _maybe_git_auto_update() -> None:
    """Optional: pull origin/main when FORGE_AUTO_UPDATE=1 (throttled)."""
    if not _auto_update_enabled():
        return
    if not (ROOT / ".git").is_dir():
        return

    cache_dir = ROOT / ".forge" / "cache"
    cache_file = cache_dir / "plugin_auto_update.json"
    now = time.time()
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if now - float(data.get("last_check", 0)) < _AUTO_UPDATE_INTERVAL_SEC:
                return
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    try:
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=str(ROOT),
            capture_output=True,
            timeout=90,
            check=False,
        )
        behind = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        count = int((behind.stdout or "0").strip() or "0")
        if count > 0:
            subprocess.run(["git", "checkout", "main"], cwd=str(ROOT), capture_output=True, timeout=30, check=False)
            subprocess.run(
                ["git", "reset", "--hard", "origin/main"],
                cwd=str(ROOT),
                capture_output=True,
                timeout=30,
                check=False,
            )
            _sync_opencode_assets()
            _mark_pending_restart(count)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({"last_check": now, "pulled_commits": count}, indent=2),
            encoding="utf-8",
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return


def _ensure_runtime_deps() -> None:
    try:
        import mcp  # noqa: F401
        import pydantic  # noqa: F401
    except ImportError:
        _pip_install(["-r", str(ROOT / "requirements.txt")])


def _ensure_editable_package() -> None:
    expected = _read_project_version()
    try:
        import sdk_forge

        installed = Path(sdk_forge.__file__).resolve().parent.parent
        if installed.resolve() != ROOT.resolve():
            _pip_install(["-e", str(ROOT)])
            return
        if expected and getattr(sdk_forge, "__version__", "") != expected:
            _pip_install(["-e", str(ROOT), "--force-reinstall"])
    except ImportError:
        _pip_install(["-e", str(ROOT)])


def main() -> None:
    _maybe_git_auto_update()
    _ensure_runtime_deps()
    _ensure_editable_package()
    from mcp_server import main as mcp_main

    mcp_main()


if __name__ == "__main__":
    main()
