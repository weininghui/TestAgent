"""Forge profile presets (default vs production).
Forge 配置预设（default / production）。
"""

from __future__ import annotations

from typing import Any

PRODUCTION_PRESETS: dict[str, Any] = {
    "forge_profile": "production",
    "scaffold_quality_gate": True,
    "quality_gate_mode": "block",
    "max_placeholder_ratio": 0.05,
    "min_assertion_score": 80,
    "block_weak_tests": True,
    "block_agent_markers": True,
    "assertion_quality_gate": True,
    "min_line_coverage_pct": 80,
    "coverage_gate": True,
    "max_enrich_rounds": 3,
    "autopilot_profile": "production",
    "auto_golden_snapshot": True,
}


def resolve_forge_config(
    config: dict[str, Any],
    profile_override: str = "",
) -> dict[str, Any]:
    """Merge production presets when forge_profile=production or CLI override."""
    merged = dict(config)
    profile = (profile_override or config.get("forge_profile") or "default").strip().lower()
    if profile == "production":
        for key, value in PRODUCTION_PRESETS.items():
            if key == "forge_profile":
                merged[key] = "production"
            elif key not in merged or merged.get(key) in (None, ""):
                merged[key] = value
            elif key in ("quality_gate_mode", "max_placeholder_ratio", "min_assertion_score"):
                merged.setdefault(key, value)
        merged["forge_profile"] = "production"
    else:
        merged.setdefault("forge_profile", "default")
    return merged
