"""One-shot probe + compile + run pipeline.
一次性探测、编译、运行流水线。
"""

from __future__ import annotations

from pathlib import Path

from sdk_forge.config import load_forge_config
from sdk_forge.quality_gate import run_scaffold_quality_gate
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
) -> dict:
    """Run full build; quality gate, save state, auto HTML report.
    执行完整构建；质量门禁、保存状态、自动生成 HTML 报告。
    """
    cache_root = project_dir or ""
    if not cache_root and source_dir:
        cache_root = str(Path(source_dir).parent)

    config = load_forge_config(start=cache_root or Path.cwd())
    quality_gate: dict = {"passed": True, "skipped": True}

    if cache_root and not parse_bool(skip_quality_gate, default=False):
        quality_gate = run_scaffold_quality_gate(cache_root, config)
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
        if not quality_gate.get("skipped"):
            update_workflow_stage(cache_root, "build", {"quality_gate": quality_gate.get("passed")})

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
    result["quality_gate"] = {
        "passed": quality_gate.get("passed", True),
        "ratio": quality_gate.get("placeholder_ratio"),
        "mode": quality_gate.get("mode", "warn"),
        "max_placeholder_ratio": quality_gate.get("max_placeholder_ratio", 0.5),
        "skipped": quality_gate.get("skipped", True),
    }

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
