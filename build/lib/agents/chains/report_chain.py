"""Report Generator Chain.

Takes all pipeline stage outputs via ``PipelineMemory`` and uses an LLM
to produce a comprehensive Markdown report and JSON data file.

The chain follows the same pattern as ``APIAnalysisChain``:

1. Retrieves all stage outputs from ``PipelineMemory``.
2. Builds a summary via ``PipelineMemory.summarize_for_next_stage("report")``.
3. Sends the summary to the LLM via ``LLMWrapper.invoke_structured()`` with
   the ``ReportOutput`` Pydantic schema for reliable structured output.
4. Writes ``report.md`` and ``report.json`` via ``write_report_file``.
5. Returns the report directory path.

Edge cases handled:
- Empty memory (no stages executed) → minimal report with "no data" notation.
- Missing stage outputs → graceful degradation noting which stages had output.
- LLM failure → basic structural report from available metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from agents.cache import LLMCache
from agents.llm import LLMWrapper
from agents.memory import PipelineMemory
from agents.prompts import PromptBuilder
from agents.prompts.report_prompt import HUMAN_TEMPLATE, SYSTEM_PROMPT
from agents.tools.code_gen_tools import ensure_output_dir, write_report_file

# ``write_report_file`` is a LangChain ``@tool``-decorated function, which in
# this environment creates a ``StructuredTool`` object that is NOT directly
# callable.  We access the underlying Python function via ``.func``.
_write_report_file = write_report_file.func

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic schema for structured LLM output
# ---------------------------------------------------------------------------


class ReportOutput(BaseModel):
    """Structured report output from the LLM.

    The system prompt in ``report_prompt.py`` instructs the LLM to produce a
    JSON object with exactly two keys:

    - ``markdown_report`` — a complete human-readable Markdown string.
    - ``json_summary`` — a machine-readable structured summary dict.

    This schema is passed to ``LLMWrapper.invoke_structured()`` so the LLM
    produces output matching these fields.
    """

    markdown_report: str = Field(
        description=(
            "Complete Markdown report string covering SDK overview, analysis "
            "summary, test case summary, generated files manifest, build and "
            "run instructions, and CI pipeline description."
        ),
    )
    json_summary: dict[str, Any] = Field(
        description=(
            "Structured JSON summary with inventory_counts, analysis, "
            "test_cases, generated_files metadata, pipeline_timestamp, "
            "and sdk_root."
        ),
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _compute_stage_hash(memory: PipelineMemory) -> str:
    """Compute a SHA-256 hash of all stage outputs for cache keying.

    The hash is computed over the JSON-serialised content of every stage
    output, sorted by key to ensure determinism across runs with identical
    data.
    """
    all_outputs = memory.get_all_outputs()
    raw = json.dumps(all_outputs, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Report chain
# ---------------------------------------------------------------------------


class ReportChain:
    """Synthesize pipeline stage outputs into a Markdown report + JSON summary.

    The chain:

    1. Retrieves all stage outputs from ``PipelineMemory``.
    2. Builds a summary via ``PipelineMemory.summarize_for_next_stage("report")``.
    3. Sends the summary to the LLM via ``LLMWrapper.invoke_structured()`` with
       the ``ReportOutput`` Pydantic schema for reliable structured output.
    4. Writes ``report.md`` and ``report.json`` via ``write_report_file``.
    5. Returns the report directory path.

    Parameters
    ----------
    llm:
        An ``LLMWrapper`` instance used for LLM communication.
    prompt:
        A ``PromptTemplate`` (from ``agents.prompts.report_prompt``) that
        formats the stage outputs summary for the LLM. Defaults to
        ``HUMAN_TEMPLATE``.
    cache:
        Optional ``LLMCache`` for caching report results keyed by stage output
        content hash.
    """

    def __init__(
        self,
        llm: LLMWrapper,
        prompt: PromptTemplate = HUMAN_TEMPLATE,
        cache: LLMCache | None = None,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        """Initialise the report chain.

        Args:
            llm: An ``LLMWrapper`` instance.
            prompt: A ``PromptTemplate`` instance whose ``input_variables``
                include ``stage_outputs``. Defaults to ``HUMAN_TEMPLATE``.
            cache: Optional ``LLMCache`` for caching.
            prompt_builder: Optional ``PromptBuilder`` for dynamic system-prompt
                construction. When provided, the hardcoded ``SYSTEM_PROMPT`` is
                replaced with a context-aware prompt built by the builder.

        Raises:
            TypeError: If *llm* is not an ``LLMWrapper`` or *prompt* is not
                a ``PromptTemplate``.
        """
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

    def run(self, memory: PipelineMemory, output_root: str = "output") -> str:
        """Generate a Markdown report and JSON summary from pipeline memory.

        Parameters
        ----------
        memory:
            The ``PipelineMemory`` instance containing all stage outputs.
        output_root:
            Root directory for output files (default: ``"output"``). The
            report files are written to ``<output_root>/reports/``.

        Returns
        -------
        str
            Absolute path to the report directory (``<output_root>/reports/``).
        """
        # --- Check for empty memory ---
        all_outputs = memory.get_all_outputs()
        if not all_outputs:
            logger.info("Empty pipeline memory — writing minimal empty report")
            return self._write_empty_report(output_root)

        # --- Build stage summary for LLM context ---
        stage_summary = memory.summarize_for_next_stage("report")

        # --- Check cache ---
        cache_key = _compute_stage_hash(memory)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("Report cache hit (key=%s...)", cache_key[:12])
                return self._write_report_from_cached(cached, output_root)

        # --- Invoke LLM ---
        try:
            report_output = self._invoke_llm(stage_summary)
        except Exception as exc:
            logger.error("LLM report generation failed: %s", exc)
            report_output = self._build_fallback_report(memory)

        # --- Write cache ---
        if self._cache is not None:
            self._cache.set(
                cache_key,
                {
                    "markdown_report": report_output.markdown_report,
                    "json_summary": report_output.json_summary,
                },
            )
            logger.debug("Report result cached (key=%s...)", cache_key[:12])

        # --- Write files and return path ---
        return self._write_report_files(report_output, output_root)

    # ------------------------------------------------------------------
    # Internal helpers — LLM invocation
    # ------------------------------------------------------------------

    def _invoke_llm(self, stage_summary: str) -> ReportOutput:
        """Invoke the LLM to generate the report.

        Attempts the LLM call once with the standard messages. If that fails
        (e.g. malformed response), a second attempt is made with an explicit
        format-correction instruction appended.

        Args:
            stage_summary: Concatenated stage summaries from
                ``PipelineMemory.summarize_for_next_stage()``.

        Returns:
            A validated ``ReportOutput`` instance.

        Raises:
            Exception: If both the initial call and the retry fail.
        """
        messages = self._build_messages(stage_summary)

        try:
            result: ReportOutput = self._llm.invoke_structured(
                messages=messages,
                output_schema=ReportOutput,
            )
            return result
        except Exception as exc:
            logger.warning(
                "First report LLM call failed: %s. Retrying with "
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
                    output_schema=ReportOutput,
                )
                return result
            except Exception as inner_exc:
                logger.error(
                    "Report LLM call failed after format-correction retry: %s",
                    inner_exc,
                )
                raise

    def _build_messages(self, stage_summary: str) -> list[dict]:
        """Build the system + user message list for the LLM call.

        Args:
            stage_summary: The concatenated summaries of all prior pipeline
                stages.

        Returns:
            A list of message dicts with ``role`` and ``content`` keys.
        """
        human_message = self._prompt.format(stage_outputs=stage_summary)
        system_content = (
            self._prompt_builder.build_system_only("report")
            if self._prompt_builder is not None
            else SYSTEM_PROMPT
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": human_message},
        ]

    # ------------------------------------------------------------------
    # Internal helpers — file writing
    # ------------------------------------------------------------------

    def _write_report_files(
        self,
        report_output: ReportOutput,
        output_root: str,
    ) -> str:
        """Write the report Markdown and JSON files to disk.

        Args:
            report_output: The ``ReportOutput`` from the LLM.
            output_root: Root output directory.

        Returns:
            Absolute path to the reports directory.
        """
        reports_dir = str(Path(output_root) / "reports")
        ensure_output_dir(reports_dir)

        # Write the Markdown report
        _write_report_file(
            file_path="report.md",
            content=report_output.markdown_report,
            fmt="md",
            output_root=reports_dir,
        )
        logger.info("Markdown report written to %s/report.md", reports_dir)

        # Write the JSON summary
        json_content = json.dumps(
            report_output.json_summary,
            indent=2,
            ensure_ascii=False,
        )
        _write_report_file(
            file_path="report.json",
            content=json_content,
            fmt="json",
            output_root=reports_dir,
        )
        logger.info("JSON report written to %s/report.json", reports_dir)

        logger.info("Report generation complete — directory: %s", reports_dir)
        return str(Path(reports_dir).absolute())

    def _write_report_from_cached(
        self,
        cached: dict[str, Any],
        output_root: str,
    ) -> str:
        """Write report files from cached data without invoking the LLM.

        Args:
            cached: A dict with ``markdown_report`` and ``json_summary`` keys.
            output_root: Root output directory.

        Returns:
            Absolute path to the reports directory.
        """
        markdown = cached.get("markdown_report", "")
        json_summary = cached.get("json_summary", {})

        reports_dir = str(Path(output_root) / "reports")
        ensure_output_dir(reports_dir)

        _write_report_file(
            file_path="report.md",
            content=markdown,
            fmt="md",
            output_root=reports_dir,
        )
        _write_report_file(
            file_path="report.json",
            content=json.dumps(json_summary, indent=2, ensure_ascii=False),
            fmt="json",
            output_root=reports_dir,
        )

        return str(Path(reports_dir).absolute())

    # ------------------------------------------------------------------
    # Internal helpers — empty memory report
    # ------------------------------------------------------------------

    def _write_empty_report(self, output_root: str) -> str:
        """Write a minimal report when pipeline memory contains no data.

        Args:
            output_root: Root output directory.

        Returns:
            Absolute path to the reports directory.
        """
        reports_dir = str(Path(output_root) / "reports")
        ensure_output_dir(reports_dir)

        now = datetime.now(timezone.utc).isoformat()

        markdown = (
            f"# SDK Pipeline Report\n\n"
            f"**Analysis Date:** {now}\n\n"
            f"## Pipeline Status\n\n"
            f"No pipeline stage data was found. No stages have been "
            f"executed yet.\n\n"
            f"| Stage | Status |\n"
            f"|-------|--------|\n"
            f"| (all) | ⚠️ No data available |\n\n"
            f"---\n\n"
            f"*This is an automatically generated minimal report. "
            f"Run the pipeline stages before invoking the report chain "
            f"to obtain a full analysis.*\n"
        )

        json_summary = {
            "sdk_root": "",
            "pipeline_timestamp": now,
            "notes": "No pipeline stage data available.",
            "inventory_counts": {},
            "analysis": {},
            "test_cases": {},
            "generated_files": {},
        }

        _write_report_file(
            file_path="report.md",
            content=markdown,
            fmt="md",
            output_root=reports_dir,
        )
        _write_report_file(
            file_path="report.json",
            content=json.dumps(json_summary, indent=2, ensure_ascii=False),
            fmt="json",
            output_root=reports_dir,
        )

        logger.info("Empty report written to %s", reports_dir)
        return str(Path(reports_dir).absolute())

    # ------------------------------------------------------------------
    # Internal helpers — fallback report when LLM is unreachable
    # ------------------------------------------------------------------

    def _build_fallback_report(self, memory: PipelineMemory) -> ReportOutput:
        """Build a basic structural report from available metadata.

        This is used when the LLM is unreachable or returns an invalid
        response. The report is assembled from whatever stage outputs are
        present in memory, noting which stages had data and which did not.

        Args:
            memory: The ``PipelineMemory`` instance.

        Returns:
            A ``ReportOutput`` populated with whatever data is available.
        """
        all_outputs = memory.get_all_outputs()
        now = datetime.now(timezone.utc).isoformat()

        # Identify which stages produced output
        stage_list = memory.get_stage_order()
        stages_with_data = [s for s in stage_list if all_outputs.get(s)]
        stages_empty = [s for s in stage_list if not all_outputs.get(s)]

        sections: list[str] = [
            "# SDK Pipeline Report\n\n",
            f"**Analysis Date:** {now}\n\n",
            "**Status:** ⚠️ Report generated in fallback mode "
            "(LLM was unavailable).\n\n",
        ]

        # --- Pipeline stage summary ---
        sections.append("## Pipeline Stage Summary\n\n")
        sections.append("| Stage | Status |\n")
        sections.append("|-------|--------|\n")
        for s in stages_with_data:
            sections.append(f"| {s} | ✅ Data available |\n")
        for s in stages_empty:
            sections.append(f"| {s} | ❌ No output |\n")
        sections.append("\n")

        # --- API Overview (from scanner stage) ---
        scanner_output = all_outputs.get("scanner")
        if scanner_output:
            sections.append("## API Overview\n\n")
            sections.append("```json\n")
            sections.append(
                json.dumps(scanner_output, indent=2, ensure_ascii=False)[:3000]
            )
            sections.append("\n```\n\n")

        # --- Analysis Summary ---
        analysis_output = all_outputs.get("analysis")
        if analysis_output:
            sections.append("## Analysis Summary\n\n")
            sections.append("```json\n")
            sections.append(
                json.dumps(analysis_output, indent=2, ensure_ascii=False)[:3000]
            )
            sections.append("\n```\n\n")

        # --- Test Design ---
        test_output = all_outputs.get("test_design")
        if test_output:
            sections.append("## Test Design\n\n")
            sections.append("```json\n")
            sections.append(
                json.dumps(test_output, indent=2, ensure_ascii=False)[:3000]
            )
            sections.append("\n```\n\n")

        # --- Generated Files ---
        code_gen_output = all_outputs.get("code_gen")
        ci_gen_output = all_outputs.get("ci_gen")
        if code_gen_output or ci_gen_output:
            sections.append("## Generated Files\n\n")
            sections.append("| Source | Details |\n")
            sections.append("|--------|--------|\n")
            if code_gen_output:
                file_count = self._count_files_in_output(code_gen_output)
                sections.append(
                    f"| Code Gen | {file_count} file(s) produced |\n"
                )
            if ci_gen_output:
                file_count = self._count_files_in_output(ci_gen_output)
                sections.append(
                    f"| CI Gen | {file_count} file(s) produced |\n"
                )
            sections.append("\n")

        # --- Notes ---
        sections.append("---\n\n")
        sections.append(
            "*This report was generated in fallback mode because the LLM "
            "was unavailable or returned an invalid response. Consider "
            "re-running the report stage when the LLM is accessible for a "
            "full natural-language analysis.*\n"
        )

        markdown_report = "".join(sections)

        json_summary: dict[str, Any] = {
            "sdk_root": "",
            "pipeline_timestamp": now,
            "stages_executed": stage_list,
            "stages_with_output": stages_with_data,
            "stages_empty": stages_empty,
            "notes": (
                "Report generated in fallback mode — LLM was unavailable "
                "or returned an invalid response."
            ),
        }

        # Include raw stage data in the JSON summary when available
        for stage_name in stages_with_data:
            json_summary[stage_name] = str(all_outputs[stage_name])[:500]

        return ReportOutput(
            markdown_report=markdown_report,
            json_summary=json_summary,
        )

    @staticmethod
    def _count_files_in_output(output: dict[str, Any]) -> int:
        """Count the number of generated files in a code_gen or ci_gen output.

        Scans for common keys that hold file mappings:
        - ``files``: a dict of filename → content
        - ``generated_files``: a dict of filename → content
        - ``filenames``: a list of filenames

        Returns 0 if no file-related keys are found.
        """
        for key in ("files", "generated_files"):
            value = output.get(key, {})
            if isinstance(value, dict):
                return len(value)
        for key in ("filenames",):
            value = output.get(key, [])
            if isinstance(value, list):
                return len(value)
        return 0
