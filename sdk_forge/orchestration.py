"""Multi-agent orchestration: enrich batches and next-action planning.
多 Agent 编排：enrich 分批与 next_actions 规划。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sdk_forge.config import load_forge_config
from sdk_forge.plan_gap import _load_plan_state as load_plan_state
from sdk_forge.profile import resolve_forge_config
from sdk_forge.test_files import list_test_file_basenames, resolve_tests_dir
from sdk_forge.workflow import (
    clear_agent_runs,
    get_enrich_round,
    increment_enrich_round,
    load_workflow_state,
)

_RE_AGENT = re.compile(r"//\s*AGENT:|//\s*TODO:", re.IGNORECASE)


def list_test_files(project_dir: str = "", tests_dir: str = "") -> list[str]:
    return list_test_file_basenames(project_dir, tests_dir)


def files_needing_enrich(project_dir: str = "", tests_dir: str = "") -> list[str]:
    """Test files that still contain AGENT/TODO markers."""
    tests_path = resolve_tests_dir(project_dir, tests_dir)
    if not tests_path:
        return []
    needing: list[str] = []
    for path in sorted(tests_path.glob("*_test.cpp")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _RE_AGENT.search(content):
            needing.append(path.name)
    return needing


def files_needing_assertion_fix(project_dir: str = "") -> list[str]:
    """Test files with weak/tautology/agent issues from assertion quality cache."""
    from sdk_forge.assertion_quality import analyze_assertion_quality_impl, load_assertion_quality

    root = str(Path(project_dir or Path.cwd()).resolve())
    aq = load_assertion_quality(root)
    if aq.get("status") != "ok":
        analyze_assertion_quality_impl(root)
        aq = load_assertion_quality(root)
    if aq.get("status") != "ok":
        return []
    files: set[str] = set()
    for item in aq.get("weak_tests") or []:
        name = item.get("file")
        if name:
            files.add(str(name))
    return sorted(files)


def multi_agent_batch_size(project_dir: str = "") -> int:
    root = Path(project_dir or Path.cwd())
    config = load_forge_config(start=root)
    try:
        size = int(config.get("multi_agent_batch_size", 4))
    except (TypeError, ValueError):
        size = 4
    return max(1, size)


def max_enrich_rounds(project_dir: str = "") -> int:
    root = Path(project_dir or Path.cwd())
    config = load_forge_config(start=root)
    try:
        rounds = int(config.get("max_enrich_rounds", 1))
    except (TypeError, ValueError):
        rounds = 1
    return max(1, rounds)


def split_enrich_batches(files: list[str], batch_size: int = 4) -> list[dict[str, Any]]:
    """Split file basenames into enrich batches."""
    if not files:
        return []
    size = max(1, batch_size)
    batches: list[dict[str, Any]] = []
    for batch_id, start in enumerate(range(0, len(files), size)):
        chunk = files[start : start + size]
        batches.append({"batch_id": batch_id, "files": chunk})
    return batches


def _completed_agent_runs(workflow: dict[str, Any]) -> dict[str, set[int]]:
    """Map agent name -> set of completed batch_ids (batch_id -1 for non-batch agents)."""
    done: dict[str, set[int]] = {}
    for run in workflow.get("agent_runs") or []:
        if run.get("status") != "ok":
            continue
        agent = str(run.get("agent") or "")
        if not agent:
            continue
        batch_id = run.get("batch_id")
        if batch_id is None:
            batch_id = -1
        done.setdefault(agent, set()).add(int(batch_id))
    return done


def _agent_done(completed: dict[str, set[int]], agent: str, batch_id: int | None = None) -> bool:
    bids = completed.get(agent, set())
    if batch_id is None:
        return -1 in bids
    return batch_id in bids


def _all_enrich_batches_done(completed: dict[str, set[int]], batches: list[dict[str, Any]]) -> bool:
    if not batches:
        return False
    return all(_agent_done(completed, "forge-enrich", b["batch_id"]) for b in batches)


def _append_enrich_actions(
    next_actions: list[dict[str, Any]],
    pending: list[dict[str, Any]],
    batch_size: int,
    root: Path,
    enrich_round: int,
) -> None:
    parallel = batch_size > 1
    if parallel:
        for batch in pending:
            next_actions.append({
                "agent": "forge-enrich",
                "batch_id": batch["batch_id"],
                "files": batch["files"],
                "parallel": True,
                "enrich_round": enrich_round,
                "prompt_hint": (
                    f"Enrich round {enrich_round} batch {batch['batch_id']} "
                    f"files={','.join(batch['files'])} project_dir={root}"
                ),
            })
    else:
        batch = pending[0]
        next_actions.append({
            "agent": "forge-enrich",
            "batch_id": batch["batch_id"],
            "files": batch["files"],
            "parallel": False,
            "enrich_round": enrich_round,
            "prompt_hint": (
                f"Enrich round {enrich_round} batch {batch['batch_id']} "
                f"files={','.join(batch['files'])} project_dir={root}"
            ),
        })


def _maybe_retry_enrich_after_assertion(
    project_dir: str,
    root: Path,
    completed: dict[str, set[int]],
    batch_size: int,
    enrich_round: int,
    max_rounds: int,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str], list[dict[str, Any]], int]:
    """After enrich batches complete, run assertion gate; optionally start new enrich round."""
    from sdk_forge.assertion_quality import analyze_assertion_quality_impl
    from sdk_forge.quality_gate import run_assertion_quality_gate

    analyze_assertion_quality_impl(str(root))
    gate = run_assertion_quality_gate(str(root), config)
    next_actions: list[dict[str, Any]] = []

    if gate.get("passed"):
        return next_actions, gate, [], [], enrich_round

    if enrich_round >= max_rounds:
        return next_actions, gate, [], [], enrich_round

    weak_files = files_needing_assertion_fix(str(root))
    if not weak_files:
        return next_actions, gate, [], [], enrich_round

    increment_enrich_round(str(root))
    clear_agent_runs(str(root), agent="forge-enrich")
    new_round = get_enrich_round(str(root))
    batches = split_enrich_batches(weak_files, batch_size)
    _append_enrich_actions(next_actions, batches, batch_size, root, new_round)
    return next_actions, gate, weak_files, batches, new_round


def get_orchestration_context(project_dir: str = "") -> dict[str, Any]:
    """Build orchestration view for forge primary agent."""
    root = Path(project_dir or Path.cwd()).resolve()
    workflow = load_workflow_state(str(root))
    current_stage = workflow.get("stage")
    completed = _completed_agent_runs(workflow)

    batch_size = multi_agent_batch_size(str(root))
    max_rounds = max_enrich_rounds(str(root))
    enrich_round = get_enrich_round(str(root))
    raw_config = load_forge_config(start=root)
    config = resolve_forge_config(raw_config)

    plan = load_plan_state(str(root))
    has_plan = plan.get("status") != "error" and bool(plan.get("targets"))
    test_files = list_test_files(str(root))
    needing = files_needing_enrich(str(root))
    from sdk_forge.enrich import load_scaffold_quality

    scaffold_quality = load_scaffold_quality(str(root))
    has_tests = bool(test_files)

    weak_files = files_needing_assertion_fix(str(root)) if has_tests and not needing else []
    if needing:
        enrich_targets = needing
    elif weak_files and enrich_round > 0:
        enrich_targets = weak_files
    elif not scaffold_quality.get("status") == "ok" and test_files:
        enrich_targets = test_files
    else:
        enrich_targets = []

    enrich_batches = split_enrich_batches(enrich_targets, batch_size)
    build_state_path = root / ".forge" / "cache" / "last_build.json"
    has_build = build_state_path.is_file()
    assertion_gate_preview: dict[str, Any] = {"skipped": True}

    next_actions: list[dict[str, Any]] = []

    if not _agent_done(completed, "forge-env"):
        next_actions.append({
            "agent": "forge-env",
            "parallel": False,
            "prompt_hint": f"Ensure toolchain for project_dir={root}",
        })
    elif not has_plan:
        next_actions.append({
            "agent": "forge-scan",
            "parallel": False,
            "prompt_hint": f"Scan SDK and save plan for project_dir={root}",
        })
    elif not has_tests:
        next_actions.append({
            "agent": "forge-scaffold",
            "parallel": False,
            "prompt_hint": f"Generate smart scaffold for project_dir={root}",
        })
    elif enrich_targets:
        pending = [b for b in enrich_batches if not _agent_done(completed, "forge-enrich", b["batch_id"])]
        if pending:
            _append_enrich_actions(next_actions, pending, batch_size, root, enrich_round)
        elif _all_enrich_batches_done(completed, enrich_batches):
            retry_actions, assertion_gate_preview, enrich_targets, enrich_batches, enrich_round = (
                _maybe_retry_enrich_after_assertion(
                    str(root), root, completed, batch_size, enrich_round, max_rounds, config,
                )
            )
            if retry_actions:
                next_actions.extend(retry_actions)
            elif not assertion_gate_preview.get("passed") and enrich_round >= max_rounds:
                next_actions.append({
                    "agent": "forge-review",
                    "parallel": False,
                    "blocked": True,
                    "prompt_hint": f"Assertion gate failed after {max_rounds} enrich rounds; review project_dir={root}",
                })
            elif not _agent_done(completed, "forge-review"):
                next_actions.append({
                    "agent": "forge-review",
                    "parallel": False,
                    "prompt_hint": f"Production readiness review for project_dir={root}",
                })
            elif not _agent_done(completed, "forge-build"):
                profile = config.get("autopilot_profile") or config.get("forge_profile") or "production"
                next_actions.append({
                    "agent": "forge-build",
                    "parallel": False,
                    "prompt_hint": f"Build profile={profile} project_dir={root}",
                })
    elif not _agent_done(completed, "forge-review"):
        from sdk_forge.assertion_quality import analyze_assertion_quality_impl
        from sdk_forge.quality_gate import run_assertion_quality_gate

        analyze_assertion_quality_impl(str(root))
        assertion_gate_preview = run_assertion_quality_gate(str(root), config)
        needs_review = (
            config.get("forge_profile") == "production"
            or not assertion_gate_preview.get("passed")
        )
        if needs_review:
            next_actions.append({
                "agent": "forge-review",
                "parallel": False,
                "prompt_hint": f"Production readiness review for project_dir={root}",
            })
        elif not _agent_done(completed, "forge-build") or not has_build:
            profile = config.get("autopilot_profile") or config.get("forge_profile") or "default"
            next_actions.append({
                "agent": "forge-build",
                "parallel": False,
                "prompt_hint": f"Build profile={profile} project_dir={root}",
            })

    needs_enrichment = bool(needing) or bool(weak_files) or (
        scaffold_quality.get("status") == "ok" and scaffold_quality.get("needs_enrichment")
    )

    merge_ready = (
        not next_actions
        and has_build
        and assertion_gate_preview.get("passed") is not False
    )

    return {
        "status": "ok",
        "current_stage": current_stage,
        "batch_size": batch_size,
        "enrich_round": enrich_round,
        "max_enrich_rounds": max_rounds,
        "parallel_enrich_enabled": batch_size > 1,
        "enrich_batches": enrich_batches,
        "files_needing_enrich": needing,
        "files_needing_assertion_fix": weak_files,
        "needs_enrichment": needs_enrichment,
        "has_plan": has_plan,
        "has_tests": has_tests,
        "assertion_gate_preview": assertion_gate_preview,
        "merge_ready": merge_ready,
        "next_actions": next_actions,
        "completed_agents": {k: sorted(v) for k, v in completed.items()},
    }
