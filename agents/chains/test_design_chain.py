"""TestCase Design Chain.

Takes an ``APIInventory`` (from the scanner stage) together with an analysis
report (from the analysis stage) and uses an LLM to design comprehensive
test cases, returned as a ``TestCaseCollection``.
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
from agents.prompts.test_design_prompt import HUMAN_TEMPLATE, SYSTEM_PROMPT
from ir.api_schema import APIInventory
from ir.testcase_schema import TestCaseCollection, TestCaseInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic schemas for structured LLM output
# ---------------------------------------------------------------------------


class LLMTestCase(BaseModel):
    """A single test case as produced by the LLM in structured-output mode.

    Mirrors the ``TestCaseInfo`` IR schema but defined as a Pydantic
    ``BaseModel`` so it can be used with ``LLMWrapper.invoke_structured()``.
    """

    test_id: str = Field(description="Unique test case identifier")
    api_id: str = Field(description="API element this test targets")
    test_name: str = Field(
        description="Descriptive test name in GTest convention",
    )
    category: str = Field(
        description='Test category: "unit", "integration", or "contract"',
    )
    subtype: str = Field(description="Test subtype within the category")
    priority: str = Field(description='Priority: "P0", "P1", "P2", or "P3"')
    setup_requirements: list[str] = Field(
        default_factory=list,
        description="Prerequisites before the test can run",
    )
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters for the test",
    )
    expected_behavior: str = Field(
        default="",
        description="What the test expects to happen",
    )
    assertion_type: str = Field(
        default="EXPECT_TRUE",
        description="GTest assertion macro to use",
    )
    needs_fixture: bool = Field(
        default=False,
        description="Whether a test fixture is required",
    )
    needs_mock: bool = Field(
        default=False,
        description="Whether mocking is required",
    )
    needs_testdata: bool = Field(
        default=False,
        description="Whether external test data is needed",
    )
    confidence: float = Field(
        default=0.5,
        description="LLM confidence in this test case (0.0 – 1.0)",
    )


class LLMTestCaseCollection(BaseModel):
    """Top-level structured output from the LLM.

    Mirrors the output format specified in
    ``agents.prompts.test_design_prompt.SYSTEM_PROMPT`` section 6.
    """

    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about uncovered APIs or limitations",
    )
    cases: list[LLMTestCase] = Field(
        default_factory=list,
        description="Designed test cases",
    )


# ---------------------------------------------------------------------------
# Test design chain
# ---------------------------------------------------------------------------


class TestDesignChain:
    """Design comprehensive test cases for an ``APIInventory``.

    The chain:

    1. Builds a summary of the inventory (functions, classes, enums, modules).
    2. Combines it with analysis insights (complexity, risk_areas,
       test_priorities).
    3. Sends the combined payload to the LLM via
       ``LLMWrapper.invoke_structured()`` with the ``LLMTestCaseCollection``
       Pydantic schema for reliable structured output.
    4. Parses the result into a ``TestCaseCollection`` from the IR layer.

    Parameters
    ----------
    llm:
        An ``LLMWrapper`` instance used for LLM communication.
    prompt:
        A ``PromptTemplate`` (from ``agents.prompts.test_design_prompt``) that
        formats the inventory and analysis payload for the LLM.
    cache:
        Optional ``LLMCache`` for caching test design results keyed by
        inventory + analysis content hash.
    """

    def __init__(
        self,
        llm: LLMWrapper,
        prompt: PromptTemplate = HUMAN_TEMPLATE,
        cache: LLMCache | None = None,
    ) -> None:
        if not isinstance(llm, LLMWrapper):
            raise TypeError("llm must be an LLMWrapper instance")
        if not isinstance(prompt, PromptTemplate):
            raise TypeError("prompt must be a PromptTemplate instance")

        self._llm = llm
        self._prompt = prompt
        self._cache = cache

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        inventory: APIInventory,
        analysis: dict[str, Any],
    ) -> TestCaseCollection:
        """Design test cases from an inventory and analysis report.

        Parameters
        ----------
        inventory:
            The ``APIInventory`` produced by the scanner stage.
        analysis:
            The analysis dict produced by ``APIAnalysisChain.run()``.

        Returns
        -------
        TestCaseCollection
            A collection of ``TestCaseInfo`` objects with designed tests.
        """
        # --- Edge case: empty inventory ------------------------------------
        if self._is_empty(inventory):
            logger.info("Empty inventory — returning empty TestCaseCollection")
            return TestCaseCollection(cases=[])

        # --- Check cache ---------------------------------------------------
        cache_key = self._build_cache_key(inventory, analysis)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("Test design cache hit (key=%s…)", cache_key[:12])
                return TestCaseCollection.from_dict(cached)

        # --- Build inventory summary + LLM messages ------------------------
        summary = self._build_inventory_summary(inventory)
        messages = self._build_messages(summary, analysis)

        # --- Invoke LLM ----------------------------------------------------
        llm_result = self._invoke_with_retry(messages)

        # --- Convert to TestCaseCollection and enforce limits --------------
        result = self._to_testcase_collection(llm_result)

        # --- Write cache ---------------------------------------------------
        if self._cache is not None:
            self._cache.set(cache_key, result.to_dict())
            logger.debug("Test design result cached (key=%s…)", cache_key[:12])

        return result

    # ------------------------------------------------------------------
    # Internal helpers — emptiness check
    # ------------------------------------------------------------------

    @staticmethod
    def _is_empty(inventory: APIInventory) -> bool:
        """Return True if the inventory contains no analysable items."""
        return all(
            not h.functions and not h.classes and not h.enums
            for m in inventory.modules
            for h in m.headers
        )

    # ------------------------------------------------------------------
    # Internal helpers — inventory summary
    # ------------------------------------------------------------------

    @staticmethod
    def _build_inventory_summary(inventory: APIInventory) -> dict[str, Any]:
        """Build a concise JSON-serialisable summary of the inventory."""
        modules_list: list[dict[str, Any]] = []
        total_functions = 0
        total_classes = 0
        total_enums = 0

        for module in inventory.modules:
            headers_list: list[dict[str, Any]] = []
            for header in module.headers:
                funcs = [f.to_dict() for f in header.functions]
                classes_list: list[dict[str, Any]] = []
                for cls in header.classes:
                    classes_list.append({
                        "class_id": cls.class_id,
                        "name": cls.name,
                        "qualified_name": cls.qualified_name,
                        "namespace": cls.namespace,
                        "kind": cls.kind,
                        "methods": [m.to_dict() for m in cls.methods],
                    })
                enums_list: list[dict[str, Any]] = []
                for enum in header.enums:
                    enums_list.append({
                        "enum_id": enum.enum_id,
                        "name": enum.name,
                        "qualified_name": enum.qualified_name,
                        "namespace": enum.namespace,
                        "values": [v.to_dict() for v in enum.values],
                    })
                headers_list.append({
                    "header_id": header.header_id,
                    "path": header.path,
                    "relative_path": header.relative_path,
                    "functions": funcs,
                    "classes": classes_list,
                    "enums": enums_list,
                    "aliases": [a.to_dict() for a in header.aliases],
                })
                total_functions += len(header.functions)
                total_classes += len(header.classes)
                total_enums += len(header.enums)

            modules_list.append({
                "module_id": module.module_id,
                "name": module.name,
                "headers": headers_list,
            })

        return {
            "sdk_root": inventory.sdk_root,
            "modules": modules_list,
            "counts": {
                "functions": total_functions,
                "classes": total_classes,
                "enums": total_enums,
                "headers": sum(len(m.headers) for m in inventory.modules),
                "modules": len(inventory.modules),
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers — cache key
    # ------------------------------------------------------------------

    @staticmethod
    def _build_cache_key(
        inventory: APIInventory,
        analysis: dict[str, Any],
    ) -> str:
        """Generate a SHA-256 cache key from inventory + analysis content."""
        raw = inventory.to_json() + json.dumps(analysis, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Internal helpers — LLM message construction
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        summary: dict[str, Any],
        analysis: dict[str, Any],
    ) -> list[dict]:
        """Build the system + user message list for the LLM call."""
        inventory_json = json.dumps(summary, indent=2, ensure_ascii=False)
        analysis_report = json.dumps(analysis, indent=2, ensure_ascii=False)
        human_message = self._prompt.format(
            inventory_json=inventory_json,
            analysis_report=analysis_report,
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": human_message},
        ]

    # ------------------------------------------------------------------
    # Internal helpers — LLM invocation with retry
    # ------------------------------------------------------------------

    def _invoke_with_retry(
        self,
        messages: list[dict],
    ) -> LLMTestCaseCollection:
        """Invoke the LLM with structured output.

        The first attempt uses the standard message list. If it fails (e.g.
        malformed JSON), a second attempt is made with an explicit
        format-correction instruction appended.
        """
        try:
            return self._llm.invoke_structured(
                messages=messages,
                output_schema=LLMTestCaseCollection,
            )
        except Exception as exc:
            logger.warning(
                "First test-design LLM call failed: %s. Retrying with "
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
                return self._llm.invoke_structured(
                    messages=messages + [fix_message],
                    output_schema=LLMTestCaseCollection,
                )
            except Exception as inner_exc:
                logger.error(
                    "Test-design LLM call failed after format-correction "
                    "retry: %s",
                    inner_exc,
                )
                return LLMTestCaseCollection(warnings=[], cases=[])

    # ------------------------------------------------------------------
    # Internal helpers — result conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _to_testcase_collection(
        llm_result: LLMTestCaseCollection,
    ) -> TestCaseCollection:
        """Convert an ``LLMTestCaseCollection`` to an IR ``TestCaseCollection``.

        Enforces the maximum limit of 100 test cases by truncating excess
        items.
        """
        MAX_CASES = 100

        cases = llm_result.cases
        if len(cases) > MAX_CASES:
            logger.warning(
                "LLM returned %d test cases; truncating to %d.",
                len(cases),
                MAX_CASES,
            )
            cases = cases[:MAX_CASES]

        return TestCaseCollection(
            cases=[
                TestCaseInfo(
                    test_id=case.test_id,
                    api_id=case.api_id,
                    test_name=case.test_name,
                    category=case.category,
                    subtype=case.subtype,
                    priority=case.priority,
                    setup_requirements=list(case.setup_requirements),
                    inputs=dict(case.inputs),
                    expected_behavior=case.expected_behavior,
                    assertion_type=case.assertion_type,
                    needs_fixture=case.needs_fixture,
                    needs_mock=case.needs_mock,
                    needs_testdata=case.needs_testdata,
                    confidence=case.confidence,
                )
                for case in cases
            ],
        )
