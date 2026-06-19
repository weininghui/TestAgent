"""Structured test plan generation from scan results."""

from __future__ import annotations

import json
import re
from typing import Any

from sdk_forge.scan import scan_headers_impl

_NOISE_SYMBOL = re.compile(
    r"^(_)?(YAML_CPP_API|API|EXPORT|IMPORT|DLL|DEPRECATED|nodiscard|fallthrough)$",
    re.IGNORECASE,
)
_MACRO_LIKE = re.compile(r"^[A-Z][A-Z0-9_]*(_API|_EXPORT|_H)$")


def _is_noise_symbol(name: str, kind: str = "function") -> bool:
    if not name or len(name) < 2:
        return True
    if _NOISE_SYMBOL.match(name):
        return True
    if _MACRO_LIKE.match(name):
        return True
    if kind == "class" and name.isupper() and len(name) > 4:
        return True
    if name.startswith("__"):
        return True
    return False


def _target_priority(target: dict[str, Any]) -> tuple[int, str]:
    """Lower sort key = higher priority."""
    kind_rank = 0 if target.get("kind") == "function" else 1
    conditional_rank = 1 if target.get("conditional") else 0
    mock_rank = 1 if target.get("needs_mock") else 0
    return (kind_rank, conditional_rank, mock_rank, str(target.get("symbol", "")).lower())

def _has_pointer(params: str) -> bool:
    return "*" in (params or "")


def _function_scenarios(fn: dict[str, Any]) -> list[dict[str, str]]:
    params = fn.get("params") or ""
    scenarios = [
        {"name": "normal", "description": "typical valid inputs", "priority": "high"},
        {"name": "boundary", "description": "edge values (0, max, empty)", "priority": "medium"},
    ]
    if _has_pointer(params):
        scenarios.append({"name": "error", "description": "null pointer / invalid buffer", "priority": "high"})
    else:
        scenarios.append({"name": "error", "description": "invalid input / error return path", "priority": "low"})
    return scenarios


def _class_scenarios(cls: dict[str, Any], file_info: dict[str, Any]) -> list[dict[str, str]]:
    virtual_methods = [
        fn for fn in file_info.get("functions", [])
        if fn.get("virtual") and fn.get("class") == cls.get("name")
    ]
    scenarios = [
        {"name": "construction", "description": "default or parameterized construction", "priority": "high"},
        {"name": "methods", "description": "exercise public methods", "priority": "high"},
    ]
    if virtual_methods:
        scenarios.append({"name": "mock", "description": "use GMock for virtual methods", "priority": "high"})
    return scenarios


def suggest_test_plan_impl(
    sdk_root: str = "",
    scan_json: str | dict[str, Any] | None = None,
    include_dirs: list[str] | str | None = None,
    max_targets: int | str = 0,
) -> dict[str, Any]:
    from sdk_forge.util import parse_bool

    try:
        limit = int(max_targets) if str(max_targets).strip() not in ("", "0", "none") else 0
    except (TypeError, ValueError):
        limit = 0

    if scan_json:
        if isinstance(scan_json, str):
            try:
                scan_data = json.loads(scan_json)
            except json.JSONDecodeError as exc:
                return {"status": "error", "error": f"Invalid scan JSON: {exc}"}
        else:
            scan_data = scan_json
    elif sdk_root:
        scan_data = scan_headers_impl(sdk_root, include_dirs=include_dirs or [])
    else:
        return {"status": "error", "error": "Provide sdk_root or scan_json"}

    if scan_data.get("status") == "error":
        return scan_data

    targets: list[dict[str, Any]] = []
    summary = {"functions": 0, "classes": 0, "virtual": 0, "conditional": 0, "filtered": 0}
    for file_info in scan_data.get("files", []):
        filename = file_info.get("file", "")
        for fn in file_info.get("functions", []):
            if fn.get("kind") == "method":
                continue
            symbol = fn.get("name", "")
            if _is_noise_symbol(symbol, "function"):
                summary["filtered"] += 1
                continue
            conditional = bool(fn.get("conditional"))
            if conditional:
                summary["conditional"] += 1
            targets.append({
                "symbol": fn.get("name", ""),
                "kind": "function",
                "file": filename,
                "return_type": fn.get("return_type", ""),
                "params": fn.get("params", ""),
                "scenarios": _function_scenarios(fn),
                "conditional": conditional,
                "needs_mock": False,
                "suggested_compile_args": ["-DFEATURE_ENABLED"] if conditional else [],
            })
            summary["functions"] += 1

        class_methods: dict[str, list] = {}
        virtual_in_file = [fn for fn in file_info.get("functions", []) if fn.get("virtual")]
        class_names = [cls.get("name") for cls in file_info.get("classes", []) if cls.get("name")]

        for cls in file_info.get("classes", []):
            name = cls.get("name", "")
            if _is_noise_symbol(name, "class"):
                summary["filtered"] += 1
                continue
            if len(class_names) == 1 and virtual_in_file:
                methods = virtual_in_file
                has_virtual = True
            else:
                methods = [fn for fn in virtual_in_file if name.lower() in (fn.get("name") or "").lower()]
                has_virtual = bool(methods) or bool(virtual_in_file and len(class_names) == 1)
            conditional = bool(cls.get("conditional"))
            if has_virtual:
                summary["virtual"] += 1
            if conditional:
                summary["conditional"] += 1
            targets.append({
                "symbol": name,
                "kind": cls.get("kind", "class"),
                "file": filename,
                "methods": [m.get("name") for m in methods if m.get("name")],
                "scenarios": _class_scenarios(cls, file_info),
                "conditional": conditional,
                "needs_mock": has_virtual,
                "suggested_compile_args": ["-DFEATURE_ENABLED"] if conditional else [],
            })
            summary["classes"] += 1

    total_before_limit = len(targets)
    if limit > 0 and len(targets) > limit:
        targets = sorted(targets, key=_target_priority)[:limit]

    return {
        "status": "ok",
        "sdk_root": scan_data.get("sdk_root") or sdk_root or None,
        "targets": targets,
        "summary": summary,
        "target_count": len(targets),
        "total_candidates": total_before_limit,
        "max_targets": limit if limit > 0 else None,
    }