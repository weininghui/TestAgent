"""Test file path helpers for enrich and orchestration."""

from __future__ import annotations

from pathlib import Path


def resolve_tests_dir(project_dir: str, tests_dir: str = "") -> Path | None:
    """Locate tests/ or test/ under project root."""
    root = Path(project_dir or Path.cwd()).resolve()
    if tests_dir:
        path = Path(tests_dir)
        if not path.is_absolute():
            path = root / path
        return path if path.is_dir() else None
    for candidate in ("tests", "test"):
        alt = root / candidate
        if alt.is_dir():
            return alt
    return None


def list_test_file_basenames(project_dir: str = "", tests_dir: str = "") -> list[str]:
    """Return sorted *_test.cpp basenames."""
    tests_path = resolve_tests_dir(project_dir, tests_dir)
    if not tests_path:
        return []
    return sorted(p.name for p in tests_path.glob("*_test.cpp"))


def parse_test_files_filter(test_files: list[str] | str = "") -> set[str]:
    """Normalize test file filter to lowercase basenames."""
    if not test_files:
        return set()
    if isinstance(test_files, str):
        parts = [p.strip() for p in test_files.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in test_files if str(p).strip()]
    return {Path(p).name.lower() for p in parts}


def match_test_file(path: Path, allowed: set[str]) -> bool:
    if not allowed:
        return True
    return path.name.lower() in allowed or str(path.resolve()).lower() in allowed
