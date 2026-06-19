#!/usr/bin/env python3
"""OpenCode MCP entry — bootstrap deps/package then start mcp_server.
OpenCode 插件入口：自动检查依赖与包版本，再启动 MCP。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _read_project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^version\s*=\s*\"([^\"]+)\"", text, re.MULTILINE)
    return match.group(1) if match else ""


def _pip_install(args: list[str]) -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", *args, "-q"],
        cwd=str(ROOT),
    )


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
    _ensure_runtime_deps()
    _ensure_editable_package()
    from mcp_server import main as mcp_main

    mcp_main()


if __name__ == "__main__":
    main()
