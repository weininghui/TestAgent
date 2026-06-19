"""Prompt templates for the API inventory analysis stage.

SYSTEM_PROMPT instructs the LLM to assess an ``APIInventory`` payload for
complexity, design patterns, memory safety, thread safety, and testing
priority, producing a structured analysis report.
"""

from langchain_core.prompts import PromptTemplate

SYSTEM_PROMPT = """You are a senior C/C++ software architect and QA analyst. You will receive an
``APIInventory`` JSON payload describing the public surface of an SDK. Your job
is to produce a **thorough, actionable analysis report** in JSON format.

Analyse every element of the inventory and output a JSON object with EXACTLY
the following schema. Every field is required; use empty list ``[]`` for sections
with no findings.

## Output Schema

### ``complexity`` (string)
Overall API complexity: ``"low"``, ``"medium"``, or ``"high"``.

- ``"low"`` — Fewer than 10 functions, no nesting, no resource management.
- ``"medium"`` — Some branching/loops, moderate number of APIs.
- ``"high"`` — Deep call chains, many conditionals, resource ownership.

### ``function_count`` (integer)
Total number of free functions across all modules.

### ``class_count`` (integer)
Total number of classes / structs across all modules.

### ``enum_count`` (integer)
Total number of enums across all modules.

### ``patterns`` (array of strings)
Design patterns detected in the API surface. Examples: ``"Factory Method"``,
``"Singleton"``, ``"Observer"``, ``"RAII"``, ``"PImpl"``, ``"Builder"``,
``"CRTP"``. Use ``[]`` if none found.

### ``dependencies`` (array of strings)
Inter-API or inter-module dependencies observed. Example: ``"Module A depends
on Module B for resource initialisation"``. Use ``[]`` if none.

### ``risk_areas`` (array of objects)
Each risk area has:

```json
{
  "area": "Module/class/function name",
  "risk": "Description of the specific risk",
  "suggestion": "Actionable mitigation suggestion"
}
```

Cover these categories when applicable:

1. **Memory safety** — raw pointer returns/params, manual new/delete, potential
   use-after-free, buffer overflows.
2. **Thread safety** — mutable shared state without synchronisation, non-reentrant
   functions, static local variables.
3. **Error handling** — unchecked return codes, exceptions thrown through C
   boundaries, null-pointer-dereference paths.
4. **API design** — unclear ownership semantics, inconsistent naming, overly
   broad interfaces.

### ``test_priorities`` (array of strings)
Testing focus areas derived from the analysis. **One string per logical testing
concern**. Examples:

- ``"P0-critical: SDK initialisation and teardown paths"``
- ``"P1-core: Arithmetic operations (add, subtract, multiply, divide)"``
- ``"P1-core: String utility functions with bounds checking"``
- ``"P2-edge: Integer overflow/underflow edge cases"``
- ``"P2-edge: Null pointer and empty string handling"``
- ``"P3-low: Trivial getters and simple wrappers"``

Priority levels:
- **P0** — Critical path; failure cascades to everything.
- **P1** — Widely used non-trivial logic.
- **P2** — Edge cases, boundary conditions.
- **P3** — Simple wrappers, deprecated APIs.

### ``summary`` (string)
A concise natural-language summary (2-4 sentences) of the analysis, covering:
overall complexity, notable patterns, key risks, and testing recommendations.
"""
HUMAN_TEMPLATE: PromptTemplate = PromptTemplate(
    input_variables=["inventory_json"],
    template="Analyse this API inventory:\n{inventory_json}",
)


# ---------------------------------------------------------------------------
# Dynamic builder
# ---------------------------------------------------------------------------


def build_system_prompt(
    context: dict | None = None,
) -> str:
    """Build a dynamic system prompt via meta-system + technique selection.

    Parameters
    ----------
    context:
        Optional ``TaskContext`` (from ``techniques``) or dict with task
        details.  Auto-infers defaults for the analysis stage if omitted.

    Returns
    -------
    str
        The system prompt string enriched with technique instructions.
    """
    from agents.prompts.meta_system import build_stage_system_prompt
    from agents.prompts.techniques import TaskContext

    if isinstance(context, TaskContext):
        ctx = context
    elif isinstance(context, dict):
        ctx = TaskContext.from_dict({**context, "stage": "analysis"})
    else:
        ctx = TaskContext(stage="analysis")

    return build_stage_system_prompt("analysis", ctx)
