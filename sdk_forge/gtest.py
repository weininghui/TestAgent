"""GTest version resolution and download helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from sdk_forge.cache import gtest_cache_dir
from sdk_forge.util import run_subprocess

GTEST_REPO = "https://github.com/google/googletest.git"

# Newest first — resolve_gtest_tag walks this list when pinning by version string.
KNOWN_TAGS = ("v1.14.0", "v1.13.0", "v1.12.0")


def _parse_major(version_line: str) -> int | None:
    match = re.search(r"(\d+)", version_line)
    return int(match.group(1)) if match else None


def detect_cmake_major() -> int | None:
    cmake = shutil.which("cmake")
    if not cmake:
        return None
    try:
        result = run_subprocess([cmake, "--version"], timeout=15)
        first = (result.stdout or result.stderr or "").splitlines()[0]
        return _parse_major(first)
    except (subprocess.TimeoutExpired, OSError):
        return None


def detect_compiler() -> dict:
    if sys.platform == "win32":
        cl = shutil.which("cl")
        if not cl:
            return {"kind": "msvc", "major": None, "version": "", "available": False}
        try:
            result = subprocess.run(
                ["cl"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            text = (result.stderr or result.stdout or "")
            msvc = re.search(r"(\d{2})\d{2}", text)
            major = int(msvc.group(1)) if msvc else None
            return {
                "kind": "msvc",
                "major": major,
                "version": text.splitlines()[0][:120] if text else "",
                "available": True,
            }
        except (subprocess.TimeoutExpired, OSError):
            return {"kind": "msvc", "major": None, "version": "", "available": True}

    for kind, names in (("gcc", ("g++", "gcc")), ("clang", ("clang++", "clang"))):
        for name in names:
            path = shutil.which(name)
            if not path:
                continue
            try:
                result = run_subprocess([name, "--version"], timeout=15)
                first = (result.stdout or result.stderr or "").splitlines()[0]
                return {
                    "kind": kind,
                    "major": _parse_major(first),
                    "version": first[:120],
                    "available": True,
                    "binary": name,
                }
            except (subprocess.TimeoutExpired, OSError):
                return {"kind": kind, "major": None, "version": "", "available": True, "binary": name}

    return {"kind": "unknown", "major": None, "version": "", "available": False}


def normalize_gtest_tag(version: str) -> str:
    raw = (version or "").strip()
    if not raw or raw.lower() == "auto":
        return ""
    if raw.startswith("v"):
        return raw
    return f"v{raw}"


def resolve_gtest_tag(gtest_version: str = "auto") -> str:
    """Pick a googletest git tag based on toolchain and optional pin."""
    pinned = normalize_gtest_tag(gtest_version)
    if pinned:
        return pinned if pinned in KNOWN_TAGS else pinned

    compiler = detect_compiler()
    cmake_major = detect_cmake_major()
    kind = compiler.get("kind")
    major = compiler.get("major")

    if kind == "msvc":
        if major is not None and major >= 19:
            return "v1.14.0"
        if major is not None and major >= 17:
            return "v1.13.0"
        return "v1.14.0" if major is None else "v1.12.0"

    if kind == "gcc":
        if major is not None and major >= 12:
            return "v1.14.0"
        if major is not None and major >= 9:
            return "v1.13.0"
        if major is not None:
            return "v1.12.0"
        return "v1.14.0"

    if kind == "clang":
        if major is not None and major >= 15:
            return "v1.14.0"
        if major is not None and major >= 10:
            return "v1.13.0"
        if major is not None:
            return "v1.12.0"
        return "v1.14.0"

    if sys.platform == "win32":
        return "v1.14.0"

    if cmake_major is not None and cmake_major < 3:
        return "v1.12.0"

    return "v1.14.0"


def normalize_gtest_source(gtest_source: str) -> str:
    source = (gtest_source or "auto").lower()
    if source in ("auto", "cached", "fetch", "system"):
        return source
    return "auto"


def gtest_source_path(tag: str) -> Path:
    safe = tag.lstrip("v").replace(".", "_")
    return gtest_cache_dir() / "src" / f"googletest-{safe}"


def ensure_gtest(tag: str, force: bool = False) -> dict:
    """Download googletest into forge cache when git is available."""
    dest = gtest_source_path(tag)
    if dest.exists() and (dest / "CMakeLists.txt").exists() and not force:
        return {
            "status": "ok",
            "tag": tag,
            "path": str(dest.resolve()),
            "downloaded": False,
            "method": "cache",
        }

    git = shutil.which("git")
    if not git:
        return {
            "status": "ok",
            "tag": tag,
            "path": str(dest.resolve()),
            "downloaded": False,
            "method": "cmake_fetch",
            "hint": "git not in PATH; CMake FetchContent will download during configure",
        }

    if dest.exists() and force:
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = run_subprocess(
            [git, "clone", "--depth", "1", "--branch", tag, GTEST_REPO, str(dest)],
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "tag": tag, "error": "git clone timed out (300s)"}
    except OSError as exc:
        return {"status": "error", "tag": tag, "error": str(exc)}

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0 or not (dest / "CMakeLists.txt").exists():
        shutil.rmtree(dest, ignore_errors=True)
        return {
            "status": "error",
            "tag": tag,
            "error": output.strip() or f"git clone failed with code {result.returncode}",
            "method": "git",
        }

    return {
        "status": "ok",
        "tag": tag,
        "path": str(dest.resolve()),
        "downloaded": True,
        "method": "git",
    }


def gtest_toolchain_info() -> dict:
    compiler = detect_compiler()
    cmake_major = detect_cmake_major()
    tag = resolve_gtest_tag("auto")
    path = gtest_source_path(tag)
    return {
        "recommended_tag": tag,
        "cached": path.exists() and (path / "CMakeLists.txt").exists(),
        "cache_path": str(path),
        "compiler": compiler,
        "cmake_major": cmake_major,
        "repo": GTEST_REPO,
    }
