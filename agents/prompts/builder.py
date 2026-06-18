"""PromptBuilder — dynamic prompt construction with reasoning techniques.

The central orchestrator that:
1. **Analyses** the task context (stage, input size, error state, etc.)
2. **Selects** appropriate reasoning techniques (CoT, ToT, few-shot, etc.)
3. **Composes** a system prompt dynamically using the selected techniques
4. **Formats** the user message with actual data

Usage::

    from agents.prompts.builder import PromptBuilder

    builder = PromptBuilder()
    messages = builder.build(
        stage="scanner",
        context={
            "sdk_root": "/path/to/sdk",
            "input_size": 15,  # number of headers
            "requires_structured": True,
        },
        template_vars={
            "sdk_root": "/path/to/sdk",
            "header_files": "...",
            "header_content": "...",
        },
    )
    # → [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.prompts import PromptTemplate

from agents.prompts.meta_system import build_stage_system_prompt
from agents.prompts.techniques import TaskContext, TechniqueSelector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fallback human templates for each stage
# ---------------------------------------------------------------------------

_STAGE_HUMAN_TEMPLATES: dict[str, PromptTemplate] = {}

# Lazy-import to avoid circular deps at module level
def _get_human_template(stage: str) -> PromptTemplate:
    """Return the human-side PromptTemplate for *stage*."""
    if not _STAGE_HUMAN_TEMPLATES:
        _lazy_load_templates()
    template = _STAGE_HUMAN_TEMPLATES.get(stage)
    if template is None:
        raise ValueError(f"No human template for stage '{stage}'")
    return template


def _lazy_load_templates() -> None:
    """Import and register all human templates."""
    from agents.prompts.analysis_prompt import HUMAN_TEMPLATE as analysis_ht
    from agents.prompts.ci_gen_prompt import HUMAN_TEMPLATE as ci_gen_ht
    from agents.prompts.code_gen_prompt import HUMAN_TEMPLATE as code_gen_ht
    from agents.prompts.report_prompt import HUMAN_TEMPLATE as report_ht
    from agents.prompts.scanner_prompt import HUMAN_TEMPLATE as scanner_ht
    from agents.prompts.test_design_prompt import HUMAN_TEMPLATE as test_design_ht

    _STAGE_HUMAN_TEMPLATES.update({
        "scanner": scanner_ht,
        "analysis": analysis_ht,
        "test_design": test_design_ht,
        "code_gen": code_gen_ht,
        "ci_gen": ci_gen_ht,
        "report": report_ht,
    })


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

class PromptBuilder:
    """Builds dynamic prompts with context-aware technique selection.

    Parameters
    ----------
    technique_selector:
        Optional custom ``TechniqueSelector``. Defaults to a fresh instance.
    """

    def __init__(
        self,
        technique_selector: TechniqueSelector | None = None,
    ) -> None:
        self._selector = technique_selector or TechniqueSelector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        stage: str,
        context: dict[str, Any] | TaskContext | None = None,
        template_vars: dict[str, Any] | None = None,
        system_override: str | None = None,
    ) -> list[dict[str, str]]:
        """Construct a message list for an LLM invocation.

        Parameters
        ----------
        stage:
            Pipeline stage name (``"scanner"``, ``"analysis"``, etc.).
        context:
            Task context dict or ``TaskContext`` instance.  If ``None``, a
            minimal context is inferred from *stage*.
        template_vars:
            Variables to format into the human-side template.
        system_override:
            If provided, use this exact string as the system prompt instead of
            building one dynamically.

        Returns
        -------
        list[dict[str, str]]
            ``[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]``

        Raises
        ------
        ValueError
            If *stage* is not recognised.
        """
        # 1 — Build or parse context ----------------------------------------
        ctx = self._to_context(stage, context)

        # 2 — Build system prompt -------------------------------------------
        system_content = system_override or build_stage_system_prompt(stage, ctx)

        # 3 — Build human message -------------------------------------------
        human_content = ""
        if template_vars:
            try:
                template = _get_human_template(stage)
                human_content = template.format(**template_vars)
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "Failed to format human template for '%s': %s. "
                    "Falling back to raw template_vars.", stage, exc
                )
                human_content = _fmt_fallback(template_vars)

        # 4 — Assemble messages ---------------------------------------------
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_content},
        ]
        if human_content:
            messages.append({"role": "user", "content": human_content})

        return messages

    def build_system_only(
        self,
        stage: str,
        context: dict[str, Any] | TaskContext | None = None,
    ) -> str:
        """Build only the system prompt string (no human message).

        Useful for chains that construct the user message separately.
        """
        ctx = self._to_context(stage, context)
        return build_stage_system_prompt(stage, ctx)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_context(
        stage: str,
        raw: dict[str, Any] | TaskContext | None,
    ) -> TaskContext:
        """Normalise *raw* to a ``TaskContext``."""
        if isinstance(raw, TaskContext):
            return raw
        if isinstance(raw, dict):
            return TaskContext.from_dict({**raw, "stage": stage})
        return TaskContext(stage=stage)

    @staticmethod
    def _fmt_fallback(template_vars: dict[str, Any]) -> str:
        """Fallback formatting when the PromptTemplate fails."""
        lines: list[str] = []
        for key, value in template_vars.items():
            lines.append(f"{key}: {value}")
        return "\n\n".join(lines)
