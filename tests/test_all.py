#!/usr/bin/env python3
"""Combined test suite for the SDK Test Generation Agent.

Previously split across test_integration.py, test_mcp_server.py, and
test_multi_agent.py — now consolidated into a single file.

Usage:
    python tests/test_all.py
    python -m pytest tests/test_all.py -v
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest

logging.basicConfig(level=logging.WARNING)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SERVER_SCRIPT = os.path.join(PROJECT_ROOT, "mcp_server.py")


# =========================================================================
# Part 1 — Integration tests (from test_integration.py)
# =========================================================================

class TestIntegration(unittest.TestCase):
    """Integration test suite for the refactored project."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = PROJECT_ROOT
        cls.agents_dir = os.path.join(cls.root, "agents")
        cls.cli_py = os.path.join(cls.root, "cli.py")

    def _py_files(self, *directories: str):
        for d in directories:
            if not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.endswith(".py"):
                        yield os.path.join(root, f)

    def _grep_lines(self, pattern: str, *file_paths: str):
        found: dict[str, list[tuple[int, str]]] = {}
        for path in file_paths:
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if re.search(pattern, line):
                            found.setdefault(path, []).append((lineno, line.rstrip()))
            except Exception:
                pass
        return found

    # a) CLEANUP_MANIFEST.md
    def test_cleanup_manifest(self) -> None:
        manifest = os.path.join(self.root, "CLEANUP_MANIFEST.md")
        self.assertTrue(os.path.isfile(manifest), "CLEANUP_MANIFEST.md not found")
        with open(manifest, "r", encoding="utf-8") as f:
            content = f.read()
        for d in ("GoogleTest1.17.0", "GoogleTest1.8.1", "ninja", "parsers",
                  "generators", "planners", "runners", "repair", "knowledge",
                  "utils", "WebUI", "templates", "exe_pack", "docs"):
            self.assertIn(d, content, f"'{d}' not mentioned in CLEANUP_MANIFEST.md")

    # b) No stale imports
    def test_no_stale_imports(self) -> None:
        stale_modules = ["generators", "parsers", "runners", "repair", "knowledge", "utils", "WebUI"]
        files = list(self._py_files(self.agents_dir))
        if os.path.isfile(self.cli_py):
            files.append(self.cli_py)
        failures: list[str] = []
        for mod in stale_modules:
            found = self._grep_lines(rf'^\s*(?:from|import)\s+{mod}\b', *files)
            for fpath, lines in found.items():
                rel = os.path.relpath(fpath, self.root)
                for lineno, line in lines:
                    failures.append(f"  {rel}:{lineno}: {line}")
        if failures:
            self.fail(f"Stale imports ({len(failures)} occurrences):\n" + "\n".join(failures))

    # c) No urllib references
    def test_no_urllib(self) -> None:
        files = list(self._py_files(self.agents_dir))
        if os.path.isfile(self.cli_py):
            files.append(self.cli_py)
        found = self._grep_lines(r"urllib", *files)
        if found:
            lines: list[str] = []
            for fpath, hits in found.items():
                rel = os.path.relpath(fpath, self.root)
                for lineno, line in hits:
                    lines.append(f"  {rel}:{lineno}: {line}")
            self.fail(f"'urllib' references found ({len(lines)}):\n" + "\n".join(lines))

    # d) No libclang references
    def test_no_libclang(self) -> None:
        files = list(self._py_files(self.agents_dir))
        if os.path.isfile(self.cli_py):
            files.append(self.cli_py)
        found = self._grep_lines(r"libclang", *files)
        if found:
            lines: list[str] = []
            for fpath, hits in found.items():
                rel = os.path.relpath(fpath, self.root)
                for lineno, line in hits:
                    lines.append(f"  {rel}:{lineno}: {line}")
            self.fail(f"'libclang' references found ({len(lines)}):\n" + "\n".join(lines))

    # e) Schemas importable
    def test_schemas_importable(self) -> None:
        from schemas.api_schema import APIInventory
        from schemas.testcase_schema import TestCaseCollection
        from schemas.contract_schema import ContractInfo
        for cls in (APIInventory, TestCaseCollection, ContractInfo):
            self.assertIsInstance(cls, type)

    # f) IR serialization round-trip
    def test_schema_serialization(self) -> None:
        from schemas.api_schema import APIInventory, ModuleInfo
        inv = APIInventory(
            sdk_root="/fake/sdk",
            modules=[ModuleInfo(module_id="mod::test", name="test", headers=[])],
        )
        d = inv.to_dict()
        self.assertIn("sdk_root", d)
        self.assertEqual(d["sdk_root"], "/fake/sdk")
        inv2 = APIInventory.from_dict(d)
        self.assertEqual(inv2.sdk_root, "/fake/sdk")
        self.assertEqual(len(inv2.modules), 1)
        json_str = inv.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["sdk_root"], "/fake/sdk")

    # g) All agent modules importable
    def test_agents_importable(self) -> None:
        from agents.llm import LLMWrapper
        from agents.cache import LLMCache
        from agents.memory import PipelineMemory
        from agents.chains.scanner_chain import SDKScannerChain
        from agents.chains.analysis_chain import APIAnalysisChain
        from agents.chains.test_design_chain import TestDesignChain
        from agents.chains.code_gen_chain import CodeGenChain
        from agents.chains.ci_gen_chain import CIGenChain
        from agents.chains.report_chain import ReportChain
        from agents.pipeline import Pipeline
        for cls in (LLMWrapper, LLMCache, PipelineMemory, SDKScannerChain,
                     APIAnalysisChain, TestDesignChain, CodeGenChain,
                     CIGenChain, ReportChain, Pipeline):
            self.assertIsInstance(cls, type)

    # h) PipelineConfig
    def test_config(self) -> None:
        from agents.config import PipelineConfig
        cfg = PipelineConfig()
        self.assertEqual(cfg.output_root, "./output")
        self.assertEqual(cfg.model, "longcat")
        d = {"sdk_root": "/tmp/sdk", "output_root": "./out", "no_cache": True,
             "model": "dashscope", "llm_enabled": True}
        cfg2 = PipelineConfig.from_dict(d)
        self.assertEqual(cfg2.sdk_root, "/tmp/sdk")
        self.assertEqual(cfg2.model, "dashscope")
        d2 = cfg2.as_dict()
        self.assertEqual(d2["sdk_root"], "/tmp/sdk")

    # i) Pipeline init
    def test_pipeline_init(self) -> None:
        with tempfile.TemporaryDirectory(prefix="test_pipe_") as tmpdir:
            from agents.llm import LLMWrapper
            from agents.pipeline import Pipeline
            llm = LLMWrapper({"llm_api_key": "test-key"})
            pipeline = Pipeline(llm=llm, config={"sdk_root": tmpdir, "output_root": tmpdir,
                                                  "no_cache": True, "model": "test-model"})
            stages = pipeline.get_stages()
            self.assertEqual(len(stages), 6)
            self.assertEqual(stages, ["scanner", "analysis", "test_design",
                                       "code_gen", "ci_gen", "report"])

    # j) Pipeline dry-run
    def test_pipeline_dry_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="test_dryrun_") as tmpdir:
            from agents.llm import LLMWrapper
            from agents.pipeline import Pipeline
            llm = LLMWrapper({"llm_api_key": "test-key"})
            pipeline = Pipeline(llm=llm, config={"sdk_root": tmpdir, "output_root": tmpdir,
                                                  "no_cache": True, "model": "test-model"})
            pipeline.dry_run()

    # k) CLI --help
    def test_cli_help(self) -> None:
        result = subprocess.run(
            [sys.executable, self.cli_py, "--help"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=self.root,
        )
        self.assertEqual(result.returncode, 0,
                         f"cli.py --help failed (rc={result.returncode})")

    # l) CLI dry-run
    def test_cli_dry_run(self) -> None:
        tmpdir = tempfile.mkdtemp(prefix="test_dryrun_cli_")
        result = subprocess.run(
            [sys.executable, self.cli_py, "--sdk-root", tmpdir, "--dry-run", "--verbose"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=self.root,
        )
        self.assertEqual(result.returncode, 0,
                         f"cli.py dry-run failed (rc={result.returncode})")

    # m) Model presets
    def test_models_presets(self) -> None:
        from agents.models import get_llm, get_model, list_models, LONG_CAT
        names = list_models()
        self.assertIn("longcat", names)
        self.assertIn("dashscope", names)
        cfg = get_model("longcat")
        self.assertEqual(cfg.model, "LongCat-2.0-Preview")
        fallback = get_model("nonexistent")
        self.assertEqual(fallback.model, LONG_CAT.model)
        llm_cfg = LONG_CAT.to_llm_config()
        self.assertIn("llm_model", llm_cfg)
        llm = get_llm("longcat")
        from agents.llm import LLMWrapper
        self.assertIsInstance(llm, LLMWrapper)

    # n) LangChain imports
    def test_langchain_imports(self) -> None:
        from langchain_core.tools import tool
        from langchain_openai import ChatOpenAI
        self.assertTrue(callable(tool))
        self.assertIsInstance(ChatOpenAI, type)

    # o) Deleted directories are gone
    def test_deleted_dirs_gone(self) -> None:
        deleted = ["GoogleTest1.17.0", "GoogleTest1.8.1", "ninja", "generators",
                   "parsers", "planners", "runners", "repair", "knowledge",
                   "utils", "WebUI", "templates", "exe_pack", "docs"]
        still_present = [d for d in deleted if os.path.exists(os.path.join(self.root, d))]
        if still_present:
            self.fail(f"Expected deleted directories still exist: {', '.join(still_present)}")


# =========================================================================
# Part 2 — Multi-agent tests (from test_multi_agent.py)
# =========================================================================

class TestMultiAgent(unittest.TestCase):
    """Tests for the LangGraph multi-agent pipeline."""

    def test_import(self):
        from agents.multi_agent import MultiAgentPipeline, DEFAULT_STAGES, AgentError
        self.assertIsInstance(DEFAULT_STAGES, list)
        self.assertEqual(len(DEFAULT_STAGES), 6)
        self.assertIn("scanner", DEFAULT_STAGES)

    def test_graph_construction(self):
        from agents.models import get_llm
        from agents.multi_agent import MultiAgentPipeline
        llm = get_llm("longcat")
        pipe = MultiAgentPipeline(llm, {"sdk_root": "C:/test", "output_root": "./output"})
        graph = pipe.graph
        self.assertIsNotNone(graph)
        config = graph.get_graph().nodes
        node_names = [n.id for n in config.values()]
        for expected in ("router", "scanner", "analysis", "test_design", "code_gen", "ci_gen", "report"):
            self.assertIn(expected, node_names, f"Missing node: {expected}")

    def test_router_all_done(self):
        from agents.models import get_llm
        from agents.multi_agent import MultiAgentPipeline
        llm = get_llm("longcat")
        pipe = MultiAgentPipeline(llm, {"sdk_root": "C:/test", "output_root": "./output"})
        state = pipe.graph.invoke({
            "goal": "test", "sdk_root": "C:/test", "output_root": "./output",
            "model": "longcat", "stages": ["scanner", "analysis"],
            "completed_stages": ["scanner", "analysis"],
            "errors": [], "status": "running",
        })
        self.assertEqual(state["status"], "completed")

    def test_router_error_abort(self):
        from agents.models import get_llm
        from agents.multi_agent import MultiAgentPipeline
        llm = get_llm("longcat")
        pipe = MultiAgentPipeline(llm, {"sdk_root": "C:/test", "output_root": "./output"})
        state = pipe.graph.invoke({
            "goal": "test", "sdk_root": "C:/test", "output_root": "./output",
            "model": "longcat", "stages": ["scanner", "analysis"],
            "completed_stages": ["scanner"],
            "errors": [{"stage": "scanner", "error": "test error", "elapsed_sec": 0.5}],
            "status": "running",
        })
        self.assertEqual(state["status"], "failed")

    def test_agent_dry_run(self):
        from agent import TestGenAgent
        agent = TestGenAgent(model="longcat", output_root="./output")
        plan = agent.plan("generate tests for C:/test/sdk")
        self.assertIsNotNone(plan["sdk_root"])
        self.assertIn("stages", plan)
        self.assertEqual(len(plan["stages"]), 6)


# =========================================================================
# Part 3 — MCP server smoke test (from test_mcp_server.py)
# =========================================================================

class TestMCPServer(unittest.TestCase):
    """Smoke-test for the MCP server via JSON-RPC over stdio."""

    def test_mcp_smoke(self):
        proc = subprocess.Popen(
            [sys.executable, "-u", SERVER_SCRIPT],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
            env={**os.environ, "OPENAI_API_KEY": "sk-test-key", "PYTHONIOENCODING": "utf-8"},
        )
        self.addCleanup(proc.terminate)

        stdout_lines: list[str] = []
        _stop = threading.Event()

        def _reader():
            while not _stop.is_set():
                line = proc.stdout.readline()
                if not line:
                    break
                stdout_lines.append(line)

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        def send(method: str, params: dict | None = None, req_id: int = 1) -> dict | None:
            payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            deadline = time.time() + 8.0
            collected = len(stdout_lines)
            while time.time() < deadline:
                if len(stdout_lines) > collected:
                    new_count = len(stdout_lines)
                    for i in range(collected, new_count):
                        raw = stdout_lines[i].strip()
                        if not raw:
                            continue
                        try:
                            obj = json.loads(raw)
                            if obj.get("id") == req_id:
                                return obj
                        except json.JSONDecodeError:
                            pass
                    collected = new_count
                time.sleep(0.1)
            return None

        # Initialize
        init_resp = send("initialize", {
            "protocolVersion": "0.1.0", "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        }, req_id=1)
        self.assertIsNotNone(init_resp, "No initialize response")

        # tools/list
        list_resp = send("tools/list", req_id=2)
        self.assertIsNotNone(list_resp, "No tools/list response")
        tools = list_resp.get("result", {}).get("tools", [])
        self.assertGreater(len(tools), 0, "No tools returned")

        # tools/call with non-existent SDK (fast-fail expected)
        call_resp = send("tools/call", {
            "name": "generate_tests",
            "arguments": {"sdk_root": "/tmp/nonexistent_sdk_xyz",
                          "model": "longcat", "output_root": "./output"},
        }, req_id=3)
        self.assertIsNotNone(call_resp, "No tools/call response")

        _stop.set()
        proc.terminate()
        proc.wait(timeout=5)


# =========================================================================
# Entry point
# =========================================================================

if __name__ == "__main__":
    unittest.main()
