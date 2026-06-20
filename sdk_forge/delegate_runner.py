"""CLI delegation runtime — spawn sub-agents via `opencode run` (v5.6)."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from sdk_forge.delegation import poll_cli_delegate_processes, register_delegation_impl


def _opencode_command() -> list[str]:
    exe = shutil.which("opencode")
    if exe:
        return [exe]
    return ["opencode"]


def dispatch_cli_delegate_impl(
    project_dir: str,
    agent: str,
    prompt: str,
    batch_id: int | None = None,
    title: str = "",
) -> dict[str, Any]:
    """Start a background `opencode run` subprocess for a forge sub-agent."""
    if not agent or not prompt:
        return {"status": "error", "error": "agent and prompt required"}
    root = Path(project_dir or Path.cwd()).resolve()
    task_id = f"cli_{uuid.uuid4().hex[:12]}"
    display = title or agent
    cmd = [
        *_opencode_command(),
        "run",
        "--agent",
        agent,
        "--dir",
        str(root),
        "--format",
        "json",
        "--title",
        display,
        prompt,
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        return {"status": "error", "error": f"Failed to start opencode run: {exc}"}

    reg = register_delegation_impl(
        str(root),
        task_id,
        agent,
        batch_id=batch_id,
        title=display,
        session_id="",
        runtime="cli",
        pid=proc.pid,
    )
    if reg.get("status") != "ok":
        return reg
    return {
        "status": "ok",
        "task_id": task_id,
        "pid": proc.pid,
        "runtime": "cli",
        "agent": agent,
        "batch_id": batch_id,
        "command": cmd,
        "delegation": reg.get("delegation"),
        "navigate_hint": (
            f"CLI delegate running (pid={proc.pid}). "
            f"When session_id is known, call update_forge_delegation_session. "
            f"Or: opencode session list"
        ),
    }
