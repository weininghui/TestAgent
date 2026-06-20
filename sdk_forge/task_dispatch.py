"""OMO task() dispatch builder aligned with OpenCode GUI Task cards (v5.9)."""

from __future__ import annotations

import re
from typing import Any

from sdk_forge.delegation import delegation_concurrency, delegation_mode
from sdk_forge.orchestration import get_orchestration_context

FORBIDDEN_TOOLS = ("call_omo_agent",)
FORBIDDEN_PARAM_PATTERNS = (
    re.compile(r"\btask\s*\(\s*agent\s*=", re.IGNORECASE),
    re.compile(r"\btitle\s*=", re.IGNORECASE),
)

TASK_GUI_MODES = frozenset({"omo", "task"})


def normalize_delegation_mode(mode: str) -> str:
    """`task` is an alias for `omo` (OpenCode GUI Task card path)."""
    m = (mode or "omo").strip().lower()
    if m == "task":
        return "omo"
    return m


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
    mode = normalize_delegation_mode(orch.get("delegation_mode") or delegation_mode(project_dir))
    gui_task_card = mode in TASK_GUI_MODES
    dispatchable = [a for a in actions if not a.get("blocked")]

    dispatches: list[dict[str, Any]] = []
    for action in dispatchable:
        if mode == "cli":
            dispatches.append({
                "tool": "dispatch_forge_delegate",
                "args": {
                    "agent": action.get("agent"),
                    "prompt": action.get("prompt_hint") or action.get("prompt"),
                    "batch_id": action.get("batch_id"),
                    "title": action.get("description"),
                },
                "gui_expect": "No Task card — CLI subprocess fallback",
            })
            continue
        if mode == "inline":
            dispatches.append({
                "tool": "task",
                "args": {
                    "subagent_type": action.get("subagent_type") or action.get("agent"),
                    "load_skills": action.get("load_skills", []),
                    "description": action.get("description"),
                    "prompt": action.get("prompt_hint") or action.get("prompt"),
                    "run_in_background": False,
                },
                "gui_expect": "No OMO Task card — inline sync fallback",
                "gui_task_card": False,
            })
            continue
        dispatches.append(build_omo_task_call(action))

    parallel = [d for d in dispatches if d.get("args", {}).get("run_in_background")]
    serial = [d for d in dispatches if not d.get("args", {}).get("run_in_background")]
    background = [a for a in dispatchable if a.get("run_in_background")]
    foreground = [a for a in dispatchable if not a.get("run_in_background")]

    return {
        "status": "ok",
        "delegation_mode": mode,
        "delegation_concurrency": orch.get("delegation_concurrency") or delegation_concurrency(project_dir),
        "dispatch_protocol": "omo_task_only" if gui_task_card else f"{mode}_fallback",
        "gui_task_card": gui_task_card,
        "forbidden_tools": list(FORBIDDEN_TOOLS),
        "forbidden_params": ["task(agent=...)", "title="],
        "task_dispatches": dispatches,
        "parallel_dispatches": parallel,
        "serial_dispatches": serial,
        "background_actions": background,
        "foreground_actions": foreground,
        "fire_parallel_in_one_turn": len(parallel) > 1,
        "user_hint_zh": (
            "同一轮回复内并行调用所有 parallel_dispatches 的 task()，GUI 应显示 Task 卡片"
            if gui_task_card
            else "当前为后备模式，GUI 不会出现 OMO Task 卡片"
        ),
        "orchestration_status": "needs_agent" if dispatchable else ("ok" if orch.get("merge_ready") else "idle"),
        "merge_ready": bool(orch.get("merge_ready")),
    }


def validate_delegation_tool_text_impl(text: str) -> dict[str, Any]:
    """Detect wrong tool usage in agent output or user paste."""
    raw = text or ""
    issues: list[str] = []
    if "call_omo_agent" in raw:
        issues.append(
            "call_omo_agent does not render OpenCode Task cards — use "
            "task(subagent_type=..., load_skills=[], description=..., run_in_background=...)"
        )
    for pat in FORBIDDEN_PARAM_PATTERNS:
        if pat.search(raw):
            issues.append(f"forbidden parameter pattern: {pat.pattern}")
    return {
        "status": "ok" if not issues else "invalid",
        "issues": issues,
        "fix": "Use get_task_dispatch_plan() and invoke task() with returned args",
    }


def get_task_dispatch_plan_impl(project_dir: str = "") -> dict[str, Any]:
    """Full task dispatch plan for forge primary (v5.9)."""
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
    return base
