#!/usr/bin/env python3
"""End-to-end integration tests for the refactored project.

Validates: cleanup manifest, stale imports, IR schemas, agent modules,
config loading, pipeline init, CLI, dry-run, caching, memory, and
deleted directory verification.

Usage:
    python tests/test_integration.py
    python -m pytest tests/test_integration.py -v
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

# Ensure the project root is on sys.path so that ``ir``, ``agents`` etc.
# can be imported when running from the ``tests/`` directory.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestIntegration(unittest.TestCase):
    """Integration test suite for the refactored project."""

    # ─────────────────────────────────────────────────────────────────────
    # Class-level fixtures
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = PROJECT_ROOT
        cls.agents_dir = os.path.join(cls.root, "agents")
        cls.app_py = os.path.join(cls.root, "app.py")

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _py_files(self, *directories: str):
        """Yield all ``.py`` file paths under *directories* (recursive)."""
        for d in directories:
            if not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.endswith(".py"):
                        yield os.path.join(root, f)

    def _grep_lines(self, pattern: str, *file_paths: str):
        """Search *file_paths* for *pattern*.

        Returns
        -------
        dict[str, list[tuple[int, str]]]
            ``{path: [(line_number, line_text), ...]}``
        """
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

    # ─────────────────────────────────────────────────────────────────────
    # a) CLEANUP_MANIFEST.md exists and lists deleted directories
    # ─────────────────────────────────────────────────────────────────────

    def test_cleanup_manifest(self) -> None:
        """Verify ``CLEANUP_MANIFEST.md`` exists and lists every deleted dir."""
        manifest = os.path.join(self.root, "CLEANUP_MANIFEST.md")
        self.assertTrue(
            os.path.isfile(manifest),
            "CLEANUP_MANIFEST.md not found at project root",
        )
        with open(manifest, "r", encoding="utf-8") as f:
            content = f.read()

        deleted_dirs = [
            "GoogleTest1.17.0",
            "GoogleTest1.8.1",
            "ninja",
            "parsers",
            "generators",
            "planners",
            "runners",
            "repair",
            "knowledge",
            "utils",
            "WebUI",
            "templates",
            "exe_pack",
            "docs",
        ]
        for d in deleted_dirs:
            self.assertIn(
                d,
                content,
                f"Deleted directory '{d}' not mentioned in CLEANUP_MANIFEST.md",
            )

    # ─────────────────────────────────────────────────────────────────────
    # b) No stale imports from deleted modules
    # ─────────────────────────────────────────────────────────────────────

    def test_no_stale_imports(self) -> None:
        """No ``from/import <deleted_module>`` statements in ``agents/`` or ``app.py``."""
        stale_modules = [
            "generators",
            "parsers",
            "runners",
            "repair",
            "knowledge",
            "utils",
            "WebUI",
        ]
        files = list(self._py_files(self.agents_dir))
        if os.path.isfile(self.app_py):
            files.append(self.app_py)

        failures: list[str] = []
        for mod in stale_modules:
            # Match both ``from generators.xxx import`` and ``import generators``
            pattern = rf'^\s*(?:from|import)\s+{mod}\b'
            found = self._grep_lines(pattern, *files)
            for fpath, lines in found.items():
                rel = os.path.relpath(fpath, self.root)
                for lineno, line in lines:
                    failures.append(f"  {rel}:{lineno}: {line}")

        if failures:
            self.fail(
                f"Stale imports from deleted modules ({len(failures)} occurrence(s)):\n"
                + "\n".join(failures)
            )

    # ─────────────────────────────────────────────────────────────────────
    # c) No urllib references
    # ─────────────────────────────────────────────────────────────────────

    def test_no_urllib(self) -> None:
        """No ``urllib`` references in ``agents/`` or ``app.py``."""
        files = list(self._py_files(self.agents_dir))
        if os.path.isfile(self.app_py):
            files.append(self.app_py)

        found = self._grep_lines(r"urllib", *files)
        if found:
            lines: list[str] = []
            for fpath, hits in found.items():
                rel = os.path.relpath(fpath, self.root)
                for lineno, line in hits:
                    lines.append(f"  {rel}:{lineno}: {line}")
            self.fail(
                f"'urllib' references found ({len(lines)} occurrence(s)):\n"
                + "\n".join(lines)
            )

    # ─────────────────────────────────────────────────────────────────────
    # d) No libclang references
    # ─────────────────────────────────────────────────────────────────────

    def test_no_libclang(self) -> None:
        """No ``libclang`` references in ``agents/`` or ``app.py``."""
        files = list(self._py_files(self.agents_dir))
        if os.path.isfile(self.app_py):
            files.append(self.app_py)

        found = self._grep_lines(r"libclang", *files)
        if found:
            lines: list[str] = []
            for fpath, hits in found.items():
                rel = os.path.relpath(fpath, self.root)
                for lineno, line in hits:
                    lines.append(f"  {rel}:{lineno}: {line}")
            self.fail(
                f"'libclang' references found ({len(lines)} occurrence(s)):\n"
                + "\n".join(lines)
            )

    # ─────────────────────────────────────────────────────────────────────
    # e) IR schemas are importable
    # ─────────────────────────────────────────────────────────────────────

    def test_ir_schemas_importable(self) -> None:
        """IR schema classes import without errors."""
        from ir.api_schema import APIInventory
        from ir.testcase_schema import TestCaseCollection
        from ir.contract_schema import ContractInfo

        for cls in (APIInventory, TestCaseCollection, ContractInfo):
            self.assertTrue(
                isinstance(cls, type),
                f"{cls.__name__} is not a class",
            )

    # ─────────────────────────────────────────────────────────────────────
    # f) IR serialization round-trip
    # ─────────────────────────────────────────────────────────────────────

    def test_ir_serialization(self) -> None:
        """``APIInventory.to_dict()`` / ``from_dict()`` round-trip preserves data."""
        from ir.api_schema import APIInventory, ModuleInfo

        # --- build a sample inventory ---
        inv = APIInventory(
            sdk_root="/fake/sdk",
            modules=[
                ModuleInfo(
                    module_id="mod::test",
                    name="test",
                    headers=[],
                ),
            ],
        )

        # --- serialize to dict ---
        d = inv.to_dict()
        self.assertIn("sdk_root", d)
        self.assertEqual(d["sdk_root"], "/fake/sdk")
        self.assertIn("modules", d)
        self.assertEqual(len(d["modules"]), 1)
        self.assertEqual(d["modules"][0]["module_id"], "mod::test")

        # --- deserialize back ---
        inv2 = APIInventory.from_dict(d)
        self.assertEqual(inv2.sdk_root, "/fake/sdk")
        self.assertEqual(len(inv2.modules), 1)
        self.assertEqual(inv2.modules[0].module_id, "mod::test")
        self.assertEqual(inv2.modules[0].name, "test")

        # --- verify JSON serialization also works ---
        json_str = inv.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["sdk_root"], "/fake/sdk")

    # ─────────────────────────────────────────────────────────────────────
    # g) All agents modules import cleanly
    # ─────────────────────────────────────────────────────────────────────

    def test_agents_importable(self) -> None:
        """All core agent modules import without errors."""
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

        for cls in (
            LLMWrapper,
            LLMCache,
            PipelineMemory,
            SDKScannerChain,
            APIAnalysisChain,
            TestDesignChain,
            CodeGenChain,
            CIGenChain,
            ReportChain,
            Pipeline,
        ):
            self.assertTrue(
                isinstance(cls, type),
                f"{cls.__name__} is not a class",
            )

    # ─────────────────────────────────────────────────────────────────────
    # h) PipelineConfig dataclass works
    # ─────────────────────────────────────────────────────────────────────

    def test_config_py(self) -> None:
        """``agents.config.PipelineConfig`` works correctly.

        All configuration is now in pure Python — no YAML files.
        """
        from agents.config import PipelineConfig

        # — defaults —
        cfg = PipelineConfig()
        self.assertEqual(cfg.output_root, "./output")
        self.assertEqual(cfg.model, "longcat")
        self.assertEqual(cfg.log_level, "INFO")
        self.assertFalse(cfg.no_cache)

        # — from_dict round-trip —
        d = {
            "sdk_root": "/tmp/sdk",
            "output_root": "./out",
            "no_cache": True,
            "model": "dashscope",
            "llm_enabled": True,
        }
        cfg2 = PipelineConfig.from_dict(d)
        self.assertEqual(cfg2.sdk_root, "/tmp/sdk")
        self.assertEqual(cfg2.output_root, "./out")
        self.assertTrue(cfg2.no_cache)
        self.assertEqual(cfg2.model, "dashscope")
        self.assertTrue(cfg2.llm_enabled)

        # — as_dict preserves values —
        d2 = cfg2.as_dict()
        self.assertEqual(d2["sdk_root"], "/tmp/sdk")
        self.assertEqual(d2["model"], "dashscope")
        self.assertTrue(d2["no_cache"])

    # ─────────────────────────────────────────────────────────────────────
    # i) Pipeline init with mock LLM
    # ─────────────────────────────────────────────────────────────────────

    def test_pipeline_init(self) -> None:
        """``Pipeline`` initialises with a mock ``LLMWrapper`` and yields 6 stages."""
        with tempfile.TemporaryDirectory(prefix="test_pipeline_") as tmpdir:
            from agents.llm import LLMWrapper
            from agents.pipeline import Pipeline

            llm = LLMWrapper({"llm_api_key": "test-key"})
            config: dict = {
                "sdk_root": tmpdir,
                "output_root": tmpdir,
                "no_cache": True,
                "model": "test-model",
            }
            pipeline = Pipeline(llm=llm, config=config)

            stages = pipeline.get_stages()
            self.assertEqual(len(stages), 6)
            self.assertEqual(
                stages,
                ["scanner", "analysis", "test_design", "code_gen", "ci_gen", "report"],
            )

    # ─────────────────────────────────────────────────────────────────────
    # j) Pipeline dry-run
    # ─────────────────────────────────────────────────────────────────────

    def test_pipeline_dry_run(self) -> None:
        """``Pipeline.dry_run()`` executes without raising."""
        with tempfile.TemporaryDirectory(prefix="test_dryrun_") as tmpdir:
            from agents.llm import LLMWrapper
            from agents.pipeline import Pipeline

            llm = LLMWrapper({"llm_api_key": "test-key"})
            config: dict = {
                "sdk_root": tmpdir,
                "output_root": tmpdir,
                "no_cache": True,
                "model": "test-model",
            }
            pipeline = Pipeline(llm=llm, config=config)
            # Should not raise any exception
            pipeline.dry_run()

    # ─────────────────────────────────────────────────────────────────────
    # k) CLI --help
    # ─────────────────────────────────────────────────────────────────────

    def test_cli_help(self) -> None:
        """``python app.py --help`` exits with code 0."""
        result = subprocess.run(
            [sys.executable, self.app_py, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=self.root,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"app.py --help failed (rc={result.returncode})\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )

    # ─────────────────────────────────────────────────────────────────────
    # l) CLI dry-run
    # ─────────────────────────────────────────────────────────────────────

    def test_cli_dry_run(self) -> None:
        """``python app.py --sdk-root <dir> --dry-run`` exits with code 0."""
        tmpdir = tempfile.mkdtemp(prefix="test_dryrun_cli_")
        result = subprocess.run(
            [
                sys.executable,
                self.app_py,
                "--sdk-root",
                tmpdir,
                "--dry-run",
                "--verbose",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=self.root,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"app.py dry-run failed (rc={result.returncode})\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )

    # ─────────────────────────────────────────────────────────────────────
    # m) LangChain imports
    # ─────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────
    # n2) models.py — model presets work
    # ─────────────────────────────────────────────────────────────────────

    def test_models_presets(self) -> None:
        """``agents.models`` provides presets, ``get_llm()``, ``list_models()``."""
        from agents.models import get_llm, get_model, list_models, LONG_CAT, DASHSCOPE

        # — list_models returns known presets —
        names = list_models()
        self.assertIn("longcat", names)
        self.assertIn("dashscope", names)
        self.assertIn("default", names)

        # — get_model returns correct config —
        cfg = get_model("longcat")
        self.assertEqual(cfg.model, "LongCat-2.0-Preview")
        self.assertIn("chat", cfg.base_url)

        cfg2 = get_model("dashscope")
        self.assertEqual(cfg2.model, "kimi-k2.5")

        # — get_model falls back to default for unknown names —
        fallback = get_model("nonexistent")
        self.assertEqual(fallback.model, LONG_CAT.model)

        # — to_llm_config produces correct keys for LLMWrapper —
        llm_cfg = LONG_CAT.to_llm_config()
        self.assertIn("llm_model", llm_cfg)
        self.assertIn("llm_base_url", llm_cfg)
        self.assertIn("llm_api_key_env", llm_cfg)
        self.assertEqual(llm_cfg["llm_model"], "LongCat-2.0-Preview")

        # — get_llm returns an LLMWrapper instance —
        llm = get_llm("longcat")
        from agents.llm import LLMWrapper
        self.assertIsInstance(llm, LLMWrapper)

    def test_langchain_imports(self) -> None:
        """Key ``langchain_core`` and ``langchain_openai`` imports work."""
        from langchain_core.tools import tool
        from langchain_openai import ChatOpenAI

        self.assertTrue(callable(tool), "langchain_core.tools.tool is not callable")
        self.assertTrue(
            isinstance(ChatOpenAI, type),
            "ChatOpenAI is not a class",
        )

    # ─────────────────────────────────────────────────────────────────────
    # n) Deleted directories are gone
    # ─────────────────────────────────────────────────────────────────────

    def test_deleted_dirs_gone(self) -> None:
        """All specified directories are absent from the project root."""
        deleted = [
            "GoogleTest1.17.0",
            "GoogleTest1.8.1",
            "ninja",
            "generators",
            "parsers",
            "planners",
            "runners",
            "repair",
            "knowledge",
            "utils",
            "WebUI",
            "templates",
            "exe_pack",
            "docs",
        ]
        still_present: list[str] = []
        for d in deleted:
            path = os.path.join(self.root, d)
            if os.path.exists(path):
                still_present.append(d)

        if still_present:
            self.fail(
                f"Expected deleted directories still exist: {', '.join(still_present)}"
            )


# ─────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
