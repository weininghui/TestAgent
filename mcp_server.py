#!/usr/bin/env python3
"""MCP server — expose the LangChain test-generation pipeline as LLM-callable tools.

Usage
-----
    # Run with stdio transport (default for OpenCode skills)
    python mcp_server.py

    # Or with SSE transport (for remote/container use)
    python mcp_server.py --transport sse --port 8080

Once running, the LLM (or any MCP client) can call any of the 6 tools
defined below.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from agents.cache import LLMCache
from agents.config import PipelineConfig
from agents.memory import PipelineMemory
from agents.models import get_llm, list_models
from agents.pipeline import Pipeline

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp_server")

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "SDK Test Agent",
    instructions="""SDK Test Generation Agent — automated C/C++ test case generation
via LLM analysis of SDK header files.

Workflow (end-to-end):
  1. ``scan_headers`` — discover and extract API signatures from ``.h`` files
  2. ``analyze_api`` — analyse the inventory for complexity and patterns
  3. ``design_test_cases`` — design a comprehensive ``TestCaseCollection``
  4. ``generate_gtest_code`` — write compilable GoogleTest C++ source code
  5. ``generate_ci_config`` — write CMakeLists.txt + GitHub Actions workflow
  6. ``generate_report`` — synthesise a Markdown + JSON summary

All tools accept an ``sdk_root`` path and an optional ``model`` preset name
(default: ``longcat``).  The model API key is read from the ``OPENAI_API_KEY``
environment variable.

Example invocation from the LLM:
  ``generate_tests(sdk_root="/path/to/sdk")``
""",
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_MODEL_CACHE: dict[str, Pipeline] = {}


def _get_pipeline(sdk_root: str, model: str, output_root: str) -> Pipeline:
    """Return a cached or freshly created ``Pipeline``.

    Pipelines are cached by ``(model, output_root)`` so that subsequent
    calls reuse the same LLM instance (avoids re-authentication).
    """
    key = f"{model}::{output_root}"
    if key not in _MODEL_CACHE:
        llm = get_llm(model)
        cfg = PipelineConfig(
            sdk_root=sdk_root,
            output_root=output_root,
            llm_enabled=True,
            model=model,
        )
        _MODEL_CACHE[key] = Pipeline(llm=llm, config=cfg.as_dict())
    return _MODEL_CACHE[key]


def _fmt(result: object, title: str = "") -> str:
    """Pretty-print a stage result as human-readable text."""
    lines = [f"# {title}", ""] if title else []
    if isinstance(result, str):
        lines.append(result)
    elif hasattr(result, "model_dump"):
        lines.append(json.dumps(result.model_dump(), indent=2, default=str))
    elif hasattr(result, "to_dict"):
        lines.append(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        lines.append(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    description="""Discover and analyse SDK header files.

Scans ``sdk_root`` for ``.h`` files, reads each one, and invokes the LLM to
extract a structured API inventory (functions, classes, enums, macros).

Returns a human-readable summary of the SDK modules and symbols found.
""",
)
async def scan_headers(
    sdk_root: Annotated[
        str,
        "Absolute path to the SDK root directory to scan for .h files.",
    ],
    model: Annotated[
        str,
        f"Model preset name. Choices: {', '.join(list_models())} (default: longcat)",
    ] = "longcat",
) -> str:
    pipeline = _get_pipeline(sdk_root, model, output_root="./output")
    inventory = pipeline.scanner_chain.run(sdk_root)
    pipeline.memory.store_stage_output("scanner", pipeline._to_serializable(inventory))
    return _fmt(inventory, "SDK API Inventory")


@mcp.tool(
    description="""Analyse a previously-scanned API inventory for complexity, patterns,
dependencies, and potential integration risks.

Requires that ``scan_headers`` has been called first (stage results are read
from PipelineMemory).
""",
)
async def analyze_api(
    sdk_root: Annotated[
        str,
        "Absolute path to the SDK root directory (used for cache key).",
    ],
    model: Annotated[
        str,
        f"Model preset name. Choices: {', '.join(list_models())} (default: longcat)",
    ] = "longcat",
) -> str:
    pipeline = _get_pipeline(sdk_root, model, output_root="./output")
    inventory = pipeline.memory.get_stage_output(
        "scanner"
    ) or pipeline.scanner_chain.run(sdk_root)
    analysis = pipeline.analysis_chain.run(inventory)
    pipeline.memory.store_stage_output("analysis", analysis)
    return _fmt(analysis, "API Analysis Report")


@mcp.tool(
    description="""Design test cases for the scanned SDK.

Runs scanner → analysis → test_design stages sequentially.
Returns a structured TestCaseCollection with up to 100 targeted test cases.

Use this when you want to see the test plan *before* generating code.
""",
)
async def design_test_cases(
    sdk_root: Annotated[
        str,
        "Absolute path to the SDK root directory.",
    ],
    model: Annotated[
        str,
        f"Model preset name. Choices: {', '.join(list_models())} (default: longcat)",
    ] = "longcat",
    max_test_cases: Annotated[
        int,
        "Maximum number of test cases to generate (default: 100).",
    ] = 100,
) -> str:
    pipeline = _get_pipeline(sdk_root, model, output_root="./output")

    # Stage 1: Scanner
    inventory = pipeline.memory.get_stage_output("scanner")
    if not inventory:
        inventory = pipeline.scanner_chain.run(sdk_root)
        pipeline.memory.store_stage_output(
            "scanner", pipeline._to_serializable(inventory)
        )

    # Stage 2: Analysis
    analysis = pipeline.memory.get_stage_output("analysis")
    if not analysis:
        analysis = pipeline.analysis_chain.run(inventory)
        pipeline.memory.store_stage_output("analysis", analysis)

    # Stage 3: Test design
    test_collection = pipeline.test_design_chain.run(inventory, analysis)
    pipeline.memory.store_stage_output("test_design", test_collection)
    return _fmt(test_collection, "Test Case Collection")


@mcp.tool(
    description="""Generate compilable C++ GoogleTest source files on disk.

Runs the full pipeline (scan → analyze → design → code_gen) then writes
``.cpp`` files to ``<output_root>/generated/``.

Returns the list of written files and a summary of generated test coverage.
""",
)
async def generate_gtest_code(
    sdk_root: Annotated[
        str,
        "Absolute path to the SDK root directory.",
    ],
    model: Annotated[
        str,
        f"Model preset name. Choices: {', '.join(list_models())} (default: longcat)",
    ] = "longcat",
    output_root: Annotated[
        str,
        "Output directory for generated files (default: ./output).",
    ] = "./output",
) -> str:
    pipeline = _get_pipeline(sdk_root, model, output_root)

    # Scanner
    inventory = pipeline.scanner_chain.run(sdk_root)
    pipeline.memory.store_stage_output("scanner", pipeline._to_serializable(inventory))

    # Analysis
    analysis = pipeline.analysis_chain.run(inventory)
    pipeline.memory.store_stage_output("analysis", analysis)

    # Test design
    test_collection = pipeline.test_design_chain.run(inventory, analysis)
    pipeline.memory.store_stage_output("test_design", test_collection)

    # Code generation
    code_gen_output = pipeline.code_gen_chain.run(test_collection)
    pipeline.memory.store_stage_output("code_gen", code_gen_output)
    pipeline.memory.persist()

    # List generated files
    gen_dir = Path(output_root) / "generated"
    files = sorted(gen_dir.rglob("*.cpp")) + sorted(gen_dir.rglob("*.h"))
    file_list = "\n".join(f"  - {f}" for f in files)

    return (
        f"# Generated GTest Code\n\n"
        f"**Output directory**: {gen_dir}\n\n"
        f"**Files written** ({len(files)}):\n{file_list}\n\n"
        f"**Test count**: {getattr(test_collection, 'total', len(getattr(test_collection, 'cases', [])))}\n"
    )


@mcp.tool(
    description="""Generate CMakeLists.txt and ``.github/workflows/ci.yml`` for the
test project.  The generated CMake uses FetchContent to pull GoogleTest
automatically.

Call this *after* ``generate_gtest_code`` to get the build system config.
""",
)
async def generate_ci_config(
    sdk_root: Annotated[
        str,
        "Absolute path to the SDK root directory.",
    ],
    model: Annotated[
        str,
        f"Model preset name. Choices: {', '.join(list_models())} (default: longcat)",
    ] = "longcat",
    output_root: Annotated[
        str,
        "Output directory (default: ./output).",
    ] = "./output",
) -> str:
    pipeline = _get_pipeline(sdk_root, model, output_root)

    # Need inventory + test_collection from memory
    inventory = pipeline.memory.get_stage_output("scanner")
    if not inventory:
        inventory = pipeline.scanner_chain.run(sdk_root)
        pipeline.memory.store_stage_output(
            "scanner", pipeline._to_serializable(inventory)
        )

    test_collection = pipeline.memory.get_stage_output("test_design")
    if not test_collection:
        analysis = pipeline.memory.get_stage_output("analysis") or pipeline.analysis_chain.run(inventory)
        test_collection = pipeline.test_design_chain.run(inventory, analysis)
        pipeline.memory.store_stage_output("test_design", test_collection)

    ci_output = pipeline.ci_gen_chain.run(inventory, test_collection)
    pipeline.memory.store_stage_output("ci_gen", ci_output)
    pipeline.memory.persist()

    gen_dir = Path(output_root) / "generated"
    cmake_files = sorted(gen_dir.rglob("CMakeLists.txt"))
    workflow_dir = Path(output_root) / ".github" / "workflows"
    workflow_files = sorted(workflow_dir.rglob("*.yml")) + sorted(
        workflow_dir.rglob("*.yaml")
    )

    return (
        f"# CI Config Generated\n\n"
        f"**CMakeLists.txt**:\n"
        + "\n".join(f"  - {f}" for f in cmake_files or ["(not found)"])
        + f"\n\n**CI workflows**:\n"
        + "\n".join(f"  - {f}" for f in workflow_files or ["(not found)"])
    )


@mcp.tool(
    description="""Generate a final Markdown report and JSON summary for all pipeline
stages.  Requires that some stages have been run previously (results read
from PipelineMemory).

Returns both the Markdown report text and a JSON summary.
""",
)
async def generate_report(
    sdk_root: Annotated[
        str,
        "Absolute path to the SDK root directory.",
    ],
    model: Annotated[
        str,
        f"Model preset name. Choices: {', '.join(list_models())} (default: longcat)",
    ] = "longcat",
    output_root: Annotated[
        str,
        "Output directory (default: ./output).",
    ] = "./output",
) -> str:
    pipeline = _get_pipeline(sdk_root, model, output_root)

    report = pipeline.report_chain.run(pipeline.memory)
    pipeline.memory.store_stage_output("report", report)
    pipeline.memory.persist()

    if hasattr(report, "model_dump"):
        report_dict = report.model_dump()
    elif hasattr(report, "to_dict"):
        report_dict = report.to_dict()
    else:
        report_dict = str(report)

    md = report_dict.get("markdown", "") if isinstance(report_dict, dict) else ""
    json_summary = (
        json.dumps(report_dict, indent=2, default=str, ensure_ascii=False)
        if isinstance(report_dict, dict)
        else str(report_dict)
    )

    output = f"# Test Report\n\n{md}\n\n---\n\n## JSON Summary\n\n```json\n{json_summary}\n```"
    return output


@mcp.tool(
    description="""End-to-end test generation pipeline.  Runs all 6 stages in
sequence and returns the final report.

This is the recommended entry point when you want the full treatment.
""",
)
async def generate_tests(
    sdk_root: Annotated[
        str,
        "Absolute path to the SDK root directory to analyse and generate tests for.",
    ],
    model: Annotated[
        str,
        f"Model preset name. Choices: {', '.join(list_models())} (default: longcat)",
    ] = "longcat",
    output_root: Annotated[
        str,
        "Output directory for generated files (default: ./output).",
    ] = "./output",
) -> str:
    """End-to-end pipeline: scan → analyse → design → generate → report."""
    try:
        pipeline = _get_pipeline(sdk_root, model, output_root)
    except Exception as exc:
        return f"# Error\n\nPipeline initialisation failed: {exc}"

    # Run full pipeline
    try:
        results = pipeline.run()
    except Exception as exc:
        return (
            f"# Pipeline Error\n\n"
            f"**SDK root**: {sdk_root}\n"
            f"**Model**: {model}\n\n"
            f"The pipeline failed during execution: **{type(exc).__name__}**: {exc}\n\n"
            f"Possible causes:\n"
            f"- SDK root does not exist or has no headers\n"
            f"- LLM API key is invalid or missing\n"
            f"- LLM returned an unparseable response\n\n"
            f"Try running ``scan_headers`` first to verify the SDK path."
        )

    # Collect output summary
    gen_dir = Path(output_root) / "generated"
    try:
        files = sorted(gen_dir.rglob("*.cpp"))
    except Exception:
        files = []

    report_dir = results.get("report", "")
    return (
        f"# Test Generation Complete\n\n"
        f"**SDK root**: {sdk_root}\n"
        f"**Model**: {model}\n"
        f"**Output**: {output_root}\n"
        f"**Report**: {report_dir}\n\n"
        f"## Stages Executed\n"
        + "\n".join(f"  - {s}" for s in pipeline.get_stages())
        + f"\n\n## Generated Files ({len(files)})\n"
        + "\n".join(f"  - {f}" for f in files[:20])
        + ("\n  - ... (more)" if len(files) > 20 else "")
    )


@mcp.tool(
    description="""High-level goal-driven entry point.  Accepts a natural-language
goal and autonomously determines the SDK path, model, and pipeline stages
to execute.

Use this tool when the user provides a descriptive goal rather than
explicit tool parameters.  Examples:
  - "generate tests for C:/path/to/sdk"
  - "scan and analyse /home/user/sdk"
  - "full pipeline for D:/dev/my-sdk using dashscope model"

If the user provides an explicit ``sdk_root`` or is very specific about
which stages to run, prefer the individual tools (``scan_headers``,
``generate_tests``, etc.) instead.
""",
)
async def agent_goal(
    goal: Annotated[
        str,
        "Natural-language goal describing what tests to generate and for which SDK.",
    ],
) -> str:
    """Execute a high-level goal via the autonomous agent."""
    try:
        from agent import TestGenAgent

        result = TestGenAgent().run(goal)
    except Exception as exc:
        return f"# Agent Error\n\nAgent execution failed: **{type(exc).__name__}**: {exc}"

    status = result.get("status", "unknown")
    if status == "error":
        return (
            f"# Agent Goal Failed\n\n"
            f"**Goal**: {goal}\n\n"
            f"**Error**: {result.get('error', 'Unknown error')}\n\n"
            f"**Help**: {result.get('help', 'Try a more explicit goal.')}"
        )

    return (
        f"# Agent Goal Complete\n\n"
        f"**Goal**: {goal}\n"
        f"**SDK root**: {result.get('sdk_root', 'N/A')}\n"
        f"**Model**: {result.get('model', 'N/A')}\n"
        f"**Stages executed**: {', '.join(result.get('stages_executed', []))}\n\n"
        f"**Generated files** ({len(result.get('generated_files', []))}):\n"
        + "\n".join(f"  - {f}" for f in result.get("generated_files", [])[:20])
        + ("\n  - ... (more)" if len(result.get("generated_files", [])) > 20 else "")
    )


# ---------------------------------------------------------------------------
# Reusable CLI entry point (used by pyproject.toml [project.scripts])
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the ``testgen-mcp`` console script."""
    import argparse

    parser = argparse.ArgumentParser(description="MCP server for SDK Test Agent")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080).",
    )
    args = parser.parse_args()

    logger.info(
        "Starting MCP server — transport=%s port=%d",
        args.transport,
        args.port,
    )

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP server for SDK Test Agent")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080).",
    )
    args = parser.parse_args()

    logger.info(
        "Starting MCP server — transport=%s port=%d",
        args.transport,
        args.port,
    )

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")
