"""SDK header file tools for LangChain agents.

Provides @tool-decorated functions for reading and analyzing C/C++ SDK header files.
All functions include descriptive docstrings consumed by the LLM as tool descriptions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

from langchain_core.tools import tool


def _resolve_and_validate_path(file_path: str, sdk_root: str) -> Path:
    """Resolve *file_path* and verify it is under *sdk_root*.

    Performs path traversal protection by resolving both paths to absolute
    canonical forms and checking that *file_path* is a child of *sdk_root*.

    Args:
        file_path: The path to validate.
        sdk_root: The allowed root directory.

    Returns:
        The resolved absolute Path.

    Raises:
        ValueError: If *file_path* is not under *sdk_root*.
    """
    sdk_root_path = Path(sdk_root).resolve(strict=False)
    target_path = Path(file_path).resolve(strict=False)

    try:
        target_path.relative_to(sdk_root_path)
    except ValueError:
        raise ValueError(
            f"Access denied: '{file_path}' is not under the allowed SDK root "
            f"'{sdk_root}'."
        )

    return target_path


@tool
def list_header_files(sdk_root: str) -> List[str]:
    """Recursively list all C/C++ header (.h) files under SDK root.

    Searches ``sdk_root/include/`` first (standard SDK layout); if that
    directory does not exist, falls back to searching the entire
    ``sdk_root`` tree.  Common non-SDK directories (``.venv``, ``venv``,
    ``node_modules``, ``__pycache__``, ``build``, ``out``) are excluded.
    Returns absolute paths sorted alphabetically.

    Args:
        sdk_root: The root directory of the SDK.

    Returns:
        A sorted list of absolute file paths to ``.h`` files.
    """
    header_files: List[str] = []

    # Standard SDK layout: look under sdk_root/include/
    include_dir = Path(sdk_root) / "include"
    if include_dir.exists() and include_dir.is_dir():
        for h_path in include_dir.rglob("*.h"):
            if h_path.is_file():
                header_files.append(str(h_path.resolve(strict=False)))

    if header_files:
        return sorted(header_files)

    # Fallback: search sdk_root itself (for loose .h files in project root)
    _EXCLUDED_DIRS = {
        ".venv", "venv", "node_modules", "__pycache__",
        "build", "out", ".git", ".svn", ".idea", ".vscode",
    }
    for h_path in Path(sdk_root).rglob("*.h"):
        if not h_path.is_file():
            continue
        # Check if the file is inside an excluded directory
        rel = h_path.relative_to(sdk_root)
        if any(part in _EXCLUDED_DIRS for part in rel.parts[:-1]):
            continue
        header_files.append(str(h_path.resolve(strict=False)))

    return sorted(header_files)


@tool
def read_header_file(file_path: str, sdk_root: str) -> str:
    """Read and return the full content of a C/C++ header (``.h``) file.

    **Security**: validates that *file_path* is located under the configured
    *sdk_root* before reading, preventing arbitrary file / path-traversal
    access.

    Args:
        file_path: Absolute path to the ``.h`` file to read.
        sdk_root: The configured SDK root directory used for path validation.

    Returns:
        The full text content of the header file decoded as UTF-8.

    Raises:
        ValueError: If *file_path* is outside *sdk_root*.
        FileNotFoundError: If the file does not exist.
        PermissionError: If the OS denies read access.
        UnicodeDecodeError: If the file content is not valid UTF-8.
    """
    target = _resolve_and_validate_path(file_path, sdk_root)

    if not target.exists():
        raise FileNotFoundError(f"Header file not found: '{target}'")

    if not target.is_file():
        raise ValueError(f"Path is not a file: '{target}'")

    try:
        return target.read_text(encoding="utf-8")
    except PermissionError:
        raise PermissionError(f"Permission denied reading header file: '{target}'")
    except UnicodeDecodeError:
        raise UnicodeDecodeError(
            "utf-8",
            b"",
            0,
            0,
            f"Unable to decode header file as UTF-8: '{target}'",
        )


@tool
def extract_function_signatures(header_content: str) -> List[dict[str, Any]]:
    """Extract function signatures from C/C++ header content.

    .. note::
       **Placeholder** — currently returns an empty list.
       This will be implemented with LLM-based extraction in a future version.

    Args:
        header_content: The full text content of a header file.

    Returns:
        A list of dictionaries, each representing a parsed function signature.
        Currently always returns an empty list.
    """
    _ = header_content  # consumed by future LLM implementation
    return []


@tool
def extract_class_definitions(header_content: str) -> List[dict[str, Any]]:
    """Extract class / struct definitions from C/C++ header content.

    .. note::
       **Placeholder** — currently returns an empty list.
       This will be implemented with LLM-based extraction in a future version.

    Args:
        header_content: The full text content of a header file.

    Returns:
        A list of dictionaries, each representing a parsed class or struct
        definition.  Currently always returns an empty list.
    """
    _ = header_content  # consumed by future LLM implementation
    return []


@tool
def extract_enum_definitions(header_content: str) -> List[dict[str, Any]]:
    """Extract enum definitions from C/C++ header content.

    .. note::
       **Placeholder** — currently returns an empty list.
       This will be implemented with LLM-based extraction in a future version.

    Args:
        header_content: The full text content of a header file.

    Returns:
        A list of dictionaries, each representing a parsed enum definition.
        Currently always returns an empty list.
    """
    _ = header_content  # consumed by future LLM implementation
    return []
