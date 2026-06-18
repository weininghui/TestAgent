"""Meta-system prompt templates.

Instead of hardcoding a fixed reasoning strategy for each stage, these
meta-prompts instruct the LLM to **self-select the best approach** based
on the specific data and context it receives.

Each template describes:
1. **The goal** — what the stage needs to produce.
2. **Available techniques** — reasoning strategies the LLM can choose from.
3. **Guidance** — rough indicators for when each technique is appropriate.
4. **Output contract** — what the final response must look like.

The LLM then dynamically constructs its own reasoning approach, adapting
to the complexity and ambiguity of the actual input.
"""

from __future__ import annotations

from typing import Any

from agents.prompts.techniques import (
    TaskContext,
    Technique,
    format_technique_instructions,
)

# ---------------------------------------------------------------------------
# Stage-specific meta-system prompt builders
# ---------------------------------------------------------------------------

# Each ``_build_*_system_prompt`` function takes a ``TaskContext`` and returns
# a system-prompt string that includes meta-instructions + technique guidance.


def build_scanner_system_prompt(context: TaskContext) -> str:
    """Build dynamic scanner system prompt with technique selection."""
    techniques = _select_techniques(context)

    return f"""You are an expert C/C++ static analysis engine. Your task is to parse SDK header files and produce a **complete, structured JSON inventory** of every public API surface element.

## Task Scope
- **SDK root**: {{sdk_root}}
- **Files to scan**: {{header_files}}
- **Total headers in this batch**: {context.input_size} file(s)

## Extraction Requirements
Extract the following from each header file:
1. **Functions** — free (non-member) functions with full signatures, params, return types.
2. **Classes/Structs** — class definitions with methods, access levels, const/static qualifiers.
3. **Enums** — enum types and their values.
4. **Typedefs/Using** — type alias declarations.

Group extracted data into modules. Each module has a unique ``module_id`` (e.g. ``mod::vision``). Place orphan headers into a ``"root"`` module.

## Output Schema
Return **only** a valid JSON object matching the ``APIInventory`` structure. The JSON must have:
```json
{{"sdk_root": "...", "modules": [{{"module_id": "...", "name": "...", "headers": [...]}}]}}
```

{format_technique_instructions(techniques, context)}

## Quality Rules
- **Every** symbol must be captured — no omissions.
- Preserve types verbatim (e.g. ``"const char*"``, ``"std::vector<int>"``).
- Include symbols inside ``#ifdef`` blocks (do not evaluate preprocessor conditions).
- Do **not** include implementation bodies, macros, ``#include`` directives, or comments.
- Return ONLY valid JSON — no markdown fences, no commentary, no extra text."""


def build_analysis_system_prompt(context: TaskContext) -> str:
    """Build dynamic analysis system prompt."""
    techniques = _select_techniques(context)

    return f"""You are a senior C/C++ software architect and QA analyst. You receive an ``APIInventory`` JSON payload describing the public surface of an SDK. Your job is to produce a **thorough, actionable analysis report**.

## Analysis Dimensions
Analyse **every** element and produce a JSON with these sections:
1. **function_complexity** — For each function/method: cyclomatic estimate (low/medium/high), reasoning, param count, suspicious flag.
2. **class_hierarchy_analysis** — Base classes, polymorphism, rule-of-five compliance, cohesion.
3. **design_patterns** — Detect patterns (Factory, Singleton, RAII, PImpl, CRTP, etc.).
4. **memory_management_concerns** — Raw pointers, manual new/delete, ownership ambiguity.
5. **thread_safety** — Mutable shared state, reentrancy, locking.
6. **test_priorities** — P0–P3 ratings with rationale and test suggestions.

{format_technique_instructions(techniques, context)}

## Output Format
Return ONLY a valid JSON object with the six keys above. Empty lists for sections with no findings. No markdown fences, no extra commentary."""


def build_test_design_system_prompt(context: TaskContext) -> str:
    """Build dynamic test design system prompt."""
    techniques = _select_techniques(context)

    return f"""You are a senior C/C++ test architect specialised in Google Test (GTest) and SDK verification. Design a **comprehensive test suite** for the given API inventory.

## Coverage Mandate
- Cover **every** public API surface element at least once.
- Maximum **100 test cases**. If coverage exceeds 100, prioritise P0/P1 items.
- For suspicious functions or rule-of-five violations, add **additional** targeted tests.

## Test Categories
1. **Unit tests** — Normal, null-input, empty-input, boundary, error-code for each function. Construction, destruction, method-call, edge-case for each class.
2. **Integration tests** — Multi-API workflows (init→configure→process→teardown), resource cycles, data flow.
3. **Contract tests** — Precondition violation, postcondition verification, invariant checks.

{format_technique_instructions(techniques, context)}

## Output Format
Return ONLY a JSON object:
```json
{{"warnings": [], "cases": [{{"test_id": "...", "api_id": "...", ...}}]}}
```
No markdown fences, no extra text."""


def build_code_gen_system_prompt(context: TaskContext) -> str:
    """Build dynamic code generation system prompt."""
    techniques = _select_techniques(context)

    return f"""You are an expert C++ test-code generator specialising in Google Test (GTest). Produce **compilable C++ source files** implementing every test case in the ``TestCaseCollection``.

## File Structure
- One ``.cc`` file per SDK module (e.g. ``test_vision.cc``, ``test_core.cc``).
- Each file must be self-contained with proper ``#include`` directives.
- Use ``TEST_F`` fixtures for classes with 3+ test cases, ``TEST`` for free functions.

## Code Quality
- Follow Arrange-Act-Comment pattern in each test body.
- Use appropriate assertion macros (``EXPECT_EQ``, ``EXPECT_NEAR``, ``ASSERT_TRUE``, etc.).
- Use ``TEST_P`` for parameterised tests when the same logic applies to multiple inputs.
- No ``using namespace`` in global scope.
- Wrap helpers and test data in anonymous namespaces.

{format_technique_instructions(techniques, context)}

## Output Format
Return a JSON object mapping filename to complete source content:
```json
{{"files": {{"test_core.cc": "// entire source...", "test_vision.cc": "// ..."}}}}
```
Each file must compile independently. Do NOT include markdown fences."""


def build_ci_gen_system_prompt(context: TaskContext) -> str:
    """Build dynamic CI/CD generation system prompt."""
    techniques = _select_techniques(context)

    return f"""You are a senior build-and-CI engineer specialised in C++ projects. Produce a complete, portable build-and-test pipeline for the generated GTest suite.

## Deliverables
1. **CMakeLists.txt** — CMake project using FetchContent for GTest, one executable per test file, CTest enabled, Ninja generator.
2. **.github/workflows/test.yml** — GitHub Actions workflow for matrix builds (windows-latest, ubuntu-latest; Debug, Release).
3. **CMakePresets.json** — Presets for MSVC and GCC with configurable SDK paths.

{format_technique_instructions(techniques, context)}

## Output Format
Return a JSON object:
```json
{{"files": {{"CMakeLists.txt": "...", ".github/workflows/test.yml": "...", "CMakePresets.json": "..."}}, "notes": [] }}
```
No markdown fences. Each file must be complete and ready to use."""


def build_report_system_prompt(context: TaskContext) -> str:
    """Build dynamic report synthesis system prompt."""
    techniques = _select_techniques(context)

    return f"""You are a technical documentation specialist. Combine outputs from all pipeline stages into a comprehensive Markdown report and a structured JSON summary.

## Report Sections
1. **SDK Overview** — Headers scanned, modules, functions, classes, enums, typedefs.
2. **Analysis Summary** — Complexity distribution, patterns, memory/thread concerns, test priorities, top 5 risks.
3. **Test Case Summary** — Counts by category and subtype, coverage warnings.
4. **Generated Files Manifest** — File list with types and line counts.
5. **Build & Run Instructions** — CMake configure, build, and test commands.
6. **CI Pipeline** — Brief workflow description.

## JSON Summary
Include a structured ``json_summary`` with inventory counts, analysis stats, test case metrics, and file manifest. Include an ISO 8601 timestamp.

{format_technique_instructions(techniques, context)}

## Output Format
```json
{{"markdown_report": "...", "json_summary": {{...}}}}
```
Escape backticks and special characters properly in the Markdown string. No outer markdown fences."""


# ---------------------------------------------------------------------------
# Helper — technique selection
# ---------------------------------------------------------------------------

def _select_techniques(context: TaskContext) -> set[Technique]:
    """Select techniques for a system-prompt build, with defaults."""
    from agents.prompts.techniques import TechniqueSelector
    selector = TechniqueSelector()
    return selector.select(context)


# ---------------------------------------------------------------------------
# Builder map: stage → builder function
# ---------------------------------------------------------------------------

STAGE_SYSTEM_PROMPT_BUILDERS: dict[str, Any] = {
    "scanner": build_scanner_system_prompt,
    "analysis": build_analysis_system_prompt,
    "test_design": build_test_design_system_prompt,
    "code_gen": build_code_gen_system_prompt,
    "ci_gen": build_ci_gen_system_prompt,
    "report": build_report_system_prompt,
}


def build_stage_system_prompt(stage: str, context: TaskContext) -> str:
    """Build a system prompt for *stage* using the appropriate builder.

    Raises
    ------
    ValueError
        If *stage* has no registered builder.
    """
    builder = STAGE_SYSTEM_PROMPT_BUILDERS.get(stage)
    if builder is None:
        raise ValueError(
            f"No system-prompt builder registered for stage '{stage}'. "
            f"Available: {list(STAGE_SYSTEM_PROMPT_BUILDERS)}"
        )
    return builder(context)
