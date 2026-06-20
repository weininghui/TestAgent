"""Benchmark pipeline: plan → scaffold → quality → build metrics JSON.
基准流水线：plan → scaffold → quality → build，产出指标 JSON。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdk_forge.infra.config import load_forge_config
from sdk_forge.pipeline.enrich import analyze_scaffold_quality_impl
from sdk_forge.pipeline.core import build_pipeline_impl
from sdk_forge.pipeline.plan import suggest_test_plan_impl
from sdk_forge.pipeline.quality_gate import run_scaffold_quality_gate
from sdk_forge.infra.session import save_plan_state
from sdk_forge.pipeline.templates import generate_test_skeleton_impl
from sdk_forge.domain.util import parse_bool


def run_bench_impl(
    project_dir: str = "",
    sdk_root: str = "",
    fidelity: str = "smart",
    run_build: bool | str = True,
    clean_build: bool | str = True,
) -> dict[str, Any]:
    """Run full forge pipeline and write `.forge/cache/bench_last.json`.
    执行完整流水线并写入基准指标 JSON。
    """
    root = Path(project_dir or Path.cwd()).resolve()
    if not root.is_dir():
        return {"status": "error", "error": f"Project directory not found: {root}"}

    config = load_forge_config(start=root)
    sdk = sdk_root or config.get("sdk_root") or ""
    if sdk and not Path(sdk).is_absolute():
        sdk = str((root / sdk).resolve())
    if not sdk:
        return {"status": "error", "error": "Provide sdk_root or set sdk_root in .forge config"}

    tests_dir = str(root / (config.get("tests_dir") or "tests"))
    build_dir = str(root / (config.get("build_dir") or "build"))
    tests_path = Path(tests_dir)
    build_path = Path(build_dir)

    plan = suggest_test_plan_impl(sdk_root=sdk)
    if plan.get("status") != "ok":
        return plan
    save_plan_state(str(root), plan)

    scaffold = generate_test_skeleton_impl(
        plan_json=plan,
        output_dir=tests_dir,
        overwrite=True,
        fidelity=fidelity if fidelity in ("smart", "skeleton") else "smart",
    )
    if scaffold.get("status") != "ok":
        return scaffold

    quality = analyze_scaffold_quality_impl(str(root), tests_dir=tests_dir)
    gate = run_scaffold_quality_gate(str(root), config, tests_dir=tests_dir)

    metrics: dict[str, Any] = {
        "status": "ok",
        "project_dir": str(root),
        "sdk_root": sdk,
        "fidelity": scaffold.get("fidelity", fidelity),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_count": plan.get("target_count", 0),
        "files_written": len(scaffold.get("files_written") or []),
        "placeholder_ratio": quality.get("placeholder_ratio"),
        "needs_enrichment": quality.get("needs_enrichment", False),
        "quality_gate": {
            "passed": gate.get("passed"),
            "mode": gate.get("mode"),
            "ratio": gate.get("placeholder_ratio"),
        },
        "build_status": None,
        "test_pass_rate": None,
    }

    if parse_bool(run_build, default=True):
        if parse_bool(clean_build, default=True) and build_path.exists():
            shutil.rmtree(build_path, ignore_errors=True)
        build_path.mkdir(parents=True, exist_ok=True)
        build_result = build_pipeline_impl(
            project_dir=str(root),
            source_dir=tests_dir,
            build_dir=build_dir,
            sdk_root=sdk,
            run_after_compile=True,
            max_retries=1,
        )
        metrics["build_status"] = build_result.get("status")
        run_info = build_result.get("run") or {}
        total = run_info.get("total") or 0
        passed = run_info.get("passed") or 0
        if total:
            metrics["test_pass_rate"] = round(passed / total, 4)
        metrics["build"] = {
            "status": build_result.get("status"),
            "total": total,
            "passed": passed,
            "failed": run_info.get("failed"),
        }

    cache = root / ".forge" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    out_path = cache / "bench_last.json"
    out_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    metrics["bench_path"] = str(out_path.resolve())
    return metrics
