#!/usr/bin/env python3
"""MCP server — file-operation tools for SDK Test Forge Agent (v2.5)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

try:
    import clang.cindex as clang
    from clang.cindex import CursorKind

    _CLANG_AVAILABLE = True
except ImportError:
    clang = None  # type: ignore[assignment]
    CursorKind = None  # type: ignore[assignment,misc]
    _CLANG_AVAILABLE = False

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
  - scan_headers     → parse .h/.hpp (libclang with regex fallback)
  - probe_sdk        → suggest include/lib/pkg-config settings
  - delete_tests     → remove existing GTest files
  - compile_tests    → CMake build with SDK linking and GTest cache
  - run_tests        → execute compiled test binary
""",
)

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
    r"^\s*(?:typedef\s+(.+?)\s+(\w+)|using\s+(\w+)\s*=\s*(.+?))\s*;",
    re.MULTILINE,
)
_RE_PC_CFLAGS = re.compile(r"^Cflags:\s*(.+)$", re.MULTILINE)
_RE_PC_LIBS = re.compile(r"^Libs:\s*(.+)$", re.MULTILINE)
_RE_PC_LIBDIR = re.compile(r"^Libdir:\s*(.+)$", re.MULTILINE)


@dataclass
class HeaderFileInfo:
    path: str
    filename: str
    includes: list[str] = field(default_factory=list)
    functions: list[dict] = field(default_factory=list)
    classes: list[dict] = field(default_factory=list)
    enums: list[dict] = field(default_factory=list)
    typedefs: list[dict] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    raw_line_count: int = 0
    parser: str = "regex"


def _parse_bool(value: bool | str | None, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    stripped = str(value).strip().lower()
    if stripped in ("", "true", "1", "yes", "on"):
        return True
    if stripped in ("false", "0", "no", "off"):
        return False
    return default


def _normalize_str_list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            return [stripped]
        return []
    return [str(item) for item in value if str(item).strip()]


def _normalize_json_list(value: list[Any] | str | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            return []
        return []
    return list(value)


def _cmake_path(path: str) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def _gtest_cache_dir() -> Path:
    env = os.environ.get("FORGE_GTEST_CACHE")
    if env:
        cache = Path(env)
    elif sys.platform == "win32":
        cache = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "sdk-test-forge" / "gtest"
    else:
        cache = Path.home() / ".cache" / "sdk-test-forge" / "gtest"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _build_compile_args(include_dirs: list[str], compile_args: list[str]) -> list[str]:
    args = ["-std=c++17", "-x", "c++"]
    for item in compile_args:
        if item.strip():
            args.append(item.strip())
    for item in include_dirs:
        args.append(f"-I{_cmake_path(item)}")
    return args


def _cursor_namespace(cursor: Any) -> str:
    parts: list[str] = []
    current = cursor.semantic_parent
    while current is not None:
        if CursorKind is not None and current.kind == CursorKind.NAMESPACE:
            parts.append(current.spelling)
        current = current.semantic_parent
    return "::".join(reversed(parts))


def _parse_header(content: str, filepath: str) -> HeaderFileInfo:
    info = HeaderFileInfo(path=filepath, filename=Path(filepath).name, raw_line_count=len(content.splitlines()), parser="regex")
    info.includes = [m.group(1) for m in _RE_INCLUDE.finditer(content)]
    for m in _RE_FUNCTION.finditer(content):
        name = m.group("name")
        if name.startswith("_") or name in ("if", "else", "for", "while", "switch", "return"):
            continue
        info.functions.append({
            "name": name,
            "return_type": m.group("return_type").strip(),
            "params": m.group("params").strip(),
            "line": content[: m.start("name")].count("\n") + 1,
            "kind": "function",
        })
    for m in _RE_CLASS.finditer(content):
        info.classes.append({"name": m.group(2), "kind": m.group(1), "line": content[: m.start()].count("\n") + 1})
    for m in _RE_ENUM.finditer(content):
        info.enums.append({"name": m.group(1), "line": content[: m.start()].count("\n") + 1})
    for m in _RE_TYPEDEF.finditer(content):
        if m.group(1) is not None and m.group(2) is not None:
            type_str, alias = m.group(1).strip(), m.group(2).strip()
        else:
            alias, type_str = m.group(3).strip(), m.group(4).strip()
        info.typedefs.append({"type": type_str, "alias": alias, "line": content[: m.start()].count("\n") + 1})
    return info


def _parse_header_clang(filepath: str, compile_args: list[str]) -> HeaderFileInfo | None:
    if not _CLANG_AVAILABLE or clang is None or CursorKind is None:
        return None
    try:
        index = clang.Index.create()
        tu = index.parse(filepath, args=compile_args)
        if not tu:
            return None
        info = HeaderFileInfo(path=filepath, filename=Path(filepath).name, parser="libclang")
        try:
            info.raw_line_count = len(Path(filepath).read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            info.raw_line_count = 0
        namespaces: set[str] = set()

        def walk(cursor: Any) -> None:
            if cursor.location.file and str(cursor.location.file) != str(Path(filepath).resolve()):
                return
            ns = _cursor_namespace(cursor)
            if ns:
                namespaces.add(ns)
            kind = cursor.kind
            line = cursor.location.line
            if kind in (CursorKind.FUNCTION_DECL, CursorKind.CXX_METHOD):
                is_static = False
                is_virtual = False
                try:
                    is_static = cursor.is_static_method()
                except Exception:
                    pass
                try:
                    is_virtual = cursor.is_virtual_method()
                except Exception:
                    pass
                fn_kind = "method" if kind == CursorKind.CXX_METHOD else "function"
                info.functions.append({
                    "name": cursor.spelling,
                    "return_type": cursor.result_type.spelling if cursor.result_type else "",
                    "params": ", ".join(
                        f"{c.type.spelling} {c.spelling}".strip() for c in cursor.get_arguments()
                    ),
                    "line": line,
                    "namespace": ns,
                    "static": is_static,
                    "virtual": is_virtual,
                    "kind": fn_kind,
                })
            elif kind in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL, CursorKind.CLASS_TEMPLATE):
                info.classes.append({
                    "name": cursor.spelling,
                    "kind": "class" if kind != CursorKind.STRUCT_DECL else "struct",
                    "line": line,
                    "namespace": ns,
                })
            elif kind == CursorKind.ENUM_DECL:
                info.enums.append({"name": cursor.spelling, "line": line, "namespace": ns})
            for child in cursor.get_children():
                walk(child)

        walk(tu.cursor)
        info.namespaces = sorted(namespaces)
        return info
    except Exception as exc:
        logger.warning("libclang parse failed for %s: %s", filepath, exc)
        return None


def _header_to_summary(info: HeaderFileInfo) -> dict:
    return {
        "file": info.filename,
        "path": info.path,
        "parser": info.parser,
        "lines": info.raw_line_count,
        "includes": info.includes,
        "namespaces": info.namespaces,
        "functions": info.functions,
        "classes": info.classes,
        "enums": info.enums,
        "typedefs": info.typedefs,
    }


def _gtest_cmake_block(gtest_source: str) -> str:
    source = (gtest_source or "cached").lower()
    if source == "system":
        return """
find_package(GTest REQUIRED)
"""
    cache_dir = _cmake_path(str(_gtest_cache_dir()))
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


def _sdk_link_cmake_block(
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
        prefix = ";".join(_cmake_path(item) for item in cmake_prefix_path)
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

    include_dirs = ["${CMAKE_CURRENT_SOURCE_DIR}", *(_cmake_path(item) for item in sdk_include_dirs)]
    blocks.append("target_include_directories(run_tests PRIVATE\n    " + "\n    ".join(include_dirs) + "\n)")
    if sdk_lib_dirs:
        blocks.append(
            "target_link_directories(run_tests PRIVATE\n    "
            + "\n    ".join(_cmake_path(item) for item in sdk_lib_dirs)
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


def _generate_cmake_content(
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
) -> str:
    file_list = "\n    ".join(test_file_names)
    gtest_block = _gtest_cmake_block(gtest_source)
    sdk_block = _sdk_link_cmake_block(
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

{gtest_block}
add_executable(run_tests
    {file_list}
)

{sdk_block}
"""


def _discover_test_files(src_path: Path) -> list[Path]:
    discovered: list[Path] = []
    for pattern in ("*_test.cpp", "*Test.cpp", "*_test.cc", "*_test.cxx"):
        discovered.extend(sorted(src_path.glob(pattern)))
    return list(dict.fromkeys(discovered))


def _collect_header_files(sdk_path: Path) -> list[Path]:
    headers: list[Path] = []
    for pattern in ("*.h", "*.hpp"):
        headers.extend(sdk_path.rglob(pattern))
    return sorted(set(headers))


def _parse_pkg_config(pc_path: Path) -> dict:
    text = pc_path.read_text(encoding="utf-8", errors="replace")
    cflags = " ".join(_RE_PC_CFLAGS.findall(text))
    libs = " ".join(_RE_PC_LIBS.findall(text))
    libdirs = " ".join(_RE_PC_LIBDIR.findall(text))
    include_dirs = [item[2:] for item in cflags.split() if item.startswith("-I")]
    lib_dirs = [item[2:] for item in libs.split() if item.startswith("-L")]
    if libdirs and not lib_dirs:
        lib_dirs = [libdirs]
    link_libraries = [item[2:] for item in libs.split() if item.startswith("-l")]
    return {
        "pkg_config_file": str(pc_path),
        "pkg_config_packages": [pc_path.stem],
        "sdk_include_dirs": include_dirs,
        "sdk_lib_dirs": lib_dirs,
        "link_libraries": link_libraries,
    }


def _run_subprocess(cmd: list[str], cwd: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


@mcp.tool(description="Scan .h/.hpp headers using libclang when available, with regex fallback.")
async def scan_headers(
    sdk_root: Annotated[str, "Absolute path to the SDK root directory."],
    include_dirs: Annotated[list[str] | str, "Optional include dirs for libclang (-I)."] = "",
    compile_args: Annotated[list[str] | str, "Optional extra compile args for libclang."] = "",
    use_clang: Annotated[bool | str, "Use libclang when available (default true)."] = True,
) -> str:
    sdk_path = Path(sdk_root)
    if not sdk_path.is_dir():
        return json.dumps({"error": f"SDK root directory not found: {sdk_root}", "status": "error"}, indent=2)

    include_list = _normalize_str_list(include_dirs)
    compile_list = _normalize_str_list(compile_args)
    clang_args = _build_compile_args(include_list, compile_list)
    want_clang = _parse_bool(use_clang, default=True)

    header_files: list[HeaderFileInfo] = []
    parsers_used: set[str] = set()

    for h_file in _collect_header_files(sdk_path):
        info: HeaderFileInfo | None = None
        if want_clang:
            info = _parse_header_clang(str(h_file.resolve()), clang_args)
        if info is None:
            try:
                content = h_file.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                logger.warning("Cannot read %s: %s", h_file, exc)
                continue
            info = _parse_header(content, str(h_file))
        header_files.append(info)
        parsers_used.add(info.parser)

    summaries = [_header_to_summary(hf) for hf in header_files]
    result = {
        "status": "ok",
        "sdk_root": sdk_root,
        "parser": "+".join(sorted(parsers_used)) if parsers_used else "regex",
        "libclang_available": _CLANG_AVAILABLE,
        "total_files": len(header_files),
        "total_functions": sum(len(hf.functions) for hf in header_files),
        "total_classes": sum(len(hf.classes) for hf in header_files),
        "total_enums": sum(len(hf.enums) for hf in header_files),
        "files": summaries,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Probe an SDK root or .pc file and suggest compile_tests parameters.")
async def probe_sdk(
    sdk_root: Annotated[str, "SDK root directory or path to a .pc file."],
) -> str:
    target = Path(sdk_root)
    if not target.exists():
        return json.dumps({"error": f"Path not found: {sdk_root}", "status": "error"}, indent=2)

    if target.is_file() and target.suffix == ".pc":
        suggestion = _parse_pkg_config(target)
        suggestion["status"] = "ok"
        suggestion["sdk_root"] = str(target.parent)
        return json.dumps(suggestion, indent=2, ensure_ascii=False)

    if not target.is_dir():
        return json.dumps({"error": f"Not a directory: {sdk_root}", "status": "error"}, indent=2)

    include_dirs: list[str] = []
    lib_dirs: list[str] = []
    for name in ("include", "inc", "public", "headers"):
        candidate = target / name
        if candidate.is_dir():
            include_dirs.append(str(candidate.resolve()))
    for name in ("lib", "libs", "build", "out"):
        candidate = target / name
        if candidate.is_dir():
            lib_dirs.append(str(candidate.resolve()))

    pc_files = sorted(target.rglob("*.pc"))
    pkg_config_packages: list[str] = []
    if pc_files:
        parsed = _parse_pkg_config(pc_files[0])
        include_dirs = list(dict.fromkeys(include_dirs + parsed["sdk_include_dirs"]))
        lib_dirs = list(dict.fromkeys(lib_dirs + parsed["sdk_lib_dirs"]))
        pkg_config_packages = parsed["pkg_config_packages"]

    link_libraries: list[str] = []
    if (target / "CMakeLists.txt").exists():
        link_libraries.append(target.name.replace("-", "_"))

    result = {
        "status": "ok",
        "sdk_root": str(target.resolve()),
        "sdk_include_dirs": include_dirs,
        "sdk_lib_dirs": lib_dirs,
        "link_libraries": link_libraries,
        "pkg_config_packages": pkg_config_packages,
        "pkg_config_files": [str(p) for p in pc_files[:5]],
        "cmake_prefix_path": [str(target.resolve())],
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Delete existing GTest files recursively.")
async def delete_tests(test_dir: Annotated[str, "Directory to scan for existing test files."]) -> str:
    test_path = Path(test_dir)
    if not test_path.is_dir():
        return json.dumps({"error": f"Directory not found: {test_dir}", "status": "error"}, indent=2)

    patterns = [
        "*_test.cpp", "*_test.cc", "*_test.cxx", "test_*.cpp", "test_*.cc",
        "*_unittest.cpp", "*_unittest.cc", "*_tests.cpp", "*_tests.cc", "*Test.cpp", "*Test.cc",
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
    return json.dumps({"status": "ok", "directory": test_dir, "deleted_count": len(deleted), "deleted_files": deleted}, indent=2, ensure_ascii=False)


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
) -> str:
    src_path = Path(source_dir)
    build_path = Path(build_dir)
    if not src_path.is_dir():
        return json.dumps({"error": f"Source directory not found: {source_dir}", "status": "error"}, indent=2)

    cmake_file = src_path / "CMakeLists.txt"
    if not cmake_file.exists():
        test_files = _discover_test_files(src_path)
        if not test_files:
            return json.dumps({"error": f"No test files found in {source_dir}", "status": "error"}, indent=2)
        project_name = src_path.name.replace("-", "_").replace(" ", "_")
        cmake_content = _generate_cmake_content(
            project_name=project_name,
            test_file_names=[f.name for f in test_files],
            sdk_include_dirs=_normalize_str_list(sdk_include_dirs),
            sdk_lib_dirs=_normalize_str_list(sdk_lib_dirs),
            link_libraries=_normalize_str_list(link_libraries),
            cmake_prefix_path=_normalize_str_list(cmake_prefix_path),
            find_packages=[p for p in _normalize_json_list(find_packages) if isinstance(p, dict)],
            pkg_config_packages=_normalize_str_list(pkg_config_packages),
            extra_cmake_snippet=extra_cmake_snippet,
            gtest_source=gtest_source or "cached",
        )
        cmake_file.write_text(cmake_content, encoding="utf-8")

    build_path.mkdir(parents=True, exist_ok=True)
    try:
        result = _run_subprocess(["cmake", str(src_path.resolve())], cwd=str(build_path.resolve()))
    except FileNotFoundError:
        return json.dumps({"error": "cmake not found. Install CMake and ensure it's in PATH.", "status": "error"}, indent=2)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "cmake configure timed out (600s).", "status": "error"}, indent=2)

    cmake_output = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return json.dumps({"status": "cmake_error", "stage": "configure", "output": cmake_output}, indent=2, ensure_ascii=False)

    try:
        build_result = _run_subprocess(["cmake", "--build", str(build_path.resolve())], cwd=str(build_path.resolve()))
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "cmake build timed out (600s).", "status": "error"}, indent=2)

    build_output = (build_result.stdout or "") + "\n" + (build_result.stderr or "")
    if build_result.returncode != 0:
        return json.dumps({"status": "cmake_error", "stage": "build", "output": build_output}, indent=2, ensure_ascii=False)

    binary_path = build_path / "run_tests"
    exe_suffix = ".exe" if sys.platform == "win32" else ""
    if exe_suffix and binary_path.with_suffix(exe_suffix).exists():
        binary_path = binary_path.with_suffix(exe_suffix)
    elif not binary_path.exists():
        for sub in ["Debug", "Release", "RelWithDebInfo"]:
            candidate = build_path / sub / f"run_tests{exe_suffix}"
            if candidate.exists():
                binary_path = candidate
                break

    return json.dumps({
        "status": "ok",
        "binary_path": str(binary_path) if binary_path.exists() else None,
        "gtest_cache_dir": str(_gtest_cache_dir()),
        "build_output": build_output,
    }, indent=2, ensure_ascii=False)


@mcp.tool(description="Run a compiled GTest binary and return structured results.")
async def run_tests(
    build_dir: Annotated[str, "Build directory containing run_tests binary."],
    test_filter: Annotated[str, "Optional GTest filter pattern."] = "",
) -> str:
    build_path = Path(build_dir)
    binary = build_path / "run_tests"
    exe_suffix = ".exe" if sys.platform == "win32" else ""
    if exe_suffix and binary.with_suffix(exe_suffix).exists():
        binary = binary.with_suffix(exe_suffix)
    elif not binary.exists():
        for sub in ["Debug", "Release", "RelWithDebInfo"]:
            candidate = build_path / sub / f"run_tests{exe_suffix}"
            if candidate.exists():
                binary = candidate
                break
        if not binary.exists():
            for f in build_path.rglob(f"run_*{exe_suffix}" if exe_suffix else "run_*"):
                if f.is_file() and (not exe_suffix or f.suffix == ".exe"):
                    binary = f
                    break

    if not binary.exists():
        return json.dumps({"error": f"Test binary not found in {build_dir}. Run compile_tests first.", "status": "error"}, indent=2)

    cmd = [str(binary)]
    if test_filter:
        cmd.extend(["--gtest_filter", test_filter])

    try:
        result = _run_subprocess(cmd)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Test execution timed out (600s).", "status": "error"}, indent=2)

    full_output = (result.stdout or "") + "\n" + (result.stderr or "")
    passed = failed = skipped = total = 0
    failed_tests: list[str] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
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
    m_total = re.search(r"\[==========\] Running (\d+) tests", result.stdout or "")
    total = int(m_total.group(1)) if m_total else passed + failed + skipped

    return json.dumps({
        "status": "ok" if result.returncode == 0 else "test_failures",
        "return_code": result.returncode,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failed_tests": failed_tests,
        "output": full_output,
    }, indent=2, ensure_ascii=False)


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


if __name__ == "__main__":
    main()
