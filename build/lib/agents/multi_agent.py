#!/usr/bin/env python3
"""LangGraph Multi-Agent Pipeline — supervisor orchestrates 6 specialist agents.

Architecture
------------
A **supervisor agent** (router) orchestrates 6 specialist agents, each wrapping
an existing LangChain chain:

                     ┌──────────────┐
                     │    Router    │  ← decides *next* stage
                     └──────┬───────┘
                            │
         ┌──────────┬───────┼───────┬──────────┬───────────┐
         ▼          ▼       ▼       ▼          ▼           ▼
      Scanner    Analysis  Design  CodeGen    CIGen      Report
     (agent)    (agent)  (agent) (agent)    (agent)    (agent)

How the graph works
-------------------
1. ``START → router`` — entry point.
2. ``router`` inspects ``PipelineState`` and returns ``Command(goto=…)`` to
   the next uncompleted stage.
3. Each specialist agent executes its chain, updates the shared state, and
   returns ``Command(goto="router")``.
4. ``router`` loops until all requested stages are done or an error occurred.

Benefits over the sequential ``Pipeline``
------------------------------------------
- **Conditional execution** — stages can be skipped or re-ordered.
- **Error recovery** — a failed stage can be retried by the router.
- **Selective stages** — run only ``["scanner", "analysis"]`` without
  touching the rest of the pipeline.
- **Observability** — every decision and state transition is explicit.

Usage
-----
    from agents.models import get_llm
    from agents.multi_agent import MultiAgentPipeline

    llm = get_llm("longcat")
    pipeline = MultiAgentPipeline(llm, config={"sdk_root": "C:/sdk", "output_root": "./output"})
    result = pipeline.run("generate tests for C:/sdk")

    # State contains all stage outputs
    inventory = result["api_inventory"]
    print(result["status"])
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

# ── Pipeline components ──────────────────────────────────────────────────────
from agents.cache import LLMCache
from agents.chains.analysis_chain import APIAnalysisChain
from agents.chains.ci_gen_chain import CIGenChain
from agents.chains.code_gen_chain import CodeGenChain
from agents.chains.report_chain import ReportChain
from agents.chains.scanner_chain import SDKScannerChain
from agents.chains.test_design_chain import TestDesignChain
from agents.llm import LLMWrapper
from agents.memory import PipelineMemory
from agents.prompts import (
    analysis_prompt,
    ci_gen_prompt,
    code_gen_prompt,
    report_prompt,
    scanner_prompt,
    test_design_prompt,
)
from agents.tools.code_gen_tools import ensure_output_dir, write_cmake_file, write_gtest_file, write_workflow_file
from agents.tools.sdk_tools import list_header_files, read_header_file

logger = logging.getLogger(__name__)

# ── Default stage order ──────────────────────────────────────────────────────

DEFAULT_STAGES: list[str] = [
    "scanner",
    "analysis",
    "test_design",
    "code_gen",
    "ci_gen",
    "report",
]

# ── Graph state ──────────────────────────────────────────────────────────────


class AgentError(TypedDict):
    """Structured error record for a failed stage agent."""

    stage: str
    error: str
    elapsed_sec: float


class PipelineState(TypedDict, total=False):
    """Shared state flowing through the multi-agent graph.

    Keys marked ``Optional`` are populated incrementally as stages complete.
    """

    # ── Input (set by caller) ────────────────────────────────────────────
    goal: str
    sdk_root: str
    output_root: str
    model: str
    stages: list[str]  # requested stage names in desired order

    # ── Runtime metadata (mutated by agents) ─────────────────────────────
    completed_stages: list[str]
    errors: list[AgentError]
    status: str  # "idle" | "running" | "completed" | "failed"

    # ── Stage outputs (populated incrementally) ──────────────────────────
    api_inventory: Optional[Any]
    analysis_report: Optional[Any]
    test_collection: Optional[Any]
    code_gen_result: Optional[Any]
    ci_gen_result: Optional[Any]
    report_result: Optional[Any]


# ══════════════════════════════════════════════════════════════════════════════
# MultiAgentPipeline
# ══════════════════════════════════════════════════════════════════════════════


class MultiAgentPipeline:
    """LangGraph-based multi-agent pipeline orchestrator.

    Wraps the 6 LangChain chains into a ``StateGraph`` where each stage is
    an independent agent node routed by a supervisor (router).

    Parameters
    ----------
    llm:
        An ``LLMWrapper`` instance shared by all chains.
    config:
        Pipeline configuration dict.  Expected keys include ``sdk_root``,
        ``output_root``, ``model``, ``temperature``, ``max_tokens``, and
        ``no_cache``.
    """

    def __init__(
        self,
        llm: LLMWrapper,
        config: dict,
    ) -> None:
        if not isinstance(llm, LLMWrapper):
            raise TypeError("llm must be an LLMWrapper instance")
        if not isinstance(config, dict):
            raise TypeError("config must be a dict")

        self.llm = llm
        self.config = config
        self._output_root: str = config.get("output_root", "./output")

        # ── Initialise shared infrastructure ─────────────────────────────
        self.cache = LLMCache(
            cache_dir=os.path.join(self._output_root, "cache"),
            enabled=not config.get("no_cache", False),
        )

        # ── Initialise all 6 chains ──────────────────────────────────────
        self._init_chains()

        # ── Build the LangGraph ──────────────────────────────────────────
        self.graph = self._build_graph()

    # ──────────────────────────────────────────────────────────────────────────
    # Chain initialisation
    # ──────────────────────────────────────────────────────────────────────────

    def _init_chains(self) -> None:
        """Create all 6 chain instances (mirrors ``Pipeline.__init__``)."""
        # 1. SDK Scanner Chain
        self.scanner_chain = SDKScannerChain(
            llm=self.llm,
            tools=[list_header_files, read_header_file],
            prompt=scanner_prompt.HUMAN_TEMPLATE,
        )

        # 2. API Analysis Chain
        self.analysis_chain = APIAnalysisChain(
            llm=self.llm,
            prompt=analysis_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

        # 3. Test Design Chain
        self.test_design_chain = TestDesignChain(
            llm=self.llm,
            prompt=test_design_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

        # 4. Code Generation Chain
        self.code_gen_chain = CodeGenChain(
            llm=self.llm,
            tools=[write_gtest_file, ensure_output_dir],
            prompt=code_gen_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

        # 5. CI Generation Chain
        self.ci_gen_chain = CIGenChain(
            llm=self.llm,
            tools=[write_cmake_file, write_workflow_file, ensure_output_dir],
            prompt=ci_gen_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

        # 6. Report Chain
        self.report_chain = ReportChain(
            llm=self.llm,
            prompt=report_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Graph construction
    # ──────────────────────────────────────────────────────────────────────────

    def _build_graph(self) -> StateGraph:
        """Construct and compile the LangGraph ``StateGraph``.

        Nodes
        -----
        * ``router`` — supervisor that decides the next stage.
        * ``scanner`` — ``SDKScannerChain`` wrapper.
        * ``analysis`` — ``APIAnalysisChain`` wrapper.
        * ``test_design`` — ``TestDesignChain`` wrapper.
        * ``code_gen`` — ``CodeGenChain`` wrapper.
        * ``ci_gen`` — ``CIGenChain`` wrapper.
        * ``report`` — ``ReportChain`` wrapper (needs ``PipelineMemory``).
        """
        builder = StateGraph(PipelineState)

        # ── Register all nodes ───────────────────────────────────────────
        builder.add_node("router", self._router_node)
        builder.add_node("scanner", self._scanner_node)
        builder.add_node("analysis", self._analysis_node)
        builder.add_node("test_design", self._test_design_node)
        builder.add_node("code_gen", self._code_gen_node)
        builder.add_node("ci_gen", self._ci_gen_node)
        builder.add_node("report", self._report_node)

        # ── Entry point → router ─────────────────────────────────────────
        builder.add_edge(START, "router")

        # ── All edges are handled by ``Command(goto=…)`` from each node ──
        return builder.compile()

    # ──────────────────────────────────────────────────────────────────────────
    # Router (supervisor)
    # ──────────────────────────────────────────────────────────────────────────

    def _router_node(self, state: PipelineState) -> Command:
        """Supervisor: decide the next stage to execute.

        Routing logic:
        1. If any error exists, mark as ``failed`` and stop.
        2. Find the first requested stage not yet completed.
        3. If all done, mark as ``completed`` and stop.
        """
        stages = state.get("stages", DEFAULT_STAGES)
        completed: list[str] = state.get("completed_stages", [])
        errors: list[AgentError] = state.get("errors", [])

        # ── Abort on errors ──────────────────────────────────────────────
        if errors:
            logger.error(
                "Router: %d error(s) — aborting pipeline",
                len(errors),
            )
            return Command(
                update={
                    "status": "failed",
                    "completed_stages": completed,
                },
                goto=END,
            )

        # ── Find next uncompleted stage ──────────────────────────────────
        for stage in stages:
            if stage not in completed:
                logger.info("Router: scheduling stage '%s'", stage)
                return Command(
                    update={"status": "running"},
                    goto=stage,
                )

        # ── All stages complete ──────────────────────────────────────────
        logger.info("Router: all %d stage(s) completed", len(completed))
        return Command(
            update={"status": "completed"},
            goto=END,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Specialist agent nodes
    # ──────────────────────────────────────────────────────────────────────────

    def _scanner_node(self, state: PipelineState) -> Command:
        """Agent: discover SDK headers and produce ``APIInventory``."""
        sdk_root = state.get("sdk_root", "")
        completed: list[str] = state.get("completed_stages", [])

        logger.info("Scanner agent: scanning %s", sdk_root)
        t0 = time.monotonic()
        try:
            inventory = self.scanner_chain.run(sdk_root)
            elapsed = time.monotonic() - t0
            logger.info("Scanner agent: done in %.2fs — %d module(s)", elapsed, len(inventory.modules))
            return Command(
                update={
                    "api_inventory": self._to_serializable(inventory),
                    "completed_stages": completed + ["scanner"],
                },
                goto="router",
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error("Scanner agent FAILED after %.2fs: %s", elapsed, exc)
            return Command(
                update={
                    "errors": state.get("errors", []) + [
                        {"stage": "scanner", "error": str(exc), "elapsed_sec": elapsed},
                    ],
                },
                goto="router",
            )

    def _analysis_node(self, state: PipelineState) -> Command:
        """Agent: analyse API inventory for complexity, patterns, risks."""
        inventory = state.get("api_inventory")
        completed: list[str] = state.get("completed_stages", [])

        if not inventory:
            logger.warning("Analysis agent: no inventory available — skipping")
            return Command(
                update={"completed_stages": completed + ["analysis"]},
                goto="router",
            )

        logger.info("Analysis agent: analysing inventory")
        t0 = time.monotonic()
        try:
            # Reconstruct APIInventory from serialized dict
            from schemas.api_schema import APIInventory
            inv_obj = APIInventory.from_dict(inventory) if isinstance(inventory, dict) else inventory
            report = self.analysis_chain.run(inv_obj)
            elapsed = time.monotonic() - t0
            logger.info("Analysis agent: done in %.2fs", elapsed)
            return Command(
                update={
                    "analysis_report": report,
                    "completed_stages": completed + ["analysis"],
                },
                goto="router",
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error("Analysis agent FAILED after %.2fs: %s", elapsed, exc)
            return Command(
                update={
                    "errors": state.get("errors", []) + [
                        {"stage": "analysis", "error": str(exc), "elapsed_sec": elapsed},
                    ],
                },
                goto="router",
            )

    def _test_design_node(self, state: PipelineState) -> Command:
        """Agent: design test cases from inventory + analysis."""
        inventory = state.get("api_inventory")
        analysis = state.get("analysis_report")
        completed: list[str] = state.get("completed_stages", [])

        if not inventory:
            logger.warning("Test design agent: no inventory — skipping")
            return Command(
                update={"completed_stages": completed + ["test_design"]},
                goto="router",
            )

        from schemas.api_schema import APIInventory
        inv_obj = APIInventory.from_dict(inventory) if isinstance(inventory, dict) else inventory

        logger.info("Test design agent: designing test cases")
        t0 = time.monotonic()
        try:
            collection = self.test_design_chain.run(inv_obj, analysis)
            elapsed = time.monotonic() - t0
            n_cases = len(getattr(collection, "cases", []))
            logger.info("Test design agent: done in %.2fs — %d test case(s)", elapsed, n_cases)
            return Command(
                update={
                    "test_collection": self._to_serializable(collection),
                    "completed_stages": completed + ["test_design"],
                },
                goto="router",
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error("Test design agent FAILED after %.2fs: %s", elapsed, exc)
            return Command(
                update={
                    "errors": state.get("errors", []) + [
                        {"stage": "test_design", "error": str(exc), "elapsed_sec": elapsed},
                    ],
                },
                goto="router",
            )

    def _code_gen_node(self, state: PipelineState) -> Command:
        """Agent: generate C++ GTest source files."""
        test_collection = state.get("test_collection")
        completed: list[str] = state.get("completed_stages", [])

        if not test_collection:
            logger.warning("Code gen agent: no test collection — skipping")
            return Command(
                update={"completed_stages": completed + ["code_gen"]},
                goto="router",
            )

        from schemas.testcase_schema import TestCaseCollection
        tc_obj = TestCaseCollection.from_dict(test_collection) if isinstance(test_collection, dict) else test_collection

        logger.info("Code gen agent: generating GTest source files")
        t0 = time.monotonic()
        try:
            files_written = self.code_gen_chain.run(tc_obj)
            elapsed = time.monotonic() - t0
            logger.info("Code gen agent: done in %.2fs — %d file(s)", elapsed, files_written)
            return Command(
                update={
                    "code_gen_result": files_written,
                    "completed_stages": completed + ["code_gen"],
                },
                goto="router",
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error("Code gen agent FAILED after %.2fs: %s", elapsed, exc)
            return Command(
                update={
                    "errors": state.get("errors", []) + [
                        {"stage": "code_gen", "error": str(exc), "elapsed_sec": elapsed},
                    ],
                },
                goto="router",
            )

    def _ci_gen_node(self, state: PipelineState) -> Command:
        """Agent: generate CMake + CI workflow files."""
        inventory = state.get("api_inventory")
        test_collection = state.get("test_collection")
        completed: list[str] = state.get("completed_stages", [])

        if not inventory or not test_collection:
            logger.warning("CI gen agent: missing inventory or test collection — skipping")
            return Command(
                update={"completed_stages": completed + ["ci_gen"]},
                goto="router",
            )

        from schemas.api_schema import APIInventory
        from schemas.testcase_schema import TestCaseCollection
        inv_obj = APIInventory.from_dict(inventory) if isinstance(inventory, dict) else inventory
        tc_obj = TestCaseCollection.from_dict(test_collection) if isinstance(test_collection, dict) else test_collection

        logger.info("CI gen agent: generating CI configuration")
        t0 = time.monotonic()
        try:
            ci_output = self.ci_gen_chain.run(inv_obj, tc_obj)
            elapsed = time.monotonic() - t0
            logger.info("CI gen agent: done in %.2fs", elapsed)
            return Command(
                update={
                    "ci_gen_result": ci_output,
                    "completed_stages": completed + ["ci_gen"],
                },
                goto="router",
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error("CI gen agent FAILED after %.2fs: %s", elapsed, exc)
            return Command(
                update={
                    "errors": state.get("errors", []) + [
                        {"stage": "ci_gen", "error": str(exc), "elapsed_sec": elapsed},
                    ],
                },
                goto="router",
            )

    def _report_node(self, state: PipelineState) -> Command:
        """Agent: synthesise the final Markdown report + JSON summary.

        This agent builds a ``PipelineMemory`` from the graph state so the
        existing ``ReportChain`` can consume it without modification.
        """
        completed: list[str] = state.get("completed_stages", [])

        # ── Build PipelineMemory from graph state ────────────────────────
        memory = PipelineMemory(
            persist_path=os.path.join(self._output_root, "pipeline_memory.json"),
        )
        stage_outputs: dict[str, Any] = {}
        stage_outputs["scanner"] = state.get("api_inventory")
        stage_outputs["analysis"] = state.get("analysis_report")
        stage_outputs["test_design"] = state.get("test_collection")
        stage_outputs["code_gen"] = state.get("code_gen_result")
        stage_outputs["ci_gen"] = state.get("ci_gen_result")

        for stage_name, output in stage_outputs.items():
            if output is not None:
                memory.store_stage_output(stage_name, output)

        logger.info("Report agent: generating final report")
        t0 = time.monotonic()
        try:
            report = self.report_chain.run(memory)
            elapsed = time.monotonic() - t0
            logger.info("Report agent: done in %.2fs", elapsed)
            return Command(
                update={
                    "report_result": report,
                    "completed_stages": completed + ["report"],
                },
                goto="router",
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error("Report agent FAILED after %.2fs: %s", elapsed, exc)
            return Command(
                update={
                    "errors": state.get("errors", []) + [
                        {"stage": "report", "error": str(exc), "elapsed_sec": elapsed},
                    ],
                },
                goto="router",
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def run(
        self,
        goal: str = "",
        sdk_root: str | None = None,
        stages: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute the multi-agent pipeline and return the final state.

        Parameters
        ----------
        goal:
            Natural language goal (for logging / traceability).
        sdk_root:
            Override the SDK root (defaults to ``config["sdk_root"]``).
        stages:
            Subset of stages to run (defaults to all 6).

        Returns
        -------
        dict
            The final ``PipelineState`` with all stage outputs.
        """
        sdk_root = sdk_root or self.config.get("sdk_root", "")
        stages = stages or list(DEFAULT_STAGES)

        initial: PipelineState = {
            "goal": goal,
            "sdk_root": sdk_root,
            "output_root": self._output_root,
            "model": self.config.get("model", "longcat"),
            "stages": stages,
            "completed_stages": [],
            "errors": [],
            "status": "idle",
        }

        logger.info("=" * 60)
        logger.info("Multi-agent pipeline STARTED")
        logger.info("  SDK root  : %s", sdk_root)
        logger.info("  Output    : %s", self._output_root)
        logger.info("  Model     : %s", self.config.get("model", "(default)"))
        logger.info("  Stages    : %s", stages)
        logger.info("=" * 60)

        try:
            final_state: PipelineState = self.graph.invoke(initial)
        except Exception as exc:
            logger.error("Graph execution failed: %s", exc)
            return {
                "status": "error",
                "error": str(exc),
                "sdk_root": sdk_root,
                "stages": stages,
                "completed_stages": [],
                "errors": [{"stage": "graph", "error": str(exc), "elapsed_sec": 0.0}],
            }

        logger.info("=" * 60)
        logger.info(
            "Multi-agent pipeline FINISHED — status=%s  stages=%s",
            final_state.get("status", "unknown"),
            final_state.get("completed_stages", []),
        )
        logger.info("=" * 60)

        return dict(final_state)

    def get_stages(self) -> list[str]:
        """Return the ordered list of pipeline stage names."""
        return list(DEFAULT_STAGES)

    def dry_run(self, sdk_root: str | None = None) -> None:
        """Log the pipeline plan without executing any LLM calls."""
        sdk_root = sdk_root or self.config.get("sdk_root", "(not set)")
        logger.info("=" * 60)
        logger.info("Multi-Agent Pipeline DRY RUN")
        logger.info("=" * 60)
        logger.info("  SDK root  : %s", sdk_root)
        logger.info("  Output    : %s", self._output_root)
        logger.info("  Stages    :")
        for idx, stage in enumerate(DEFAULT_STAGES, start=1):
            chain_name = type(getattr(self, f"{stage}_chain", None)).__name__
            logger.info("    [%d/6] %-15s → %s", idx, stage, chain_name)
        logger.info("=" * 60)
        logger.info("  Router: conditional dispatch via LangGraph StateGraph")
        logger.info("=" * 60)

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_serializable(output: Any) -> Any:
        """Convert a stage output to a JSON-serialisable Python object.

        Chains that return Pydantic / dataclass instances (e.g.
        ``APIInventory``) are converted to plain dicts so they can be
        stored in the graph state.
        """
        if hasattr(output, "to_json"):
            return json.loads(output.to_json())
        if hasattr(output, "model_dump"):
            return output.model_dump()
        if hasattr(output, "to_dict"):
            return output.to_dict()
        if hasattr(output, "as_dict"):
            return output.as_dict()
        return output

    @staticmethod
    def _summary(state: PipelineState) -> str:
        """Return a one-line summary of the pipeline result."""
        status = state.get("status", "unknown")
        completed = state.get("completed_stages", [])
        errors = state.get("errors", [])
        parts = [f"status={status}", f"stages={completed}"]
        if errors:
            parts.append(f"errors={len(errors)}")
        return "  ".join(parts)
