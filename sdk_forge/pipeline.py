"""One-shot probe + compile + run pipeline.
一次性探测、编译、运行流水线。
"""

from __future__ import annotations

from pathlib import Path

from sdk_forge.config import load_forge_config
from sdk_forge.coverage import collect_coverage_impl
from sdk_forge.coverage_expand import coverage_expand_impl
from sdk_forge.plan_gap import analyze_plan_gap_impl
from sdk_forge.profile import resolve_forge_config
from sdk_forge.quality_gate import (
    run_assertion_quality_gate,
    run_coverage_gate,
    run_scaffold_quality_gate,
)
from sdk_forge.report import auto_generate_report
from sdk_forge.retry import build_with_retry_impl, save_build_state
from sdk_forge.util import parse_bool
from sdk_forge.workflow import update_workflow_stage


def build_pipeline_impl(
    project_dir: str = "",
    source_dir: str = "",
    build_dir: str = "",
    sdk_root: str = "",
    run_after_compile: bool | str = True,
    max_retries: int | str = 1,
    auto_fix_config: bool | str = False,
    skip_quality_gate: bool | str = False,
    auto_setup_toolchain: bool | str = True,
    profile: str = "",
) -> dict:
    """Run full build; quality gates, save state, auto HTML report."""
    cache_root = project_dir or ""
    if not cache_root and source_dir:
        cache_root = str(Path(source_dir).parent)

    raw_config = load_forge_config(start=cache_root or Path.cwd())
    config = resolve_forge_config(raw_config, profile)
    quality_gate: dict = {"passed": True, "skipped": True}
    assertion_gate: dict = {"passed": True, "skipped": True}
    coverage_gate_result: dict = {"passed": True, "skipped": True}

    if cache_root and not parse_bool(skip_quality_gate, default=False):
        quality_gate = run_scaffold_quality_gate(cache_root, config, profile_override=profile)
        if not quality_gate.get("passed") and quality_gate.get("mode") == "block":
            return {
                "status": "scaffold_quality_blocked",
                "error": (
                    f"Scaffold placeholder ratio {quality_gate.get('placeholder_ratio')} "
                    f"exceeds max {quality_gate.get('max_placeholder_ratio')}. "
                    "Run enrich_test_cases and fix // AGENT: markers."
                ),
                "quality_gate": {
                    "passed": False,
                    "ratio": quality_gate.get("placeholder_ratio"),
                    "mode": quality_gate.get("mode"),
                    "max_placeholder_ratio": quality_gate.get("max_placeholder_ratio"),
                },
                "scaffold_quality": quality_gate.get("quality"),
            }

        assertion_gate = run_assertion_quality_gate(cache_root, config, profile_override=profile)
        if not assertion_gate.get("passed") and assertion_gate.get("mode") == "block":
            return {
                "status": "assertion_quality_blocked",
                "error": "; ".join(assertion_gate.get("block_reasons") or [
                    f"Assertion score {assertion_gate.get('score')} below minimum",
                ]),
                "assertion_gate": {
                    "passed": False,
                    "score": assertion_gate.get("score"),
                    "min_assertion_score": assertion_gate.get("min_assertion_score"),
                    "weak_test_count": assertion_gate.get("weak_test_count"),
                },
                "assertion_quality": assertion_gate.get("quality"),
            }

        if not quality_gate.get("skipped"):
            update_workflow_stage(cache_root, "quality_gate", {
                "scaffold_passed": quality_gate.get("passed"),
                "assertion_passed": assertion_gate.get("passed"),
            })

    result = build_with_retry_impl(
        project_dir=project_dir,
        source_dir=source_dir,
        build_dir=build_dir,
        sdk_root=sdk_root,
        run_after_compile=run_after_compile,
        max_retries=max_retries,
        auto_fix_config=auto_fix_config,
        auto_setup_toolchain=auto_setup_toolchain,
    )

    is_production = config.get("forge_profile") == "production"
    if cache_root and is_production and result.get("status") == "ok":
        build_dir_resolved = result.get("build_dir") or build_dir
        source_dir_resolved = result.get("source_dir") or source_dir
        if build_dir_resolved:
            try:
                collect_coverage_impl(
                    build_dir=str(build_dir_resolved),
                    source_dir=str(source_dir_resolved or ""),
                )
            except (OSError, TypeError):
                pass
        try:
            coverage_expand_impl(project_dir=cache_root)
            analyze_plan_gap_impl(cache_root)
        except (OSError, TypeError):
            pass

        coverage_gate_result = run_coverage_gate(cache_root, config, profile_override=profile)
        if not coverage_gate_result.get("passed") and not coverage_gate_result.get("skipped"):
            result["status"] = "coverage_gate_blocked"
            result["error"] = (
                f"Line coverage {coverage_gate_result.get('line_coverage_pct')}% "
                f"below min {coverage_gate_result.get('min_line_coverage_pct')}%"
            )

    result["quality_gate"] = {
        "passed": quality_gate.get("passed", True),
        "ratio": quality_gate.get("placeholder_ratio"),
        "mode": quality_gate.get("mode", "warn"),
        "max_placeholder_ratio": quality_gate.get("max_placeholder_ratio", 0.5),
        "skipped": quality_gate.get("skipped", True),
    }
    result["assertion_gate"] = {
        "passed": assertion_gate.get("passed", True),
        "score": assertion_gate.get("score"),
        "min_assertion_score": assertion_gate.get("min_assertion_score"),
        "weak_test_count": assertion_gate.get("weak_test_count", 0),
        "skipped": assertion_gate.get("skipped", True),
        "block_reasons": assertion_gate.get("block_reasons") or [],
    }
    result["coverage_gate"] = {
        "passed": coverage_gate_result.get("passed", True),
        "skipped": coverage_gate_result.get("skipped", True),
        "line_coverage_pct": coverage_gate_result.get("line_coverage_pct"),
        "min_line_coverage_pct": coverage_gate_result.get("min_line_coverage_pct"),
    }
    result["forge_profile"] = config.get("forge_profile", "default")

    if project_dir or result.get("source_dir"):
        try:
            cache_root = project_dir or str(Path(result.get("source_dir", ".")).parent)
            save_build_state(cache_root, result)
        except OSError:
            pass

    if cache_root:
        if parse_bool(config.get("auto_report", True), default=True):
            try:
                report_result = auto_generate_report(cache_root, result)
                if report_result.get("status") == "ok":
                    update_workflow_stage(cache_root, "report")
                    result["html_path"] = report_result["html_path"]
                    result["report"] = {
                        "format": "html",
                        "html_path": report_result["html_path"],
                        "summary": report_result.get("summary"),
                    }
            except OSError:
                pass

    return result
