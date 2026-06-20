#!/usr/bin/env python3
"""One-shot refactor: move sdk_forge modules into layered subpackages + shims."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "sdk_forge"

SHIM_TEMPLATE = '''\
"""Backward-compatible import path for ``{old_mod}``.

Implementation: ``{target}``
"""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("{target}")
'''

PACKAGE_NAMES = {"domain", "orchestration", "delegation", "pipeline", "infra"}

# (subpackage, docstring, {filename -> new_name inside package}, core_module_for_init)
LAYOUT: dict[str, tuple[str, dict[str, str | None], str | None]] = {
    "domain": (
        "Domain layer — shared types, parsing helpers, and plan-gap logic.",
        {
            "errors.py": None,
            "util.py": None,
            "test_files.py": None,
            "hint_actions.py": None,
            "plan_gap.py": None,
        },
        None,
    ),
    "orchestration": (
        "Orchestration layer — workflow state, stage planning, and autopilot.",
        {
            "orchestration.py": "core.py",
            "workflow.py": None,
            "workflow_advance.py": None,
            "autopilot.py": None,
        },
        "core",
    ),
    "delegation": (
        "Delegation layer — task() tracking, dispatch plans, and session navigation.",
        {
            "delegation.py": "core.py",
            "task_dispatch.py": None,
            "session_nav.py": None,
        },
        "core",
    ),
    "pipeline": (
        "Pipeline layer — scan, plan, scaffold, enrich, build, and test execution.",
        {
            "pipeline.py": "core.py",
            "scan.py": None,
            "scan_merge.py": None,
            "enrich.py": None,
            "assertion_quality.py": None,
            "quality_gate.py": None,
            "build.py": None,
            "run.py": None,
            "retry.py": None,
            "templates.py": None,
            "codegen.py": None,
            "coverage.py": None,
            "coverage_expand.py": None,
            "init.py": None,
            "golden.py": None,
            "oracle.py": None,
            "test_fix.py": None,
            "mock.py": None,
            "bench.py": None,
            "plan.py": None,
            "probe.py": None,
        },
        "core",
    ),
    "infra": (
        "Infrastructure layer — config, session, toolchain, reporting, and caches.",
        {
            "config.py": None,
            "session.py": None,
            "cache.py": None,
            "compdb.py": None,
            "doctor.py": None,
            "toolchain.py": None,
            "toolchain_install.py": None,
            "gtest.py": None,
            "profile.py": None,
            "report.py": None,
            "report_html.py": None,
            "learn.py": None,
            "clean.py": None,
        },
        None,
    ),
}


def move_files() -> None:
    for subpkg, (doc, files, core_mod) in LAYOUT.items():
        dest_dir = PKG / subpkg
        dest_dir.mkdir(parents=True, exist_ok=True)

        for src_name, new_name in files.items():
            src = PKG / src_name
            if not src.exists():
                raise SystemExit(f"Missing source: {src}")
            dst_name = new_name or src_name
            dst = dest_dir / dst_name
            shutil.move(str(src), str(dst))

        init_lines = [f'"""{doc}"""', ""]
        if core_mod:
            init_lines.append(f"from sdk_forge.{subpkg}.{core_mod} import *  # noqa: F403")
            init_lines.append(f"from sdk_forge.{subpkg}.{core_mod} import __all__  # noqa: F401")
        (dest_dir / "__init__.py").write_text("\n".join(init_lines) + "\n", encoding="utf-8")


def write_shims() -> None:
    for subpkg, (_, files, _) in LAYOUT.items():
        for src_name, new_name in files.items():
            old_mod = src_name[:-3]
            if old_mod in PACKAGE_NAMES:
                continue
            mod = (new_name or src_name)[:-3]
            target = f"sdk_forge.{subpkg}.{mod}"
            shim = PKG / f"{old_mod}.py"
            shim.write_text(SHIM_TEMPLATE.format(old_mod=old_mod, target=target), encoding="utf-8")


def main() -> None:
    move_files()
    write_shims()
    print("Layered refactor complete.")


if __name__ == "__main__":
    main()
