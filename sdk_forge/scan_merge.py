"""Merge parallel scan batches into a single plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sdk_forge.plan import suggest_test_plan_impl
from sdk_forge.scan import header_to_summary
from sdk_forge.session import save_plan_state
from sdk_forge.workflow import clear_scan_batches, get_scan_batches, update_workflow_stage


def _merge_scan_dicts(batches: list[dict[str, Any]], sdk_root: str) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    parsers: set[str] = set()
    for batch in batches:
        for item in batch.get("files") or []:
            files.append(item)
        parser = str(batch.get("parser") or "")
        if parser:
            parsers.update(parser.split("+"))

    return {
        "status": "ok",
        "sdk_root": sdk_root,
        "parser": "+".join(sorted(parsers)) if parsers else "regex",
        "libclang_available": any(b.get("libclang_available") for b in batches),
        "cached": False,
        "header_count": len(files),
        "total_files": len(files),
        "total_functions": sum(len(f.get("functions") or []) for f in files),
        "total_classes": sum(len(f.get("classes") or []) for f in files),
        "total_enums": sum(len(f.get("enums") or []) for f in files),
        "files": files,
        "merged_from_batches": len(batches),
    }


def merge_scan_batches_impl(
    project_dir: str,
    sdk_root: str = "",
    max_targets: int | str = 0,
) -> dict[str, Any]:
    """Merge stored scan batches, suggest plan, and save last_plan.json."""
    root = Path(project_dir or Path.cwd()).resolve()
    batches_map = get_scan_batches(str(root))
    if not batches_map:
        return {"status": "error", "error": "No scan batches to merge"}

    ordered = [batches_map[k] for k in sorted(batches_map, key=lambda x: int(x))]
    sdk = sdk_root or (ordered[0].get("sdk_root") if ordered else "")
    if not sdk:
        return {"status": "error", "error": "sdk_root required for merge"}

    merged = _merge_scan_dicts(ordered, sdk)
    plan = suggest_test_plan_impl(scan_json=merged, sdk_root=sdk, max_targets=max_targets)
    if plan.get("status") != "ok":
        return {"status": "error", "error": plan.get("error", "plan failed"), "scan": merged}

    save_plan_state(str(root), plan)
    update_workflow_stage(str(root), "plan", {"merged_scan_batches": len(ordered)})
    clear_scan_batches(str(root))
    return {
        "status": "ok",
        "plan": plan,
        "scan": merged,
        "merged_batches": len(ordered),
        "target_count": len(plan.get("targets") or []),
    }


def scan_headers_subset_impl(
    sdk_root: str,
    header_files: list[str],
    include_dirs: list[str] | str | None = "",
    compile_args: list[str] | str | None = "",
    use_clang: bool | str = True,
    use_cache: bool | str = False,
) -> dict[str, Any]:
    """Scan only the listed header basenames under sdk_root."""
    from sdk_forge.scan import (
        CLANG_AVAILABLE,
        HeaderFileInfo,
        build_compile_args,
        collect_header_files,
        parse_header,
        parse_header_clang,
    )
    from sdk_forge.util import normalize_str_list, parse_bool

    sdk_path = Path(sdk_root)
    if not sdk_path.is_dir():
        return {"status": "error", "error": f"SDK root not found: {sdk_root}"}

    want = {str(h).replace("\\", "/").split("/")[-1] for h in header_files}
    all_headers = collect_header_files(sdk_path)
    headers = [h for h in all_headers if h.name in want]
    if not headers:
        return {"status": "error", "error": f"No matching headers in batch: {sorted(want)}"}

    include_list = normalize_str_list(include_dirs)
    compile_list = normalize_str_list(compile_args)
    clang_args = build_compile_args(include_list, compile_list)
    want_clang = parse_bool(use_clang, default=True)

    header_infos: list[HeaderFileInfo] = []
    parsers_used: set[str] = set()
    for h_file in headers:
        info: HeaderFileInfo | None = None
        if want_clang:
            info = parse_header_clang(str(h_file.resolve()), clang_args)
        if info is None:
            try:
                content = h_file.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return {"status": "error", "error": str(exc)}
            info = parse_header(content, str(h_file))
        header_infos.append(info)
        parsers_used.add(info.parser)

    summaries = [header_to_summary(hf) for hf in header_infos]
    return {
        "status": "ok",
        "sdk_root": sdk_root,
        "parser": "+".join(sorted(parsers_used)) if parsers_used else "regex",
        "libclang_available": CLANG_AVAILABLE,
        "cached": False,
        "header_count": len(headers),
        "total_files": len(header_infos),
        "total_functions": sum(len(hf.functions) for hf in header_infos),
        "total_classes": sum(len(hf.classes) for hf in header_infos),
        "total_enums": sum(len(hf.enums) for hf in header_infos),
        "files": summaries,
        "batch_header_files": sorted(want),
    }
