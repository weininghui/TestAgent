"""
Code generation tools for creating various file types.

This module provides:
1. ``@tool``-decorated functions (``StructuredTool`` objects) for use by
   LangChain agents in the multi-agent pipeline.
2. Plain ``_raw_*`` function aliases for direct use by chain code (avoids
   ``'StructuredTool' object is not callable`` errors in newer LangChain
   versions where ``__call__`` was removed from ``BaseTool``).
"""

import os
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _write_file_to_disk(
    file_path: str,
    content: str,
    output_root: str = "output",
    description: str = "",
) -> str:
    """Core file-writing logic shared by all code-gen tools.

    Validates the path (no traversal), creates parent directories,
    and writes the content with UTF-8 encoding.

    Args:
        file_path: Relative path to the output file.
        content: File content to write.
        output_root: Root directory for output.
        description: Human-readable label for log messages.

    Returns:
        Absolute path of the written file.

    Raises:
        ValueError: If path contains ``..`` or is absolute.
        OSError: If directory or file creation fails.
        PermissionError: If permission denied.
    """
    if ".." in file_path or file_path.startswith("/"):
        raise ValueError(
            f"Invalid file path: '{file_path}'. "
            f"Path must be relative to output_root."
        )

    ensure_output_dir(output_root)

    full_path = Path(output_root) / file_path

    if full_path.exists():
        print(
            f"WARNING: File '{full_path}' already exists. "
            f"Overwriting without backup."
        )

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return str(full_path.absolute())
    except PermissionError:
        raise PermissionError(
            f"Permission denied writing to '{full_path}'."
        )
    except OSError as e:
        raise OSError(f"Failed to write file '{full_path}': {e}")


# ---------------------------------------------------------------------------
# Plain implementations — can be called directly from chain code
# (not wrapped by ``@tool``, so they remain regular Python functions).
# ---------------------------------------------------------------------------


def ensure_output_dir(path: str) -> bool:
    """
    Create directory if it doesn't exist.

    Args:
        path: Directory path to ensure exists

    Returns:
        bool: True if directory exists or was created successfully

    Raises:
        OSError: If directory cannot be created
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        raise OSError(f"Failed to create directory '{path}': {e}")


def raw_write_gtest_file(
    file_path: str,
    content: str,
    output_root: str = "output",
) -> str:
    """Write a generated Google Test (``.cc``) file.

    Plain function — safe for direct import and use by chain code.
    """
    return _write_file_to_disk(
        file_path, content, output_root, description="GTest file"
    )


def raw_write_cmake_file(
    file_path: str,
    content: str,
    output_root: str = "output",
) -> str:
    """Write a ``CMakeLists.txt`` configuration file.

    Plain function — safe for direct import and use by chain code.
    """
    return _write_file_to_disk(
        file_path, content, output_root, description="CMake file"
    )


def raw_write_workflow_file(
    file_path: str,
    content: str,
    output_root: str = "output",
) -> str:
    """Write a CI/CD workflow YAML file.

    Plain function — safe for direct import and use by chain code.
    """
    return _write_file_to_disk(
        file_path, content, output_root, description="workflow file"
    )


def raw_write_report_file(
    file_path: str,
    content: str,
    fmt: str = "md",
    output_root: str = "output",
) -> str:
    """Write a report file in Markdown or JSON format.

    Plain function — safe for direct import and use by chain code.
    """
    if fmt not in ("md", "json"):
        raise ValueError(f"Invalid format '{fmt}'. Must be 'md' or 'json'.")
    return _write_file_to_disk(
        file_path, content, output_root, description="report file"
    )


# ---------------------------------------------------------------------------
# ``@tool``-decorated versions — for use by LangChain agents / multi-agent
# pipeline.  These are ``StructuredTool`` objects and must be invoked via
# ``.invoke()`` in newer LangChain versions.
# ---------------------------------------------------------------------------


@tool
def write_gtest_file(
    file_path: str,
    content: str,
    output_root: str = "output",
) -> str:
    """Write a generated Google Test (.cpp) file.

    Args:
        file_path: Path for the .cpp file (relative to output_root)
        content: C++ source code content to write
        output_root: Root directory for output files (default: "output")

    Returns:
        str: Absolute path of the written file
    """
    return raw_write_gtest_file(file_path, content, output_root)


@tool
def write_cmake_file(
    file_path: str,
    content: str,
    output_root: str = "output",
) -> str:
    """Write a CMakeLists.txt configuration file.

    Args:
        file_path: Path for the CMakeLists.txt file (relative to output_root)
        content: CMake configuration content to write
        output_root: Root directory for output files (default: "output")

    Returns:
        str: Absolute path of the written file
    """
    return raw_write_cmake_file(file_path, content, output_root)


@tool
def write_workflow_file(
    file_path: str,
    content: str,
    output_root: str = "output",
) -> str:
    """Write a CI/CD workflow YAML file.

    Args:
        file_path: Path for the workflow YAML file (relative to output_root)
        content: YAML workflow content to write
        output_root: Root directory for output files (default: "output")

    Returns:
        str: Absolute path of the written file
    """
    return raw_write_workflow_file(file_path, content, output_root)


@tool
def write_report_file(
    file_path: str,
    content: str,
    fmt: str = "md",
    output_root: str = "output",
) -> str:
    """Write a report file in either Markdown or JSON format.

    Args:
        file_path: Path for the report file (relative to output_root)
        content: Report content to write
        fmt: Output format - "md" for Markdown or "json" for JSON (default: "md")
        output_root: Root directory for output files (default: "output")

    Returns:
        str: Absolute path of the written file
    """
    return raw_write_report_file(file_path, content, fmt, output_root)
