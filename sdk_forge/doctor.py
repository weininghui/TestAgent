"""Environment diagnostics for SDK Test Forge."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from sdk_forge.cache import gtest_cache_dir, scan_cache_dir
from sdk_forge.gtest import ensure_gtest, gtest_toolchain_info
from sdk_forge.scan import CLANG_AVAILABLE


def _check_cmd(name: str) -> dict:
    path = shutil.which(name)
    version = ""
    if path:
        try:
            result = subprocess.run(
                [name, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            version = (result.stdout or result.stderr or "").splitlines()[0][:120]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            version = "found"
    return {"name": name, "ok": bool(path), "path": path or "", "version": version}


def doctor_impl() -> dict:
    checks: list[dict] = []
    checks.append({"name": "python", "ok": True, "version": sys.version.split()[0]})
    checks.append(_check_cmd("cmake"))
    checks.append(_check_cmd("pkg-config"))

    cxx = "cl" if sys.platform == "win32" else "g++"
    checks.append(_check_cmd(cxx))

    gtest_cache = gtest_cache_dir()
    scan_cache = scan_cache_dir()
    cache_ok = True
    try:
        (gtest_cache / ".doctor").write_text("ok", encoding="utf-8")
        (gtest_cache / ".doctor").unlink(missing_ok=True)
        (scan_cache / ".doctor").write_text("ok", encoding="utf-8")
        (scan_cache / ".doctor").unlink(missing_ok=True)
    except OSError:
        cache_ok = False

    checks.append({
        "name": "forge_cache",
        "ok": cache_ok,
        "gtest_cache": str(gtest_cache),
        "scan_cache": str(scan_cache),
    })
    gtest_info = gtest_toolchain_info()
    tag = gtest_info["recommended_tag"]
    gtest_fetch = ensure_gtest(tag, force=False)
    checks.append({
        "name": "googletest",
        "ok": gtest_fetch.get("status") == "ok",
        "tag": tag,
        "path": gtest_info["cache_path"],
        "cached": gtest_info["cached"],
        "method": gtest_fetch.get("method", ""),
        "compiler": gtest_info["compiler"].get("kind"),
        "hint": gtest_fetch.get("hint", ""),
    })
    checks.append({
        "name": "libclang",
        "ok": CLANG_AVAILABLE,
        "hint": "pip install libclang; set LIBCLANG_PATH on Windows" if not CLANG_AVAILABLE else "",
    })

    if sys.platform == "win32" and not os.environ.get("LIBCLANG_PATH"):
        checks.append({
            "name": "LIBCLANG_PATH",
            "ok": False,
            "hint": "Set to LLVM bin directory when using libclang",
        })

    failed = [c["name"] for c in checks if not c.get("ok", True)]
    return {
        "status": "ok" if not failed else "issues_found",
        "platform": platform.platform(),
        "checks": checks,
        "failed": failed,
        "ready": len(failed) == 0,
    }
