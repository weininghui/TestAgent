"""Command-line interface for SDK Test Forge."""

from __future__ import annotations

import argparse
import json
import sys

from sdk_forge.build import compile_tests_impl
from sdk_forge.clean import delete_tests_impl
from sdk_forge.coverage import collect_coverage_impl
from sdk_forge.doctor import doctor_impl
from sdk_forge.init import init_project_impl
from sdk_forge.mock import generate_mocks_impl
from sdk_forge.pipeline import build_pipeline_impl
from sdk_forge.compdb import export_compile_commands_impl, get_compile_commands_impl
from sdk_forge.plan import suggest_test_plan_impl
from sdk_forge.plan_gap import analyze_plan_gap_impl
from sdk_forge.probe import probe_sdk_impl
from sdk_forge.report import report_impl
from sdk_forge.run import run_tests_impl
from sdk_forge.scan import scan_headers_impl
from sdk_forge.session import get_session_context_impl, save_plan_state
from sdk_forge.templates import generate_test_skeleton_impl
from sdk_forge.test_fix import analyze_test_failures_impl, propose_test_fixes_impl
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
        gtest_version=args.gtest_version,
        coverage=args.coverage,
        coverage_tool=args.coverage_tool,
        sanitizer=args.sanitizer,
        use_config=not args.no_config,
    )
    return _emit(result, args.quiet)


def cmd_run(args: argparse.Namespace) -> int:
    return _emit(run_tests_impl(args.build_dir, args.filter or ""), args.quiet)


def cmd_clean(args: argparse.Namespace) -> int:
    return _emit(delete_tests_impl(args.test_dir), args.quiet)


def cmd_coverage(args: argparse.Namespace) -> int:
    result = collect_coverage_impl(args.build_dir, args.source_dir or "", args.coverage_tool)
    if args.project_dir and result.get("status") == "ok":
        from sdk_forge.coverage import save_coverage_cache
        path = save_coverage_cache(args.project_dir, result)
        if path:
            result["saved_to"] = path
    return _emit(result, args.quiet)


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


def cmd_doctor(args: argparse.Namespace) -> int:
    return _emit(doctor_impl(), args.quiet)


def cmd_init(args: argparse.Namespace) -> int:
    return _emit(
        init_project_impl(args.target_dir, sdk_root=args.sdk_root or "", project_name=args.name),
        args.quiet,
    )


def cmd_build(args: argparse.Namespace) -> int:
    return _emit(
        build_pipeline_impl(
            project_dir=args.project_dir or "",
            source_dir=args.source_dir or "",
            build_dir=args.build_dir or "",
            sdk_root=args.sdk_root or "",
            run_after_compile=not args.no_run,
            max_retries=args.retry,
            auto_fix_config=args.auto_fix_config,
        ),
        args.quiet,
    )


def cmd_plan(args: argparse.Namespace) -> int:
    scan_data = None
    if args.scan_file:
        scan_data = open(args.scan_file, encoding="utf-8").read()
    result = suggest_test_plan_impl(
        sdk_root=args.sdk_root or "",
        scan_json=scan_data,
        include_dirs=args.include or [],
    )
    if args.output:
        open(args.output, "w", encoding="utf-8").write(json.dumps(result, indent=2, ensure_ascii=False))
    if args.project_dir and result.get("status") == "ok":
        save_plan_state(args.project_dir, result)
    return _emit(result, args.quiet)


def cmd_scaffold(args: argparse.Namespace) -> int:
    plan_data = None
    if args.plan_file:
        plan_data = open(args.plan_file, encoding="utf-8").read()
    result = generate_test_skeleton_impl(
        plan_json=plan_data,
        output_dir=args.output or "tests",
        sdk_root=args.sdk_root or "",
        project_name=args.name,
        overwrite=args.overwrite,
    )
    return _emit(result, args.quiet)


def cmd_analyze(args: argparse.Namespace) -> int:
    run_data = None
    if args.run_file:
        run_data = open(args.run_file, encoding="utf-8").read()
    return _emit(
        analyze_test_failures_impl(build_dir=args.build_dir or "", run_json=run_data),
        args.quiet,
    )


def cmd_propose_fix(args: argparse.Namespace) -> int:
    analysis = None
    if args.analysis_file:
        analysis = open(args.analysis_file, encoding="utf-8").read()
    return _emit(
        propose_test_fixes_impl(
            build_dir=args.build_dir or "",
            analysis_json=analysis,
            project_dir=args.project_dir or "",
            tests_dir=args.tests_dir or "",
        ),
        args.quiet,
    )


def cmd_gap(args: argparse.Namespace) -> int:
    plan_data = None
    if args.plan_file:
        plan_data = open(args.plan_file, encoding="utf-8").read()
    return _emit(
        analyze_plan_gap_impl(
            project_dir=args.project_dir or "",
            plan_json=plan_data,
            tests_dir=args.tests_dir or "",
            sdk_root=args.sdk_root or "",
        ),
        args.quiet,
    )


def cmd_compdb(args: argparse.Namespace) -> int:
    if args.build_dir:
        result = export_compile_commands_impl(args.build_dir, args.project_dir or "")
    else:
        result = get_compile_commands_impl(args.project_dir or "")
    return _emit(result, args.quiet)


def cmd_session(args: argparse.Namespace) -> int:
    return _emit(get_session_context_impl(args.project_dir or ""), args.quiet)


def cmd_report(args: argparse.Namespace) -> int:
    result = report_impl(
        project_dir=args.project_dir or "",
        build_state_json=args.state_file and open(args.state_file, encoding="utf-8").read() or "",
        output_format=args.format,
    )
    if args.output and result.get("markdown"):
        open(args.output, "w", encoding="utf-8").write(result["markdown"])
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
    p_compile.add_argument("--gtest-source", default="auto", choices=["auto", "cached", "fetch", "system"])
    p_compile.add_argument("--gtest-version", default="auto", help="Pin googletest tag, e.g. 1.14.0 or v1.13.0")
    p_compile.add_argument("--coverage", action="store_true")
    p_compile.add_argument("--coverage-tool", default="gcov")
    p_compile.add_argument("--sanitizer", default="none", help="none, asan, ubsan, asan+ubsan")
    p_compile.add_argument("--no-config", action="store_true", help="Skip .forge.yaml/.forge.json")
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
    p_cov.add_argument("--project-dir", default="", help="Save coverage summary to .forge/cache/")
    p_cov.set_defaults(func=cmd_coverage)

    p_mocks = sub.add_parser("mocks", help="Generate GMock templates")
    p_mocks.add_argument("--sdk-root", default="")
    p_mocks.add_argument("--scan-file", default="")
    p_mocks.add_argument("--class-name", default="")
    p_mocks.add_argument("--output", default="")
    p_mocks.set_defaults(func=cmd_mocks)

    p_doctor = sub.add_parser("doctor", help="Check toolchain and forge cache")
    p_doctor.set_defaults(func=cmd_doctor)

    p_init = sub.add_parser("init", help="Scaffold forge test project")
    p_init.add_argument("target_dir")
    p_init.add_argument("--sdk-root", default="")
    p_init.add_argument("--name", default="sdk_tests")
    p_init.set_defaults(func=cmd_init)

    p_build = sub.add_parser("build", help="Probe + compile + run from .forge config")
    p_build.add_argument("--project-dir", default="")
    p_build.add_argument("--source-dir", default="")
    p_build.add_argument("--build-dir", default="")
    p_build.add_argument("--sdk-root", default="")
    p_build.add_argument("--no-run", action="store_true")
    p_build.add_argument("--retry", type=int, default=1, help="Max compile attempts with auto-fix (default 1)")
    p_build.add_argument("--auto-fix-config", action="store_true", help="Write applied fixes back to .forge config")
    p_build.set_defaults(func=cmd_build)

    p_plan = sub.add_parser("plan", help="Suggest structured test plan from SDK scan")
    p_plan.add_argument("sdk_root", nargs="?", default="")
    p_plan.add_argument("--scan-file", default="", help="Use existing scan JSON instead of scanning")
    p_plan.add_argument("--include", action="append", default=[])
    p_plan.add_argument("--output", default="")
    p_plan.add_argument("--project-dir", default="", help="Save plan to .forge/cache/last_plan.json")
    p_plan.set_defaults(func=cmd_plan)

    p_scaffold = sub.add_parser("scaffold", help="Generate GTest skeleton from plan or SDK scan")
    p_scaffold.add_argument("sdk_root", nargs="?", default="")
    p_scaffold.add_argument("--plan-file", default="")
    p_scaffold.add_argument("--output", default="tests")
    p_scaffold.add_argument("--name", default="sdk_tests")
    p_scaffold.add_argument("--overwrite", action="store_true")
    p_scaffold.set_defaults(func=cmd_scaffold)

    p_analyze = sub.add_parser("analyze", help="Analyze GTest failures from build dir")
    p_analyze.add_argument("build_dir", nargs="?", default="")
    p_analyze.add_argument("--run-file", default="")
    p_analyze.set_defaults(func=cmd_analyze)

    p_propose = sub.add_parser("propose-fix", help="Propose assertion fixes (no auto-edit)")
    p_propose.add_argument("build_dir", nargs="?", default="")
    p_propose.add_argument("--analysis-file", default="")
    p_propose.add_argument("--project-dir", default="")
    p_propose.add_argument("--tests-dir", default="")
    p_propose.set_defaults(func=cmd_propose_fix)

    p_gap = sub.add_parser("gap", help="Analyze plan vs tests/coverage gap")
    p_gap.add_argument("--project-dir", default="")
    p_gap.add_argument("--plan-file", default="")
    p_gap.add_argument("--tests-dir", default="")
    p_gap.add_argument("--sdk-root", default="")
    p_gap.set_defaults(func=cmd_gap)

    p_compdb = sub.add_parser("compdb", help="Export or read compile_commands.json cache")
    p_compdb.add_argument("build_dir", nargs="?", default="")
    p_compdb.add_argument("--project-dir", default="")
    p_compdb.set_defaults(func=cmd_compdb)

    p_session = sub.add_parser("session", help="Show session context JSON")
    p_session.add_argument("--project-dir", default="")
    p_session.set_defaults(func=cmd_session)

    p_report = sub.add_parser("report", help="Generate markdown report from last build")
    p_report.add_argument("--project-dir", default="")
    p_report.add_argument("--state-file", default="")
    p_report.add_argument("--format", default="markdown", choices=["markdown", "json"])
    p_report.add_argument("--output", default="")
    p_report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
