"""CMake generation and test compilation."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from sdk_forge.infra.cache import gtest_cache_dir
from sdk_forge.infra.compdb import export_compile_commands_impl
from sdk_forge.domain.errors import parse_cmake_error
from sdk_forge.domain.hint_actions import parse_cmake_error_with_actions
from sdk_forge.infra.gtest import ensure_gtest, gtest_source_path, normalize_gtest_source, resolve_gtest_tag
from sdk_forge.domain.util import cmake_path, normalize_json_list, normalize_str_list, run_subprocess


def gtest_cmake_block(gtest_source: str, gtest_tag: str = "v1.14.0", local_path: str = "") -> str:
    source = normalize_gtest_source(gtest_source)
    if source == "system":
        return """
find_package(GTest REQUIRED)
"""
    msvc_crt = """
if(MSVC)
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
endif()
"""
    local = local_path or str(gtest_source_path(gtest_tag))
    local_cmake = Path(local) / "CMakeLists.txt"
    if local_cmake.exists():
        cmake_local = cmake_path(local)
        return f"""{msvc_crt}
set(FORGE_GTEST_SOURCE_DIR "{cmake_local}")
add_subdirectory(${{FORGE_GTEST_SOURCE_DIR}} ${{CMAKE_BINARY_DIR}}/googletest EXCLUDE_FROM_ALL)
"""

    cache_dir = cmake_path(str(gtest_cache_dir()))
    update_disconnected = "TRUE" if source == "cached" else "FALSE"
    return f"""{msvc_crt}
include(FetchContent)
set(FETCHCONTENT_BASE_DIR "{cache_dir}")
set(FETCHCONTENT_UPDATES_DISCONNECTED {update_disconnected})
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG {gtest_tag}
    GIT_SHALLOW TRUE
)
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


def sanitizer_cmake_block(sanitizer: str) -> tuple[str, list[str]]:
    mode = (sanitizer or "none").strip().lower()
    hints: list[str] = []
    if mode in ("", "none", "off", "false"):
        return "", hints
    if sys.platform == "win32":
        hints.append("Sanitizers are not supported with MSVC on Windows — use Linux/clang or GCC")
        return "", hints
    flags = ""
    if mode in ("asan", "address"):
        flags = "address"
    elif mode in ("ubsan", "undefined"):
        flags = "undefined"
    elif mode in ("asan+ubsan", "address+undefined", "all"):
        flags = "address,undefined"
    else:
        hints.append(f"Unknown sanitizer '{sanitizer}' — use asan, ubsan, or asan+ubsan")
        return "", hints
    block = f"""
set(CMAKE_CXX_FLAGS "${{CMAKE_CXX_FLAGS}} -fsanitize={flags}")
set(CMAKE_C_FLAGS "${{CMAKE_C_FLAGS}} -fsanitize={flags}")
set(CMAKE_EXE_LINKER_FLAGS "${{CMAKE_EXE_LINKER_FLAGS}} -fsanitize={flags}")
"""
    return block, hints


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
    gtest_source: str = "auto",
    gtest_version: str = "auto",
    coverage: bool = False,
    coverage_tool: str = "gcov",
    sanitizer: str = "none",
) -> str:
    file_list = "\n    ".join(test_file_names)
    tag = resolve_gtest_tag(gtest_version)
    gtest_block = gtest_cmake_block(gtest_source, tag)
    cov_block = coverage_cmake_block(coverage, coverage_tool)
    san_block, _ = sanitizer_cmake_block(sanitizer)
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
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
{cov_block}{san_block}
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
    gtest_source: str = "auto",
    gtest_version: str = "auto",
    coverage: bool | str = False,
    coverage_tool: str = "gcov",
    sanitizer: str = "none",
    use_config: bool | str = True,
    probe_context: dict | None = None,
    force_regenerate_cmake: bool | str = False,
) -> dict:
    from sdk_forge.infra.config import compile_params_from_config, load_forge_config, merge_compile_params
    from sdk_forge.domain.util import parse_bool

    want_config = parse_bool(use_config, default=True)
    overrides = {
        "sdk_include_dirs": sdk_include_dirs,
        "sdk_lib_dirs": sdk_lib_dirs,
        "link_libraries": link_libraries,
        "cmake_prefix_path": cmake_prefix_path,
        "find_packages": find_packages,
        "pkg_config_packages": pkg_config_packages,
        "extra_cmake_snippet": extra_cmake_snippet,
        "gtest_source": gtest_source,
        "gtest_version": gtest_version,
        "coverage": coverage,
        "coverage_tool": coverage_tool,
        "sanitizer": sanitizer,
    }
    if want_config:
        config = load_forge_config(start=source_dir)
        params = merge_compile_params(compile_params_from_config(config), overrides)
    else:
        params = merge_compile_params({}, overrides)

    src_path = Path(source_dir)
    build_path = Path(build_dir)
    if not src_path.is_dir():
        return {"error": f"Source directory not found: {source_dir}", "status": "error"}

    want_coverage = parse_bool(params.get("coverage"), default=False)
    sanitizer_mode = str(params.get("sanitizer") or "none")
    _, sanitizer_hints = sanitizer_cmake_block(sanitizer_mode)
    force_cmake = parse_bool(force_regenerate_cmake, default=False)
    gtest_mode = normalize_gtest_source(str(params.get("gtest_source") or "auto"))
    gtest_tag = resolve_gtest_tag(str(params.get("gtest_version") or "auto"))
    gtest_fetch: dict = {"status": "skipped", "tag": gtest_tag}

    if gtest_mode != "system":
        force_fetch = gtest_mode == "fetch"
        gtest_fetch = ensure_gtest(gtest_tag, force=force_fetch)
        if gtest_fetch.get("status") == "error":
            if force_fetch:
                return {
                    "status": "error",
                    "error": gtest_fetch.get("error", "Failed to download googletest"),
                    "gtest": gtest_fetch,
                    "hints": [
                        "Check network and git access to github.com/google/googletest",
                        f"Pin gtest_version in .forge.yaml (resolved tag: {gtest_tag})",
                    ],
                }
            gtest_fetch = {
                "status": "ok",
                "tag": gtest_tag,
                "path": str(gtest_source_path(gtest_tag)),
                "downloaded": False,
                "method": "cmake_fetch",
                "hint": gtest_fetch.get("error", "git prefetch failed; CMake FetchContent will retry"),
            }

    cmake_file = src_path / "CMakeLists.txt"
    if force_cmake and cmake_file.exists():
        cmake_file.unlink(missing_ok=True)

    if not cmake_file.exists():
        test_files = discover_test_files(src_path)
        if not test_files:
            return {"error": f"No test files found in {source_dir}", "status": "error"}
        project_name = src_path.name.replace("-", "_").replace(" ", "_")
        cmake_content = generate_cmake_content(
            project_name=project_name,
            test_file_names=[f.name for f in test_files],
            sdk_include_dirs=normalize_str_list(params.get("sdk_include_dirs")),
            sdk_lib_dirs=normalize_str_list(params.get("sdk_lib_dirs")),
            link_libraries=normalize_str_list(params.get("link_libraries")),
            cmake_prefix_path=normalize_str_list(params.get("cmake_prefix_path")),
            find_packages=[p for p in normalize_json_list(params.get("find_packages")) if isinstance(p, dict)],
            pkg_config_packages=normalize_str_list(params.get("pkg_config_packages")),
            extra_cmake_snippet=str(params.get("extra_cmake_snippet", "") or ""),
            gtest_source=gtest_mode,
            gtest_version=gtest_tag,
            coverage=want_coverage,
            coverage_tool=str(params.get("coverage_tool", "gcov") or "gcov"),
            sanitizer=sanitizer_mode,
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
        parsed = parse_cmake_error_with_actions(cmake_output, probe_context)
        return {
            "status": "cmake_error",
            "stage": "configure",
            "output": cmake_output,
            "hints": parsed["hints"],
            "actions": parsed["actions"],
        }

    try:
        build_result = run_subprocess(["cmake", "--build", str(build_path.resolve())], cwd=str(build_path.resolve()))
    except subprocess.TimeoutExpired:
        return {"error": "cmake build timed out (600s).", "status": "error"}

    build_output = (build_result.stdout or "") + "\n" + (build_result.stderr or "")
    compile_duration_sec = round(time.monotonic() - compile_start, 2)
    if build_result.returncode != 0:
        combined = cmake_output + "\n" + build_output
        parsed = parse_cmake_error_with_actions(combined, probe_context)
        return {
            "status": "cmake_error",
            "stage": "build",
            "output": build_output,
            "hints": parsed["hints"],
            "actions": parsed["actions"],
            "compile_duration_sec": compile_duration_sec,
        }

    binary_path = find_test_binary(build_path)
    config = load_forge_config(start=source_dir) if want_config else {}
    project_dir = config.get("_config_dir", str(src_path.parent))

    compdb_result = export_compile_commands_impl(str(build_path), project_dir)
    result = {
        "status": "ok",
        "binary_path": str(binary_path) if binary_path else None,
        "gtest_cache_dir": str(gtest_cache_dir()),
        "gtest_tag": gtest_tag,
        "gtest_source": gtest_mode,
        "gtest": gtest_fetch,
        "coverage_enabled": want_coverage,
        "sanitizer": sanitizer_mode,
        "sanitizer_hints": sanitizer_hints,
        "compile_duration_sec": compile_duration_sec,
        "config_file": config.get("_config_path") if want_config else None,
        "build_output": build_output,
    }
    if compdb_result.get("status") == "ok":
        result["compile_commands"] = compdb_result.get("path")
    return result
