"""Scaffold and assertion quality gates before build.
构建前脚手架与语义断言质量门禁。
"""

from __future__ import annotations

from typing import Any

from sdk_forge.assertion_quality import analyze_assertion_quality_impl
from sdk_forge.enrich import analyze_scaffold_quality_impl
from sdk_forge.profile import resolve_forge_config
from sdk_forge.util import parse_bool


def quality_gate_settings(config: dict[str, Any], profile_override: str = "") -> dict[str, Any]:
    """Read gate settings from .forge config with defaults."""
    cfg = resolve_forge_config(config, profile_override)
    enabled = parse_bool(cfg.get("scaffold_quality_gate", True), default=True)
    mode = str(cfg.get("quality_gate_mode", "warn") or "warn").strip().lower()
    if mode not in ("warn", "block"):
        mode = "warn"
    try:
        max_ratio = float(cfg.get("max_placeholder_ratio", 0.5))
    except (TypeError, ValueError):
        max_ratio = 0.5
    try:
        min_assertion_score = float(cfg.get("min_assertion_score", 60))
    except (TypeError, ValueError):
        min_assertion_score = 60
    if cfg.get("forge_profile") == "production":
        min_assertion_score = max(min_assertion_score, float(cfg.get("min_assertion_score", 80)))
    try:
        min_line_coverage_pct = float(cfg.get("min_line_coverage_pct", 80))
    except (TypeError, ValueError):
        min_line_coverage_pct = 80
    is_production = cfg.get("forge_profile") == "production"
    return {
        "enabled": enabled,
        "mode": mode if not is_production else (mode if cfg.get("quality_gate_mode") else "block"),
        "max_placeholder_ratio": max_ratio,
        "forge_profile": cfg.get("forge_profile", "default"),
        "assertion_quality_gate": parse_bool(cfg.get("assertion_quality_gate", True), default=True),
        "min_assertion_score": min_assertion_score,
        "block_weak_tests": parse_bool(cfg.get("block_weak_tests", is_production), default=is_production),
        "block_agent_markers": parse_bool(cfg.get("block_agent_markers", is_production), default=is_production),
        "coverage_gate": parse_bool(cfg.get("coverage_gate", is_production), default=is_production),
        "min_line_coverage_pct": min_line_coverage_pct,
    }


def run_scaffold_quality_gate(
    project_dir: str,
    config: dict[str, Any] | None = None,
    tests_dir: str = "",
    profile_override: str = "",
) -> dict[str, Any]:
    cfg = config or {}
    settings = quality_gate_settings(cfg, profile_override)
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


def run_assertion_quality_gate(
    project_dir: str,
    config: dict[str, Any] | None = None,
    tests_dir: str = "",
    profile_override: str = "",
) -> dict[str, Any]:
    """Run semantic assertion quality gate."""
    cfg = config or {}
    settings = quality_gate_settings(cfg, profile_override)
    if not settings["assertion_quality_gate"]:
        return {"passed": True, "skipped": True, "mode": settings["mode"]}

    quality = analyze_assertion_quality_impl(project_dir, tests_dir=tests_dir)
    if quality.get("status") == "error":
        return {
            "passed": True,
            "skipped": True,
            "reason": quality.get("error"),
            "mode": settings["mode"],
        }

    score = float(quality.get("score", 0))
    weak_tests = quality.get("weak_tests") or []
    block_reasons: list[str] = []

    if score < settings["min_assertion_score"]:
        block_reasons.append(f"score {score} < min {settings['min_assertion_score']}")

    if settings["block_agent_markers"]:
        agent_tests = [t for t in weak_tests if "agent_remaining" in (t.get("issues") or [])]
        if agent_tests:
            block_reasons.append(f"{len(agent_tests)} test(s) still contain // AGENT:")

    if settings["block_weak_tests"]:
        weak_only = [t for t in weak_tests if "weak" in (t.get("issues") or []) or "tautology" in (t.get("issues") or [])]
        if weak_only:
            block_reasons.append(f"{len(weak_only)} weak/tautology test(s)")

    passed = not block_reasons and score >= settings["min_assertion_score"]
    return {
        "passed": passed,
        "skipped": False,
        "mode": settings["mode"],
        "score": score,
        "min_assertion_score": settings["min_assertion_score"],
        "weak_test_count": quality.get("weak_test_count", 0),
        "weak_tests": weak_tests[:20],
        "block_reasons": block_reasons,
        "quality": quality,
        "hint": "Replace weak assertions and // AGENT: markers before production build",
    }


def run_coverage_gate(
    project_dir: str,
    config: dict[str, Any] | None = None,
    profile_override: str = "",
) -> dict[str, Any]:
    """Check line coverage against threshold (production profile)."""
    import json
    from pathlib import Path

    cfg = config or {}
    settings = quality_gate_settings(cfg, profile_override)
    if not settings["coverage_gate"]:
        return {"passed": True, "skipped": True}

    cov_path = Path(project_dir or Path.cwd()) / ".forge" / "cache" / "coverage.json"
    if not cov_path.is_file():
        return {
            "passed": False,
            "skipped": False,
            "mode": settings["mode"],
            "min_line_coverage_pct": settings["min_line_coverage_pct"],
            "hint": "Run build with coverage enabled to populate .forge/cache/coverage.json",
        }
    try:
        cov = json.loads(cov_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"passed": False, "skipped": False, "error": "Invalid coverage cache"}

    line_pct = cov.get("line_coverage_pct")
    if line_pct is None:
        return {"passed": False, "skipped": False, "hint": "No line_coverage_pct in coverage cache"}

    passed = float(line_pct) >= settings["min_line_coverage_pct"]
    return {
        "passed": passed,
        "skipped": False,
        "line_coverage_pct": line_pct,
        "min_line_coverage_pct": settings["min_line_coverage_pct"],
        "uncovered_symbols": cov.get("uncovered_symbols") or [],
        "coverage": cov,
    }
