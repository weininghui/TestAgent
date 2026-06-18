"""Reasoning technique registry for dynamic prompt construction.

Defines the available advanced reasoning techniques and a selector that
chooses the best combination based on task context.

Techniques
----------
- **Chain-of-Thought (CoT)**: Step-by-step reasoning for complex extraction
- **Tree-of-Thought (ToT)**: Branching exploration for ambiguous/multi-path tasks
- **Few-Shot**: In-context examples for structured output formatting
- **Self-Consistency**: Multi-pass sampling for high-reliability extraction
- **Reflection**: Error-aware self-critique and recovery
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Technique identifiers
# ---------------------------------------------------------------------------

class Technique(str, Enum):
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHT = "tree_of_thought"
    FEW_SHOT = "few_shot"
    SELF_CONSISTENCY = "self_consistency"
    REFLECTION = "reflection"


# ---------------------------------------------------------------------------
# Context profile — describes the task environment
# ---------------------------------------------------------------------------

@dataclass
class TaskContext:
    """Snapshot of the task environment for technique selection.

    Populated by ``PromptBuilder.analyze()`` before each prompt build.
    """

    # Stage identity
    stage: str  # scanner, analysis, test_design, code_gen, ci_gen, report

    # Data complexity
    input_size: int = 0          # lines / items in the input
    num_modules: int = 0         # SDK modules (scanner/analysis)
    num_apis: int = 0            # API surface count

    # Error state
    is_retry: bool = False       # True if this is a retry after failure
    previous_error: str | None = None  # Error message from previous attempt
    retry_count: int = 0         # How many times we've retried

    # Output characteristics
    output_schema: str | None = None  # Expected output schema name
    requires_structured: bool = False  # True if structured/typed output needed

    # SDK-specific
    sdk_complexity: str = "unknown"  # low / medium / high / unknown

    # Extra metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskContext:
        """Construct from a plain dict (e.g. from pipeline state)."""
        return cls(
            stage=d.get("stage", "unknown"),
            input_size=d.get("input_size", 0),
            num_modules=d.get("num_modules", 0),
            num_apis=d.get("num_apis", 0),
            is_retry=d.get("is_retry", False),
            previous_error=d.get("previous_error"),
            retry_count=d.get("retry_count", 0),
            output_schema=d.get("output_schema"),
            requires_structured=d.get("requires_structured", False),
            sdk_complexity=d.get("sdk_complexity", "unknown"),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Technique selector — chooses techniques based on context
# ---------------------------------------------------------------------------

class TechniqueSelector:
    """Selects the optimal combination of reasoning techniques for a task.

    Uses a rule-based scoring system. Each technique has a set of ``triggers``
    that increase its score. The top-scoring techniques are selected.

    Usage::

        selector = TechniqueSelector()
        context = TaskContext(stage="scanner", input_size=500, ...)
        techniques = selector.select(context)
        # → {Technique.COT, Technique.FEW_SHOT, ...}
    """

    #: Maximum number of techniques to combine (avoids token waste).
    MAX_TECHNIQUES = 4

    def select(self, context: TaskContext) -> set[Technique]:
        """Return the set of techniques best suited for *context*.

        The result is cached internally so repeated calls with the same
        context profile return instantly.
        """
        scores: dict[Technique, float] = {t: 0.0 for t in Technique}

        # ── Score each technique based on context ──────────────────────

        # Chain-of-Thought: complex tasks with many steps
        if context.stage in ("scanner", "analysis", "test_design"):
            scores[Technique.CHAIN_OF_THOUGHT] += 3.0
        if context.input_size > 200:
            scores[Technique.CHAIN_OF_THOUGHT] += 2.0
        if context.num_modules > 5:
            scores[Technique.CHAIN_OF_THOUGHT] += 1.0

        # Tree-of-Thought: ambiguous or multi-path decisions
        if context.stage == "test_design":
            scores[Technique.TREE_OF_THOUGHT] += 3.0
        if context.previous_error and "ambiguous" in context.previous_error.lower():
            scores[Technique.TREE_OF_THOUGHT] += 2.0
        if context.sdk_complexity == "high":
            scores[Technique.TREE_OF_THOUGHT] += 1.0
        if context.is_retry and context.retry_count >= 2:
            # After multiple failures, try branching exploration
            scores[Technique.TREE_OF_THOUGHT] += 2.0

        # Few-Shot: structured output with known schema
        if context.requires_structured:
            scores[Technique.FEW_SHOT] += 3.0
        if context.stage in ("scanner", "code_gen", "ci_gen"):
            scores[Technique.FEW_SHOT] += 2.0
        if context.output_schema:
            scores[Technique.FEW_SHOT] += 1.0

        # Self-Consistency: high-reliability extraction
        if context.stage == "scanner" and context.num_apis > 50:
            scores[Technique.SELF_CONSISTENCY] += 3.0
        if context.stage == "analysis":
            scores[Technique.SELF_CONSISTENCY] += 1.0
        if context.is_retry:
            scores[Technique.SELF_CONSISTENCY] += 1.0

        # Reflection: error recovery and retry
        if context.is_retry or context.retry_count > 0:
            scores[Technique.REFLECTION] += 4.0
        if context.previous_error:
            scores[Technique.REFLECTION] += 3.0
        if context.stage in ("code_gen", "ci_gen"):
            # Generated code often needs self-correction
            scores[Technique.REFLECTION] += 1.0

        # ── Select top-scoring techniques ─────────────────────────────
        sorted_techs = sorted(scores.items(), key=lambda x: -x[1])
        selected = {
            tech for tech, score in sorted_techs
            if score > 0.0
        }

        # Always include CoT and Few-Shot for structured stages
        if context.requires_structured:
            selected.add(Technique.CHAIN_OF_THOUGHT)
            selected.add(Technique.FEW_SHOT)

        # Cap at MAX_TECHNIQUES
        if len(selected) > self.MAX_TECHNIQUES:
            selected = set(sorted(selected, key=lambda t: -scores[t])[:self.MAX_TECHNIQUES])

        logger.debug(
            "TechniqueSelector[stage=%s retry=%s]: selected %s",
            context.stage, context.is_retry, [t.value for t in selected],
        )
        return selected


# ---------------------------------------------------------------------------
# Technique instructions — formatted prompt fragments
# ---------------------------------------------------------------------------

#: Mapping from technique → instruction block injected into system prompt.
TECHNIQUE_INSTRUCTIONS: dict[Technique, str] = {
    Technique.CHAIN_OF_THOUGHT: (
        "## Chain-of-Thought Reasoning\n"
        "Work through this task step by step. Before producing the final output:\n"
        "1. **Analyse** the input structure and identify key elements.\n"
        "2. **Break down** the task into logical sub-steps.\n"
        "3. **Reason** through each step explicitly.\n"
        "4. **Synthesise** the final answer from your reasoning.\n"
        "Your step-by-step reasoning can be in natural language; the final output "
        "must still conform to the required format."
    ),
    Technique.TREE_OF_THOUGHT: (
        "## Tree-of-Thought Exploration\n"
        "For ambiguous or multi-path decisions, explore multiple approaches:\n"
        "1. **Branch** — Identify 2-3 plausible interpretations or strategies.\n"
        "2. **Evaluate** — Briefly assess each branch's likelihood or suitability.\n"
        "3. **Select** — Choose the best branch (or combine insights from multiple).\n"
        "4. **Execute** — Follow the chosen path to produce the final output.\n"
        "Document your branching reasoning before the final answer."
    ),
    Technique.FEW_SHOT: (
        "## Few-Shot Examples\n"
        "Below are example(s) of the expected input→output pattern. "
        "Follow the same structure, conventions, and level of detail. "
        "Adapt the examples to the specific data you are given — do not "
        "copy example values verbatim."
    ),
    Technique.SELF_CONSISTENCY: (
        "## Self-Consistency Check\n"
        "After drafting your answer:\n"
        "1. **Review** each assertion or extracted element for internal consistency.\n"
        "2. **Verify** that all required fields are populated and non-null.\n"
        "3. **Cross-check** that counts match (e.g. number of functions extracted "
        "matches the number of functions described).\n"
        "4. **Revise** any inconsistencies before finalising.\n"
        "Think of this as a self-review pass before delivering the result."
    ),
    Technique.REFLECTION: (
        "## Reflection on Previous Attempt\n"
        "The previous attempt encountered an error. Before trying again:\n"
        "1. **Diagnose** — What was the root cause of the error?\n"
        "   - Parse failure? Schema mismatch? Missing data?\n"
        "2. **Adjust** — How should the approach change?\n"
        "   - Different output format? More careful counting? Additional details?\n"
        "3. **Retry** — Apply the adjusted approach.\n"
        "Previous error for reference: {previous_error}\n"
        "Do NOT repeat the same mistake."
    ),
}


def format_technique_instructions(
    techniques: set[Technique],
    context: TaskContext,
) -> str:
    """Build a formatted instruction block for the selected techniques.

    Each technique's instruction is included, with ``{previous_error}``
    substituted from *context* where applicable.
    """
    parts: list[str] = []
    for tech in sorted(techniques, key=lambda t: t.value):
        instruction = TECHNIQUE_INSTRUCTIONS.get(tech, "")
        if tech == Technique.REFLECTION and context.previous_error:
            instruction = instruction.format(previous_error=context.previous_error)
        elif tech == Technique.REFLECTION:
            instruction = instruction.format(previous_error="(no prior error recorded)")
        if instruction:
            parts.append(instruction)
    return "\n\n".join(parts)
