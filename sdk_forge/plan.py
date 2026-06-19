"""Structured test plan generation from scan results.
从扫描结果生成结构化测试计划。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sdk_forge.codegen import classify_type, parse_params
from sdk_forge.scan import scan_headers_impl

_NOISE_SYMBOL = re.compile(
    r"^(_)?(YAML_CPP_API|API|EXPORT|IMPORT|DLL|DEPRECATED|nodiscard|fallthrough)$",
    re.IGNORECASE,
)
_MACRO_LIKE = re.compile(r"^[A-Z][A-Z0-9_]*(_API|_EXPORT|_H)$")
_RE_ENUM_BODY = re.compile(r"enum\s+(?:class\s+)?(\w+)\s*\{([^}]+)\}", re.DOTALL)
_RE_NAMESPACE = re.compile(r"namespace\s+(\w+)\s*\{")


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
    kind_rank = {"function": 0, "enum": 1, "class": 2, "struct": 2}.get(target.get("kind", "function"), 3)
    conditional_rank = 1 if target.get("conditional") else 0
    mock_rank = 1 if target.get("needs_mock") else 0
    return (kind_rank, conditional_rank, mock_rank, str(target.get("symbol", "")).lower())


def _has_pointer(params: str) -> bool:
    return "*" in (params or "")


def _read_header_text(sdk_root: str, filename: str) -> str:
    if not sdk_root or not filename:
        return ""
    path = Path(sdk_root) / filename
    if not path.is_file():
        alt = Path(sdk_root) / Path(filename).name
        if alt.is_file():
            path = alt
        else:
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _extract_namespace(text: str) -> str:
    m = _RE_NAMESPACE.search(text)
    return m.group(1) if m else ""


def _extract_enum_members(text: str, enum_name: str) -> list[dict[str, str]]:
    for m in _RE_ENUM_BODY.finditer(text):
        if m.group(1) != enum_name:
            continue
        body = m.group(2)
        members = []
        for part in body.split(","):
            part = part.strip()
            if not part or part.startswith("//"):
                continue
            name = re.sub(r"=\s*\d+.*", "", part).strip()
            if name and re.match(r"^\w+$", name):
                members.append({"name": name})
        return members
    return []


def _find_parser_for_enum(functions: list[dict], enum_name: str) -> str:
    for fn in functions:
        ret = (fn.get("return_type") or "")
        if enum_name in ret and "string" in (fn.get("params") or "").lower():
            return fn.get("name", "")
    for fn in functions:
        name = (fn.get("name") or "").lower()
        if "parse" in name and enum_name.lower() in (fn.get("return_type") or "").lower():
            return fn.get("name", "")
    return ""


def _function_scenarios(fn: dict[str, Any]) -> list[dict[str, Any]]:
    params = fn.get("params") or ""
    parsed = parse_params(params)
    scenarios: list[dict[str, Any]] = [
        {"name": "normal", "description": "typical valid inputs", "priority": "high"},
        {"name": "boundary", "description": "edge values (0, max, empty)", "priority": "medium"},
    ]
    if parsed and classify_type(parsed[0].type_name) == "int":
        scenarios.append({"name": "overflow", "description": "integer overflow edge", "priority": "low"})
    if parsed and classify_type(parsed[0].type_name) == "string":
        scenarios.append({"name": "empty_input", "description": "empty string input", "priority": "medium"})
    if _has_pointer(params):
        scenarios.append({"name": "error", "description": "null pointer / invalid buffer", "priority": "high"})
    else:
        scenarios.append({"name": "error", "description": "invalid input / error return path", "priority": "low"})
    return scenarios


def _class_scenarios(cls: dict[str, Any], file_info: dict[str, Any]) -> list[dict[str, Any]]:
    virtual_methods = [
        fn for fn in file_info.get("functions", [])
        if fn.get("virtual") and fn.get("class") == cls.get("name")
    ]
    scenarios: list[dict[str, Any]] = [
        {"name": "construction", "description": "default or parameterized construction", "priority": "high"},
        {"name": "methods", "description": "exercise public methods", "priority": "high"},
        {"name": "copy_move", "description": "copy/move semantics", "priority": "low"},
        {"name": "destructor", "description": "RAII teardown", "priority": "low"},
        {
            "name": "lifecycle",
            "description": "init → operate → verify → teardown",
            "priority": "medium",
            "lifecycle": ["init", "operate", "verify", "teardown"],
        },
    ]
    if virtual_methods:
        scenarios.append({"name": "mock", "description": "use GMock for virtual methods", "priority": "high"})
    return scenarios


def _enum_scenarios() -> list[dict[str, Any]]:
    return [
        {"name": "normal", "description": "parse/map to primary enum member", "priority": "high"},
        {"name": "boundary", "description": "alternate enum member", "priority": "medium"},
    ]


def _should_use_test_p(fn: dict[str, Any]) -> bool:
    parsed = parse_params(fn.get("params") or "")
    if len(parsed) != 1:
        return False
    return classify_type(parsed[0].type_name) in ("int", "string")


def suggest_test_plan_impl(
    sdk_root: str = "",
    scan_json: str | dict[str, Any] | None = None,
    include_dirs: list[str] | str | None = None,
    max_targets: int | str = 0,
) -> dict[str, Any]:
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

    root = scan_data.get("sdk_root") or sdk_root or ""
    targets: list[dict[str, Any]] = []
    summary = {
        "functions": 0, "classes": 0, "enums": 0, "virtual": 0,
        "conditional": 0, "filtered": 0, "parameterized": 0,
    }

    for file_info in scan_data.get("files", []):
        filename = file_info.get("file", "")
        header_text = _read_header_text(root, filename)
        namespace = _extract_namespace(header_text)
        functions = file_info.get("functions", [])

        for fn in functions:
            if fn.get("kind") == "method":
                continue
            symbol = fn.get("name", "")
            if _is_noise_symbol(symbol, "function"):
                summary["filtered"] += 1
                continue
            conditional = bool(fn.get("conditional"))
            if conditional:
                summary["conditional"] += 1
            use_tp = _should_use_test_p(fn)
            if use_tp:
                summary["parameterized"] += 1
            targets.append({
                "symbol": symbol,
                "kind": "function",
                "file": filename,
                "return_type": fn.get("return_type", ""),
                "params": fn.get("params", ""),
                "namespace": namespace,
                "scenarios": _function_scenarios(fn),
                "conditional": conditional,
                "needs_mock": False,
                "use_test_p": use_tp,
                "suggested_compile_args": ["-DFEATURE_ENABLED"] if conditional else [],
            })
            summary["functions"] += 1

        virtual_in_file = [fn for fn in functions if fn.get("virtual")]
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
                "namespace": namespace,
                "methods": [m.get("name") for m in methods if m.get("name")],
                "scenarios": _class_scenarios(cls, file_info),
                "conditional": conditional,
                "needs_mock": has_virtual,
                "suggested_compile_args": ["-DFEATURE_ENABLED"] if conditional else [],
            })
            summary["classes"] += 1

        for enum_info in file_info.get("enums", []):
            enum_name = enum_info.get("name", "")
            if _is_noise_symbol(enum_name, "function"):
                continue
            members = _extract_enum_members(header_text, enum_name)
            parser = _find_parser_for_enum(functions, enum_name)
            targets.append({
                "symbol": enum_name,
                "kind": "enum",
                "file": filename,
                "namespace": namespace,
                "enum_members": members,
                "parser_function": parser,
                "scenarios": _enum_scenarios(),
                "conditional": bool(enum_info.get("conditional")),
                "needs_mock": False,
            })
            summary["enums"] += 1

        for td in file_info.get("typedefs", []):
            alias = td.get("alias", "")
            type_str = td.get("type", "")
            if "(*)" in type_str or "(*" in type_str:
                if _is_noise_symbol(alias, "function"):
                    continue
                targets.append({
                    "symbol": alias,
                    "kind": "typedef",
                    "file": filename,
                    "namespace": namespace,
                    "typedef_type": type_str,
                    "scenarios": [{"name": "normal", "description": "function pointer smoke", "priority": "low"}],
                    "conditional": bool(td.get("conditional")),
                    "needs_mock": False,
                })

    total_before_limit = len(targets)
    if limit > 0 and len(targets) > limit:
        targets = sorted(targets, key=_target_priority)[:limit]

    return {
        "status": "ok",
        "sdk_root": root or None,
        "targets": targets,
        "summary": summary,
        "target_count": len(targets),
        "total_candidates": total_before_limit,
        "max_targets": limit if limit > 0 else None,
    }
