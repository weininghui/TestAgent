r"""Prompt templates and dynamic prompt construction toolkit.

This package provides:

- **Static prompts**: Per-stage ``SYSTEM_PROMPT`` constants and
  ``HUMAN_TEMPLATE`` ``PromptTemplate`` instances in each module (e.g.
  ``scanner_prompt``, ``analysis_prompt``, ...).
- **``build_system_prompt()``**: Per-stage functions that delegate to the
  meta-system builder for dynamic, technique-enriched prompts.
- **``PromptBuilder``**: Central orchestrator that analyses task context,
  selects reasoning techniques, and assembles the final message list.
- **Techniques**: ``Technique`` enum, ``TaskContext`` dataclass, and
  ``TechniqueSelector`` for rule-based technique selection.
- **Meta-system**: ``build_stage_system_prompt()`` and per-stage builder
  functions in ``meta_system``.
- **Repair prompt**: ``build_repair_system_prompt()`` and ``build_fix_prompt()``
  for error-recovery scenarios.

Usage::

    from agents.prompts import PromptBuilder

    builder = PromptBuilder()
    messages = builder.build(
        stage="scanner",
        context={"input_size": 15},
        template_vars={"sdk_root": "...", "header_files": "...", "header_content": "..."},
    )
"""

from __future__ import annotations

from agents.prompts.builder import PromptBuilder
from agents.prompts.meta_system import (
    STAGE_SYSTEM_PROMPT_BUILDERS,
    build_stage_system_prompt,
    build_scanner_system_prompt,
    build_analysis_system_prompt,
    build_test_design_system_prompt,
    build_code_gen_system_prompt,
    build_ci_gen_system_prompt,
    build_report_system_prompt,
)
from agents.prompts.techniques import (
    TECHNIQUE_INSTRUCTIONS,
    TaskContext,
    Technique,
    TechniqueSelector,
    format_technique_instructions,
)
from agents.prompts.repair_prompt import build_fix_prompt, build_repair_system_prompt

# Per-stage convenience builders
from agents.prompts.scanner_prompt import build_system_prompt as build_scanner_prompt
from agents.prompts.analysis_prompt import build_system_prompt as build_analysis_prompt
from agents.prompts.test_design_prompt import build_system_prompt as build_test_design_prompt
from agents.prompts.code_gen_prompt import build_system_prompt as build_code_gen_prompt
from agents.prompts.ci_gen_prompt import build_system_prompt as build_ci_gen_prompt
from agents.prompts.report_prompt import build_system_prompt as build_report_prompt

# Human templates for each stage
from agents.prompts.scanner_prompt import HUMAN_TEMPLATE as SCANNER_HUMAN_TEMPLATE
from agents.prompts.analysis_prompt import HUMAN_TEMPLATE as ANALYSIS_HUMAN_TEMPLATE
from agents.prompts.test_design_prompt import HUMAN_TEMPLATE as TEST_DESIGN_HUMAN_TEMPLATE
from agents.prompts.code_gen_prompt import HUMAN_TEMPLATE as CODE_GEN_HUMAN_TEMPLATE
from agents.prompts.ci_gen_prompt import HUMAN_TEMPLATE as CI_GEN_HUMAN_TEMPLATE
from agents.prompts.report_prompt import HUMAN_TEMPLATE as REPORT_HUMAN_TEMPLATE

__all__ = [
    # Core builder
    "PromptBuilder",
    # Meta-system builders
    "build_stage_system_prompt",
    "STAGE_SYSTEM_PROMPT_BUILDERS",
    "build_scanner_system_prompt",
    "build_analysis_system_prompt",
    "build_test_design_system_prompt",
    "build_code_gen_system_prompt",
    "build_ci_gen_system_prompt",
    "build_report_system_prompt",
    # Technique infrastructure
    "Technique",
    "TaskContext",
    "TechniqueSelector",
    "TECHNIQUE_INSTRUCTIONS",
    "format_technique_instructions",
    # Repair prompts
    "build_repair_system_prompt",
    "build_fix_prompt",
    # Per-stage convenience builders
    "build_scanner_prompt",
    "build_analysis_prompt",
    "build_test_design_prompt",
    "build_code_gen_prompt",
    "build_ci_gen_prompt",
    "build_report_prompt",
    # Human templates
    "SCANNER_HUMAN_TEMPLATE",
    "ANALYSIS_HUMAN_TEMPLATE",
    "TEST_DESIGN_HUMAN_TEMPLATE",
    "CODE_GEN_HUMAN_TEMPLATE",
    "CI_GEN_HUMAN_TEMPLATE",
    "REPORT_HUMAN_TEMPLATE",
]
