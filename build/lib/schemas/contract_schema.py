"""Schema definitions for behavior contract IR."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ContractInfo:
    """Behavior contract inferred for one API."""

    api_id: str
    summary: str
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    error_cases: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    determinism_level: str = "unknown"
    confidence_level: float = 0.5
    assertion_strength: str = "weak"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            api_id=data.get("api_id", ""),
            summary=data.get("summary", ""),
            preconditions=data.get("preconditions", []),
            postconditions=data.get("postconditions", []),
            error_cases=data.get("error_cases", []),
            side_effects=data.get("side_effects", []),
            determinism_level=data.get("determinism_level", "unknown"),
            confidence_level=data.get("confidence_level", 0.5),
            assertion_strength=data.get("assertion_strength", "weak")
        )


@dataclass
class ContractCollection:
    """Collection of API contracts."""

    items: list[ContractInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.to_dict() for item in self.items]}

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(items=[ContractInfo.from_dict(item) for item in data.get("items", [])])


def build_contract_examples() -> list[ContractInfo]:
    """Provide sample contract entries for quick reference."""
    return [
        ContractInfo(
            api_id="func::math::normalize",
            summary="Normalize a numeric value into [0, 1] range.",
            preconditions=["input range max > min"],
            postconditions=["result is between 0 and 1"],
            error_cases=["division by zero when max == min"],
            side_effects=[],
            determinism_level="deterministic",
            confidence_level=0.8,
            assertion_strength="strong",
        ),
        ContractInfo(
            api_id="func::vision::resize_image",
            summary="Resize image buffer into target dimensions.",
            preconditions=["input image pointer is not null", "width/height > 0"],
            postconditions=["output buffer has expected dimensions"],
            error_cases=["invalid size returns error code"],
            side_effects=["writes output buffer"],
            determinism_level="deterministic",
            confidence_level=0.7,
            assertion_strength="medium",
        ),
        ContractInfo(
            api_id="func::sdk::init_context",
            summary="Initialize SDK runtime context.",
            preconditions=["config pointer is valid", "not initialized twice without reset"],
            postconditions=["returns valid context handle"],
            error_cases=["invalid license", "resource allocation failure"],
            side_effects=["allocates internal resources", "opens log files"],
            determinism_level="partially_deterministic",
            confidence_level=0.6,
            assertion_strength="medium",
        ),
    ]
