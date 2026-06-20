"""OMO task() dispatch builder aligned with OpenCode GUI Task cards (v5.10)."""

from __future__ import annotations

import re
from typing import Any

from sdk_forge.delegation.core import delegation_concurrency
from sdk_forge.orchestration.core import get_orchestration_context

FORBIDDEN_TOOLS = ("call_omo_agent",)
FORBIDDEN_PARAM_PATTERNS = (
    re.compile(r"\btask\s*\(\s*agent\s*=", re.IGNORECASE),
    re.compile(r"\btitle\s*=", re.IGNORECASE),
)


def validate_task_action(action: dict[str, Any]) -> list[str]:
    """Return validation errors for an OMO task dispatch action."""
    errors: list[str] = []
    if not action.get("subagent_type"):
        errors.append("missing subagent_type")
    if "load_skills" not in action:
        errors.append("missing load_skills (must be explicit [])")
    if not action.get("description"):
        errors.append("missing description (3-5 words for GUI Task card)")
    if not action.get("prompt") and not action.get("prompt_hint"):
        errors.append("missing prompt or prompt_hint")
    if action.get("agent") and not action.get("subagent_type"):
        errors.append("use subagent_type= not agent=")
    if action.get("title") and not action.get("description"):
        errors.append("use description= not title= (GUI card label)")
    return errors


def build_omo_task_call(action: dict[str, Any]) -> dict[str, Any]:
    """Build OMO delegate-task args for one next_action (OpenCode GUI Task card)."""
    subagent = str(action.get("subagent_type") or action.get("agent") or "")
    description = str(action.get("description") or action.get("title") or subagent)
    prompt = str(action.get("prompt") or action.get("prompt_hint") or "")
    run_bg = bool(action.get("run_in_background"))
    args: dict[str, Any] = {
        "subagent_type": subagent,
        "load_skills": action.get("load_skills") if action.get("load_skills") is not None else [],
        "description": description,
        "prompt": prompt,
        "run_in_background": run_bg,
    }
    return {
        "tool": "task",
        "args": args,
        "agent": subagent,
        "batch_id": action.get("batch_id"),
        "gui_expect": "OpenCode Task card (agent name + description)",
        "validation_errors": validate_task_action({**action, **args, "prompt_hint": prompt}),
    }


def build_task_dispatches_impl(project_dir: str = "") -> dict[str, Any]:
    """Build ready-to-invoke OMO task() calls from orchestration next_actions."""
    orch = get_orchestration_context(project_dir)
    actions = orch.get("next_actions") or []
    dispatchable = [a for a in actions if not a.get("blocked")]

    dispatches = [build_omo_task_call(action) for action in dispatchable]

    parallel = [d for d in dispatches if d.get("args", {}).get("run_in_background")]
    serial = [d for d in dispatches if not d.get("args", {}).get("run_in_background")]
    background = [a for a in dispatchable if a.get("run_in_background")]
    foreground = [a for a in dispatchable if not a.get("run_in_background")]

    return {
        "status": "ok",
        "delegation_mode": "omo",
        "delegation_concurrency": orch.get("delegation_concurrency")
        or delegation_concurrency(project_dir),
        "dispatch_protocol": "omo_task_only",
        "gui_task_card": True,
        "forbidden_tools": list(FORBIDDEN_TOOLS),
        "forbidden_params": ["task(agent=...)", "title="],
        "task_dispatches": dispatches,
        "parallel_dispatches": parallel,
        "serial_dispatches": serial,
        "background_actions": background,
        "foreground_actions": foreground,
        "fire_parallel_in_one_turn": len(parallel) > 1,
        "invocation_guide": {
            "tool_name": "task",
            "how": "MUST use native tool call (function calling). Markdown/code-block task(...) does NOT execute.",
            "not_mcp": True,
            "mcp_prefix": "sdk-forge_",
            "forbidden_substitute": "call_omo_agent",
            "opencode_ref": "https://github.com/anomalyco/opencode — packages/opencode/src/tool/task.ts",
            "success_signal": "OpenCode GUI shows Explore-style Task card",
            "failure_signal": "Gray code block with task(...) in assistant message = failed dispatch",
            "example_tool_call": {
                "subagent_type": "librarian",
                "load_skills": [],
                "description": "Quick research",
                "prompt": "Find something interesting about AI history.",
                "run_in_background": True,
            },
        },
        "user_hint_zh": (
            "必须用 tool call 调用 task，禁止在回复里写 task(...) 代码块。"
            "出现 Task 卡片=成功；出现灰色代码块=失败需重试。"
        ),
        "orchestration_status": "needs_agent"
        if dispatchable
        else ("ok" if orch.get("merge_ready") else "idle"),
        "merge_ready": bool(orch.get("merge_ready")),
    }


def validate_delegation_tool_text_impl(text: str) -> dict[str, Any]:
    """Detect wrong tool usage in agent output or user paste."""
    raw = text or ""
    issues: list[str] = []
    if "call_omo_agent" in raw:
        issues.append(
            "call_omo_agent is removed — use task tool call with "
            "subagent_type, load_skills=[], description, run_in_background"
        )
    for pat in FORBIDDEN_PARAM_PATTERNS:
        if pat.search(raw):
            issues.append(f"forbidden parameter pattern: {pat.pattern}")
    return {
        "status": "ok" if not issues else "invalid",
        "issues": issues,
        "fix": "Use get_task_dispatch_plan() then tool-call task with returned args",
    }


def get_task_dispatch_plan_impl(project_dir: str = "") -> dict[str, Any]:
    """Full task dispatch plan for forge primary."""
    base = build_task_dispatches_impl(project_dir)
    base["after_dispatch"] = [
        "register_from_omo_task_result(omo_result_text=result, ...)",
        "sync_delegation_sessions(project_dir=...)",
        "get_subagent_dashboard(project_dir=..., include_preview=true)",
    ]
    base["after_completion"] = [
        "background_output(task_id=..., block=false)",
        "advance_forge_workflow(...)",
    ]
    base["on_timeout"] = [
        "get_subagent_dashboard(include_preview=true) — check health/issues in live_preview",
        "check_subagent_health(project_dir=...)",
        "recover_stalled_subagent(task_id=..., action=retry) — records error + triggers max_agent_retries retry",
        "opencode run --session <session_id> --continue — manual resume if retry not enough",
        "Split large file writes into smaller batches to avoid Upstream idle timeout",
    ]
    return base
