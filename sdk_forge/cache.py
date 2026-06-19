"""Cache directory helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_CACHE_NAMES = ("sdk-forge", "sdk-test-forge")


def _resolve_cache_subdir(subdir: str) -> Path:
    """Return cache path, preferring sdk-forge with fallback to legacy sdk-test-forge."""
    env_key = "FORGE_GTEST_CACHE" if subdir == "gtest" else "FORGE_SCAN_CACHE"
    env = os.environ.get(env_key)
    if env:
        cache = Path(env)
        cache.mkdir(parents=True, exist_ok=True)
        return cache

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        candidates = [base / name / subdir for name in _CACHE_NAMES]
    else:
        candidates = [Path.home() / ".cache" / name / subdir for name in _CACHE_NAMES]

    for cache in candidates:
        if cache.is_dir():
            return cache
    cache = candidates[0]
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def gtest_cache_dir() -> Path:
    return _resolve_cache_subdir("gtest")


def scan_cache_dir() -> Path:
    return _resolve_cache_subdir("scan")
