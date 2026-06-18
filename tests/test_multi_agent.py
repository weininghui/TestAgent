"""Tests for the LangGraph multi-agent pipeline."""

from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.WARNING)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _test_import():
    """Verify the module imports cleanly."""
    from agents.multi_agent import MultiAgentPipeline, DEFAULT_STAGES, AgentError

    assert isinstance(DEFAULT_STAGES, list)
    assert len(DEFAULT_STAGES) == 6
    assert "scanner" in DEFAULT_STAGES
    print(f"[PASS] Import OK — {len(DEFAULT_STAGES)} stages")


def _test_graph_construction():
    """Verify the StateGraph compiles without errors."""
    from agents.models import get_llm
    from agents.multi_agent import MultiAgentPipeline

    llm = get_llm("longcat")
    pipe = MultiAgentPipeline(llm, {"sdk_root": "C:/test", "output_root": "./output"})
    graph = pipe.graph
    assert graph is not None
    # Check that the graph has the expected nodes
    config = graph.get_graph().nodes
    node_names = [n.id for n in config.values()]
    for expected in ("router", "scanner", "analysis", "test_design", "code_gen", "ci_gen", "report"):
        assert expected in node_names, f"Missing node: {expected}"
    print(f"[PASS] Graph compiled — {len(node_names)} nodes: {node_names}")


def _test_router_all_done():
    """Router sets status=completed when all stages are done."""
    from agents.models import get_llm
    from agents.multi_agent import MultiAgentPipeline

    llm = get_llm("longcat")
    pipe = MultiAgentPipeline(llm, {"sdk_root": "C:/test", "output_root": "./output"})

    state = pipe.graph.invoke({
        "goal": "test",
        "sdk_root": "C:/test",
        "output_root": "./output",
        "model": "longcat",
        "stages": ["scanner", "analysis"],
        "completed_stages": ["scanner", "analysis"],
        "errors": [],
        "status": "running",
    })
    assert state["status"] == "completed", f"Expected completed, got {state['status']}"
    print(f"[PASS] Router all-done → status=completed")


def _test_router_error_abort():
    """Router sets status=failed when errors exist."""
    from agents.models import get_llm
    from agents.multi_agent import MultiAgentPipeline

    llm = get_llm("longcat")
    pipe = MultiAgentPipeline(llm, {"sdk_root": "C:/test", "output_root": "./output"})

    state = pipe.graph.invoke({
        "goal": "test",
        "sdk_root": "C:/test",
        "output_root": "./output",
        "model": "longcat",
        "stages": ["scanner", "analysis"],
        "completed_stages": ["scanner"],
        "errors": [{"stage": "scanner", "error": "test error", "elapsed_sec": 0.5}],
        "status": "running",
    })
    assert state["status"] == "failed", f"Expected failed, got {state['status']}"
    print(f"[PASS] Router error → status=failed")


def _test_agent_dry_run():
    """Dry-run via the agent CLI entry point."""
    from agent import TestGenAgent

    agent = TestGenAgent(model="longcat", output_root="./output")
    plan = agent.plan("generate tests for C:/test/sdk")
    assert plan["sdk_root"] is not None
    assert "stages" in plan
    assert len(plan["stages"]) == 6
    print(f"[PASS] Agent dry-run: {len(plan['stages'])} stages for {plan['sdk_root']}")


# ── Main ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        _test_import,
        _test_graph_construction,
        _test_router_all_done,
        _test_router_error_abort,
        _test_agent_dry_run,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failures += 1

    print(f"\n{'=' * 50}")
    if failures:
        print(f"❌ {failures}/{len(tests)} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"✅ All {len(tests)} test(s) PASSED")
