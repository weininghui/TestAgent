"""Command-line interface for SDK Test Forge."""

from __future__ import annotations

import argparse
import json
import sys

from sdk_forge.build import compile_tests_impl
from sdk_forge.clean import delete_tests_impl
from sdk_forge.coverage import collect_coverage_impl
from sdk_forge.mock import generate_mocks_impl
from sdk_forge.probe import probe_sdk_impl
from sdk_forge.run import run_tests_impl
from sdk_forge.scan import scan_headers_impl
from sdk_forge.util import normalize_str_list, parse_bool


def _emit(result: dict, quiet: bool = False) -> int:
    if quiet and result.get("status") in ("ok", "test_failures"):
        keys = ("status", "total", "passed", "failed", "binary_path", "line_coverage_pct", "mock_count")
        result = {k: result[k] for k in keys if k in result}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    status = result.get("status", "error")
    if status == "ok":
        return 0
    if status == "test_failures":
        return 1
    return 2


def cmd_scan(args: argparse.Namespace) -> int:
    result = scan_headers_impl(
        args.sdk_root,
        include_dirs=args.include or [],
        compile_args=args.compile_arg or [],
        use_clang=not args.no_clang,
        use_cache=not args.no_cache,
    )
    return _emit(result, args.quiet)


def cmd_probe(args: argparse.Namespace) -> int:
    return _emit(probe_sdk_impl(args.sdk_root), args.quiet)


def cmd_compile(args: argparse.Namespace) -> int:
    sdk_include = args.include or []
    sdk_lib = args.lib_dir or []
    link = args.link or []
    prefix = args.prefix or []
    pkg_config = args.pkg_config or []

    if args.from_probe:
        probe = probe_sdk_impl(args.from_probe)
        if probe.get("status") != "ok":
            return _emit(probe, args.quiet)
        sdk_include = list(dict.fromkeys(sdk_include + probe.get("sdk_include_dirs", [])))
        sdk_lib = list(dict.fromkeys(sdk_lib + probe.get("sdk_lib_dirs", [])))
        link = list(dict.fromkeys(link + probe.get("link_libraries", [])))
        prefix = list(dict.fromkeys(prefix + probe.get("cmake_prefix_path", [])))
        pkg_config = list(dict.fromkeys(pkg_config + probe.get("pkg_config_packages", [])))

    result = compile_tests_impl(
        args.source_dir,
        args.build_dir,
        sdk_include_dirs=sdk_include,
        sdk_lib_dirs=sdk_lib,
        link_libraries=link,
        cmake_prefix_path=prefix,
        find_packages=args.find_package or [],
        pkg_config_packages=pkg_config,
        extra_cmake_snippet=args.cmake_snippet or "",
        gtest_source=args.gtest_source,
        coverage=args.coverage,
        coverage_tool=args.coverage_tool,
    )
    return _emit(result, args.quiet)


def cmd_run(args: argparse.Namespace) -> int:
    return _emit(run_tests_impl(args.build_dir, args.filter or ""), args.quiet)


def cmd_clean(args: argparse.Namespace) -> int:
    return _emit(delete_tests_impl(args.test_dir), args.quiet)


def cmd_coverage(args: argparse.Namespace) -> int:
    return _emit(
        collect_coverage_impl(args.build_dir, args.source_dir or "", args.coverage_tool),
        args.quiet,
    )


def cmd_mocks(args: argparse.Namespace) -> int:
    if args.scan_file:
        scan_data = open(args.scan_file, encoding="utf-8").read()
        result = generate_mocks_impl(scan_data, args.class_name or "")
    else:
        scan_result = scan_headers_impl(args.sdk_root, use_cache=True)
        result = generate_mocks_impl(scan_result, args.class_name or "")
    if args.output and result.get("header"):
        open(args.output, "w", encoding="utf-8").write(result["header"])
    return _emit(result, args.quiet)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge", description="SDK Test Forge CLI")
    parser.add_argument("--quiet", action="store_true", help="Minimal JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan SDK headers")
    p_scan.add_argument("sdk_root")
    p_scan.add_argument("--include", action="append", default=[])
    p_scan.add_argument("--compile-arg", action="append", default=[])
    p_scan.add_argument("--no-clang", action="store_true")
    p_scan.add_argument("--no-cache", action="store_true")
    p_scan.set_defaults(func=cmd_scan)

    p_probe = sub.add_parser("probe", help="Probe SDK layout")
    p_probe.add_argument("sdk_root")
    p_probe.set_defaults(func=cmd_probe)

    p_compile = sub.add_parser("compile", help="Compile GTest project")
    p_compile.add_argument("source_dir")
    p_compile.add_argument("build_dir")
    p_compile.add_argument("--include", action="append", default=[])
    p_compile.add_argument("--lib-dir", action="append", default=[])
    p_compile.add_argument("--link", action="append", default=[])
    p_compile.add_argument("--prefix", action="append", default=[])
    p_compile.add_argument("--pkg-config", action="append", default=[])
    p_compile.add_argument("--find-package", action="append", default=[])
    p_compile.add_argument("--cmake-snippet", default="")
    p_compile.add_argument("--from-probe", default="", help="SDK root to probe for auto include/lib/link")
    p_compile.add_argument("--gtest-source", default="cached", choices=["cached", "fetch", "system"])
    p_compile.add_argument("--coverage", action="store_true")
    p_compile.add_argument("--coverage-tool", default="gcov")
    p_compile.set_defaults(func=cmd_compile)

    p_run = sub.add_parser("run", help="Run compiled tests")
    p_run.add_argument("build_dir")
    p_run.add_argument("--filter", default="")
    p_run.set_defaults(func=cmd_run)

    p_clean = sub.add_parser("clean", help="Delete GTest files")
    p_clean.add_argument("test_dir")
    p_clean.set_defaults(func=cmd_clean)

    p_cov = sub.add_parser("coverage", help="Collect coverage report")
    p_cov.add_argument("build_dir")
    p_cov.add_argument("--source-dir", default="")
    p_cov.add_argument("--coverage-tool", default="gcov")
    p_cov.set_defaults(func=cmd_coverage)

    p_mocks = sub.add_parser("mocks", help="Generate GMock templates")
    p_mocks.add_argument("--sdk-root", default="")
    p_mocks.add_argument("--scan-file", default="")
    p_mocks.add_argument("--class-name", default="")
    p_mocks.add_argument("--output", default="")
    p_mocks.set_defaults(func=cmd_mocks)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
