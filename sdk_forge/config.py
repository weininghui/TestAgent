"""Load .forge.yaml / .forge.json project configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FORGE_CONFIG_NAMES = (".forge.yaml", ".forge.yml", ".forge.json")


def find_forge_config(start: str | Path) -> Path | None:
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        for name in FORGE_CONFIG_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
        if directory.parent == directory:
            break
    return None


def _parse_yaml(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML required for .forge.yaml — pip install pyyaml or use .forge.json"
        ) from exc
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def load_forge_config(path: str | Path | None = None, start: str | Path | None = None) -> dict[str, Any]:
    config_path: Path | None
    if path:
        config_path = Path(path)
    elif start:
        config_path = find_forge_config(start)
    else:
        config_path = find_forge_config(Path.cwd())

    if not config_path or not config_path.exists():
        return {}

    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix == ".json":
        data = json.loads(text)
    else:
        data = _parse_yaml(text)

    if not isinstance(data, dict):
        return {}

    result = dict(data)
    result["_config_path"] = str(config_path.resolve())
    result["_config_dir"] = str(config_path.parent.resolve())
    return result


def resolve_config_lists(config: dict[str, Any], key: str) -> list[str]:
    value = config.get(key, [])
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value if str(item).strip()]


def resolve_path(config: dict[str, Any], key: str, default: str = "") -> str:
    base = Path(config.get("_config_dir", Path.cwd()))
    raw = str(config.get(key, default) or default).strip()
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        path = (base / path).resolve()
    return str(path)


def compile_params_from_config(config: dict[str, Any]) -> dict[str, Any]:
    if not config:
        return {}
    return {
        "sdk_include_dirs": resolve_config_lists(config, "sdk_include_dirs"),
        "sdk_lib_dirs": resolve_config_lists(config, "sdk_lib_dirs"),
        "link_libraries": resolve_config_lists(config, "link_libraries"),
        "cmake_prefix_path": resolve_config_lists(config, "cmake_prefix_path"),
        "pkg_config_packages": resolve_config_lists(config, "pkg_config_packages"),
        "find_packages": config.get("find_packages") or [],
        "extra_cmake_snippet": str(config.get("extra_cmake_snippet", "") or ""),
        "gtest_source": str(config.get("gtest_source", "auto") or "auto"),
        "gtest_version": str(config.get("gtest_version", "auto") or "auto"),
        "coverage": bool(config.get("coverage", False)),
        "coverage_tool": str(config.get("coverage_tool", "gcov") or "gcov"),
        "sanitizer": str(config.get("sanitizer", "none") or "none"),
    }


def merge_compile_params(config_params: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(config_params)
    list_keys = (
        "sdk_include_dirs", "sdk_lib_dirs", "link_libraries",
        "cmake_prefix_path", "pkg_config_packages",
    )
    for key in list_keys:
        base = list(merged.get(key) or [])
        extra = overrides.get(key)
        if extra is None:
            continue
        if isinstance(extra, str):
            from sdk_forge.util import normalize_str_list
            extra_list = normalize_str_list(extra)
        else:
            extra_list = list(extra)
        merged[key] = list(dict.fromkeys([*base, *extra_list]))
    for key in ("extra_cmake_snippet", "gtest_source", "gtest_version", "coverage_tool", "sanitizer", "find_packages"):
        if overrides.get(key) not in (None, "", []):
            merged[key] = overrides[key]
    if overrides.get("coverage") is not None:
        merged["coverage"] = overrides["coverage"]
    return merged


_ACTION_TO_PARAM = {
    "merge_link_libraries": "link_libraries",
    "merge_sdk_include_dirs": "sdk_include_dirs",
    "merge_sdk_lib_dirs": "sdk_lib_dirs",
    "merge_cmake_prefix_path": "cmake_prefix_path",
    "merge_pkg_config_packages": "pkg_config_packages",
}


def apply_actions_to_params(
    params: dict[str, Any],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply hint_actions to compile params (returns new dict)."""
    overrides: dict[str, Any] = {}
    for action in actions:
        action_type = str(action.get("type", ""))
        param_key = _ACTION_TO_PARAM.get(action_type)
        if not param_key:
            continue
        values = action.get("values") or []
        if not values:
            continue
        existing = overrides.get(param_key, params.get(param_key, []))
        overrides[param_key] = list(dict.fromkeys([*list(existing or []), *[str(v) for v in values]]))
    return merge_compile_params(params, overrides)


def save_forge_config(config: dict[str, Any]) -> dict[str, Any]:
    """Write compile-related keys back to the config file."""
    config_path = config.get("_config_path")
    if not config_path:
        return {"status": "error", "error": "No _config_path in config — cannot save"}

    path = Path(config_path)
    keys_to_save = (
        "sdk_root", "tests_dir", "build_dir",
        "sdk_include_dirs", "sdk_lib_dirs", "link_libraries",
        "cmake_prefix_path", "pkg_config_packages", "find_packages",
        "extra_cmake_snippet", "gtest_source", "gtest_version",
        "coverage", "coverage_tool", "sanitizer",
        "scaffold_quality_gate", "max_placeholder_ratio", "quality_gate_mode", "auto_report",
        "multi_agent_batch_size", "forge_profile", "autopilot_profile",
        "max_enrich_rounds", "auto_golden_snapshot", "max_agent_retries",
        "scan_batch_size", "auto_oracle_draft",
        "delegation_mode", "delegation_concurrency",
        "min_assertion_score", "block_weak_tests", "block_agent_markers",
        "assertion_quality_gate", "coverage_gate", "min_line_coverage_pct",
    )
    payload = {k: config[k] for k in keys_to_save if k in config}

    if path.suffix == ".json":
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            return {"status": "error", "error": "PyYAML required to save .forge.yaml"}
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    return {"status": "ok", "config_file": str(path.resolve())}
