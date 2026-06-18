"""Repair prompts — compilation error diagnosis and fix generation.

This module implements a **reflection-driven repair loop**:

1. Receives a compilation error (compiler output + failing source code).
2. Uses chain-of-thought to diagnose the root cause.
3. Generates a corrected version.
4. Optionally self-validates the fix.

The prompts here are dynamic — the LLM decides the best repair strategy
based on the error type (syntax, type mismatch, missing include, linker
error, etc.).
"""

from __future__ import annotations

from typing import Any

from agents.prompts.techniques import (
    TaskContext,
    Technique,
    TechniqueSelector,
    format_technique_instructions,
)


def build_repair_system_prompt(context: TaskContext | None = None) -> str:
    """Build system prompt for compilation error repair.

    Parameters
    ----------
    context:
        Optional task context. If provided, technique selection adapts to
        the error type and retry count.
    """
    if context is None:
        context = TaskContext(stage="repair", is_retry=False)

    # Always include reflection + CoT for repair tasks
    techniques = {Technique.REFLECTION, Technique.CHAIN_OF_THOUGHT, Technique.SELF_CONSISTENCY}

    base = f"""You are a senior C++ reliability engineer specialised in fixing compilation errors in Google Test (GTest) test suites.

## Your Task
You receive:
1. **Source file(s)** — C++ GTest source code that failed to compile.
2. **Compiler output** — The error messages from the compiler (MSVC, GCC, or Clang).
3. **SDK headers** — (optional) The SDK header files being tested.

Diagnose the root cause and produce a **corrected version** of the source file(s).

## Diagnosis Process
Before writing the fix, analyse the error systematically:

### 1. Error Classification
- **Syntax error** — Missing semicolons, brackets, or typos.
- **Type mismatch** — Wrong argument types, missing casts, const correctness.
- **Missing include** — Header not included, wrong path, typo in include.
- **Linker error** — Missing symbol definition, wrong library linkage.
- **API mismatch** — SDK API was used incorrectly (wrong function signature, missing namespace).
- **Test logic error** — Assertion misuse, fixture setup failure.

### 2. Root Cause
Explain in 1-2 sentences what the compiler is complaining about and why.

### 3. Fix Strategy
Describe the minimal change that resolves the error without altering test semantics.

{format_technique_instructions(techniques, context)}

## Fix Rules
- Make the **minimum change** needed to fix the compilation error.
- Preserve the original test intent and coverage.
- Do not remove tests unless they are fundamentally impossible (and explain why).
- Ensure all includes are present.
- Use the correct GTest/GMock macros for the assertion type.
- Verify namespace qualifications match the SDK headers.

## Output Format
```json
{{"diagnosis": {{"error_type": "...", "root_cause": "...", "fix_strategy": "..."}}, "files": {{"filename.cc": "// corrected source..."}}, "warnings": []}}
```

No markdown fences, no extra commentary."""

    return base


def build_fix_prompt(
    source_files: dict[str, str],
    compiler_output: str,
    sdk_headers: dict[str, str] | None = None,
    attempt: int = 1,
) -> list[dict[str, str]]:
    """Build a repair message pair for a compilation error.

    Parameters
    ----------
    source_files:
        Map of filename → source content for the failing files.
    compiler_output:
        Raw compiler error output.
    sdk_headers:
        Optional map of SDK header filename → content, for context.
    attempt:
        Current repair attempt number (1-based). Used for technique selection.

    Returns
    -------
    list[dict[str, str]]
        ``[system_message, user_message]`` ready for LLM invocation.
    """
    ctx = TaskContext(
        stage="repair",
        is_retry=attempt > 1,
        retry_count=attempt - 1,
        previous_error=compiler_output[:500] if attempt > 1 else None,
        requires_structured=True,
        output_schema="RepairOutput",
    )

    system = build_repair_system_prompt(ctx)

    # Build user message with source and error
    parts: list[str] = ["## Source Files\n"]
    for fname, content in source_files.items():
        parts.append(f"### {fname}\n```cpp\n{content}\n```\n")

    parts.append(f"## Compiler Output\n```\n{compiler_output}\n```\n")

    if sdk_headers:
        parts.append("## SDK Headers (context)\n")
        for fname, content in list(sdk_headers.items())[:5]:  # limit to 5
            parts.append(f"### {fname}\n```cpp\n{content[:2000]}\n```\n")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(parts)},
    ]
