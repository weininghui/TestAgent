"""Header scanning with libclang, regex fallback, and scan cache."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdk_forge.cache import scan_cache_dir
from sdk_forge.util import cmake_path, parse_bool

logger = logging.getLogger("sdk_forge.scan")

try:
    import clang.cindex as clang
    from clang.cindex import CursorKind

    CLANG_AVAILABLE = True
except ImportError:
    clang = None  # type: ignore[assignment]
    CursorKind = None  # type: ignore[assignment,misc]
    CLANG_AVAILABLE = False

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
_RE_IF_DIRECTIVE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)$", re.MULTILINE)


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


def compute_if_depths(content: str) -> dict[int, int]:
    """Return 1-based line number -> #if nesting depth at that line."""
    depths: dict[int, int] = {}
    depth = 0
    for line_no, line in enumerate(content.splitlines(), start=1):
        m = _RE_IF_DIRECTIVE.match(line)
        if m:
            directive = m.group(1)
            if directive in ("if", "ifdef", "ifndef"):
                depth += 1
            elif directive == "endif":
                depth = max(0, depth - 1)
        depths[line_no] = depth
    return depths


def is_conditional_line(line: int, depths: dict[int, int]) -> bool:
    return depths.get(line, 0) > 0


def apply_conditional(symbols: list[dict], depths: dict[int, int]) -> None:
    for sym in symbols:
        sym["conditional"] = is_conditional_line(sym.get("line", 0), depths)


def build_compile_args(include_dirs: list[str], compile_args: list[str]) -> list[str]:
    args = ["-std=c++17", "-x", "c++"]
    for item in compile_args:
        if item.strip():
            args.append(item.strip())
    for item in include_dirs:
        args.append(f"-I{cmake_path(item)}")
    return args


def cursor_namespace(cursor: Any) -> str:
    parts: list[str] = []
    current = cursor.semantic_parent
    while current is not None:
        if CursorKind is not None and current.kind == CursorKind.NAMESPACE:
            parts.append(current.spelling)
        current = current.semantic_parent
    return "::".join(reversed(parts))


def parse_header(content: str, filepath: str) -> HeaderFileInfo:
    info = HeaderFileInfo(
        path=filepath,
        filename=Path(filepath).name,
        raw_line_count=len(content.splitlines()),
        parser="regex",
    )
    depths = compute_if_depths(content)
    info.includes = [m.group(1) for m in _RE_INCLUDE.finditer(content)]
    for m in _RE_FUNCTION.finditer(content):
        name = m.group("name")
        if name.startswith("_") or name in ("if", "else", "for", "while", "switch", "return"):
            continue
        line = content[: m.start("name")].count("\n") + 1
        info.functions.append({
            "name": name,
            "return_type": m.group("return_type").strip(),
            "params": m.group("params").strip(),
            "line": line,
            "kind": "function",
            "conditional": is_conditional_line(line, depths),
        })
    for m in _RE_CLASS.finditer(content):
        line = content[: m.start()].count("\n") + 1
        info.classes.append({
            "name": m.group(2),
            "kind": m.group(1),
            "line": line,
            "conditional": is_conditional_line(line, depths),
        })
    for m in _RE_ENUM.finditer(content):
        line = content[: m.start()].count("\n") + 1
        info.enums.append({
            "name": m.group(1),
            "line": line,
            "conditional": is_conditional_line(line, depths),
        })
    for m in _RE_TYPEDEF.finditer(content):
        line = content[: m.start()].count("\n") + 1
        if m.group(1) is not None and m.group(2) is not None:
            type_str, alias = m.group(1).strip(), m.group(2).strip()
        else:
            alias, type_str = m.group(3).strip(), m.group(4).strip()
        info.typedefs.append({
            "type": type_str,
            "alias": alias,
            "line": line,
            "conditional": is_conditional_line(line, depths),
        })
    return info


def parse_header_clang(filepath: str, compile_args: list[str]) -> HeaderFileInfo | None:
    if not CLANG_AVAILABLE or clang is None or CursorKind is None:
        return None
    try:
        content = Path(filepath).read_text(encoding="utf-8", errors="replace")
    except OSError:
        content = ""
    depths = compute_if_depths(content)
    try:
        index = clang.Index.create()
        tu = index.parse(filepath, args=compile_args)
        if not tu:
            return None
        info = HeaderFileInfo(path=filepath, filename=Path(filepath).name, parser="libclang")
        info.raw_line_count = len(content.splitlines())
        namespaces: set[str] = set()

        def walk(cursor: Any) -> None:
            if cursor.location.file and str(cursor.location.file) != str(Path(filepath).resolve()):
                return
            ns = cursor_namespace(cursor)
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
                    "conditional": is_conditional_line(line, depths),
                })
            elif kind in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL, CursorKind.CLASS_TEMPLATE):
                info.classes.append({
                    "name": cursor.spelling,
                    "kind": "class" if kind != CursorKind.STRUCT_DECL else "struct",
                    "line": line,
                    "namespace": ns,
                    "conditional": is_conditional_line(line, depths),
                })
            elif kind == CursorKind.ENUM_DECL:
                info.enums.append({
                    "name": cursor.spelling,
                    "line": line,
                    "namespace": ns,
                    "conditional": is_conditional_line(line, depths),
                })
            for child in cursor.get_children():
                walk(child)

        walk(tu.cursor)
        info.namespaces = sorted(namespaces)
        return info
    except Exception as exc:
        logger.warning("libclang parse failed for %s: %s", filepath, exc)
        return None


def header_to_summary(info: HeaderFileInfo) -> dict:
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


def collect_header_files(sdk_path: Path) -> list[Path]:
    headers: list[Path] = []
    for pattern in ("*.h", "*.hpp"):
        headers.extend(sdk_path.rglob(pattern))
    return sorted(set(headers))


def scan_cache_key(
    sdk_root: str,
    headers: list[Path],
    include_dirs: list[str],
    compile_args: list[str],
) -> str:
    parts = [str(Path(sdk_root).resolve()), *include_dirs, *compile_args]
    for h in headers:
        try:
            stat = h.stat()
            parts.append(f"{h}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            parts.append(str(h))
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return digest


def load_scan_cache(cache_key: str) -> dict | None:
    cache_file = scan_cache_dir() / f"{cache_key}.json"
    if not cache_file.exists():
        return None
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_scan_cache(cache_key: str, result: dict) -> None:
    cache_file = scan_cache_dir() / f"{cache_key}.json"
    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def scan_headers_impl(
    sdk_root: str,
    include_dirs: list[str] | str | None = "",
    compile_args: list[str] | str | None = "",
    use_clang: bool | str = True,
    use_cache: bool | str = True,
) -> dict:
    from sdk_forge.util import normalize_str_list

    sdk_path = Path(sdk_root)
    if not sdk_path.is_dir():
        return {"error": f"SDK root directory not found: {sdk_root}", "status": "error"}

    include_list = normalize_str_list(include_dirs)
    compile_list = normalize_str_list(compile_args)
    clang_args = build_compile_args(include_list, compile_list)
    want_clang = parse_bool(use_clang, default=True)
    want_cache = parse_bool(use_cache, default=True)

    headers = collect_header_files(sdk_path)
    cache_key = scan_cache_key(sdk_root, headers, include_list, compile_list)

    if want_cache:
        cached = load_scan_cache(cache_key)
        if cached is not None:
            cached["cached"] = True
            cached["cache_key"] = cache_key
            return cached

    header_files: list[HeaderFileInfo] = []
    parsers_used: set[str] = set()

    for h_file in headers:
        info: HeaderFileInfo | None = None
        if want_clang:
            info = parse_header_clang(str(h_file.resolve()), clang_args)
        if info is None:
            try:
                content = h_file.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                logger.warning("Cannot read %s: %s", h_file, exc)
                continue
            info = parse_header(content, str(h_file))
        header_files.append(info)
        parsers_used.add(info.parser)

    summaries = [header_to_summary(hf) for hf in header_files]
    result = {
        "status": "ok",
        "sdk_root": sdk_root,
        "parser": "+".join(sorted(parsers_used)) if parsers_used else "regex",
        "libclang_available": CLANG_AVAILABLE,
        "cached": False,
        "cache_key": cache_key,
        "total_files": len(header_files),
        "total_functions": sum(len(hf.functions) for hf in header_files),
        "total_classes": sum(len(hf.classes) for hf in header_files),
        "total_enums": sum(len(hf.enums) for hf in header_files),
        "files": summaries,
    }
    if want_cache:
        save_scan_cache(cache_key, result)
    return result
