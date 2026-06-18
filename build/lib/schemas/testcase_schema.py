"""Schema definitions for TestCase Intermediate Representation (IR)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TestCaseInfo:
    """Structured testcase definition for generation and execution."""

    test_id: str
    api_id: str
    test_name: str
    category: str
    subtype: str
    priority: str
    setup_requirements: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    expected_behavior: str = ""
    assertion_type: str = "EXPECT_TRUE"
    needs_fixture: bool = False
    needs_mock: bool = False
    needs_testdata: bool = False
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            test_id=data.get("test_id", ""),
            api_id=data.get("api_id", ""),
            test_name=data.get("test_name", ""),
            category=data.get("category", ""),
            subtype=data.get("subtype", ""),
            priority=data.get("priority", ""),
            setup_requirements=data.get("setup_requirements", []),
            inputs=data.get("inputs", {}),
            expected_behavior=data.get("expected_behavior", ""),
            assertion_type=data.get("assertion_type", "EXPECT_TRUE"),
            needs_fixture=data.get("needs_fixture", False),
            needs_mock=data.get("needs_mock", False),
            needs_testdata=data.get("needs_testdata", False),
            confidence=data.get("confidence", 0.5)
        )


@dataclass
class TestCaseCollection:
    """Collection container for testcase IR objects."""

    cases: list[TestCaseInfo] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.cases)

    def __bool__(self) -> bool:
        return bool(self.cases)

    def __iter__(self):
        return iter(self.cases)

    def to_dict(self) -> dict[str, Any]:
        return {"cases": [case.to_dict() for case in self.cases]}

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(cases=[TestCaseInfo.from_dict(case) for case in data.get("cases", [])])


def build_testcase_examples() -> list[TestCaseInfo]:
    """Provide quick examples for unit/integration/resource cases."""
    return [
        TestCaseInfo(
            test_id="tc::normalize::normal",
            api_id="func::math::normalize",
            test_name="Normalize_ValidInput_ReturnsUnitInterval",
            category="unit",
            subtype="normal",
            priority="P1",
            inputs={"x": 5, "min": 0, "max": 10},
            expected_behavior="Return value in [0,1] and equals 0.5",
            assertion_type="EXPECT_NEAR",
            confidence=0.9,
        ),
        TestCaseInfo(
            test_id="tc::resize::boundary_zero_width",
            api_id="func::vision::resize_image",
            test_name="Resize_ZeroWidth_ReturnsError",
            category="unit",
            subtype="boundary",
            priority="P1",
            inputs={"width": 0, "height": 480},
            expected_behavior="API returns error code for invalid width",
            assertion_type="EXPECT_NE",
            needs_testdata=True,
            confidence=0.8,
        ),
        TestCaseInfo(
            test_id="tc::init::repeat_call",
            api_id="func::sdk::init_context",
            test_name="InitContext_RepeatCall_HandledGracefully",
            category="integration",
            subtype="resource",
            priority="P2",
            setup_requirements=["license file available"],
            expected_behavior="Second initialization reports already initialized or no-op",
            assertion_type="EXPECT_TRUE",
            needs_fixture=True,
            confidence=0.65,
        ),
    ]
