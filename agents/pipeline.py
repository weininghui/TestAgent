"""Pipeline Orchestrator — sequential stage execution with error handling.

Initialises all 6 chains (scanner, analysis, test_design, code_gen, ci_gen,
report) together with a shared ``LLMCache`` and ``PipelineMemory``, then
orchestrates sequential stage execution with progress logging, timing,
error propagation, and optional dry-run support.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from agents.llm import LLMWrapper
from agents.cache import LLMCache
from agents.memory import PipelineMemory
from agents.chains.scanner_chain import SDKScannerChain
from agents.chains.analysis_chain import APIAnalysisChain
from agents.chains.test_design_chain import TestDesignChain
from agents.chains.code_gen_chain import CodeGenChain
from agents.chains.ci_gen_chain import CIGenChain
from agents.chains.report_chain import ReportChain
from agents.prompts import scanner_prompt, analysis_prompt, test_design_prompt, code_gen_prompt, ci_gen_prompt, report_prompt
from agents.tools.sdk_tools import list_header_files, read_header_file
from agents.tools.code_gen_tools import write_gtest_file, ensure_output_dir, write_cmake_file, write_workflow_file

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_STAGE_NAMES: list[str] = [
    "scanner",
    "analysis",
    "test_design",
    "code_gen",
    "ci_gen",
    "report",
]


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline Orchestrator
# ──────────────────────────────────────────────────────────────────────────────


class Pipeline:
    """Orchestrate sequential execution of the SDK test-generation pipeline.

    The pipeline consists of 6 stages run in strict order:

    1. **scanner** — discover and parse SDK header files into an API inventory.
    2. **analysis** — analyse the inventory for complexity, patterns, risks.
    3. **test_design** — design a ``TestCaseCollection`` targeting uncovered paths.
    4. **code_gen** — generate compilable GTest C++ source files.
    5. **ci_gen** — generate CMakeLists.txt and GitHub Actions workflow.
    6. **report** — synthesise a final Markdown report and JSON summary.

    Parameters
    ----------
    llm:
        An ``LLMWrapper`` instance shared by all chains.
    config:
        Pipeline configuration dict.  Expected keys include ``sdk_root``,
        ``output_root``, ``model``, ``temperature``, ``max_tokens``, and
        ``no_cache``.
    tools:
        Optional extra LangChain tools.  Each chain also receives its own
        dedicated tool list.
    """

    def __init__(
        self,
        llm: LLMWrapper,
        config: dict,
        tools: list | None = None,
    ) -> None:
        if not isinstance(llm, LLMWrapper):
            raise TypeError("llm must be an LLMWrapper instance")
        if not isinstance(config, dict):
            raise TypeError("config must be a dict")

        self.llm = llm
        self.config = config
        self.tools = tools or []

        self._output_root: str = config.get("output_root", "./output")

        # ── Shared cache ────────────────────────────────────────────────
        self.cache = LLMCache(
            cache_dir=os.path.join(self._output_root, "cache"),
            enabled=not config.get("no_cache", False),
        )

        # ── Pipeline memory (cross-stage context) ──────────────────────
        self.memory = PipelineMemory(
            persist_path=os.path.join(self._output_root, "pipeline_memory.json"),
        )

        # ── In-memory stage results (fast access, no serialisation) ────
        self._results: dict[str, Any] = {}

        # ── Initialise all 6 chains ────────────────────────────────────

        # 1. SDK Scanner Chain
        self.scanner_chain = SDKScannerChain(
            llm=llm,
            tools=[list_header_files, read_header_file],
            prompt=scanner_prompt.HUMAN_TEMPLATE,
        )

        # 2. API Analysis Chain
        self.analysis_chain = APIAnalysisChain(
            llm=llm,
            prompt=analysis_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

        # 3. Test Design Chain
        self.test_design_chain = TestDesignChain(
            llm=llm,
            prompt=test_design_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

        # 4. Code Generation Chain
        self.code_gen_chain = CodeGenChain(
            llm=llm,
            tools=[write_gtest_file, ensure_output_dir],
            prompt=code_gen_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

        # 5. CI Generation Chain
        self.ci_gen_chain = CIGenChain(
            llm=llm,
            tools=[write_cmake_file, write_workflow_file, ensure_output_dir],
            prompt=ci_gen_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

        # 6. Report Chain
        self.report_chain = ReportChain(
            llm=llm,
            prompt=report_prompt.HUMAN_TEMPLATE,
            cache=self.cache,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_stages(self) -> list[str]:
        """Return the ordered list of pipeline stage names."""
        return list(_STAGE_NAMES)

    def run(self) -> dict[str, Any]:
        """Execute all 6 pipeline stages sequentially.

        Each stage's output is stored in ``PipelineMemory`` and made
        available as input to downstream stages.  If any stage raises
        an exception the pipeline stops immediately and the error is
        propagated to the caller.

        Returns
        -------
        dict[str, Any]
            A mapping of ``{stage_name: output}`` for every completed stage.
        """
        logger.info("=" * 60)
        logger.info("Pipeline run STARTED")
        logger.info("=" * 60)
        logger.info("  SDK root  : %s", self.config.get("sdk_root", "(not set)"))
        logger.info("  Output    : %s", self._output_root)
        logger.info("  Model     : %s", self.config.get("model", "(default)"))
        logger.info("  Cache     : %s",
                     "enabled" if not self.config.get("no_cache", False) else "disabled")
        logger.info("=" * 60)

        self._results = {}

        # ---- Stage 1: SDK Scanner -----------------------------------------
        inventory = self._time_stage(
            "scanner",
            self.scanner_chain.run,
            self.config["sdk_root"],
        )
        self._results["scanner"] = inventory
        self.memory.store_stage_output("scanner", self._to_serializable(inventory))

        # ---- Stage 2: API Analysis ----------------------------------------
        analysis = self._time_stage(
            "analysis",
            self.analysis_chain.run,
            inventory,
        )
        self._results["analysis"] = analysis
        self.memory.store_stage_output("analysis", analysis)

        # ---- Stage 3: Test Design -----------------------------------------
        test_collection = self._time_stage(
            "test_design",
            self.test_design_chain.run,
            inventory,
            analysis,
        )
        self._results["test_design"] = test_collection
        self.memory.store_stage_output("test_design", test_collection)

        # ---- Stage 4: Code Generation -------------------------------------
        code_gen_output = self._time_stage(
            "code_gen",
            self.code_gen_chain.run,
            test_collection,
        )
        self._results["code_gen"] = code_gen_output
        self.memory.store_stage_output("code_gen", code_gen_output)

        # ---- Stage 5: CI Generation ---------------------------------------
        ci_gen_output = self._time_stage(
            "ci_gen",
            self.ci_gen_chain.run,
            inventory,
            test_collection,
        )
        self._results["ci_gen"] = ci_gen_output
        self.memory.store_stage_output("ci_gen", ci_gen_output)

        # ---- Stage 6: Report ----------------------------------------------
        report = self._time_stage(
            "report",
            self.report_chain.run,
            self.memory,
        )
        self._results["report"] = report
        self.memory.store_stage_output("report", report)

        # ---- Done --------------------------------------------------------
        logger.info("=" * 60)
        logger.info("Pipeline run COMPLETED — %d stages executed",
                     len(self._results))
        logger.info("=" * 60)

        return dict(self._results)

    def run_stage(self, stage_name: str, inputs: dict[str, Any]) -> Any:
        """Execute a single pipeline stage in isolation.

        Parameters
        ----------
        stage_name:
            One of the names returned by :meth:`get_stages`.
        inputs:
            A dict of keyword arguments expected by the target stage's
            ``run()`` method.  The caller is responsible for providing
            all required inputs (e.g. ``{"inventory": ...}`` for the
            ``"analysis"`` stage).

        Returns
        -------
        Any
            The raw output of the stage's ``run()`` call.

        Raises
        ------
        ValueError
            If *stage_name* is not a recognised pipeline stage.
        RuntimeError
            If the stage raises an exception during execution.
        """
        if stage_name not in _STAGE_NAMES:
            raise ValueError(
                f"Unknown stage {stage_name!r}. "
                f"Valid stages: {_STAGE_NAMES}"
            )

        stage_fn = self._resolve_stage_fn(stage_name)
        return self._time_stage(stage_name, stage_fn, **inputs)

    def dry_run(self) -> None:
        """Log all pipeline stages that *would* execute without calling the LLM.

        Useful for verifying the stage order and configuration before a
        real run.
        """
        logger.info("=" * 60)
        logger.info("Pipeline DRY RUN")
        logger.info("=" * 60)
        logger.info("  SDK root  : %s", self.config.get("sdk_root", "(not set)"))
        logger.info("  Output    : %s", self._output_root)

        for idx, stage in enumerate(_STAGE_NAMES, start=1):
            chain = getattr(self, f"{stage}_chain", None)
            chain_desc = type(chain).__name__ if chain else "(not initialised)"
            logger.info(
                "  [%d/6] %-15s → %s",
                idx,
                stage,
                chain_desc,
            )

        logger.info("=" * 60)
        logger.info("Dry-run complete — %d stage(s) would execute",
                     len(_STAGE_NAMES))
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_stage_fn(self, stage_name: str):
        """Return the bound ``run`` method of the chain for *stage_name*."""
        mapping: dict[str, Any] = {
            "scanner": self.scanner_chain.run,
            "analysis": self.analysis_chain.run,
            "test_design": self.test_design_chain.run,
            "code_gen": self.code_gen_chain.run,
            "ci_gen": self.ci_gen_chain.run,
            "report": self.report_chain.run,
        }
        fn = mapping.get(stage_name)
        if fn is None:
            raise ValueError(f"No chain run method for stage {stage_name!r}")
        return fn

    @staticmethod
    def _time_stage(stage_name: str, fn, *args, **kwargs) -> Any:
        """Invoke *fn* with timing and structured logging.

        Logs start, completion (with duration), and re-raises any
        exception after logging the failure.
        """
        logger.info(">>> Stage '%s' started", stage_name)
        start = time.monotonic()

        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "XXX Stage '%s' FAILED after %.2fs: %s: %s",
                stage_name,
                elapsed,
                type(exc).__name__,
                exc,
            )
            raise

        elapsed = time.monotonic() - start
        logger.info("<<< Stage '%s' completed in %.2fs", stage_name, elapsed)
        return result

    @staticmethod
    def _to_serializable(output: Any) -> Any:
        """Convert a stage output to a JSON-serialisable Python object.

        Chains that return Pydantic / dataclass instances (e.g.
        ``APIInventory``) are converted to plain dicts so that
        ``PipelineMemory._persist()`` can serialise them to JSON
        without relying on the ``default=str`` fallback.
        """
        if hasattr(output, "to_json"):
            return json.loads(output.to_json())
        return output
