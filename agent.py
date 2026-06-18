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

from agents.config import PipelineConfig
from agents.models import get_llm
from agents.multi_agent import DEFAULT_STAGES, MultiAgentPipeline

logger = logging.getLogger("agent")


# ---------------------------------------------------------------------------
# Intent parsing helpers
# ---------------------------------------------------------------------------

# Known model presets (used for intent extraction)
_KNOWN_MODELS = {"longcat", "dashscope", "default", "gpt-4o", "gpt-4o-mini"}

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
    """Extract a model preset name from the goal."""
    for alias_lower in _KNOWN_MODELS:
        if alias_lower in goal.lower():
            return alias_lower
    return "longcat"


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
    """Autonomous SDK Test Generation Agent.

    Accepts a high-level goal (natural language), parses the intent, and
    executes the test-generation pipeline autonomously.
    """

    def __init__(
        self,
        model: str = "longcat",
        output_root: str = "./output",
    ) -> None:
        self.model = model
        self.output_root = output_root

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
        resolved_stages: list[str] = (
            _STAGE_ORDER if "all" in stages else stages
        )

        logger.info(
            "Agent goal parsed — sdk_root=%s model=%s stages=%s",
            sdk_root, model, resolved_stages,
        )

        # 2 — Plan summary (log it for transparency)
        plan = self._build_plan(sdk_root, model, resolved_stages, output_root)
        logger.info("Agent plan:\n%s", json.dumps(plan, indent=2, default=str))

        # 3 — Build and run multi-agent pipeline
        try:
            llm = get_llm(model)
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
            "sdk_root": sdk_root,
            "model": model,
            "stages_executed": resolved_stages,
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

        resolved_stages: list[str] = (
            _STAGE_ORDER if "all" in stages else stages
        )

        return self._build_plan(sdk_root, model, resolved_stages, output_root)

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
# CLI entry point
# ---------------------------------------------------------------------------


def clicli_main() -> None:
    """CLI entry point — parse arguments and run the agent."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SDK Test Generation Agent — autonomous goal-driven entry point",
    )
    parser.add_argument(
        "--goal", "-g",
        default=None,
        help="Natural language goal (e.g. 'generate tests for C:/sdk')",
    )
    parser.add_argument(
        "--sdk-root",
        default=None,
        help="SDK root (overrides goal parsing)",
    )
    parser.add_argument(
        "--model", "-m",
        default="longcat",
        help="Model preset name (default: longcat)",
    )
    parser.add_argument(
        "--output-root", "-o",
        default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show execution plan without running the pipeline",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    agent = TestGenAgent(model=args.model, output_root=args.output_root)

    # Build goal string
    goal_parts: list[str] = []
    if args.goal:
        goal_parts.append(args.goal)
    if args.sdk_root:
        goal_parts.append(f"sdk root: {args.sdk_root}")
    goal = " ".join(goal_parts) if goal_parts else ""

    if not goal:
        # Interactive prompt
        goal = input("🎯 Enter goal for the test generation agent: ").strip()
        if not goal:
            print("No goal provided. Use --help for usage.")
            sys.exit(1)

    if args.dry_run:
        plan = agent.plan(goal)
        print(json.dumps(plan, indent=2, default=str, ensure_ascii=False))
        return

    result = agent.run(goal)
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))

    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    clicli_main()
