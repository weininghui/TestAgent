"""SDK probing and pkg-config parsing."""

from __future__ import annotations

import re
from pathlib import Path

_RE_PC_CFLAGS = re.compile(r"^Cflags:\s*(.+)$", re.MULTILINE)
_RE_PC_LIBS = re.compile(r"^Libs:\s*(.+)$", re.MULTILINE)
_RE_PC_LIBDIR = re.compile(r"^Libdir:\s*(.+)$", re.MULTILINE)


def parse_pkg_config(pc_path: Path) -> dict:
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


def probe_sdk_impl(sdk_root: str) -> dict:
    target = Path(sdk_root)
    if not target.exists():
        return {"error": f"Path not found: {sdk_root}", "status": "error"}

    if target.is_file() and target.suffix == ".pc":
        suggestion = parse_pkg_config(target)
        suggestion["status"] = "ok"
        suggestion["sdk_root"] = str(target.parent)
        return suggestion

    if not target.is_dir():
        return {"error": f"Not a directory: {sdk_root}", "status": "error"}

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
        parsed = parse_pkg_config(pc_files[0])
        include_dirs = list(dict.fromkeys(include_dirs + parsed["sdk_include_dirs"]))
        lib_dirs = list(dict.fromkeys(lib_dirs + parsed["sdk_lib_dirs"]))
        pkg_config_packages = parsed["pkg_config_packages"]

    link_libraries: list[str] = []
    if (target / "CMakeLists.txt").exists():
        link_libraries.append(target.name.replace("-", "_"))

    return {
        "status": "ok",
        "sdk_root": str(target.resolve()),
        "sdk_include_dirs": include_dirs,
        "sdk_lib_dirs": lib_dirs,
        "link_libraries": link_libraries,
        "pkg_config_packages": pkg_config_packages,
        "pkg_config_files": [str(p) for p in pc_files[:5]],
        "cmake_prefix_path": [str(target.resolve())],
    }
