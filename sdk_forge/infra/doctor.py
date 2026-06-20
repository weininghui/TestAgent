"""Environment diagnostics for SDK Forge."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

from sdk_forge import __version__ as FORGE_VERSION
from sdk_forge.infra.cache import gtest_cache_dir, scan_cache_dir
from sdk_forge.infra.gtest import ensure_gtest, gtest_toolchain_info
from sdk_forge.infra.toolchain import check_cxx_toolchain
from sdk_forge.infra.toolchain_install import detect_installers
from sdk_forge.pipeline.scan import CLANG_AVAILABLE


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
    checks.append(
        {
            "name": "sdk_test_forge",
            "ok": True,
            "version": FORGE_VERSION,
            "hint": f"SDK Forge {FORGE_VERSION} — authoritative package version",
        }
    )
    checks.append({"name": "python", "ok": True, "version": sys.version.split()[0]})
    checks.append(_check_cmd("cmake"))
    checks.append(_check_cmd("pkg-config"))

    tc = check_cxx_toolchain()
    checks.append(
        {
            "name": "cxx_compiler",
            "ok": tc.get("available", False),
            "kind": tc.get("kind", ""),
            "path": tc.get("path", ""),
            "on_path": tc.get("on_path", False),
            "version": tc.get("version", ""),
            "hint": tc.get("hint", ""),
        }
    )
    if not tc.get("available"):
        inst = detect_installers()
        checks.append(
            {
                "name": "toolchain_install",
                "ok": False,
                "auto_method": inst.get("auto_method"),
                "options": inst.get("options") or [],
                "hint": "Run: forge setup-toolchain --confirm  (or MCP setup_cxx_toolchain with confirm=true)",
            }
        )

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

    checks.append(
        {
            "name": "forge_cache",
            "ok": cache_ok,
            "gtest_cache": str(gtest_cache),
            "scan_cache": str(scan_cache),
        }
    )
    gtest_info = gtest_toolchain_info()
    tag = gtest_info["recommended_tag"]
    gtest_fetch = ensure_gtest(tag, force=False)
    checks.append(
        {
            "name": "googletest",
            "ok": gtest_fetch.get("status") == "ok",
            "tag": tag,
            "path": gtest_info["cache_path"],
            "cached": gtest_info["cached"],
            "method": gtest_fetch.get("method", ""),
            "compiler": gtest_info["compiler"].get("kind"),
            "hint": gtest_fetch.get("hint", ""),
        }
    )
    checks.append(
        {
            "name": "libclang",
            "ok": CLANG_AVAILABLE,
            "hint": "pip install libclang; set LIBCLANG_PATH on Windows"
            if not CLANG_AVAILABLE
            else "",
        }
    )

    from sdk_forge.pipeline.build import sanitizer_cmake_block

    san_block, san_hints = sanitizer_cmake_block("asan")
    sanitizer_ok = bool(san_block) or sys.platform == "win32"
    checks.append(
        {
            "name": "sanitizer",
            "ok": sanitizer_ok,
            "supported": bool(san_block),
            "hint": san_hints[0]
            if san_hints
            else ("ASan/UBSan available via sanitizer: asan in .forge.yaml" if san_block else ""),
        }
    )

    if sys.platform == "win32" and not os.environ.get("LIBCLANG_PATH"):
        checks.append(
            {
                "name": "LIBCLANG_PATH",
                "ok": False,
                "hint": "Set to LLVM bin directory when using libclang",
            }
        )

    failed = [c["name"] for c in checks if not c.get("ok", True)]
    return {
        "status": "ok" if not failed else "issues_found",
        "forge_version": FORGE_VERSION,
        "platform": platform.platform(),
        "checks": checks,
        "failed": failed,
        "ready": len(failed) == 0,
    }
