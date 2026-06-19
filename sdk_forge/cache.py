"""Cache directory helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def gtest_cache_dir() -> Path:
    env = os.environ.get("FORGE_GTEST_CACHE")
    if env:
        cache = Path(env)
    elif sys.platform == "win32":
        cache = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "sdk-test-forge" / "gtest"
    else:
        cache = Path.home() / ".cache" / "sdk-test-forge" / "gtest"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def scan_cache_dir() -> Path:
    env = os.environ.get("FORGE_SCAN_CACHE")
    if env:
        cache = Path(env)
    elif sys.platform == "win32":
        cache = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "sdk-test-forge" / "scan"
    else:
        cache = Path.home() / ".cache" / "sdk-test-forge" / "scan"
    cache.mkdir(parents=True, exist_ok=True)
    return cache
