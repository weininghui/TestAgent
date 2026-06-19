#!/usr/bin/env python3
"""MCP server — file-operation tools for SDK Test Forge Agent.

This MCP server provides Python-level tools for:
  1. scan_headers    — Scan .h files and extract API structures
  2. delete_tests    — Delete existing test files
  3. compile_tests   — Compile GTest test suites with cmake
  4. run_tests       — Run compiled test binary and return output

No external LLM dependencies. Designed to be called by OpenCode's
Test Forge Agent (which uses OpenCode's built-in model).

Usage
-----
    # stdio transport (default)
    python mcp_server.py

    # SSE transport
    python mcp_server.py --transport sse --port 8080
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp_server")

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "SDK Test Forge Tools",
    instructions="""SDK Test Forge Tools — pure file-operation helpers.

Tools:
  - scan_headers(sdk_root)    → scan .h files, extract API symbols
  - delete_tests(test_dir)    → remove existing test files
  - compile_tests(source_dir, build_dir, test_files)
                               → compile GTest files with cmake
  - run_tests(build_dir)      → run compiled test binary

These tools have NO LLM dependency. The Test Forge Agent (OpenCode)
uses its own model for analysis, design, and code generation;
these MCP tools handle the file-system and build operations.
""",
)

# ---------------------------------------------------------------------------
# Header scanning helpers
# ---------------------------------------------------------------------------

# Regex patterns for C/C++ API extraction
_RE_INCLUDE = re.compile(r'#include\s+[<"](\S+)[>"]')
_RE_FUNCTION = re.compile(
    r"""
    ^\s*
    (?:static\s+|virtual\s+|inline\s+|explicit\s+)*
    (?:const\s+)?
    (?P<return_type>[\w:]+(?:\s*<[^>]+>)?(?:\s*\*|\s*&|\s+const\s*\*|\s+const\s*&)?)
    \s+
    (?P<name>\w+)
    \s*\(
        (?P<params>[^)]*)
    \)
    \s*(?:const\s*)?
    \s*;
    """,
    re.VERBOSE | re.MULTILINE,
)
_RE_CLASS = re.compile(r"^\s*(class|struct)\s+(\w+)\s*", re.MULTILINE)
_RE_ENUM = re.compile(r"^\s*enum\s+(?:class\s+)?(\w+)\s*", re.MULTILINE)
_RE_TYPEDEF = re.compile(
    r"^\s*(?:"
    r"typedef\s+(.+?)\s+(\w+)"       # typedef unsigned long long uint64
    r"|"
    r"using\s+(\w+)\s*=\s*(.+?)"     # using Handle = void*
    r")\s*;",
    re.MULTILINE,
)


@dataclass
class FunctionInfo:
    name: str
    return_type: str
    params: str
    line: int


@dataclass
class ClassInfo:
    name: str
    kind: str  # "class" or "struct"
    line: int


@dataclass
class EnumInfo:
    name: str
    line: int


@dataclass
class HeaderFileInfo:
    path: str
    filename: str
    includes: list[str] = field(default_factory=list)
    functions: list[dict] = field(default_factory=list)
    classes: list[dict] = field(default_factory=list)
    enums: list[dict] = field(default_factory=list)
    typedefs: list[dict] = field(default_factory=list)
    raw_line_count: int = 0


def _parse_header(content: str, filepath: str) -> HeaderFileInfo:
    """Parse a C/C++ header file and extract structured API info."""
    info = HeaderFileInfo(
        path=filepath,
        filename=Path(filepath).name,
        raw_line_count=len(content.splitlines()),
    )

    # Includes
    info.includes = [m.group(1) for m in _RE_INCLUDE.finditer(content)]

    # Functions
    for m in _RE_FUNCTION.finditer(content):
        name = m.group("name")
        # Skip common non-API identifiers
        if name.startswith("_") or name in (
            "if", "else", "for", "while", "switch", "return",
        ):
            continue
        info.functions.append({
            "name": name,
            "return_type": m.group("return_type").strip(),
            "params": m.group("params").strip(),
            "line": content[: m.start("name")].count("\n") + 1,
        })

    # Classes / structs
    for m in _RE_CLASS.finditer(content):
        info.classes.append({
            "name": m.group(2),
            "kind": m.group(1),
            "line": content[: m.start()].count("\n") + 1,
        })

    # Enums
    for m in _RE_ENUM.finditer(content):
        info.enums.append({
            "name": m.group(1),
            "line": content[: m.start()].count("\n") + 1,
        })

    # Typedefs / using
    for m in _RE_TYPEDEF.finditer(content):
        if m.group(1) is not None and m.group(2) is not None:
            # typedef X alias;
            type_str = m.group(1).strip()
            alias = m.group(2).strip()
        else:
            # using alias = X;
            alias = m.group(3).strip()
            type_str = m.group(4).strip()
        info.typedefs.append({
            "type": type_str,
            "alias": alias,
            "line": content[: m.start()].count("\n") + 1,
        })

    return info


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    description="""Scan a directory for C/C++ header files (.h) and extract
structured API information: functions, classes, enums, typedefs, includes.

Returns a JSON summary of all header files found and their extracted symbols.
The agent uses this to understand the SDK's API surface before designing tests.
""",
)
async def scan_headers(
    sdk_root: Annotated[
        str,
        "Absolute path to the SDK root directory containing .h files.",
    ],
) -> str:
    """Scan SDK header files and return structured API inventory."""
    sdk_path = Path(sdk_root)
    if not sdk_path.is_dir():
        return json.dumps({
            "error": f"SDK root directory not found: {sdk_root}",
            "status": "error",
        }, indent=2)

    # Find all .h files
    header_files: list[HeaderFileInfo] = []
    total_functions = 0
    total_classes = 0
    total_enums = 0

    for h_file in sorted(sdk_path.rglob("*.h")):
        try:
            content = h_file.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Cannot read %s: %s", h_file, exc)
            continue

        info = _parse_header(content, str(h_file))
        header_files.append(info)
        total_functions += len(info.functions)
        total_classes += len(info.classes)
        total_enums += len(info.enums)

    # Build summary
    summaries = []
    for hf in header_files:
        summaries.append({
            "file": hf.filename,
            "path": hf.path,
            "lines": hf.raw_line_count,
            "includes": hf.includes,
            "functions": hf.functions,
            "classes": hf.classes,
            "enums": hf.enums,
            "typedefs": hf.typedefs,
        })

    result = {
        "status": "ok",
        "sdk_root": sdk_root,
        "total_files": len(header_files),
        "total_functions": total_functions,
        "total_classes": total_classes,
        "total_enums": total_enums,
        "files": summaries,
    }

    logger.info(
        "Scan complete — %d files, %d functions, %d classes, %d enums",
        len(header_files),
        total_functions,
        total_classes,
        total_enums,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(
    description="""Delete existing test files in a directory.

Searches for files matching common GTest patterns (*_test.cpp, *_test.cc,
test_*.cpp, *_unittest.cpp, *_tests.cpp) and removes them.

Use this BEFORE generating new tests to ensure a clean output directory.

Returns the list of deleted files.
""",
)
async def delete_tests(
    test_dir: Annotated[
        str,
        "Directory to scan for existing test files.",
    ],
) -> str:
    """Delete existing GTest test files in a directory."""
    test_path = Path(test_dir)
    if not test_path.is_dir():
        return json.dumps({
            "error": f"Directory not found: {test_dir}",
            "status": "error",
        }, indent=2)

    # Patterns to match GTest files
    patterns = [
        "*_test.cpp", "*_test.cc", "*_test.cxx",
        "test_*.cpp", "test_*.cc",
        "*_unittest.cpp", "*_unittest.cc",
        "*_tests.cpp", "*_tests.cc",
        "*Test.cpp", "*Test.cc",
    ]

    deleted: list[str] = []
    for pattern in patterns:
        for f in test_path.glob(pattern):
            if f.is_file():
                try:
                    f.unlink()
                    deleted.append(str(f))
                    logger.info("Deleted test file: %s", f)
                except OSError as exc:
                    logger.warning("Cannot delete %s: %s", f, exc)

    return json.dumps({
        "status": "ok",
        "directory": test_dir,
        "deleted_count": len(deleted),
        "deleted_files": deleted,
    }, indent=2, ensure_ascii=False)


@mcp.tool(
    description="""Compile GTest source files using CMake.

Sets up a CMake project with GoogleTest (via FetchContent), compiles the
test files, and returns compilation output (success or errors).

Parameters:
  - source_dir: Directory containing the test .cpp files and CMakeLists.txt
  - build_dir: Directory for build artifacts (will be created if missing)
  - test_files: Optional — list of test file paths. If omitted, scans for
    *_test.cpp files in source_dir.

Returns compilation output (stdout/stderr) and exit code.
""",
)
async def compile_tests(
    source_dir: Annotated[
        str,
        "Directory containing the test .cpp files.",
    ],
    build_dir: Annotated[
        str,
        "Directory for build artifacts (created if missing).",
    ],
) -> str:
    """Compile GTest test files with CMake."""
    src_path = Path(source_dir)
    build_path = Path(build_dir)

    if not src_path.is_dir():
        return json.dumps({
            "error": f"Source directory not found: {source_dir}",
            "status": "error",
        }, indent=2)

    # Check if CMakeLists.txt exists; if not, create one
    cmake_file = src_path / "CMakeLists.txt"
    if not cmake_file.exists():
        # Auto-generate CMakeLists.txt
        test_files = list(dict.fromkeys(
                     sorted(src_path.glob("*_test.cpp")) +
                     sorted(src_path.glob("*Test.cpp")) +
                     sorted(src_path.glob("*_test.cc"))
                 ))
        if not test_files:
            return json.dumps({
                "error": f"No test files (*_test.cpp, *Test.cpp) found in {source_dir}",
                "status": "error",
            }, indent=2)

        file_list = "\n    ".join(f.name for f in test_files)
        project_name = src_path.name.replace("-", "_").replace(" ", "_")

        cmake_content = f"""cmake_minimum_required(VERSION 3.14)
project({project_name} CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Fetch GoogleTest
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

# Test executable
add_executable(run_tests
    {file_list}
)

target_link_libraries(run_tests PRIVATE gtest_main gmock)
target_include_directories(run_tests PRIVATE ${{CMAKE_CURRENT_SOURCE_DIR}})
"""
        cmake_file.write_text(cmake_content, encoding="utf-8")
        logger.info("Auto-generated CMakeLists.txt in %s", src_path)

    # Create build directory
    build_path.mkdir(parents=True, exist_ok=True)

    # Run cmake configure
    logger.info("Configuring CMake in %s ...", build_path)
    try:
        result = subprocess.run(
            ["cmake", str(src_path.resolve())],
            cwd=str(build_path.resolve()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
        )
        cmake_output = (result.stdout or "") + "\n" + (result.stderr or "")
    except FileNotFoundError:
        return json.dumps({
            "error": "cmake not found. Install CMake and ensure it's in PATH.",
            "status": "error",
        }, indent=2)
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "cmake configure timed out (240s).",
            "status": "error",
        }, indent=2)

    if result.returncode != 0:
        return json.dumps({
            "status": "cmake_error",
            "stage": "configure",
            "output": cmake_output,
        }, indent=2, ensure_ascii=False)

    # Run cmake build
    logger.info("Building ...")
    try:
        build_result = subprocess.run(
            ["cmake", "--build", str(build_path.resolve())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        build_output = (build_result.stdout or "") + "\n" + (build_result.stderr or "")
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "cmake build timed out (300s).",
            "status": "error",
        }, indent=2)

    if build_result.returncode != 0:
        return json.dumps({
            "status": "cmake_error",
            "stage": "build",
            "output": build_output,
        }, indent=2, ensure_ascii=False)

    # Locate the built test binary
    binary_path = build_path / "run_tests"
    if not binary_path.exists():
        # Check in Debug/Release subdirectories
        for sub in ["Debug", "Release", "RelWithDebInfo"]:
            candidate = build_path / sub / "run_tests"
            if candidate.exists():
                binary_path = candidate
                break

    return json.dumps({
        "status": "ok",
        "binary_path": str(binary_path) if binary_path.exists() else None,
        "build_output": build_output,
    }, indent=2, ensure_ascii=False)


@mcp.tool(
    description="""Run a compiled GTest test binary and return test results.

Parses the GTest output and returns a structured result with:
  - total / passed / failed / skipped test counts
  - list of failed test names (if any)
  - full raw output

Use *after* ``compile_tests`` has produced a test binary.
""",
)
async def run_tests(
    build_dir: Annotated[
        str,
        "Build directory containing the test binary (run_tests).",
    ],
    test_filter: Annotated[
        str,
        "Optional GTest filter pattern (e.g. 'MySuite.*' to run specific tests).",
    ] = "",
) -> str:
    """Run compiled GTest test binary and return results."""
    build_path = Path(build_dir)

    # Find the test binary
    binary = build_path / "run_tests"
    if not binary.exists():
        for sub in ["Debug", "Release", "RelWithDebInfo"]:
            candidate = build_path / sub / "run_tests"
            if candidate.exists():
                binary = candidate
                break
        if not binary.exists():
            # Try to find any executable with "run_" in name
            # On Windows, executables have .exe extension
            exe_suffix = ".exe" if sys.platform == "win32" else ""
            for f in build_path.rglob(f"run_*{exe_suffix}"):
                if f.is_file() and (sys.platform != "win32" or f.suffix == ".exe"):
                    binary = f
                    break

    if not binary.exists():
        return json.dumps({
            "error": f"Test binary not found in {build_dir}. Run compile_tests first.",
            "status": "error",
        }, indent=2)

    # Build command
    cmd = [str(binary)]
    if test_filter:
        cmd.extend(["--gtest_filter", test_filter])

    logger.info("Running tests: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "Test execution timed out (600s).",
            "status": "error",
        }, indent=2)

    full_output = (result.stdout or "") + "\n" + (result.stderr or "")

    # Parse GTest output
    total = 0
    passed = 0
    failed = 0
    skipped = 0
    failed_tests: list[str] = []

    for line in result.stdout.splitlines():
        line = line.strip()
        # Match "[  PASSED  ] N tests" or "[  FAILED  ] N test"
        if line.startswith("[  PASSED  ]"):
            m = re.search(r"(\d+)\s+test", line)
            if m:
                passed = int(m.group(1))
        elif line.startswith("[  FAILED  ]"):
            m = re.search(r"(\d+)\s+test", line)
            if m:
                failed = int(m.group(1))
        elif line.startswith("[  SKIPPED ]"):
            m = re.search(r"(\d+)\s+test", line)
            if m:
                skipped = int(m.group(1))

    # Also parse individual test results to get failed test names
    for line in result.stdout.splitlines():
        if line.startswith("FAILED") or "FAILED" in line:
            parts = line.split()
            if len(parts) >= 2:
                failed_tests.append(parts[-1])

    # Better: parse the FAILED section at the end
    in_failed_section = False
    for line in result.stdout.splitlines():
        if "FAILED TEST" in line:
            in_failed_section = True
            continue
        if in_failed_section:
            stripped = line.strip()
            if stripped and not stripped.startswith("[") and stripped != "":
                failed_tests.append(stripped)

    # Total from "N tests from M test suites"
    m_total = re.search(r"\[==========\] Running (\d+) tests", result.stdout)
    if m_total:
        total = int(m_total.group(1))
    else:
        total = passed + failed + skipped

    test_results = {
        "status": "ok" if result.returncode == 0 else "test_failures",
        "return_code": result.returncode,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failed_tests": failed_tests,
        "output": full_output,
    }

    logger.info(
        "Tests complete — %d total, %d passed, %d failed, %d skipped",
        total, passed, failed, skipped,
    )
    return json.dumps(test_results, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the ``testgen-mcp`` console script."""
    import argparse

    parser = argparse.ArgumentParser(description="MCP server for SDK Test Forge")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080).",
    )
    args = parser.parse_args()

    logger.info(
        "Starting MCP server — transport=%s port=%d",
        args.transport,
        args.port,
    )

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
