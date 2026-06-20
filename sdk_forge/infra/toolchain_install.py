"""Automatic C/C++ toolchain installation via OS package managers.
通过系统包管理器自动安装 C/C++ 工具链（需用户确认）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any, Callable

from sdk_forge.infra.toolchain import check_cxx_toolchain

RunCmd = Callable[..., subprocess.CompletedProcess]


def _which(name: str) -> str | None:
    return shutil.which(name)


def detect_installers() -> dict[str, Any]:
    """Detect available installers on this machine.
    检测本机可用的包管理器。
    """
    options: list[dict[str, Any]] = []

    if sys.platform == "win32":
        if _which("winget"):
            options.append(
                {
                    "method": "winget-msvc",
                    "label": "Visual Studio 2022 Build Tools (MSVC, recommended for yaml-cpp)",
                    "manager": "winget",
                    "requires_admin": True,
                    "estimated_minutes": 20,
                }
            )
            options.append(
                {
                    "method": "winget-mingw",
                    "label": "WinLibs MinGW-w64 (g++, faster install)",
                    "manager": "winget",
                    "requires_admin": False,
                    "estimated_minutes": 5,
                }
            )
        if _which("choco"):
            options.append(
                {
                    "method": "choco-mingw",
                    "label": "MinGW via Chocolatey",
                    "manager": "choco",
                    "requires_admin": True,
                    "estimated_minutes": 10,
                }
            )
    elif sys.platform == "darwin":
        if _which("brew"):
            options.append(
                {
                    "method": "brew-llvm",
                    "label": "LLVM/clang++ via Homebrew",
                    "manager": "brew",
                    "requires_admin": False,
                    "estimated_minutes": 10,
                }
            )
        options.append(
            {
                "method": "xcode-cli",
                "label": "Xcode Command Line Tools (clang++)",
                "manager": "xcode-select",
                "requires_admin": False,
                "estimated_minutes": 15,
            }
        )
    else:
        if _which("apt-get"):
            options.append(
                {
                    "method": "apt-build-essential",
                    "label": "build-essential + cmake (Debian/Ubuntu)",
                    "manager": "apt",
                    "requires_admin": True,
                    "estimated_minutes": 5,
                }
            )
        if _which("dnf"):
            options.append(
                {
                    "method": "dnf-gcc",
                    "label": "gcc-c++ + cmake (Fedora/RHEL)",
                    "manager": "dnf",
                    "requires_admin": True,
                    "estimated_minutes": 5,
                }
            )

    return {
        "platform": sys.platform,
        "installers_available": [o["manager"] for o in options],
        "options": options,
        "auto_method": options[0]["method"] if options else None,
    }


def _pick_method(method: str) -> dict[str, Any] | None:
    detected = detect_installers()
    options = detected.get("options") or []
    if not options:
        return None
    if method in ("", "auto"):
        return options[0]
    for opt in options:
        if opt["method"] == method:
            return opt
    return None


def _build_install_command(method: str) -> tuple[list[str], int, str] | None:
    """Return argv, timeout seconds, post-install note."""
    if method == "winget-msvc":
        return (
            [
                "winget",
                "install",
                "-e",
                "--id",
                "Microsoft.VisualStudio.2022.BuildTools",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--override",
                "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended",
            ],
            3600,
            'Restart terminal or use "x64 Native Tools Command Prompt for VS", then run forge doctor.',
        )
    if method == "winget-mingw":
        return (
            [
                "winget",
                "install",
                "-e",
                "--id",
                "BrechtSanders.WinLibs.POSIX.UCRT",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            900,
            "Add MinGW bin directory to PATH if g++ is not found, then run forge doctor.",
        )
    if method == "choco-mingw":
        return (
            ["choco", "install", "mingw", "-y"],
            900,
            "Restart terminal after install, then run forge doctor.",
        )
    if method == "apt-build-essential":
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return (
                ["apt-get", "install", "-y", "build-essential", "cmake", "pkg-config"],
                600,
                "Run forge doctor to verify g++.",
            )
        return (
            ["sudo", "apt-get", "install", "-y", "build-essential", "cmake", "pkg-config"],
            600,
            "Run forge doctor to verify g++.",
        )
    if method == "dnf-gcc":
        base = ["dnf", "install", "-y", "gcc-c++", "cmake", "pkg-config"]
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            base = ["sudo"] + base
        return (base, 600, "Run forge doctor to verify g++.")
    if method == "brew-llvm":
        return (
            ["brew", "install", "llvm", "cmake"],
            900,
            "Ensure $(brew --prefix llvm)/bin is on PATH.",
        )
    if method == "xcode-cli":
        return (
            ["xcode-select", "--install"],
            60,
            "Complete the GUI dialog, then run forge doctor.",
        )
    return None


def _run_install(method: str, runner: RunCmd | None = None) -> dict[str, Any]:
    run = runner or subprocess.run
    spec = _build_install_command(method)
    if not spec:
        return {"status": "error", "error": f"Unknown install method: {method}"}

    argv, timeout, post_note = spec
    steps = [argv]

    outputs: list[str] = []
    for step in steps:
        try:
            result = run(
                step,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": f"Install timed out after {timeout}s",
                "method": method,
                "hint": "Large installs (MSVC) may need manual completion; check installer UI.",
            }
        except OSError as exc:
            return {"status": "error", "error": str(exc), "method": method}

        chunk = (result.stdout or "") + (result.stderr or "")
        outputs.append(chunk[-4000:])
        if result.returncode != 0:
            return {
                "status": "error",
                "error": f"Install command failed (exit {result.returncode})",
                "method": method,
                "command": " ".join(step),
                "output": chunk[-2000:],
                "hint": "Try running the terminal as Administrator, or install manually.",
            }

    after = check_cxx_toolchain()
    return {
        "status": "ok" if after.get("available") else "installed_needs_restart",
        "method": method,
        "compiler_now_available": after.get("available", False),
        "toolchain": after,
        "post_install": post_note,
        "output_tail": outputs[-1][-1500:] if outputs else "",
        "next_steps": [
            post_note,
            "Run forge doctor to verify cxx_compiler.",
            "If still missing, open a new terminal (PATH refresh).",
        ],
    }


def setup_toolchain_impl(
    method: str = "auto",
    confirm: bool | str = False,
    agent_mode: bool | str = False,
) -> dict[str, Any]:
    """Install C++ toolchain when missing; requires explicit confirm or agent_mode.
    缺少编译器时安装；需 confirm=true 或 agent_mode=true（Agent 全权配置环境）。
    """
    from sdk_forge.domain.util import parse_bool

    delegated = parse_bool(agent_mode, default=False)
    if not parse_bool(confirm, default=False) and not delegated:
        opt = _pick_method(method)
        detected = detect_installers()
        return {
            "status": "confirmation_required",
            "error": "Toolchain install requires confirm=true (may need admin and long download).",
            "method": opt.get("method") if opt else method,
            "install_plan": opt,
            "available_options": detected.get("options") or [],
            "hint": "Call setup_cxx_toolchain(agent_mode=true) or build_tests(auto_setup_toolchain=true).",
        }

    before = check_cxx_toolchain()
    if before.get("available"):
        return {
            "status": "ok",
            "message": "C++ compiler already available",
            "toolchain": before,
            "skipped": True,
        }

    opt = _pick_method(method)
    if not opt:
        detected = detect_installers()
        return {
            "status": "error",
            "error": "No automatic installer available on this platform",
            "platform": sys.platform,
            "available_options": detected.get("options") or [],
            "hint": "Install Visual Studio Build Tools or MinGW manually, then forge doctor.",
        }

    chosen = opt["method"]
    result = _run_install(chosen)
    result["install_plan"] = opt
    result["toolchain_before"] = before
    result["agent_mode"] = delegated
    return result


def ensure_toolchain_impl(
    method: str = "auto",
    auto_install: bool | str = True,
    agent_mode: bool | str = True,
) -> dict[str, Any]:
    """Ensure C++ toolchain is ready; auto-install when missing (Agent-friendly).
    确保工具链就绪；缺失时自动安装（面向 Agent 全自动环境配置）。
    """
    from sdk_forge.domain.util import parse_bool

    tc = check_cxx_toolchain()
    if tc.get("available"):
        return {
            "status": "ok",
            "action": "none",
            "toolchain": tc,
            "message": "C++ compiler already available",
        }

    if not parse_bool(auto_install, default=True):
        return {
            "status": "compiler_not_found",
            "action": "install_skipped",
            "toolchain": tc,
            "hint": "Set auto_install=true or call setup_cxx_toolchain(agent_mode=true)",
        }

    setup = setup_toolchain_impl(
        method=method,
        confirm=True,
        agent_mode=parse_bool(agent_mode, default=True),
    )
    after = check_cxx_toolchain()
    setup["toolchain_after"] = after
    if after.get("available"):
        setup["status"] = "ok"
        setup["action"] = "installed"
        setup["message"] = "Toolchain installed and detected"
        return setup

    setup["action"] = "installed_needs_restart"
    setup.setdefault(
        "message",
        "Install finished but compiler not on PATH yet — open a new terminal or Native Tools prompt",
    )
    return setup
