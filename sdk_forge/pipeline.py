"""One-shot probe + compile + run pipeline."""

from __future__ import annotations

from pathlib import Path

from sdk_forge.build import compile_tests_impl
from sdk_forge.config import (
    compile_params_from_config,
    find_forge_config,
    load_forge_config,
    merge_compile_params,
    resolve_path,
)
from sdk_forge.probe import probe_sdk_impl
from sdk_forge.run import run_tests_impl
from sdk_forge.util import parse_bool


def build_pipeline_impl(
    project_dir: str = "",
    source_dir: str = "",
    build_dir: str = "",
    sdk_root: str = "",
    run_after_compile: bool | str = True,
) -> dict:
    should_run = parse_bool(run_after_compile, default=True)
    start = Path(project_dir or Path.cwd())
    config = load_forge_config(start=start)

    src = source_dir or resolve_path(config, "tests_dir") or str(start / "tests")
    bld = build_dir or resolve_path(config, "build_dir") or str(start / "build")
    sdk = sdk_root or resolve_path(config, "sdk_root")

    params = compile_params_from_config(config)
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

    compile_result = compile_tests_impl(
        src,
        bld,
        sdk_include_dirs=params.get("sdk_include_dirs", []),
        sdk_lib_dirs=params.get("sdk_lib_dirs", []),
        link_libraries=params.get("link_libraries", []),
        cmake_prefix_path=params.get("cmake_prefix_path", []),
        find_packages=params.get("find_packages", []),
        pkg_config_packages=params.get("pkg_config_packages", []),
        extra_cmake_snippet=params.get("extra_cmake_snippet", ""),
        gtest_source=params.get("gtest_source", "auto"),
        gtest_version=params.get("gtest_version", "auto"),
        coverage=params.get("coverage", False),
        coverage_tool=params.get("coverage_tool", "gcov"),
    )

    result = {
        "status": compile_result.get("status", "error"),
        "config_file": config.get("_config_path"),
        "source_dir": src,
        "build_dir": bld,
        "sdk_root": sdk or None,
        "compile": compile_result,
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

    return result
