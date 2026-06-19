"""Multi-agent orchestration: enrich batches and next-action planning.
多 Agent 编排：enrich 分批与 next_actions 规划。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sdk_forge.config import load_forge_config
from sdk_forge.plan_gap import _load_plan_state as load_plan_state
from sdk_forge.test_files import list_test_file_basenames, resolve_tests_dir
from sdk_forge.workflow import load_workflow_state

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


def multi_agent_batch_size(project_dir: str = "") -> int:
    root = Path(project_dir or Path.cwd())
    config = load_forge_config(start=root)
    try:
        size = int(config.get("multi_agent_batch_size", 4))
    except (TypeError, ValueError):
        size = 4
    return max(1, size)


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


def get_orchestration_context(project_dir: str = "") -> dict[str, Any]:
    """Build orchestration view for forge primary agent."""
    root = Path(project_dir or Path.cwd()).resolve()
    workflow = load_workflow_state(str(root))
    current_stage = workflow.get("stage")
    completed = _completed_agent_runs(workflow)

    batch_size = multi_agent_batch_size(str(root))
    plan = load_plan_state(str(root))
    has_plan = plan.get("status") != "error" and bool(plan.get("targets"))
    test_files = list_test_files(str(root))
    needing = files_needing_enrich(str(root))
    from sdk_forge.enrich import load_scaffold_quality

    scaffold_quality = load_scaffold_quality(str(root))
    has_tests = bool(test_files)

    enrich_targets = needing if needing else (test_files if not scaffold_quality.get("status") == "ok" else [])
    enrich_batches = split_enrich_batches(enrich_targets, batch_size)

    build_state_path = root / ".forge" / "cache" / "last_build.json"
    has_build = build_state_path.is_file()

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
            parallel = batch_size > 1
            if parallel:
                for batch in pending:
                    next_actions.append({
                        "agent": "forge-enrich",
                        "batch_id": batch["batch_id"],
                        "files": batch["files"],
                        "parallel": True,
                        "prompt_hint": (
                            f"Enrich batch {batch['batch_id']} files={','.join(batch['files'])} "
                            f"project_dir={root}"
                        ),
                    })
            else:
                batch = pending[0]
                next_actions.append({
                    "agent": "forge-enrich",
                    "batch_id": batch["batch_id"],
                    "files": batch["files"],
                    "parallel": False,
                    "prompt_hint": (
                        f"Enrich batch {batch['batch_id']} files={','.join(batch['files'])} "
                        f"project_dir={root}"
                    ),
                })
        elif not _agent_done(completed, "forge-build"):
            next_actions.append({
                "agent": "forge-build",
                "parallel": False,
                "prompt_hint": f"Build and run tests for project_dir={root}",
            })
    elif not _agent_done(completed, "forge-build") or not has_build:
        next_actions.append({
            "agent": "forge-build",
            "parallel": False,
            "prompt_hint": f"Build and run tests for project_dir={root}",
        })

    needs_enrichment = bool(needing) or (
        scaffold_quality.get("status") == "ok" and scaffold_quality.get("needs_enrichment")
    )

    return {
        "status": "ok",
        "current_stage": current_stage,
        "batch_size": batch_size,
        "parallel_enrich_enabled": batch_size > 1,
        "enrich_batches": enrich_batches,
        "files_needing_enrich": needing,
        "needs_enrichment": needs_enrichment,
        "has_plan": has_plan,
        "has_tests": has_tests,
        "next_actions": next_actions,
        "completed_agents": {k: sorted(v) for k, v in completed.items()},
    }
