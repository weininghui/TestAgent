#!/usr/bin/env python3
"""Rewrite sdk_forge imports to layered paths and remove root shim dependency."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "sdk_forge"

# flat module name -> layered import path (without sdk_forge. prefix)
MODULE_TO_LAYER: dict[str, str] = {
    "errors": "domain.errors",
    "util": "domain.util",
    "test_files": "domain.test_files",
    "hint_actions": "domain.hint_actions",
    "plan_gap": "domain.plan_gap",
    "orchestration": "orchestration.core",
    "workflow": "orchestration.workflow",
    "workflow_advance": "orchestration.workflow_advance",
    "autopilot": "orchestration.autopilot",
    "delegation": "delegation.core",
    "task_dispatch": "delegation.task_dispatch",
    "session_nav": "delegation.session_nav",
    "pipeline": "pipeline.core",
    "scan": "pipeline.scan",
    "scan_merge": "pipeline.scan_merge",
    "enrich": "pipeline.enrich",
    "assertion_quality": "pipeline.assertion_quality",
    "quality_gate": "pipeline.quality_gate",
    "build": "pipeline.build",
    "run": "pipeline.run",
    "retry": "pipeline.retry",
    "templates": "pipeline.templates",
    "codegen": "pipeline.codegen",
    "coverage": "pipeline.coverage",
    "coverage_expand": "pipeline.coverage_expand",
    "init": "pipeline.init",
    "golden": "pipeline.golden",
    "oracle": "pipeline.oracle",
    "test_fix": "pipeline.test_fix",
    "mock": "pipeline.mock",
    "bench": "pipeline.bench",
    "plan": "pipeline.plan",
    "probe": "pipeline.probe",
    "config": "infra.config",
    "session": "infra.session",
    "cache": "infra.cache",
    "compdb": "infra.compdb",
    "doctor": "infra.doctor",
    "toolchain": "infra.toolchain",
    "toolchain_install": "infra.toolchain_install",
    "gtest": "infra.gtest",
    "profile": "infra.profile",
    "report": "infra.report",
    "report_html": "infra.report_html",
    "learn": "infra.learn",
    "clean": "infra.clean",
}

FROM_RE = re.compile(r"^(\s*)from sdk_forge\.([a-z_]+) import ", re.MULTILINE)
IMPORT_RE = re.compile(r"^(\s*)import sdk_forge\.([a-z_]+)(?: as ([a-z_]+))?\s*$", re.MULTILINE)
LAYERS = frozenset({"domain", "orchestration", "delegation", "pipeline", "infra"})
KEEP_TOP = frozenset({"cli", "__init__", "__main__"})


def rewrite(content: str) -> str:
    def from_sub(m: re.Match[str]) -> str:
        mod = m.group(2)
        if mod not in MODULE_TO_LAYER:
            return m.group(0)
        return f"{m.group(1)}from sdk_forge.{MODULE_TO_LAYER[mod]} import "

    def import_sub(m: re.Match[str]) -> str:
        mod = m.group(2)
        if mod not in MODULE_TO_LAYER:
            return m.group(0)
        alias = m.group(3) or mod.split(".")[-1]
        return f"{m.group(1)}from sdk_forge.{MODULE_TO_LAYER[mod]} import {alias}"

    content = FROM_RE.sub(from_sub, content)
    content = IMPORT_RE.sub(import_sub, content)
    # Monkeypatch strings: only rewrite flat sdk_forge.<mod>. when not already layered
    for mod, layered in MODULE_TO_LAYER.items():
        old = f"sdk_forge.{mod}."
        new = f"sdk_forge.{layered}."
        if old == new:
            continue
        # skip sdk_forge.orchestration.* — already under a layer package
        parts = layered.split(".", 1)
        if len(parts) == 2 and parts[0] in LAYERS:
            layered_prefix = f"sdk_forge.{parts[0]}."
            idx = 0
            while True:
                pos = content.find(old, idx)
                if pos == -1:
                    break
                before = content[max(0, pos - len(layered_prefix) + len("sdk_forge.")) : pos]
                if before.endswith(layered_prefix[len("sdk_forge.") :]) or any(
                    content[max(0, pos - 20) : pos].endswith(f"sdk_forge.{layer}.")
                    for layer in LAYERS
                ):
                    idx = pos + len(old)
                    continue
                content = content[:pos] + new + content[pos + len(old) :]
                idx = pos + len(new)
    return content


def targets() -> list[Path]:
    paths: list[Path] = [
        ROOT / "mcp_server.py",
        ROOT / "tests" / "test_mcp_server.py",
        PKG / "cli.py",
    ]
    for layer in ("domain", "orchestration", "delegation", "pipeline", "infra"):
        paths.extend((PKG / layer).rglob("*.py"))
    return paths


def main() -> None:
    changed = 0
    for path in targets():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        new = rewrite(text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
            print(f"updated {path.relative_to(ROOT)}")
    print(f"Done — {changed} files updated.")


if __name__ == "__main__":
    main()
