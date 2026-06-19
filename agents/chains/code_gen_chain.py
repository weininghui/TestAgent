"""Code Generation Chain — LLM-powered C++ GTest code generator.

Takes a ``TestCaseCollection`` and uses an LLM to generate compilable C++ GTest
source files, writing them via the ``code_gen_tools`` module.

Flow
----
1. **Group** — test cases are grouped by logical module (extracted from
   ``api_id``, e.g. ``func::math::normalize`` → module ``"math"``).
2. **Batch** — within each module, cases are batched (max 20 per file) to
   keep LLM prompt sizes manageable.
3. **Generate** — each batch is sent to the LLM with the ``code_gen_prompt``
   SYSTEM_PROMPT; the LLM returns JSON ``{"files": {"name.cc": "source..."}}``.
4. **Write** — each source file is persisted via ``write_gtest_file``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import PromptTemplate

from agents.cache import LLMCache
from agents.llm import LLMWrapper
from agents.prompts import PromptBuilder
from agents.prompts.code_gen_prompt import HUMAN_TEMPLATE, SYSTEM_PROMPT
from agents.tools.code_gen_tools import raw_write_gtest_file as write_gtest_file
from schemas.testcase_schema import TestCaseCollection, TestCaseInfo

logger = logging.getLogger(__name__)

#: Maximum number of test cases to include in a single generated file.
#: When a module exceeds this threshold, cases are split across multiple
#: files (e.g. ``test_core_1.cc``, ``test_core_2.cc``).
_BATCH_MAX_CASES = 20


# ---------------------------------------------------------------------------
# Module extraction & grouping helpers
# ---------------------------------------------------------------------------


def _extract_module(test_case: TestCaseInfo) -> str:
    """Extract the logical module name from a ``TestCaseInfo``'s ``api_id``.

    The ``api_id`` follows the pattern ``func::<module>::<name>``
    (e.g. ``func::math::normalize`` → ``"math"``).

    If the pattern does not contain at least two ``::``-separated segments,
    returns ``"unknown"`` as a safe fallback.
    """
    parts = test_case.api_id.split("::")
    if len(parts) >= 2:
        return parts[1]
    return "unknown"


def _group_by_module(cases: list[TestCaseInfo]) -> dict[str, list[TestCaseInfo]]:
    """Group test cases by their logical module, preserving insertion order.

    Returns a dict mapping ``module_name → list[TestCaseInfo]``.
    """
    groups: dict[str, list[TestCaseInfo]] = {}
    for case in cases:
        module = _extract_module(case)
        groups.setdefault(module, []).append(case)
    return groups


# ---------------------------------------------------------------------------
# Prompt building helpers
# ---------------------------------------------------------------------------


def _batch_to_json(cases: list[TestCaseInfo]) -> str:
    """Convert a batch of ``TestCaseInfo`` objects to a compact JSON string.

    This JSON payload is fed into the LLM via the ``test_cases_json`` prompt
    variable, matching what the ``code_gen_prompt`` SYSTEM_PROMPT expects.
    """
    data = {"cases": [case.to_dict() for case in cases]}
    return json.dumps(data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Response parsing helpers
# --------------------------------------------------------------------------


def _strip_markdown_fences(text: str) -> str:
    """Strip `` ```json `` / `` ``` `` markdown fences from LLM output.

    The system prompt asks for raw JSON, but some LLMs still wrap the
    response in fences.  This helper normalises the text.
    """
    text = text.strip()
    # Remove leading ```json or ``` (possibly with a language hint)
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl:].strip()
    # Remove trailing ```
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def _parse_code_response(response_text: str) -> dict[str, str]:
    """Parse the LLM's JSON response into ``{filename: source_code}`` dict.

    The system prompt instructs the LLM to return:
    ``{"files": {"test_module.cc": "source...", ...}}``

    Returns an empty dict on any parse failure so the caller can degrade
    gracefully (write a warning and continue).
    """
    text = _strip_markdown_fences(response_text)

    try:
        data: dict[str, Any] = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("LLM response is not valid JSON: %s", exc)
        return {}

    files_raw = data.get("files")
    if not isinstance(files_raw, dict):
        logger.warning(
            "LLM response 'files' is not a dict (got %s). Raw: %s",
            type(files_raw).__name__,
            text[:300],
        )
        return {}

    # Validate structure: keys and values must be strings
    files: dict[str, str] = {}
    for fname, source in files_raw.items():
        if isinstance(fname, str) and isinstance(source, str):
            files[fname] = source
        else:
            logger.warning(
                "Skipping non-string entry in files dict: key=%s type=%s",
                fname,
                type(source).__name__,
            )

    return files


# ---------------------------------------------------------------------------
# CodeGenChain
# ---------------------------------------------------------------------------


class CodeGenChain:
    """Generate compilable C++ GTest source files from a ``TestCaseCollection``.

    The chain:
        1. Groups test cases by logical module (extracted from ``api_id``).
        2. Batches cases within each module (max ``_BATCH_MAX_CASES`` per file).
        3. For each batch, builds a prompt and sends it to the LLM.
        4. The LLM returns JSON ``{"files": {"name.cc": "source..."}}``.
        5. Every source file is written to disk via ``write_gtest_file``.

    Parameters
    ----------
    llm:
        An ``LLMWrapper`` instance for all LLM invocations.
    tools:
        A list of LangChain ``Tool`` objects (for compatibility with agent
        frameworks).  The chain also imports and uses the underlying
        ``write_gtest_file`` function directly.
    prompt:
        A ``PromptTemplate`` whose ``input_variables`` include
        ``test_cases_json``.  Defaults to ``HUMAN_TEMPLATE`` from the
        ``code_gen_prompt`` module.
    cache:
        Optional ``LLMCache`` instance for caching LLM responses.  When
        provided, repeated generation requests for the same test-case data
        skip the LLM call and reuse cached output.
    """

    def __init__(
        self,
        llm: LLMWrapper,
        tools: list,
        prompt: PromptTemplate = HUMAN_TEMPLATE,
        cache: LLMCache | None = None,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._prompt = prompt
        self._cache = cache
        self._prompt_builder = prompt_builder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, test_collection: TestCaseCollection) -> int:
        """Generate GTest source files for every test case in *test_collection*.

        Parameters
        ----------
        test_collection:
            The ``TestCaseCollection`` produced by the test-design pipeline
            stage.

        Returns
        -------
        int
            The total number of ``.cc`` / ``.cpp`` files written to disk.
            Returns ``0`` if the collection is empty or all LLM calls fail.
        """
        cases = test_collection.cases

        # --- Edge case: empty collection ------------------------------------
        if not cases:
            logger.info("Empty test collection — no files generated.")
            return 0

        # --- Group by module ------------------------------------------------
        groups = _group_by_module(cases)
        logger.info(
            "Generating GTest code for %d test case(s) across %d module(s)",
            len(cases),
            len(groups),
        )

        total_files_written = 0

        for module_name, module_cases in groups.items():
            # Split module into batches of _BATCH_MAX_CASES
            for batch_offset in range(0, len(module_cases), _BATCH_MAX_CASES):
                batch = module_cases[batch_offset: batch_offset + _BATCH_MAX_CASES]
                files_written = self._generate_for_batch(
                    module_name=module_name,
                    cases=batch,
                    batch_number=batch_offset // _BATCH_MAX_CASES + 1,
                )
                total_files_written += files_written

        logger.info(
            "Code generation complete: %d file(s) written",
            total_files_written,
        )
        return total_files_written

    # ------------------------------------------------------------------
    # Internal: single-batch LLM generation + writing
    # ------------------------------------------------------------------

    def _generate_for_batch(
        self,
        module_name: str,
        cases: list[TestCaseInfo],
        batch_number: int,
    ) -> int:
        """Generate GTest code for a single batch of test cases.

        Steps:
        1. Build the prompt with batch context + test cases as JSON.
        2. Check the LLM result cache (if configured).
        3. Invoke the LLM (with retry for transient failures).
        4. Parse the response into a ``{filename: source}`` mapping.
        5. Write each file to disk.

        Returns the number of files successfully written.
        """
        # --- Build prompt ---------------------------------------------------
        cases_json = _batch_to_json(cases)

        batch_context = (
            f"Module: {module_name}\n"
            f"Batch: {batch_number}\n"
            f"Total test cases in this batch: {len(cases)}\n"
        )
        full_user_content = batch_context + self._prompt.format(
            test_cases_json=cases_json,
        )

        system_content = (
            self._prompt_builder.build_system_only("code_gen")
            if self._prompt_builder is not None
            else SYSTEM_PROMPT
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": full_user_content},
        ]

        # --- Cache lookup ----------------------------------------------------
        files: dict[str, str] | None = None

        if self._cache is not None:
            cached = self._cache.make_and_get(
                model=self._llm.model,
                prompt=full_user_content,
                temperature=self._llm.temperature,
            )
            if cached is not None:
                logger.info(
                    "Cache hit for module '%s' batch %d",
                    module_name,
                    batch_number,
                )
                # cached should be a dict with a "files" key
                files = _parse_code_response(json.dumps(cached))

        # --- LLM invocation --------------------------------------------------
        if files is None:
            raw_response: str | None = None
            try:
                raw_response = self._llm.invoke(messages)
            except Exception as exc:
                logger.error(
                    "LLM invocation failed for module '%s' batch %d: %s",
                    module_name,
                    batch_number,
                    exc,
                )
                return 0

            # --- Persist cache -----------------------------------------------
            files = _parse_code_response(raw_response)

            if self._cache is not None and files:
                # Store the parsed files dict (re-serialised) so the cache
                # holds a valid dict for ``_parse_code_response`` to consume.
                self._cache.make_and_set(
                    model=self._llm.model,
                    prompt=full_user_content,
                    temperature=self._llm.temperature,
                    value={"files": files},
                )

        # --- Write files -----------------------------------------------------
        return self._write_files(
            files=files,
            module_name=module_name,
            batch_number=batch_number,
        )

    # ------------------------------------------------------------------
    # Internal: file persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _write_files(
        files: dict[str, str],
        module_name: str,
        batch_number: int,
    ) -> int:
        """Write each entry in *files* to disk via ``write_gtest_file``.

        Non-compilable code is still written so a human reviewer can inspect
        and correct it (the LLM output is always surfaced).
        """
        count = 0
        for fname, source in files.items():
            try:
                written_path = write_gtest_file(file_path=fname, content=source)
                logger.info("Written: %s", written_path)
                count += 1
            except Exception as exc:
                logger.warning(
                    "Failed to write file '%s' for module '%s' batch %d: %s",
                    fname,
                    module_name,
                    batch_number,
                    exc,
                )

        if count == 0:
            logger.warning(
                "No files written for module '%s' batch %d — "
                "LLM returned empty or unparseable output, or all writes failed.",
                module_name,
                batch_number,
            )

        return count
