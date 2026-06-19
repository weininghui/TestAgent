#!/usr/bin/env python3
"""Autonomous SDK Test Generation Agent.

A goal-driven agent that wraps the 6-stage LangChain pipeline into an
autonomous reasoning-and-execution loop.

Usage
-----
    # CLI — natural language goal
    python agent.py --goal "generate tests for C:/MySDK" --model longcat

    # CLI — dry-run (show plan only)
    python agent.py --goal "generate tests for ./my_sdk" --dry-run

    # Import
    from agent import TestGenAgent
    agent = TestGenAgent(model="longcat")
    result = agent.run("generate tests for /path/to/sdk")

    # OpenCode dispatch
    task(category="deep", load_skills=["test-agent"],
         prompt="generate tests for C:/Users/me/sdk")
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from agents.agent_defs import AgentConfig, load_agents
from agents.config import PipelineConfig
from agents.llm import LLMWrapper
from agents.models import get_llm, get_model
from agents.multi_agent import DEFAULT_STAGES, MultiAgentPipeline

logger = logging.getLogger("agent")


# ---------------------------------------------------------------------------
# Intent parsing helpers
# ---------------------------------------------------------------------------

# Known model names (used for intent extraction)
_KNOWN_MODELS = {"default", "gpt-4o", "gpt-4o-mini"}

# Stage aliases  → canonical names
_STAGE_ALIASES: dict[str, str] = {
    "scan": "scanner",
    "scanner": "scanner",
    "scan headers": "scanner",
    "analyze": "analysis",
    "analysis": "analysis",
    "analyse": "analysis",
    "design": "test_design",
    "test design": "test_design",
    "test cases": "test_design",
    "generate": "code_gen",
    "code gen": "code_gen",
    "code generation": "code_gen",
    "generate code": "code_gen",
    "ci": "ci_gen",
    "ci gen": "ci_gen",
    "ci generation": "ci_gen",
    "workflow": "ci_gen",
    "report": "report",
    "all": "all",
}

_STAGE_ORDER = list(DEFAULT_STAGES)


def _resolve_stage_aliases(stages: list[str]) -> list[str]:
    """Resolve user-facing stage names to canonical pipeline stage names."""
    resolved: list[str] = []
    for s in stages:
        s_lower = s.lower().strip()
        if s_lower in _STAGE_ALIASES:
            canonical = _STAGE_ALIASES[s_lower]
            if canonical not in resolved:
                resolved.append(canonical)
        else:
            logger.warning("Unknown stage alias '%s' — ignoring", s)
    return resolved


def _extract_sdk_root(goal: str) -> str | None:
    """Extract an SDK root path from a natural language goal.

    Matches things like ``/path/to/sdk``, ``C:\\path\\to\\sdk``,
    ``./relative/path``, or bare directory names that look like paths.
    """
    # Windows absolute: C:\path or C:/path
    m = re.search(
        r"""(?x)
        (?:sdk[-\s]?(?:root|path|dir|directory)[-\s:]*)?
        (
            [A-Za-z]:[/\\][^\s,;'"]+     # Windows absolute
            |
            /[^\s,;'"]+                  # Unix absolute
            |
            \./[^\s,;'"]+                # Relative
            |
            \.\\[^\s,;'"]+               # Windows relative
        )
        """,
        goal,
    )
    if m:
        return m.group(1).strip()

    # Fallback: look for a path-like word that actually exists on disk
    for word in goal.split():
        word = word.strip(".,;:'\"()[]")
        if word.startswith(("/", ".\\", "./", "\\")) or (
            len(word) > 2 and word[1] == ":"
        ):
            p = Path(word)
            if p.exists() or p.parent.exists():
                return str(p.resolve())
    return None


def _extract_model(goal: str) -> str:
    """Extract a model name from the goal (for display only)."""
    for alias_lower in _KNOWN_MODELS:
        if alias_lower in goal.lower():
            return alias_lower
    from agents.models import get_model_config
    cfg = get_model_config()
    return cfg.model if cfg else "default"


def _extract_output_root(goal: str) -> str:
    """Extract output root from the goal."""
    m = re.search(r"(?:output[-\s]?(?:dir|root|path)[-\s:]*)([^\s,;'\"]+)", goal, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return "./output"


def _extract_stages(goal: str) -> list[str]:
    """Extract desired pipeline stage(s) from the goal."""
    # Look for keywords like "just scan", "only design", "full", "all"
    goal_lower = goal.lower()

    # Explicit full-pipeline phrases → all stages
    full_pipeline_phrases = (
        "full pipeline", "all stages", "complete", "everything",
        "generate tests", "test generation", "test suite",
    )
    if any(phrase in goal_lower for phrase in full_pipeline_phrases):
        return ["all"]

    # "just X" or "only X" → single stage
    single_match = re.search(
        r"\b(just|only)\s+(scan|scanner|analyze|analysis|design|"
        r"generate|code|ci|report)\b",
        goal_lower,
    )
    if single_match:
        return _resolve_stage_aliases([single_match.group(2)])

    # Check how many distinct stage keywords appear
    found_stages: list[str] = []
    for alias in ["scan", "analyze", "design", "generate", "ci", "report"]:
        if re.search(rf"\b{alias}\b", goal_lower):
            resolved = _STAGE_ALIASES.get(alias, "")
            if resolved and resolved not in found_stages:
                found_stages.append(resolved)

    if len(found_stages) > 1:
        # Multiple explicit stages → return specifically those
        return [s for s in _STAGE_ORDER if s in found_stages]

    if len(found_stages) == 1:
        # Single stage without "just"/"only" qualifier —
        # could be part of a general phrase ("generate tests"),
        # so default to all stages unless very narrowly framed.
        return ["all"]

    return ["all"]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class TestGenAgent:
    """Autonomous SDK Test Generation Agent (Main Agent).

    Accepts a high-level goal (natural language), parses the intent,
    selects sub-agents via the :class:`AgentRegistry`, and executes the
    test-generation pipeline autonomously.

    Scenarios
    ---------
    * **Full pipeline** — scan → analyse → design → code-gen → CI → report
    * **Quick scan** — scan + analyse only (stop before code gen)
    * **Error fix** — analyse compilation errors → fix code → re-generate
    * **Incremental update** — re-scan changed headers, update existing tests
    * **Custom subset** — user names specific stages via goal
    * **Report-only** — synthesize report from pre-existing results
    * **Multi-SDK** — run independent pipelines for each SDK root
    """

    def __init__(
        self,
        model: str = "default",
        output_root: str = "./output",
    ) -> None:
        self.model = model
        self.output_root = output_root
        self._agents = load_agents()

    # ------------------------------------------------------------------
    # Per-agent LLM factory
    # ------------------------------------------------------------------

    def _get_llm(self, stage: str | None = None) -> LLMWrapper:
        """Create an :class:`LLMWrapper` for *stage*, respecting agent config.

        When the agent config for *stage* has explicit model/base-url fields
        (set via ``agent_config.json``), this returns a per-agent LLM.
        Otherwise falls back to the default config from ``~/.sdk-test-agent/config.json``.
        """
        candidates = [stage] if stage else ["main"]
        for name in candidates:
            acfg = self._agents.get(name)
            if acfg is None:
                continue
            if acfg.model and acfg.base_url:
                return LLMWrapper(acfg.to_llm_config())
        return get_llm()

    # ------------------------------------------------------------------
    # Sub-agent queries
    # ------------------------------------------------------------------

    def list_agents(
        self,
        role: str | None = None,
        capability: str | None = None,
    ) -> list[dict[str, Any]]:
        """List registered agents, optionally filtered by role or capability."""
        agents = list(self._agents.values())
        if role:
            agents = [a for a in agents if a.role == role]
        if capability:
            agents = [a for a in agents if capability in a.capabilities]
        return [
            {
                "name": a.name,
                "role": a.role,
                "description": a.description,
                "model": a.model,
                "capabilities": list(a.capabilities),
                "tools": list(a.tools),
                "prompt_stage": a.prompt_stage,
            }
            for a in agents
        ]

    def get_agent(self, name: str) -> dict[str, Any] | None:
        """Return a single agent definition by name."""
        agent = self._agents.get(name)
        if not agent:
            return None
        return {
            "name": agent.name,
            "role": agent.role,
            "description": agent.description,
            "model": agent.model,
            "capabilities": list(agent.capabilities),
            "tools": list(agent.tools),
            "prompt_stage": agent.prompt_stage,
        }

    # ------------------------------------------------------------------
    # Scenario detection
    # ------------------------------------------------------------------

    def _detect_scenario(self, goal: str) -> str:
        """Classify the goal into a known scenario.

        Returns one of: ``"full"``, ``"quick_scan"``, ``"error_fix"``,
        ``"incremental"``, ``"custom"``, ``"report_only"``, ``"multi_sdk"``.
        """
        goal_lower = goal.lower()

        if re.search(r"\breport\b", goal_lower) and not re.search(
            r"\b(scan|generate|code|test)\b", goal_lower
        ):
            return "report_only"

        if re.search(r"\b(error|fix|repair|retry|compile)\b", goal_lower):
            return "error_fix"

        if re.search(r"\b(incremental|update|refresh|re.san)\b", goal_lower):
            return "incremental"

        if re.search(r"\b(quick|just\s+scan|only\s+scan|preview)\b", goal_lower):
            return "quick_scan"

        if re.search(r"SDK[-\s]?(root|path|dir)", goal_lower, re.IGNORECASE) and \
           goal_lower.count("sdk") > 1:
            return "multi_sdk"

        # Check for explicit stage subset
        stage_count = sum(
            1 for s in ("scan", "analyze", "design", "generate", "ci", "report")
            if re.search(rf"\b{s}\b", goal_lower)
        )
        if 0 < stage_count < 6:
            # Check whether it looks like a full-pipeline phrase
            full_phrases = (
                "full pipeline", "all stages", "complete",
                "generate tests", "test suite", "test generation",
            )
            if not any(p in goal_lower for p in full_phrases):
                return "custom"

        return "full"

    def _scenario_stages(self, scenario: str, goal: str) -> list[str] | None:
        """Return the stages to execute for a given scenario.

        Returns ``None`` to signal that the scenario is handled separately.
        """
        if scenario == "quick_scan":
            return ["scanner", "analysis"]
        if scenario == "report_only":
            return ["report"]
        if scenario == "error_fix":
            # Error fix: re-run code_gen (with fix context)
            return ["code_gen"]
        if scenario == "incremental":
            return ["scanner", "analysis", "test_design", "code_gen"]
        if scenario in ("full", "multi_sdk"):
            return None  # full pipeline — caller uses DEFAULT_STAGES
        return None  # custom — caller uses extracted stages

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, goal: str) -> dict[str, Any]:
        """Execute a high-level goal and return structured results.

        Parameters
        ----------
        goal : str
            Natural language goal describing what tests to generate and for
            which SDK.

        Returns
        -------
        dict
            Keys: ``status``, ``sdk_root``, ``model``, ``stages_executed``,
            ``stage_results``, ``errors`` (if any).
        """
        # 1 — Parse intent
        sdk_root = _extract_sdk_root(goal)
        model = _extract_model(goal)
        stages = _extract_stages(goal)
        output_root = _extract_output_root(goal)

        if not sdk_root:
            return {
                "status": "error",
                "error": "Could not determine SDK root from goal.",
                "help": (
                    "Include the SDK path in your goal, e.g.: "
                    '"generate tests for C:/path/to/sdk"'
                ),
                "goal": goal,
            }

        sdk_root = str(Path(sdk_root).resolve())

        # 1b — Detect scenario and resolve stages
        scenario = self._detect_scenario(goal)
        scenario_stages = self._scenario_stages(scenario, goal)
        resolved_stages: list[str] = (
            scenario_stages
            if scenario_stages is not None
            else (_STAGE_ORDER if "all" in stages else stages)
        )

        # Look up the sub-agent config for each stage
        sub_agents: dict[str, dict[str, Any]] = {}
        for stage in resolved_stages:
            acfg = self._agents.get(stage)
            if acfg:
                sub_agents[stage] = {
                    "name": acfg.name,
                    "role": acfg.role,
                    "model": acfg.model,
                    "prompt_stage": acfg.prompt_stage,
                }

        logger.info(
            "Agent goal parsed — scenario=%s sdk_root=%s model=%s stages=%s agents=%d",
            scenario, sdk_root, model, resolved_stages, len(sub_agents),
        )

        # 2 — Plan summary (log it for transparency)
        plan = self._build_plan(sdk_root, model, resolved_stages, output_root)
        plan["scenario"] = scenario
        plan["sub_agents"] = sub_agents
        logger.info("Agent plan:\n%s", json.dumps(plan, indent=2, default=str))

        # 3 — Build and run multi-agent pipeline
        try:
            llm = self._get_llm()
            cfg = PipelineConfig(
                sdk_root=sdk_root,
                output_root=output_root,
                llm_enabled=True,
                model=model,
            )
            pipeline = MultiAgentPipeline(llm=llm, config=cfg.as_dict())
        except Exception as exc:
            return {
                "status": "error",
                "error": f"Multi-agent pipeline initialisation failed: {exc}",
                "plan": plan,
            }

        try:
            result: dict = pipeline.run(
                goal=goal,
                sdk_root=sdk_root,
                stages=resolved_stages,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": f"Multi-agent pipeline execution failed: {exc}",
                "plan": plan,
            }

        # 4 — Synthesise results
        gen_dir = Path(output_root) / "generated"
        try:
            files = sorted(gen_dir.rglob("*.cpp")) + sorted(gen_dir.rglob("*.h"))
        except Exception:
            files = []

        # Extract stage results from the graph state
        stage_key_map: dict[str, str] = {
            "scanner": "api_inventory",
            "analysis": "analysis_report",
            "test_design": "test_collection",
            "code_gen": "code_gen_result",
            "ci_gen": "ci_gen_result",
            "report": "report_result",
        }
        stage_results: dict[str, Any] = {}
        for stage_name in resolved_stages:
            state_key = stage_key_map.get(stage_name)
            if state_key and state_key in result:
                stage_results[stage_name] = self._summarise(result[state_key])

        return {
            "status": result.get("status", "success"),
            "scenario": scenario,
            "sdk_root": sdk_root,
            "model": model,
            "stages_executed": resolved_stages,
            "sub_agents": sub_agents,
            "stage_results": stage_results,
            "generated_files": [str(f) for f in files[:50]],
            "plan": plan,
        }

    def plan(self, goal: str) -> dict[str, Any]:
        """Analyse a goal and return the execution plan without running it.

        Useful for ``--dry-run`` mode or previewing before execution.
        """
        sdk_root = _extract_sdk_root(goal)
        model = _extract_model(goal)
        stages = _extract_stages(goal)
        output_root = _extract_output_root(goal)

        if sdk_root:
            sdk_root = str(Path(sdk_root).resolve())

        scenario = self._detect_scenario(goal)
        scenario_stages = self._scenario_stages(scenario, goal)
        resolved_stages: list[str] = (
            scenario_stages
            if scenario_stages is not None
            else (_STAGE_ORDER if "all" in stages else stages)
        )

        plan = self._build_plan(sdk_root, model, resolved_stages, output_root)
        plan["scenario"] = scenario

        # Attach sub-agent info
        sub_agents: dict[str, dict[str, Any]] = {}
        for stage in resolved_stages:
            acfg = self._agents.get(stage)
            if acfg:
                sub_agents[stage] = {
                    "name": acfg.name,
                    "role": acfg.role,
                    "model": acfg.model,
                    "prompt_stage": acfg.prompt_stage,
                }
        plan["sub_agents"] = sub_agents

        return plan

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_plan(
        self,
        sdk_root: str | None,
        model: str,
        stages: list[str],
        output_root: str,
    ) -> dict[str, Any]:
        return {
            "sdk_root": sdk_root,
            "model": model,
            "stages": stages,
            "output_root": output_root,
            "sdk_exists": sdk_root is not None and Path(sdk_root).is_dir(),
            "pipeline_description": (
                f"Run {len(stages)} stage(s) on SDK at {sdk_root}"
                f" using model '{model}'"
            ),
        }

    @staticmethod
    def _summarise(value: object) -> str:
        """Return a short summary of a stage result."""
        if value is None:
            return "(none)"
        if isinstance(value, str):
            return value[:200]
        if hasattr(value, "model_dump"):
            d = value.model_dump()
        elif hasattr(value, "to_dict"):
            d = value.to_dict()
        else:
            d = str(value)
        s = json.dumps(d, default=str)
        return s[:200] + ("…" if len(s) > 200 else "")


# ---------------------------------------------------------------------------
# Interactive entry point — invoked by OpenCode when TestGen agent is active
#
# Usage:
#   python agent.py --goal "generate tests for /path/to/sdk" [--model longcat] [--dry-run]
#
# When no --goal is provided, reads from stdin (for OpenCode agent mode).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SDK Test Generation Agent")
    parser.add_argument("--goal", type=str, default=None, help="Natural language goal")
    parser.add_argument("--model", type=str, default=None, help="Model preset name")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s [%(name)s] %(message)s",
    )

    goal = args.goal
    if not goal:
        # Read from stdin (piped input or OpenCode agent mode)
        goal = sys.stdin.read().strip()

    if not goal:
        print(json.dumps({"error": "No goal provided. Pass --goal or pipe input."}, ensure_ascii=False))
        sys.exit(1)

    try:
        agent = TestGenAgent(model=args.model or "default")

        if args.dry_run:
            result = agent.plan(goal)
            result["status"] = "dry_run"
        else:
            result = agent.run(goal)

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        if result.get("status") in ("error", "dry_run"):
            sys.exit(0 if args.dry_run else 1)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
