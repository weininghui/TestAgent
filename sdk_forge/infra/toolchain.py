"""C/C++ toolchain detection and install guidance.
C/C++ 工具链检测与安装指引。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from sdk_forge.infra.gtest import detect_compiler


def _find_cl_via_vswhere() -> str | None:
    """Locate cl.exe when MSVC is installed but not on PATH (common on Windows).
    在未配置 PATH 时通过 vswhere 定位 cl.exe。
    """
    pf = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = Path(pf) / "Microsoft Visual Studio/Installer/vswhere.exe"
    if not vswhere.is_file():
        return None
    try:
        result = subprocess.run(
            [
                str(vswhere),
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-find",
                r"VC\Tools\MSVC\*\bin\Hostx64\x64\cl.exe",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            path = line.strip()
            if path.lower().endswith("cl.exe") and Path(path).is_file():
                return path
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def _windows_install_hints() -> list[str]:
    return [
        'Install Visual Studio 2022 Build Tools with workload "Desktop development with C++" '
        "(includes cl.exe and Windows SDK).",
        "Or install MinGW-w64 / MSYS2 and add g++ to PATH.",
        'After install, open "x64 Native Tools Command Prompt for VS" or restart the terminal.',
        "Run forge doctor to verify cxx_compiler before build_tests.",
    ]


def _linux_install_hints() -> list[str]:
    return [
        "Install build-essential (Debian/Ubuntu) or gcc-c++ (Fedora/RHEL).",
        "Ensure cmake and g++ are on PATH, then run forge doctor.",
    ]


def check_cxx_toolchain() -> dict[str, Any]:
    """Return compiler availability with actionable hints.
    返回编译器可用性及安装/配置建议。
    """
    info = detect_compiler()
    path = info.get("path") or shutil.which("cl" if sys.platform == "win32" else "g++") or ""

    if sys.platform == "win32" and not info.get("available"):
        for name in ("g++", "clang++"):
            alt = shutil.which(name)
            if alt:
                info = {
                    "kind": name.replace("++", ""),
                    "major": None,
                    "version": "",
                    "available": True,
                }
                path = alt
                break

    if sys.platform == "win32" and not info.get("available"):
        cl_path = _find_cl_via_vswhere()
        if cl_path:
            info = {
                "kind": "msvc",
                "major": None,
                "version": "",
                "available": True,
                "path": cl_path,
                "on_path": False,
            }
            path = cl_path

    available = bool(info.get("available"))
    kind = info.get("kind") or "unknown"
    hints = (
        []
        if available
        else (_windows_install_hints() if sys.platform == "win32" else _linux_install_hints())
    )

    message = ""
    hint = ""
    if available:
        if info.get("on_path") is False:
            hint = (
                f"MSVC found at {path} but cl.exe is not on PATH. "
                'Use "x64 Native Tools Command Prompt for VS" or add VC\\Tools\\...\\bin to PATH.'
            )
        else:
            hint = f"C++ compiler ready ({kind})."
    else:
        if sys.platform == "win32":
            message = (
                "No C++ compiler found (cl.exe / g++). "
                "GTest sources can be generated but cannot be compiled on this machine."
            )
            hint = hints[0] if hints else message
        else:
            message = "No C++ compiler found (g++/clang++)."
            hint = hints[0] if hints else message

    return {
        "available": available,
        "kind": kind,
        "path": path or info.get("path") or "",
        "on_path": info.get("on_path", bool(shutil.which("cl" if kind == "msvc" else "g++"))),
        "version": info.get("version", ""),
        "message": message,
        "hint": hint,
        "hints": hints,
        "platform": sys.platform,
    }


def compiler_gate_result() -> dict[str, Any] | None:
    """Return a build-style error dict when no compiler; else None.
    无编译器时返回 build 错误结构，否则 None。
    """
    tc = check_cxx_toolchain()
    if tc.get("available"):
        return None
    from sdk_forge.infra.toolchain_install import detect_installers

    return {
        "status": "compiler_not_found",
        "error": tc.get("message") or "C++ compiler not found",
        "hints": tc.get("hints") or [tc.get("hint", "")],
        "actions": [
            {
                "type": "setup_toolchain",
                "hint": "Run setup_cxx_toolchain(confirm=true) or: forge setup-toolchain --confirm",
                "methods": detect_installers().get("options") or [],
            }
        ],
        "toolchain": tc,
        "compile": {
            "status": "compiler_not_found",
            "stage": "toolchain",
            "hints": tc.get("hints") or [],
            "output": tc.get("message", ""),
        },
    }
