"""Test file cleanup."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("sdk_forge.clean")


def delete_tests_impl(test_dir: str) -> dict:
    test_path = Path(test_dir)
    if not test_path.is_dir():
        return {"error": f"Directory not found: {test_dir}", "status": "error"}

    patterns = [
        "*_test.cpp",
        "*_test.cc",
        "*_test.cxx",
        "test_*.cpp",
        "test_*.cc",
        "*_unittest.cpp",
        "*_unittest.cc",
        "*_tests.cpp",
        "*_tests.cc",
        "*Test.cpp",
        "*Test.cc",
    ]
    deleted_set: set[str] = set()
    for pattern in patterns:
        for f in test_path.rglob(pattern):
            if f.is_file():
                try:
                    f.unlink()
                    deleted_set.add(str(f))
                except OSError as exc:
                    logger.warning("Cannot delete %s: %s", f, exc)
    deleted = sorted(deleted_set)
    return {
        "status": "ok",
        "directory": test_dir,
        "deleted_count": len(deleted),
        "deleted_files": deleted,
    }
