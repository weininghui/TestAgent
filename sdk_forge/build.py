"""CMake generation and test compilation."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from sdk_forge.cache import gtest_cache_dir
from sdk_forge.errors import parse_cmake_error
from sdk_forge.util import cmake_path, normalize_json_list, normalize_str_list, run_subprocess


def gtest_cmake_block(gtest_source: str) -> str:
    source = (gtest_source or "cached").lower()
    if source == "system":
        return """
find_package(GTest REQUIRED)
"""
    cache_dir = cmake_path(str(gtest_cache_dir()))
    return f"""
include(FetchContent)
set(FETCHCONTENT_BASE_DIR "{cache_dir}")
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
    GIT_SHALLOW TRUE
    UPDATE_DISCONNECTED TRUE
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)
"""


def coverage_cmake_block(coverage: bool, coverage_tool: str) -> str:
    if not coverage:
        return ""
    tool = (coverage_tool or "gcov").lower()
    if tool == "llvm-cov":
        return """
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fprofile-instr-generate -fcoverage-mapping")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fprofile-instr-generate")
"""
    return """
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} --coverage -fprofile-arcs -ftest-coverage")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} --coverage")
"""


def sdk_link_cmake_block(
    sdk_include_dirs: list[str],
    sdk_lib_dirs: list[str],
    link_libraries: list[str],
    cmake_prefix_path: list[str],
    find_packages: list[dict],
    pkg_config_packages: list[str],
    extra_cmake_snippet: str,
) -> str:
    blocks: list[str] = []
    if cmake_prefix_path:
        prefix = ";".join(cmake_path(item) for item in cmake_prefix_path)
        blocks.append(f'list(APPEND CMAKE_PREFIX_PATH "{prefix}")')
    if pkg_config_packages:
        blocks.append("find_package(PkgConfig REQUIRED)")
        for pkg in pkg_config_packages:
            var = re.sub(r"[^A-Za-z0-9_]", "_", pkg).upper()
            blocks.append(f'pkg_check_modules({var} REQUIRED IMPORTED_TARGET {pkg})')
    for pkg in find_packages:
        name = str(pkg.get("name", "")).strip()
        if not name:
            continue
        components = pkg.get("components") or []
        if components:
            comp_str = " ".join(str(c) for c in components)
            blocks.append(f"find_package({name} REQUIRED COMPONENTS {comp_str})")
        else:
            blocks.append(f"find_package({name} REQUIRED)")
    if extra_cmake_snippet.strip():
        blocks.append(extra_cmake_snippet.strip())

    include_dirs = ["${CMAKE_CURRENT_SOURCE_DIR}", *(cmake_path(item) for item in sdk_include_dirs)]
    blocks.append("target_include_directories(run_tests PRIVATE\n    " + "\n    ".join(include_dirs) + "\n)")
    if sdk_lib_dirs:
        blocks.append(
            "target_link_directories(run_tests PRIVATE\n    "
            + "\n    ".join(cmake_path(item) for item in sdk_lib_dirs)
            + "\n)"
        )

    link_libs = ["gtest_main", "gmock"]
    for pkg in pkg_config_packages:
        var = re.sub(r"[^A-Za-z0-9_]", "_", pkg).upper()
        link_libs.append(f"PkgConfig::{var}")
    for pkg in find_packages:
        name = str(pkg.get("name", "")).strip()
        target = str(pkg.get("target", name)).strip()
        if target:
            link_libs.append(target)
    link_libs.extend(link_libraries)
    blocks.append(f"target_link_libraries(run_tests PRIVATE {' '.join(link_libs)})")
    return "\n".join(blocks) + "\n"


def generate_cmake_content(
    project_name: str,
    test_file_names: list[str],
    sdk_include_dirs: list[str] | None = None,
    sdk_lib_dirs: list[str] | None = None,
    link_libraries: list[str] | None = None,
    cmake_prefix_path: list[str] | None = None,
    find_packages: list[dict] | None = None,
    pkg_config_packages: list[str] | None = None,
    extra_cmake_snippet: str = "",
    gtest_source: str = "cached",
    coverage: bool = False,
    coverage_tool: str = "gcov",
) -> str:
    file_list = "\n    ".join(test_file_names)
    gtest_block = gtest_cmake_block(gtest_source)
    cov_block = coverage_cmake_block(coverage, coverage_tool)
    sdk_block = sdk_link_cmake_block(
        sdk_include_dirs or [],
        sdk_lib_dirs or [],
        link_libraries or [],
        cmake_prefix_path or [],
        find_packages or [],
        pkg_config_packages or [],
        extra_cmake_snippet,
    )
    return f"""cmake_minimum_required(VERSION 3.14)
project({project_name} CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
{cov_block}
{gtest_block}
add_executable(run_tests
    {file_list}
)

{sdk_block}
"""


def discover_test_files(src_path: Path) -> list[Path]:
    discovered: list[Path] = []
    for pattern in ("*_test.cpp", "*Test.cpp", "*_test.cc", "*_test.cxx"):
        discovered.extend(sorted(src_path.glob(pattern)))
    return list(dict.fromkeys(discovered))


def find_test_binary(build_path: Path) -> Path | None:
    binary = build_path / "run_tests"
    exe_suffix = ".exe" if sys.platform == "win32" else ""
    candidates: list[Path] = []
    if exe_suffix:
        candidates.append(binary.with_suffix(exe_suffix))
    candidates.append(binary)
    for sub in ["Debug", "Release", "RelWithDebInfo", "x64/Debug", "x64/Release"]:
        candidates.append(build_path / sub / f"run_tests{exe_suffix}")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for f in build_path.rglob(f"run_tests{exe_suffix}" if exe_suffix else "run_tests"):
        if f.is_file():
            return f
    return None


def compile_tests_impl(
    source_dir: str,
    build_dir: str,
    sdk_include_dirs: list[str] | str | None = "",
    sdk_lib_dirs: list[str] | str | None = "",
    link_libraries: list[str] | str | None = "",
    cmake_prefix_path: list[str] | str | None = "",
    find_packages: list[dict] | str | None = "",
    pkg_config_packages: list[str] | str | None = "",
    extra_cmake_snippet: str = "",
    gtest_source: str = "cached",
    coverage: bool | str = False,
    coverage_tool: str = "gcov",
) -> dict:
    from sdk_forge.util import parse_bool

    src_path = Path(source_dir)
    build_path = Path(build_dir)
    if not src_path.is_dir():
        return {"error": f"Source directory not found: {source_dir}", "status": "error"}

    want_coverage = parse_bool(coverage, default=False)
    cmake_file = src_path / "CMakeLists.txt"
    if not cmake_file.exists():
        test_files = discover_test_files(src_path)
        if not test_files:
            return {"error": f"No test files found in {source_dir}", "status": "error"}
        project_name = src_path.name.replace("-", "_").replace(" ", "_")
        cmake_content = generate_cmake_content(
            project_name=project_name,
            test_file_names=[f.name for f in test_files],
            sdk_include_dirs=normalize_str_list(sdk_include_dirs),
            sdk_lib_dirs=normalize_str_list(sdk_lib_dirs),
            link_libraries=normalize_str_list(link_libraries),
            cmake_prefix_path=normalize_str_list(cmake_prefix_path),
            find_packages=[p for p in normalize_json_list(find_packages) if isinstance(p, dict)],
            pkg_config_packages=normalize_str_list(pkg_config_packages),
            extra_cmake_snippet=extra_cmake_snippet,
            gtest_source=gtest_source or "cached",
            coverage=want_coverage,
            coverage_tool=coverage_tool,
        )
        cmake_file.write_text(cmake_content, encoding="utf-8")

    build_path.mkdir(parents=True, exist_ok=True)
    compile_start = time.monotonic()
    try:
        result = run_subprocess(["cmake", str(src_path.resolve())], cwd=str(build_path.resolve()))
    except FileNotFoundError:
        return {"error": "cmake not found. Install CMake and ensure it's in PATH.", "status": "error"}
    except subprocess.TimeoutExpired:
        return {"error": "cmake configure timed out (600s).", "status": "error"}

    cmake_output = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return {
            "status": "cmake_error",
            "stage": "configure",
            "output": cmake_output,
            "hints": parse_cmake_error(cmake_output),
        }

    try:
        build_result = run_subprocess(["cmake", "--build", str(build_path.resolve())], cwd=str(build_path.resolve()))
    except subprocess.TimeoutExpired:
        return {"error": "cmake build timed out (600s).", "status": "error"}

    build_output = (build_result.stdout or "") + "\n" + (build_result.stderr or "")
    compile_duration_sec = round(time.monotonic() - compile_start, 2)
    if build_result.returncode != 0:
        combined = cmake_output + "\n" + build_output
        return {
            "status": "cmake_error",
            "stage": "build",
            "output": build_output,
            "hints": parse_cmake_error(combined),
            "compile_duration_sec": compile_duration_sec,
        }

    binary_path = find_test_binary(build_path)
    return {
        "status": "ok",
        "binary_path": str(binary_path) if binary_path else None,
        "gtest_cache_dir": str(gtest_cache_dir()),
        "coverage_enabled": want_coverage,
        "compile_duration_sec": compile_duration_sec,
        "build_output": build_output,
    }
