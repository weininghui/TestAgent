"""Advance multi-agent workflow after a sub-agent completes."""

from __future__ import annotations

from typing import Any

from sdk_forge.orchestration import get_orchestration_context
from sdk_forge.workflow import record_agent_completion


def advance_forge_workflow_impl(
    project_dir: str = "",
    last_agent: str = "",
    last_status: str = "ok",
    batch_id: int | None = None,
    review_verdict: str = "",
    detail: dict[str, Any] | None = None,
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
        "orchestration": orch,
    }
