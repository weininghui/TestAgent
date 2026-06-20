"""Map CMake errors to machine-executable config fix actions."""

from __future__ import annotations

import re
from typing import Any

from sdk_forge.domain.errors import parse_cmake_error

ACTION_TYPES = frozenset({
    "merge_link_libraries",
    "merge_sdk_include_dirs",
    "merge_sdk_lib_dirs",
    "merge_cmake_prefix_path",
    "merge_pkg_config_packages",
})


def _action(action_type: str, values: list[str], reason: str = "") -> dict[str, Any]:
    return {"type": action_type, "values": values, "reason": reason}


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    result: list[dict[str, Any]] = []
    for action in actions:
        key = (action["type"], tuple(action.get("values") or []))
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return result


def _guess_lib_from_symbol(symbol: str, probe: dict[str, Any] | None) -> list[str]:
    if probe:
        libs = probe.get("link_libraries") or []
        if libs:
            return list(libs)
    prefix = symbol.split("_", 1)[0] if "_" in symbol else symbol
    return [prefix] if prefix else []


def parse_cmake_error_with_actions(
    output: str,
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return hints plus structured actions an agent or retry loop can apply."""
    hints = parse_cmake_error(output)
    actions: list[dict[str, Any]] = []
    text = output or ""
    lower = text.lower()
    probe = probe or {}

    if "undefined reference" in lower or "unresolved external symbol" in lower:
        m = re.search(r"undefined reference to [`']?(\w+)", text)
        symbol = m.group(1) if m else ""
        libs = _guess_lib_from_symbol(symbol, probe)
        if libs:
            actions.append(_action(
                "merge_link_libraries", libs,
                f"Link library for symbol '{symbol}'" if symbol else "Add SDK link library",
            ))
        probe_libs = probe.get("link_libraries") or []
        for lib in probe_libs:
            actions.append(_action("merge_link_libraries", [lib], "From probe_sdk suggestion"))

    if "cannot find -l" in lower:
        m = re.search(r"cannot find -l(\S+)", text)
        if m:
            lib = m.group(1)
            actions.append(_action("merge_link_libraries", [lib], f"Missing library -l{lib}"))
        probe_lib_dirs = probe.get("sdk_lib_dirs") or []
        if probe_lib_dirs:
            actions.append(_action("merge_sdk_lib_dirs", list(probe_lib_dirs), "From probe_sdk"))

    if "cannot open file" in lower and ".lib" in lower:
        probe_lib_dirs = probe.get("sdk_lib_dirs") or []
        if probe_lib_dirs:
            actions.append(_action("merge_sdk_lib_dirs", list(probe_lib_dirs), "SDK .lib path"))

    if "no such file or directory" in lower and (".h" in lower or "include" in lower):
        m = re.search(r"([^\s:]+)\.h(pp)?: No such file", text)
        header = f"{m.group(1)}.h{m.group(2) or ''}" if m else ""
        probe_includes = probe.get("sdk_include_dirs") or []
        if probe_includes:
            actions.append(_action(
                "merge_sdk_include_dirs", list(probe_includes),
                f"Include path for '{header}'" if header else "From probe_sdk",
            ))

    if "could not find" in lower and "find_package" in lower:
        prefix = probe.get("cmake_prefix_path") or []
        if prefix:
            actions.append(_action("merge_cmake_prefix_path", list(prefix), "find_package prefix"))

    if "pkg_check_modules" in lower or ("package '" in lower and "not found" in lower):
        pkgs = probe.get("pkg_config_packages") or []
        if pkgs:
            actions.append(_action("merge_pkg_config_packages", list(pkgs), "pkg-config package"))

    if not actions and probe.get("status") == "ok":
        for key, action_type in (
            ("sdk_include_dirs", "merge_sdk_include_dirs"),
            ("sdk_lib_dirs", "merge_sdk_lib_dirs"),
            ("link_libraries", "merge_link_libraries"),
            ("cmake_prefix_path", "merge_cmake_prefix_path"),
            ("pkg_config_packages", "merge_pkg_config_packages"),
        ):
            values = probe.get(key) or []
            if values:
                actions.append(_action(action_type, list(values), "Fallback probe_sdk merge"))

    return {
        "hints": hints,
        "actions": _dedupe_actions(actions),
    }
