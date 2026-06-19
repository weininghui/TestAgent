#!/usr/bin/env python3
"""MCP server — thin wrapper over sdk_forge core (v3.0)."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from sdk_forge.build import compile_tests_impl
from sdk_forge.clean import delete_tests_impl
from sdk_forge.coverage import collect_coverage_impl
from sdk_forge.mock import generate_mocks_impl
from sdk_forge.probe import probe_sdk_impl
from sdk_forge.run import run_tests_impl
from sdk_forge.scan import CLANG_AVAILABLE, scan_headers_impl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp_server")

mcp = FastMCP(
    "SDK Test Forge Tools",
    instructions="""SDK Test Forge Tools — scan, compile, and run GTest suites for C/C++ SDKs.

Tools:
  - scan_headers       → parse .h/.hpp (libclang with regex fallback)
  - probe_sdk          → suggest include/lib/pkg-config settings
  - delete_tests       → remove existing GTest files
  - compile_tests      → CMake build with SDK linking and GTest cache
  - run_tests          → execute compiled test binary
  - collect_coverage   → gcov/lcov coverage summary
  - generate_mocks     → GMock templates for virtual methods
""",
)


@mcp.tool(description="Scan .h/.hpp headers using libclang when available, with regex fallback.")
async def scan_headers(
    sdk_root: Annotated[str, "Absolute path to the SDK root directory."],
    include_dirs: Annotated[list[str] | str, "Optional include dirs for libclang (-I)."] = "",
    compile_args: Annotated[list[str] | str, "Optional extra compile args for libclang."] = "",
    use_clang: Annotated[bool | str, "Use libclang when available (default true)."] = True,
    use_cache: Annotated[bool | str, "Use scan result cache (default true)."] = True,
) -> str:
    result = scan_headers_impl(sdk_root, include_dirs, compile_args, use_clang, use_cache)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Probe an SDK root or .pc file and suggest compile_tests parameters.")
async def probe_sdk(
    sdk_root: Annotated[str, "SDK root directory or path to a .pc file."],
) -> str:
    return json.dumps(probe_sdk_impl(sdk_root), indent=2, ensure_ascii=False)


@mcp.tool(description="Delete existing GTest files recursively.")
async def delete_tests(test_dir: Annotated[str, "Directory to scan for existing test files."]) -> str:
    return json.dumps(delete_tests_impl(test_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Compile GTest sources with optional SDK/pkg-config/find_package linking.")
async def compile_tests(
    source_dir: Annotated[str, "Directory containing test .cpp files."],
    build_dir: Annotated[str, "Build directory for artifacts."],
    sdk_include_dirs: Annotated[list[str] | str, "SDK include directories."] = "",
    sdk_lib_dirs: Annotated[list[str] | str, "SDK library directories."] = "",
    link_libraries: Annotated[list[str] | str, "Libraries to link besides gtest."] = "",
    cmake_prefix_path: Annotated[list[str] | str, "CMAKE_PREFIX_PATH entries."] = "",
    find_packages: Annotated[list[dict] | str, "find_package specs as JSON list."] = "",
    pkg_config_packages: Annotated[list[str] | str, "pkg-config package names."] = "",
    extra_cmake_snippet: Annotated[str, "Extra CMake snippet appended before link lines."] = "",
    gtest_source: Annotated[str, "GTest source: fetch, cached (default), or system."] = "cached",
    coverage: Annotated[bool | str, "Enable gcov coverage flags."] = False,
    coverage_tool: Annotated[str, "Coverage tool: gcov or llvm-cov."] = "gcov",
) -> str:
    return json.dumps(
        compile_tests_impl(
            source_dir, build_dir, sdk_include_dirs, sdk_lib_dirs, link_libraries,
            cmake_prefix_path, find_packages, pkg_config_packages, extra_cmake_snippet,
            gtest_source, coverage, coverage_tool,
        ),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Run a compiled GTest binary and return structured results.")
async def run_tests(
    build_dir: Annotated[str, "Build directory containing run_tests binary."],
    test_filter: Annotated[str, "Optional GTest filter pattern."] = "",
) -> str:
    return json.dumps(run_tests_impl(build_dir, test_filter), indent=2, ensure_ascii=False)


@mcp.tool(description="Collect gcov/lcov coverage from a build directory.")
async def collect_coverage(
    build_dir: Annotated[str, "Build directory with coverage artifacts."],
    source_dir: Annotated[str, "Optional source directory for gcov."] = "",
    coverage_tool: Annotated[str, "gcov (default) or llvm-cov."] = "gcov",
) -> str:
    return json.dumps(collect_coverage_impl(build_dir, source_dir, coverage_tool), indent=2, ensure_ascii=False)


@mcp.tool(description="Generate GMock templates from scan_headers JSON or SDK root.")
async def generate_mocks(
    scan_json: Annotated[str, "JSON from scan_headers, or sdk_root if scan_json is a directory path."] = "",
    sdk_root: Annotated[str, "SDK root to scan when scan_json is empty."] = "",
    class_name: Annotated[str, "Optional class name filter."] = "",
) -> str:
    if scan_json.strip():
        data = scan_json
    elif sdk_root.strip():
        data = scan_headers_impl(sdk_root)
    else:
        return json.dumps({"status": "error", "error": "Provide scan_json or sdk_root."}, indent=2)
    if isinstance(data, dict) and data.get("status") == "error":
        return json.dumps(data, indent=2, ensure_ascii=False)
    payload = data if isinstance(data, str) else json.dumps(data)
    return json.dumps(generate_mocks_impl(payload, class_name), indent=2, ensure_ascii=False)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MCP server for SDK Test Forge")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")


# Backward-compatible re-exports for tests
from sdk_forge.build import generate_cmake_content as _generate_cmake_content
from sdk_forge.cache import gtest_cache_dir as _gtest_cache_dir
from sdk_forge.scan import (
    HeaderFileInfo,
    parse_header as _parse_header,
    parse_header_clang as _parse_header_clang,
)
from sdk_forge.util import normalize_str_list as _normalize_str_list

_CLANG_AVAILABLE = CLANG_AVAILABLE

if __name__ == "__main__":
    main()
