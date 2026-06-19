"""CMake error parsing and actionable hints."""

from __future__ import annotations

import re


def parse_cmake_error(output: str) -> list[str]:
    hints: list[str] = []
    text = output or ""
    lower = text.lower()

    if "undefined reference" in lower or "unresolved external symbol" in lower:
        hints.append("Link error: add missing library via --link or pkg_config_packages.")
        m = re.search(r"undefined reference to [`']?(\w+)", text)
        if m:
            hints.append(f"Missing symbol '{m.group(1)}' — verify link_libraries includes the SDK lib name.")

    if "cannot find -l" in lower or "cannot open file" in lower and ".lib" in lower:
        hints.append("Library not found: set sdk_lib_dirs to the directory containing the .a/.lib file.")
        m = re.search(r"cannot find -l(\S+)", text)
        if m:
            hints.append(f"Add --link {m.group(1)} and --lib-dir pointing to the built SDK.")

    if "no such file or directory" in lower and (".h" in lower or "include" in lower):
        hints.append("Header not found: add sdk_include_dirs with the SDK header root.")
        m = re.search(r"([^\s:]+\.h(pp)?): No such file", text)
        if m:
            hints.append(f"Missing header '{m.group(1)}' — run probe_sdk and pass --include paths.")

    if "could not find" in lower and "find_package" in lower:
        hints.append("find_package failed: set cmake_prefix_path to the SDK install prefix.")
        hints.append("Alternatively use pkg_config_packages if a .pc file is available.")

    if "pkg_check_modules" in lower or "package '" in lower and "not found" in lower:
        hints.append("pkg-config package not found: install the dev package or set PKG_CONFIG_PATH.")

    if "cmake was unable to find a build program" in lower or "no cmake_cxx_compiler" in lower:
        hints.append("No C++ compiler detected: install g++/MSVC Build Tools and ensure cmake is in PATH.")

    if not hints:
        hints.append("Review the CMake output above; run probe_sdk on the SDK root for suggested paths.")

    return list(dict.fromkeys(hints))
