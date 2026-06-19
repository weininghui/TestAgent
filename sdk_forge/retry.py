"""Build pipeline with automatic retry and hint-based config fixes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdk_forge.build import compile_tests_impl
from sdk_forge.config import (
    apply_actions_to_params,
    compile_params_from_config,
    load_forge_config,
    merge_compile_params,
    resolve_path,
    save_forge_config,
)
from sdk_forge.learn import learn_from_build, merge_learned_into_params
from sdk_forge.probe import probe_sdk_impl
from sdk_forge.run import run_tests_impl
from sdk_forge.util import parse_bool


def _params_to_compile_kwargs(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "sdk_include_dirs": params.get("sdk_include_dirs", []),
        "sdk_lib_dirs": params.get("sdk_lib_dirs", []),
        "link_libraries": params.get("link_libraries", []),
        "cmake_prefix_path": params.get("cmake_prefix_path", []),
        "find_packages": params.get("find_packages", []),
        "pkg_config_packages": params.get("pkg_config_packages", []),
        "extra_cmake_snippet": params.get("extra_cmake_snippet", ""),
        "gtest_source": params.get("gtest_source", "auto"),
        "gtest_version": params.get("gtest_version", "auto"),
        "coverage": params.get("coverage", False),
        "coverage_tool": params.get("coverage_tool", "gcov"),
    }


def _sync_params_to_config(config: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    updated = dict(config)
    for key in (
        "sdk_include_dirs", "sdk_lib_dirs", "link_libraries",
        "cmake_prefix_path", "pkg_config_packages", "find_packages",
        "extra_cmake_snippet", "gtest_source", "gtest_version",
        "coverage", "coverage_tool",
    ):
        if key in params:
            updated[key] = params[key]
    return updated


def build_with_retry_impl(
    project_dir: str = "",
    source_dir: str = "",
    build_dir: str = "",
    sdk_root: str = "",
    run_after_compile: bool | str = True,
    max_retries: int | str = 3,
    auto_fix_config: bool | str = False,
) -> dict[str, Any]:
    should_run = parse_bool(run_after_compile, default=True)
    fix_config = parse_bool(auto_fix_config, default=False)
    try:
        retries = max(1, int(max_retries))
    except (TypeError, ValueError):
        retries = 3

    start = Path(project_dir or Path.cwd())
    config = load_forge_config(start=start)
    src = source_dir or resolve_path(config, "tests_dir") or str(start / "tests")
    bld = build_dir or resolve_path(config, "build_dir") or str(start / "build")
    sdk = sdk_root or resolve_path(config, "sdk_root")

    params = compile_params_from_config(config)
    probe: dict[str, Any] = {}
    if sdk:
        probe = probe_sdk_impl(sdk)
        if probe.get("status") == "ok":
            params = merge_compile_params(params, {
                "sdk_include_dirs": probe.get("sdk_include_dirs", []),
                "sdk_lib_dirs": probe.get("sdk_lib_dirs", []),
                "link_libraries": probe.get("link_libraries", []),
                "cmake_prefix_path": probe.get("cmake_prefix_path", []),
                "pkg_config_packages": probe.get("pkg_config_packages", []),
            })

    if sdk:
        params = merge_learned_into_params(params, sdk, str(start))

    attempts: list[dict[str, Any]] = []
    compile_result: dict[str, Any] = {}
    auto_fixed = False

    for attempt in range(1, retries + 1):
        force_regen = attempt > 1
        compile_result = compile_tests_impl(
            src,
            bld,
            use_config=False,
            probe_context=probe if probe.get("status") == "ok" else None,
            force_regenerate_cmake=force_regen,
            **_params_to_compile_kwargs(params),
        )
        attempt_record = {
            "attempt": attempt,
            "result": compile_result.get("status", "error"),
            "stage": compile_result.get("stage"),
            "actions_applied": [],
        }

        if compile_result.get("status") == "ok":
            attempts.append(attempt_record)
            break

        actions = compile_result.get("actions") or []
        attempt_record["actions_available"] = actions
        attempts.append(attempt_record)

        if not actions or attempt >= retries:
            break

        params = apply_actions_to_params(params, actions)
        attempt_record["actions_applied"] = actions
        auto_fixed = True
        config = _sync_params_to_config(config, params)
        if fix_config:
            save_forge_config(config)

    result: dict[str, Any] = {
        "status": compile_result.get("status", "error"),
        "config_file": config.get("_config_path"),
        "source_dir": src,
        "build_dir": bld,
        "sdk_root": sdk or None,
        "compile": compile_result,
        "attempts": attempts,
        "auto_fixed": auto_fixed,
        "retries_used": len(attempts),
        "sdk_include_dirs": params.get("sdk_include_dirs", []),
        "sdk_lib_dirs": params.get("sdk_lib_dirs", []),
        "link_libraries": params.get("link_libraries", []),
        "cmake_prefix_path": params.get("cmake_prefix_path", []),
        "pkg_config_packages": params.get("pkg_config_packages", []),
    }

    if compile_result.get("status") != "ok":
        return result

    if should_run:
        run_result = run_tests_impl(bld)
        result["run"] = run_result
        result["status"] = run_result.get("status", "error")
        result["total"] = run_result.get("total", 0)
        result["passed"] = run_result.get("passed", 0)
        result["failed"] = run_result.get("failed", 0)

    if result.get("status") == "ok" and sdk:
        result["learned"] = learn_from_build(result, str(start))

    return result


def save_build_state(project_dir: str, state: dict[str, Any]) -> Path:
    root = Path(project_dir or Path.cwd())
    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "last_build.json"
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_build_state(project_dir: str) -> dict[str, Any]:
    path = Path(project_dir or Path.cwd()) / ".forge" / "cache" / "last_build.json"
    if not path.exists():
        return {"status": "error", "error": "No previous build state found"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}
