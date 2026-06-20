#!/usr/bin/env python3
"""Regenerate top-level sdk_forge shims as sys.modules aliases."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "sdk_forge"

SHIM = '''\
"""Backward-compatible import path for ``{old_mod}``.

Implementation: ``{target}``
"""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("{target}")
'''

PACKAGE_NAMES = {"domain", "orchestration", "delegation", "pipeline", "infra"}

LAYOUT = {
    "domain": {
        "errors.py": None,
        "util.py": None,
        "test_files.py": None,
        "hint_actions.py": None,
        "plan_gap.py": None,
    },
    "orchestration": {
        "orchestration.py": "core.py",
        "workflow.py": None,
        "workflow_advance.py": None,
        "autopilot.py": None,
    },
    "delegation": {
        "delegation.py": "core.py",
        "task_dispatch.py": None,
        "session_nav.py": None,
    },
    "pipeline": {
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
    "infra": {
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
}


def main() -> None:
    count = 0
    for subpkg, files in LAYOUT.items():
        for src_name, new_name in files.items():
            old_mod = src_name[:-3]
            if old_mod in PACKAGE_NAMES:
                continue
            mod = (new_name or src_name)[:-3]
            target = f"sdk_forge.{subpkg}.{mod}"
            path = PKG / f"{old_mod}.py"
            path.write_text(
                SHIM.format(old_mod=old_mod, target=target),
                encoding="utf-8",
            )
            count += 1
    print(f"Wrote {count} alias shims.")


if __name__ == "__main__":
    main()
