"""Scaffold quality gate before build.
构建前用例质量门禁。
"""

from __future__ import annotations

from typing import Any

from sdk_forge.enrich import analyze_scaffold_quality_impl
from sdk_forge.util import parse_bool


def quality_gate_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Read gate settings from .forge config with defaults.
    从 .forge 配置读取门禁参数（含默认值）。
    """
    enabled = parse_bool(config.get("scaffold_quality_gate", True), default=True)
    mode = str(config.get("quality_gate_mode", "warn") or "warn").strip().lower()
    if mode not in ("warn", "block"):
        mode = "warn"
    try:
        max_ratio = float(config.get("max_placeholder_ratio", 0.5))
    except (TypeError, ValueError):
        max_ratio = 0.5
    return {
        "enabled": enabled,
        "mode": mode,
        "max_placeholder_ratio": max_ratio,
    }


def run_scaffold_quality_gate(
    project_dir: str,
    config: dict[str, Any] | None = None,
    tests_dir: str = "",
) -> dict[str, Any]:
    """Run quality analysis and decide pass/warn/block.
    分析占位符比例并返回门禁结果。
    """
    cfg = config or {}
    settings = quality_gate_settings(cfg)
    if not settings["enabled"]:
        return {
            "passed": True,
            "skipped": True,
            "mode": settings["mode"],
            "max_placeholder_ratio": settings["max_placeholder_ratio"],
        }

    quality = analyze_scaffold_quality_impl(project_dir, tests_dir=tests_dir)
    if quality.get("status") == "error":
        return {
            "passed": True,
            "skipped": True,
            "reason": quality.get("error"),
            "mode": settings["mode"],
            "max_placeholder_ratio": settings["max_placeholder_ratio"],
        }

    ratio = float(quality.get("placeholder_ratio", 0))
    passed = ratio <= settings["max_placeholder_ratio"]
    return {
        "passed": passed,
        "skipped": False,
        "mode": settings["mode"],
        "max_placeholder_ratio": settings["max_placeholder_ratio"],
        "placeholder_ratio": ratio,
        "needs_enrichment": quality.get("needs_enrichment", False),
        "files": quality.get("files") or [],
        "quality": quality,
        "hint": "Run enrich_test_cases and replace // AGENT: markers before build",
    }
