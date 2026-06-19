"""Hands-off autopilot: programmatic init through orchestration next_actions.
一键 Autopilot — 从 SDK 路径推进到 production build 编排。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sdk_forge.config import load_forge_config, save_forge_config
from sdk_forge.doctor import doctor_impl
from sdk_forge.init import init_project_impl
from sdk_forge.orchestration import get_orchestration_context
from sdk_forge.plan import suggest_test_plan_impl
from sdk_forge.plan_gap import _load_plan_state as load_plan_state
from sdk_forge.profile import resolve_forge_config
from sdk_forge.retry import load_build_state
from sdk_forge.scan import scan_headers_impl
from sdk_forge.session import save_plan_state
from sdk_forge.templates import generate_test_skeleton_impl
from sdk_forge.test_files import list_test_file_basenames
from sdk_forge.toolchain_install import ensure_toolchain_impl
from sdk_forge.workflow import update_workflow_stage


def _resolve_project_dir(sdk_root: str, project_dir: str) -> Path:
    if project_dir:
        return Path(project_dir).resolve()
    sdk = Path(sdk_root).resolve()
    candidate = sdk.parent / f"{sdk.name}_forge_tests"
    return candidate


def _status_summary(status: str, orchestration: dict[str, Any]) -> str:
    actions = orchestration.get("next_actions") or []
    if status == "ok":
        return "Autopilot 完成：测试已构建，可合并。"
    if status == "blocked":
        return "Autopilot 阻塞：断言质量未达标且 enrich 轮次已用尽，请人工审查。"
    if status == "ready_for_build":
        return "Autopilot：编排已完成，等待 forge-build 执行 production 构建。"
    if not actions:
        return "Autopilot：无待执行子 Agent 任务。"
    agents = ", ".join(dict.fromkeys(a.get("agent", "?") for a in actions))
    round_n = orchestration.get("enrich_round", 0)
    return f"Autopilot 需要 Agent 执行：{agents}（enrich 第 {round_n} 轮）。"


def run_autopilot_impl(
    sdk_root: str = "",
    project_dir: str = "",
    profile: str = "",
    max_enrich_rounds: int | str = "",
    auto_init: bool = True,
) -> dict[str, Any]:
    """Programmatic autopilot through env/scan/scaffold; returns orchestration next_actions."""
    if not sdk_root and not project_dir:
        return {"status": "error", "error": "sdk_root or project_dir required"}

    root = _resolve_project_dir(sdk_root, project_dir)
    steps: list[str] = []

    if auto_init and not (root / ".forge.yaml").is_file():
        init_project_impl(str(root), sdk_root=sdk_root or "../sdk")
        steps.append("init")

    if sdk_root and (root / ".forge.yaml").is_file():
        cfg = load_forge_config(start=root)
        if cfg.get("sdk_root") != sdk_root:
            cfg["sdk_root"] = sdk_root.replace("\\", "/")
            save_forge_config(cfg)

    config = load_forge_config(start=root)
    if profile:
        config["forge_profile"] = profile
        config["autopilot_profile"] = profile
    if max_enrich_rounds != "":
        try:
            config["max_enrich_rounds"] = int(max_enrich_rounds)
        except (TypeError, ValueError):
            pass
    save_forge_config(config)
    config = resolve_forge_config(load_forge_config(start=root), profile_override=profile)

    ensure = ensure_toolchain_impl(agent_mode=True)
    steps.append("env")
    doctor = doctor_impl()

    plan = load_plan_state(str(root))
    has_plan = plan.get("status") != "error" and bool(plan.get("targets"))
    if not has_plan and sdk_root:
        scan = scan_headers_impl(sdk_root, use_cache=True)
        if scan.get("status") == "ok":
            plan = suggest_test_plan_impl(scan_json=scan, sdk_root=sdk_root)
            if plan.get("status") == "ok":
                save_plan_state(str(root), plan)
                update_workflow_stage(str(root), "plan")
                steps.append("scan+plan")

    test_files = list_test_file_basenames(str(root))
    plan_ok = plan.get("status") == "ok" and bool(plan.get("targets"))
    if not test_files and plan_ok:
        tests_dir = root / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        scaffold = generate_test_skeleton_impl(
            plan_json=plan if plan.get("status") == "ok" else None,
            output_dir=str(tests_dir),
            sdk_root=sdk_root,
            fidelity="smart",
            skip_existing=True,
        )
        if scaffold.get("status") == "ok":
            update_workflow_stage(str(root), "scaffold")
            steps.append("scaffold")

    orchestration = get_orchestration_context(str(root))
    next_actions = orchestration.get("next_actions") or []
    build_state = load_build_state(str(root))
    html_path = None
    if isinstance(build_state, dict):
        html_path = build_state.get("html_path")
    report_html = root / ".forge" / "cache" / "report.html"
    if report_html.is_file():
        html_path = str(report_html.resolve())

    enrich_round = orchestration.get("enrich_round", 0)
    merge_ready = bool(orchestration.get("merge_ready"))
    blocked = any(a.get("blocked") for a in next_actions)

    if blocked:
        autopilot_status = "blocked"
    elif merge_ready and build_state.get("status") == "ok":
        autopilot_status = "ok"
        if config.get("auto_golden_snapshot", True):
            from sdk_forge.golden import snapshot_golden_from_plan_impl

            snap = snapshot_golden_from_plan_impl(str(root), merge=True, confirm=True)
            steps.append("golden_snapshot")
            orchestration["golden_snapshot"] = snap
    elif next_actions:
        autopilot_status = "needs_agent"
    elif not merge_ready and not next_actions:
        autopilot_status = "ready_for_build"
    else:
        autopilot_status = "ok" if merge_ready else "needs_agent"

    return {
        "status": autopilot_status,
        "merge_ready": merge_ready,
        "orchestration": orchestration,
        "next_actions": next_actions,
        "html_path": html_path,
        "enrich_round": enrich_round,
        "steps_completed": steps,
        "status_summary": _status_summary(autopilot_status, orchestration),
        "toolchain": ensure,
        "doctor": doctor,
        "project_dir": str(root),
        "profile": config.get("forge_profile", "default"),
    }
