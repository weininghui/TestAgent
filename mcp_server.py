#!/usr/bin/env python3
"""MCP server — thin wrapper over sdk_forge core (v3.3)."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from sdk_forge.build import compile_tests_impl
from sdk_forge.clean import delete_tests_impl
from sdk_forge.coverage import collect_coverage_impl
from sdk_forge.doctor import doctor_impl
from sdk_forge.init import init_project_impl
from sdk_forge.mock import generate_mocks_impl
from sdk_forge.learn import forget_learned_config, load_learned_config
from sdk_forge.pipeline import build_pipeline_impl
from sdk_forge.plan import suggest_test_plan_impl
from sdk_forge.probe import probe_sdk_impl
from sdk_forge.report import report_impl
from sdk_forge.retry import load_build_state
from sdk_forge.run import run_tests_impl
from sdk_forge.scan import CLANG_AVAILABLE, scan_headers_impl
from sdk_forge.session import get_session_context_impl, save_plan_state
from sdk_forge.templates import generate_test_skeleton_impl
from sdk_forge.test_fix import analyze_test_failures_impl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp_server")

mcp = FastMCP(
    "SDK Test Forge Tools",
    instructions="""SDK Test Forge Tools — scan, plan, compile, and run GTest suites for C/C++ SDKs.

Tools:
  - forge_doctor        → check cmake, compiler, caches
  - init_forge_project  → scaffold tests + .forge.yaml
  - suggest_test_plan   → structured test scenarios from scan
  - generate_test_skeleton → GTest .cpp skeleton from plan
  - build_tests         → probe + compile + run with retry/auto-fix
  - analyze_test_failures → parse GTest failure output
  - forge_report        → markdown report from last build
  - get_build_state     → read last build JSON
  - get_session_context → plan + build + learned config
  - get_learned_config  → cached compile params for SDK
  - scan_headers        → parse headers (libclang + regex)
  - probe_sdk           → suggest link settings
  - compile_tests       → CMake build (reads .forge.yaml/.forge.json)
  - run_tests           → execute test binary
  - collect_coverage    → gcov/lcov summary
  - generate_mocks      → GMock templates
  - delete_tests        → remove old test files
""",
)


@mcp.tool(description="Check cmake, compiler, libclang, and forge cache directories.")
async def forge_doctor() -> str:
    return json.dumps(doctor_impl(), indent=2, ensure_ascii=False)


@mcp.tool(description="Scaffold a forge test project with tests/ and .forge.yaml.")
async def init_forge_project(
    target_dir: Annotated[str, "Directory to create the project in."],
    sdk_root: Annotated[str, "Optional SDK root for .forge.yaml template."] = "",
    project_name: Annotated[str, "Sample test file base name."] = "sdk_tests",
) -> str:
    return json.dumps(init_project_impl(target_dir, sdk_root, project_name), indent=2, ensure_ascii=False)


@mcp.tool(description="Generate structured test plan with scenarios from scan_headers JSON or SDK root.")
async def suggest_test_plan(
    sdk_root: Annotated[str, "SDK root to scan when scan_json is empty."] = "",
    scan_json: Annotated[str, "JSON from scan_headers."] = "",
    project_dir: Annotated[str, "Save plan to .forge/cache when set."] = "",
) -> str:
    result = suggest_test_plan_impl(sdk_root=sdk_root, scan_json=scan_json or None)
    if project_dir and result.get("status") == "ok":
        save_plan_state(project_dir, result)
        result["plan_saved"] = str((project_dir or ".") + "/.forge/cache/last_plan.json")
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Generate compilable GTest skeleton .cpp files from plan or SDK scan.")
async def generate_test_skeleton(
    output_dir: Annotated[str, "Directory for generated *_test.cpp files."],
    plan_json: Annotated[str, "JSON from suggest_test_plan."] = "",
    sdk_root: Annotated[str, "Scan SDK and plan when plan_json empty."] = "",
    project_name: Annotated[str, "Base name fallback."] = "sdk_tests",
    overwrite: Annotated[bool | str, "Overwrite existing test files."] = False,
) -> str:
    return json.dumps(
        generate_test_skeleton_impl(plan_json or None, output_dir, sdk_root, project_name, overwrite),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Analyze GTest failures; returns structured review_assertion actions.")
async def analyze_test_failures(
    build_dir: Annotated[str, "Build directory to run tests from."] = "",
    run_json: Annotated[str, "Optional run_tests JSON instead of re-running."] = "",
) -> str:
    return json.dumps(
        analyze_test_failures_impl(build_dir, run_json or None),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Combined session: last plan, build state, learned config, report summary.")
async def get_session_context(
    project_dir: Annotated[str, "Project root with .forge/cache/."] = "",
) -> str:
    return json.dumps(get_session_context_impl(project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Load learned compile params for an SDK from prior successful builds.")
async def get_learned_config(
    sdk_root: Annotated[str, "SDK root path."],
    project_dir: Annotated[str, "Project cache directory."] = "",
) -> str:
    return json.dumps(load_learned_config(sdk_root, project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Remove cached learned compile params for an SDK.")
async def forget_learned_config(
    sdk_root: Annotated[str, "SDK root path."],
    project_dir: Annotated[str, "Project cache directory."] = "",
) -> str:
    return json.dumps(forget_learned_config(sdk_root, project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Probe + compile + run with retry and optional auto-fix from CMake hints.")
async def build_tests(
    project_dir: Annotated[str, "Project root containing .forge.yaml or .forge.json."] = "",
    source_dir: Annotated[str, "Override tests directory."] = "",
    build_dir: Annotated[str, "Override build directory."] = "",
    sdk_root: Annotated[str, "Override SDK root for probe."] = "",
    run_after_compile: Annotated[bool | str, "Run tests after compile (default true)."] = True,
    max_retries: Annotated[int | str, "Max compile attempts with hint-based auto-fix (default 3)."] = 3,
    auto_fix_config: Annotated[bool | str, "Write applied fixes back to .forge config."] = False,
) -> str:
    return json.dumps(
        build_pipeline_impl(
            project_dir, source_dir, build_dir, sdk_root,
            run_after_compile, max_retries, auto_fix_config,
        ),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Generate markdown or JSON report from last build state.")
async def forge_report(
    project_dir: Annotated[str, "Project directory with .forge/cache/last_build.json."] = "",
    output_format: Annotated[str, "markdown (default) or json."] = "markdown",
) -> str:
    return json.dumps(report_impl(project_dir, output_format=output_format), indent=2, ensure_ascii=False)


@mcp.tool(description="Read last build state JSON from project cache.")
async def get_build_state(
    project_dir: Annotated[str, "Project directory."] = "",
) -> str:
    return json.dumps(load_build_state(project_dir), indent=2, ensure_ascii=False)


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


@mcp.tool(description="Compile GTest sources; auto-loads .forge.yaml/.forge.json from project.")
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
    gtest_source: Annotated[str, "GTest: auto (default), cached, fetch, or system."] = "auto",
    gtest_version: Annotated[str, "Pin googletest tag, e.g. 1.14.0; auto picks by toolchain."] = "auto",
    coverage: Annotated[bool | str, "Enable gcov coverage flags."] = False,
    coverage_tool: Annotated[str, "Coverage tool: gcov or llvm-cov."] = "gcov",
    use_config: Annotated[bool | str, "Load .forge.yaml/.forge.json (default true)."] = True,
) -> str:
    return json.dumps(
        compile_tests_impl(
            source_dir, build_dir, sdk_include_dirs, sdk_lib_dirs, link_libraries,
            cmake_prefix_path, find_packages, pkg_config_packages, extra_cmake_snippet,
            gtest_source, gtest_version, coverage, coverage_tool, use_config,
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
