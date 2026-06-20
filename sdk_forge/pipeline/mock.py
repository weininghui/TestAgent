"""Google Mock template generation from scan results."""

from __future__ import annotations

import json
import re


def _mock_method_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def generate_mocks_impl(scan_result: dict | str, class_name: str = "") -> dict:
    if isinstance(scan_result, str):
        try:
            scan_result = json.loads(scan_result)
        except json.JSONDecodeError as exc:
            return {"status": "error", "error": f"Invalid scan JSON: {exc}"}

    if scan_result.get("status") == "error":
        return scan_result

    mocks: list[dict] = []
    header_lines = [
        "#pragma once",
        "#include <gmock/gmock.h>",
        "",
    ]
    output_files: list[str] = []
    seen_classes: set[str] = set()

    for file_info in scan_result.get("files", []):
        file_classes = {c.get("name") for c in file_info.get("classes", []) if c.get("name")}
        for fn in file_info.get("functions", []):
            if not fn.get("virtual"):
                continue
            cls = class_name or _infer_class(fn, file_info, file_classes)
            if class_name and cls != class_name:
                continue
            if cls in seen_classes and class_name:
                pass
            seen_classes.add(cls)
            ret = fn.get("return_type") or "void"
            params = fn.get("params") or ""
            mock_cls = f"Mock{cls}"
            method = fn.get("name", "method")
            const_suffix = (
                " const" if fn.get("kind") == "method" and "const" in params.split(")")[-1] else ""
            )
            if fn.get("kind") == "method" and params.rstrip().endswith("const"):
                const_suffix = " const"
            param_types = _params_for_mock(params)
            ns = fn.get("namespace", "")
            ns_prefix = f"{ns}::" if ns else ""
            header_lines.extend(
                [
                    f"class {mock_cls} : public {ns_prefix}{cls} {{",
                    "public:",
                    f"    MOCK_METHOD({ret}, {method}, ({param_types}){const_suffix}, (override));",
                    "};",
                    "",
                ]
            )
            out_name = f"mock_{cls}.hpp"
            output_files.append(out_name)
            mocks.append(
                {
                    "class": cls,
                    "namespace": ns,
                    "mock_class": mock_cls,
                    "method": method,
                    "return_type": ret,
                    "params": params,
                    "file": file_info.get("file"),
                    "output_file": out_name,
                }
            )

    if not mocks:
        return {
            "status": "ok",
            "mock_count": 0,
            "header": "",
            "output_files": [],
            "message": "No virtual methods found in scan result.",
        }

    return {
        "status": "ok",
        "mock_count": len(mocks),
        "mocks": mocks,
        "header": "\n".join(header_lines),
        "output_files": list(dict.fromkeys(output_files)),
        "primary_output_file": output_files[0] if output_files else "",
    }


def _infer_class(fn: dict, file_info: dict, file_classes: set[str]) -> str:
    if fn.get("kind") == "method" and file_classes:
        for name in file_classes:
            if name:
                return name
    for cls in file_info.get("classes", []):
        if cls.get("kind") == "class":
            return cls.get("name", "Interface")
    ns = fn.get("namespace", "")
    return ns.split("::")[-1] if ns else "Interface"


def _params_for_mock(params: str) -> str:
    if not params.strip():
        return ""
    parts = []
    for p in params.split(","):
        p = p.strip()
        if not p:
            continue
        if p == "const":
            continue
        tokens = p.split()
        if len(tokens) >= 2:
            parts.append(" ".join(tokens[:-1]))
        else:
            parts.append(p)
    return ", ".join(parts)
