"""Advance multi-agent workflow after a sub-agent completes."""

from __future__ import annotations

from typing import Any

from sdk_forge.orchestration.core import get_orchestration_context
from sdk_forge.orchestration.workflow import record_agent_completion


def advance_forge_workflow_impl(
    project_dir: str = "",
    last_agent: str = "",
    last_status: str = "ok",
    batch_id: int | None = None,
    review_verdict: str = "",
    detail: dict[str, Any] | None = None,
    task_id: str = "",
) -> dict[str, Any]:
    """Record last agent run (if any) and return simplified next-step view."""
    root = project_dir or "."
    if last_agent:
        run_detail = dict(detail or {})
        if review_verdict:
            run_detail["review_verdict"] = review_verdict.strip().lower()
        record_agent_completion(
            root,
            last_agent,
            status=last_status or "ok",
            batch_id=batch_id,
            detail=run_detail or None,
        )
        from sdk_forge.delegation.core import complete_delegation_impl

        complete_delegation_impl(
            root,
            agent=last_agent,
            batch_id=batch_id,
            task_id=task_id,
            status=last_status or "ok",
        )

    orch = get_orchestration_context(root)
    next_actions = orch.get("next_actions") or []

    if orch.get("merge_ready"):
        status = "ok"
    elif any(a.get("blocked") for a in next_actions):
        status = "blocked"
    elif next_actions:
        status = "needs_agent"
    else:
        status = "idle"

    first = next_actions[0] if next_actions else {}
    background = [a for a in next_actions if a.get("run_in_background") and not a.get("blocked")]
    foreground = [
        a for a in next_actions if not a.get("run_in_background") and not a.get("blocked")
    ]
    return {
        "status": status,
        "next_agent": first.get("agent"),
        "next_actions": next_actions,
        "prompt_hint": first.get("prompt_hint"),
        "parallel": first.get("parallel", False),
        "batch_id": first.get("batch_id"),
        "files": first.get("files"),
        "merge_ready": bool(orch.get("merge_ready")),
        "enrich_round": orch.get("enrich_round", 0),
        "review_verdict": orch.get("review_verdict"),
        "delegation_mode": orch.get("delegation_mode"),
        "delegation": {
            "mode": orch.get("delegation_mode"),
            "concurrency": orch.get("delegation_concurrency"),
            "background_actions": background,
            "foreground_actions": foreground,
        },
        "orchestration": orch,
    }
