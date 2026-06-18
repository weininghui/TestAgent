"""API Inventory Analysis Chain.

Takes an ``APIInventory`` (from the scanner stage) and uses an LLM
to produce a structured API analysis report.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from agents.cache import LLMCache
from agents.llm import LLMWrapper
from agents.prompts import PromptBuilder
from agents.prompts.analysis_prompt import HUMAN_TEMPLATE, SYSTEM_PROMPT
from schemas.api_schema import APIInventory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic schemas for structured LLM output
# ---------------------------------------------------------------------------


class RiskArea(BaseModel):
    """A single risk area identified in the API surface."""

    area: str = Field(description="The area of concern (e.g. module, class, or function name)")
    risk: str = Field(description="Description of the specific risk")
    suggestion: str = Field(description="Actionable suggestion to mitigate the risk")


class APIAnalysisResult(BaseModel):
    """Top-level structured analysis output from the LLM.

    This schema is passed to ``LLMWrapper.invoke_structured()`` so the LLM
    produces a well-formed JSON response matching these fields exactly.
    """

    complexity: str = Field(
        description='Overall API complexity assessment: "low", "medium", or "high"',
    )
    function_count: int = Field(description="Total number of free functions found")
    class_count: int = Field(description="Total number of classes found")
    enum_count: int = Field(description="Total number of enums found")
    patterns: list[str] = Field(
        default_factory=list,
        description="Design patterns detected (e.g., factory, singleton, observer, RAII)",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Inter-API dependencies detected (e.g., Module A depends on Module B)",
    )
    risk_areas: list[RiskArea] = Field(
        default_factory=list,
        description="Risk areas identified with severity and mitigation suggestions",
    )
    test_priorities: list[str] = Field(
        default_factory=list,
        description="Suggested testing focus areas (e.g., P0-critical init paths, P1-core logic)",
    )
    summary: str = Field(
        description="Natural language analysis summary of the API surface",
    )


# ---------------------------------------------------------------------------
# Batching threshold
# ---------------------------------------------------------------------------

_BATCH_THRESHOLD = 100
"""If the total number of functions + classes + enums exceeds this value,
the inventory is analysed module-by-module and the results are aggregated."""


# ---------------------------------------------------------------------------
# Analysis chain
# ---------------------------------------------------------------------------


class APIAnalysisChain:
    """Analyse an ``APIInventory`` and produce a structured analysis report.

    The chain:

    1. Summarises the inventory payload (functions, classes, enums, modules).
    2. Sends it to the LLM via ``LLMWrapper.invoke_structured()`` with the
       ``APIAnalysisResult`` Pydantic schema for reliable structured output.
    3. Returns a plain dict with complexity, counts, patterns, risks, etc.

    Parameters
    ----------
    llm:
        An ``LLMWrapper`` instance used for LLM communication.
    prompt:
        A ``PromptTemplate`` (from ``agents.prompts.analysis_prompt``) that
        formats the inventory payload for the LLM.
    cache:
        Optional ``LLMCache`` for caching analysis results keyed by inventory
        content hash.
    """

    def __init__(
        self,
        llm: LLMWrapper,
        prompt: PromptTemplate = HUMAN_TEMPLATE,
        cache: LLMCache | None = None,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        if not isinstance(llm, LLMWrapper):
            raise TypeError("llm must be an LLMWrapper instance")
        if not isinstance(prompt, PromptTemplate):
            raise TypeError("prompt must be a PromptTemplate instance")

        self._llm = llm
        self._prompt = prompt
        self._cache = cache
        self._prompt_builder = prompt_builder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, inventory: APIInventory) -> dict[str, Any]:
        """Analyse an ``APIInventory`` and return a structured analysis dict.

        Parameters
        ----------
        inventory:
            The ``APIInventory`` produced by the scanner stage.

        Returns
        -------
        dict
            A dictionary with the following keys:

            - **complexity** (*str*) — ``"low"``, ``"medium"``, or ``"high"``.
            - **function_count** (*int*) — total free functions.
            - **class_count** (*int*) — total classes / structs.
            - **enum_count** (*int*) — total enums.
            - **patterns** (*list[str]*) — detected design patterns.
            - **dependencies** (*list[str]*) — inter-API dependency edges.
            - **risk_areas** (*list[dict]*) — each with ``area``, ``risk``,
              ``suggestion``.
            - **test_priorities** (*list[str]*) — suggested testing focus
              areas.
            - **summary** (*str*) — natural language analysis summary.
        """
        # --- Quick counts --------------------------------------------------
        total_functions = self._count_functions(inventory)
        total_classes = self._count_classes(inventory)
        total_enums = self._count_enums(inventory)

        # --- Edge case: empty inventory ------------------------------------
        if total_functions == 0 and total_classes == 0 and total_enums == 0:
            logger.info("Empty inventory — returning minimal analysis")
            return self._empty_report(inventory)

        # --- Check cache ---------------------------------------------------
        cache_key = self._build_cache_key(inventory)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("Analysis cache hit (key=%s…)", cache_key[:12])
                return cached

        # --- Decide batching strategy --------------------------------------
        total_items = total_functions + total_classes + total_enums

        if total_items > _BATCH_THRESHOLD and len(inventory.modules) > 1:
            logger.info(
                "Large inventory (%d items across %d modules) — analysing "
                "per module and aggregating",
                total_items,
                len(inventory.modules),
            )
            result = self._run_batched(inventory)
        else:
            result = self._run_single(inventory)

        # --- Populate ground-truth counts ----------------------------------
        # Ensure counts are accurate even if the LLM miscounts.
        result["function_count"] = total_functions
        result["class_count"] = total_classes
        result["enum_count"] = total_enums

        # --- Write cache ---------------------------------------------------
        if self._cache is not None:
            self._cache.set(cache_key, result)
            logger.debug("Analysis result cached (key=%s…)", cache_key[:12])

        return result

    # ------------------------------------------------------------------
    # Internal helpers — counting
    # ------------------------------------------------------------------

    @staticmethod
    def _count_functions(inventory: APIInventory) -> int:
        """Return the total number of free functions across all modules."""
        return sum(
            len(h.functions)
            for m in inventory.modules
            for h in m.headers
        )

    @staticmethod
    def _count_classes(inventory: APIInventory) -> int:
        """Return the total number of classes across all modules."""
        return sum(
            len(h.classes)
            for m in inventory.modules
            for h in m.headers
        )

    @staticmethod
    def _count_enums(inventory: APIInventory) -> int:
        """Return the total number of enums across all modules."""
        return sum(
            len(h.enums)
            for m in inventory.modules
            for h in m.headers
        )

    # ------------------------------------------------------------------
    # Internal helpers — edge-case report
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_report(inventory: APIInventory) -> dict[str, Any]:
        """Return a minimal report when the inventory is empty."""
        return {
            "complexity": "low",
            "function_count": 0,
            "class_count": 0,
            "enum_count": 0,
            "patterns": [],
            "dependencies": [],
            "risk_areas": [],
            "test_priorities": [],
            "summary": (
                f"The inventory at '{inventory.sdk_root}' contains no "
                "functions, classes, or enums. No further analysis was "
                "performed."
            ),
        }

    # ------------------------------------------------------------------
    # Internal helpers — cache key
    # ------------------------------------------------------------------

    @staticmethod
    def _build_cache_key(inventory: APIInventory) -> str:
        """Generate a SHA-256 cache key from the inventory JSON content."""
        raw = inventory.to_json()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Internal helpers — LLM message construction
    # ------------------------------------------------------------------

    def _build_messages(self, inventory: APIInventory) -> list[dict]:
        """Build the system + user message list for the LLM call."""
        inventory_json = inventory.to_json()
        human_message = self._prompt.format(inventory_json=inventory_json)
        system_content = (
            self._prompt_builder.build_system_only("analysis")
            if self._prompt_builder is not None
            else SYSTEM_PROMPT
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": human_message},
        ]

    # ------------------------------------------------------------------
    # Internal helpers — single vs. batched analysis
    # ------------------------------------------------------------------

    def _run_single(self, inventory: APIInventory) -> dict[str, Any]:
        """Analyse the entire inventory in a single LLM call."""
        messages = self._build_messages(inventory)
        return self._invoke_with_retry(messages)

    def _run_batched(self, inventory: APIInventory) -> dict[str, Any]:
        """Analyse a large inventory module-by-module and aggregate results."""
        module_results: list[dict[str, Any]] = []

        for module in inventory.modules:
            # Create a single-module inventory for focused analysis
            mini = APIInventory(
                sdk_root=inventory.sdk_root,
                modules=[module],
            )
            logger.debug(
                "Analysing module '%s' (%d headers)",
                module.name,
                len(module.headers),
            )
            messages = self._build_messages(mini)
            module_results.append(self._invoke_with_retry(messages))

        return self._aggregate(module_results, inventory)

    # ------------------------------------------------------------------
    # Internal helpers — aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate(
        module_results: list[dict[str, Any]],
        inventory: APIInventory,
    ) -> dict[str, Any]:
        """Merge per-module analysis results into a single consolidated dict.

        Pattern, dependency, and test-priority lists are deduplicated while
        preserving order. Risk areas are concatenated without dedup (each
        module-specific risk is relevant). Complexity is the highest observed
        across all modules.
        """
        total_functions = 0
        total_classes = 0
        total_enums = 0
        all_patterns: list[str] = []
        all_deps: list[str] = []
        all_risks: list[dict[str, Any]] = []
        all_tests: list[str] = []
        complexities: list[str] = []

        for r in module_results:
            total_functions += r.get("function_count", 0)
            total_classes += r.get("class_count", 0)
            total_enums += r.get("enum_count", 0)
            all_patterns.extend(r.get("patterns", []))
            all_deps.extend(r.get("dependencies", []))
            all_risks.extend(r.get("risk_areas", []))
            all_tests.extend(r.get("test_priorities", []))
            complexities.append(r.get("complexity", "low"))

        # --- Deduplicate patterns (case-insensitive) -----------------------
        seen_patterns: set[str] = set()
        unique_patterns: list[str] = []
        for p in all_patterns:
            key = p.strip().lower()
            if key and key not in seen_patterns:
                seen_patterns.add(key)
                unique_patterns.append(p)

        # --- Deduplicate dependencies (case-insensitive) -------------------
        seen_deps: set[str] = set()
        unique_deps: list[str] = []
        for d in all_deps:
            key = d.strip().lower()
            if key and key not in seen_deps:
                seen_deps.add(key)
                unique_deps.append(d)

        # --- Deduplicate test priorities (fuzzy) ---------------------------
        seen_tests: set[str] = set()
        unique_tests: list[str] = []
        for t in all_tests:
            key = t.strip().lower()
            if key and key not in seen_tests:
                seen_tests.add(key)
                unique_tests.append(t)

        # --- Aggregate complexity: highest rank wins -----------------------
        _rank = {"low": 0, "medium": 1, "high": 2}
        aggregate_complexity: str = max(
            complexities,
            key=lambda c: _rank.get(c, -1),
        )

        # --- Combine summaries ---------------------------------------------
        raw_summaries = [
            r.get("summary", "")
            for r in module_results
            if r.get("summary")
        ]
        if raw_summaries:
            combined_summary = " | ".join(raw_summaries)
        else:
            combined_summary = (
                f"Aggregated analysis of {len(module_results)} module(s) "
                f"({total_functions} functions, {total_classes} classes, "
                f"{total_enums} enums)."
            )

        return {
            "complexity": aggregate_complexity,
            "function_count": total_functions,
            "class_count": total_classes,
            "enum_count": total_enums,
            "patterns": unique_patterns,
            "dependencies": unique_deps,
            "risk_areas": all_risks,
            "test_priorities": unique_tests,
            "summary": combined_summary,
        }

    # ------------------------------------------------------------------
    # Internal helpers — LLM invocation with retry
    # ------------------------------------------------------------------

    def _invoke_with_retry(self, messages: list[dict]) -> dict[str, Any]:
        """Invoke the LLM with structured output.

        The first attempt uses the standard message list. If it fails (e.g.
        malformed JSON), a second attempt is made with an explicit
        format-correction instruction appended.
        """
        try:
            result: APIAnalysisResult = self._llm.invoke_structured(
                messages=messages,
                output_schema=APIAnalysisResult,
            )
            return self._result_to_dict(result)
        except Exception as exc:
            logger.warning(
                "First analysis LLM call failed: %s. Retrying with "
                "format-correction hint.",
                exc,
            )

            fix_message: dict = {
                "role": "user",
                "content": (
                    "The previous response was not in the correct format. "
                    "Please respond with a valid JSON object matching the "
                    "required schema exactly. Do not include any markdown "
                    "fences, code blocks, or additional text."
                ),
            }
            try:
                result = self._llm.invoke_structured(
                    messages=messages + [fix_message],
                    output_schema=APIAnalysisResult,
                )
                return self._result_to_dict(result)
            except Exception as inner_exc:
                logger.error(
                    "Analysis LLM call failed after format-correction retry: "
                    "%s",
                    inner_exc,
                )
                return self._fallback_result()

    # ------------------------------------------------------------------
    # Internal helpers — result conversion / fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _result_to_dict(result: APIAnalysisResult) -> dict[str, Any]:
        """Convert a validated ``APIAnalysisResult`` instance to a plain dict.

        Uses ``model_dump_json()`` (Pydantic v2) to serialise nested models
        then deserialises back to native Python types so that nested
        ``RiskArea`` objects become plain dicts.
        """
        return json.loads(result.model_dump_json())

    @staticmethod
    def _fallback_result() -> dict[str, Any]:
        """Return a safe fallback when the LLM is unreachable or broken."""
        return {
            "complexity": "unknown",
            "function_count": 0,
            "class_count": 0,
            "enum_count": 0,
            "patterns": [],
            "dependencies": [],
            "risk_areas": [
                {
                    "area": "LLM Analysis",
                    "risk": (
                        "Failed to obtain LLM analysis — the LLM was "
                        "unreachable or returned an invalid response."
                    ),
                    "suggestion": (
                        "Check LLM connectivity, API key, and model "
                        "availability. Retry the analysis."
                    ),
                },
            ],
            "test_priorities": [],
            "summary": (
                "Analysis could not be completed because the LLM was "
                "unreachable or returned an invalid response."
            ),
        }
