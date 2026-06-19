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
    for key in ("extra_cmake_snippet", "gtest_source", "gtest_version", "coverage_tool", "find_packages"):
        if overrides.get(key) not in (None, "", []):
            merged[key] = overrides[key]
    if overrides.get("coverage") is not None:
        merged["coverage"] = overrides["coverage"]
    return merged
