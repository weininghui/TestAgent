"""
Code generation tools for creating various file types.

This module provides LangChain @tool-decorated functions for generating
and writing different types of files including C++ source files,
CMake configuration files, CI/CD workflow files, and reports.
"""

import os
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool


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


@tool
def write_gtest_file(file_path: str, content: str, output_root: str = "output") -> str:
    """
    Write a generated Google Test (.cpp) file.

    Args:
        file_path: Path for the .cpp file (relative to output_root)
        content: C++ source code content to write
        output_root: Root directory for output files (default: "output")

    Returns:
        str: Absolute path of the written file

    Raises:
        ValueError: If path tries to escape output_root
        OSError: If file cannot be written
        PermissionError: If permission denied
    """
    # Security check: prevent path traversal
    if ".." in file_path or file_path.startswith("/"):
        raise ValueError(f"Invalid file path: '{file_path}'. Path must be relative to output_root.")

    # Ensure output directory exists
    ensure_output_dir(output_root)

    # Construct full file path
    full_path = Path(output_root) / file_path

    # Check if file already exists
    if full_path.exists():
        print(f"WARNING: File '{full_path}' already exists. Overwriting without backup.")

    try:
        # Write file with UTF-8 encoding
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(full_path.absolute())
    except PermissionError as e:
        raise PermissionError(f"Permission denied writing to '{full_path}': {e}")
    except OSError as e:
        raise OSError(f"Failed to write file '{full_path}': {e}")


@tool
def write_cmake_file(file_path: str, content: str, output_root: str = "output") -> str:
    """
    Write a CMakeLists.txt configuration file.

    Args:
        file_path: Path for the CMakeLists.txt file (relative to output_root)
        content: CMake configuration content to write
        output_root: Root directory for output files (default: "output")

    Returns:
        str: Absolute path of the written file

    Raises:
        ValueError: If path tries to escape output_root
        OSError: If file cannot be written
        PermissionError: If permission denied
    """
    # Security check: prevent path traversal
    if ".." in file_path or file_path.startswith("/"):
        raise ValueError(f"Invalid file path: '{file_path}'. Path must be relative to output_root.")

    # Ensure output directory exists
    ensure_output_dir(output_root)

    # Construct full file path
    full_path = Path(output_root) / file_path

    # Check if file already exists
    if full_path.exists():
        print(f"WARNING: File '{full_path}' already exists. Overwriting without backup.")

    try:
        # Write file with UTF-8 encoding
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(full_path.absolute())
    except PermissionError as e:
        raise PermissionError(f"Permission denied writing to '{full_path}': {e}")
    except OSError as e:
        raise OSError(f"Failed to write file '{full_path}': {e}")


@tool
def write_workflow_file(file_path: str, content: str, output_root: str = "output") -> str:
    """
    Write a CI/CD workflow YAML file.

    Args:
        file_path: Path for the workflow YAML file (relative to output_root)
        content: YAML workflow content to write
        output_root: Root directory for output files (default: "output")

    Returns:
        str: Absolute path of the written file

    Raises:
        ValueError: If path tries to escape output_root
        OSError: If file cannot be written
        PermissionError: If permission denied
    """
    # Security check: prevent path traversal
    if ".." in file_path or file_path.startswith("/"):
        raise ValueError(f"Invalid file path: '{file_path}'. Path must be relative to output_root.")

    # Ensure output directory exists
    ensure_output_dir(output_root)

    # Construct full file path
    full_path = Path(output_root) / file_path

    # Check if file already exists
    if full_path.exists():
        print(f"WARNING: File '{full_path}' already exists. Overwriting without backup.")

    try:
        # Write file with UTF-8 encoding
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(full_path.absolute())
    except PermissionError as e:
        raise PermissionError(f"Permission denied writing to '{full_path}': {e}")
    except OSError as e:
        raise OSError(f"Failed to write file '{full_path}': {e}")


@tool
def write_report_file(file_path: str, content: str, fmt: str = "md", output_root: str = "output") -> str:
    """
    Write a report file in either Markdown or JSON format.

    Args:
        file_path: Path for the report file (relative to output_root)
        content: Report content to write
        fmt: Output format - "md" for Markdown or "json" for JSON (default: "md")
        output_root: Root directory for output files (default: "output")

    Returns:
        str: Absolute path of the written file

    Raises:
        ValueError: If path tries to escape output_root or invalid format
        OSError: If file cannot be written
        PermissionError: If permission denied
    """
    # Security check: prevent path traversal
    if ".." in file_path or file_path.startswith("/"):
        raise ValueError(f"Invalid file path: '{file_path}'. Path must be relative to output_root.")

    # Validate format
    if fmt not in ("md", "json"):
        raise ValueError(f"Invalid format '{fmt}'. Must be 'md' or 'json'.")

    # Ensure output directory exists
    ensure_output_dir(output_root)

    # Construct full file path
    full_path = Path(output_root) / file_path

    # Check if file already exists
    if full_path.exists():
        print(f"WARNING: File '{full_path}' already exists. Overwriting without backup.")

    try:
        # Write file with UTF-8 encoding
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(full_path.absolute())
    except PermissionError as e:
        raise PermissionError(f"Permission denied writing to '{full_path}': {e}")
    except OSError as e:
        raise OSError(f"Failed to write file '{full_path}': {e}")
