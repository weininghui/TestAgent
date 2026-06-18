"""Schema definitions for API Intermediate Representation (IR)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParamInfo:
    """Function/method parameter metadata."""

    name: str
    type_name: str
    is_const: bool = False
    is_reference: bool = False
    is_pointer: bool = False
    default_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            name=data.get("name", ""),
            type_name=data.get("type_name", ""),
            is_const=data.get("is_const", False),
            is_reference=data.get("is_reference", False),
            is_pointer=data.get("is_pointer", False),
            default_value=data.get("default_value")
        )


@dataclass
class MethodInfo:
    """Class/struct method metadata."""

    method_id: str
    name: str
    qualified_name: str
    namespace: str
    return_type: str
    params: list[ParamInfo] = field(default_factory=list)
    is_const_method: bool = False
    is_static: bool = False
    access: str = "public"

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            method_id=data.get("method_id", ""),
            name=data.get("name", ""),
            qualified_name=data.get("qualified_name", ""),
            namespace=data.get("namespace", ""),
            return_type=data.get("return_type", ""),
            params=[ParamInfo.from_dict(p) for p in data.get("params", [])],
            is_const_method=data.get("is_const_method", False),
            is_static=data.get("is_static", False),
            access=data.get("access", "public")
        )


@dataclass
class FunctionInfo:
    """Free function metadata."""

    function_id: str
    name: str
    qualified_name: str
    namespace: str
    return_type: str
    params: list[ParamInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            function_id=data.get("function_id", ""),
            name=data.get("name", ""),
            qualified_name=data.get("qualified_name", ""),
            namespace=data.get("namespace", ""),
            return_type=data.get("return_type", ""),
            params=[ParamInfo.from_dict(p) for p in data.get("params", [])]
        )


@dataclass
class EnumValueInfo:
    """Single enum value item."""

    name: str
    value: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            name=data.get("name", ""),
            value=data.get("value")
        )


@dataclass
class EnumInfo:
    """Enum metadata."""

    enum_id: str
    name: str
    qualified_name: str
    namespace: str
    values: list[EnumValueInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            enum_id=data.get("enum_id", ""),
            name=data.get("name", ""),
            qualified_name=data.get("qualified_name", ""),
            namespace=data.get("namespace", ""),
            values=[EnumValueInfo.from_dict(v) for v in data.get("values", [])]
        )


@dataclass
class AliasInfo:
    """typedef/using metadata."""

    alias_id: str
    name: str
    qualified_name: str
    namespace: str
    target_type: str
    kind: str = "typedef"

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            alias_id=data.get("alias_id", ""),
            name=data.get("name", ""),
            qualified_name=data.get("qualified_name", ""),
            namespace=data.get("namespace", ""),
            target_type=data.get("target_type", ""),
            kind=data.get("kind", "typedef")
        )


@dataclass
class ClassInfo:
    """Class/struct metadata."""

    class_id: str
    name: str
    qualified_name: str
    namespace: str
    kind: str
    methods: list[MethodInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            class_id=data.get("class_id", ""),
            name=data.get("name", ""),
            qualified_name=data.get("qualified_name", ""),
            namespace=data.get("namespace", ""),
            kind=data.get("kind", ""),
            methods=[MethodInfo.from_dict(m) for m in data.get("methods", [])]
        )


@dataclass
class HeaderFileInfo:
    """Header-level API aggregation."""

    header_id: str
    path: str
    relative_path: str
    module: str
    namespaces: list[str] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    enums: list[EnumInfo] = field(default_factory=list)
    aliases: list[AliasInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            header_id=data.get("header_id", ""),
            path=data.get("path", ""),
            relative_path=data.get("relative_path", ""),
            module=data.get("module", ""),
            namespaces=data.get("namespaces", []),
            classes=[ClassInfo.from_dict(c) for c in data.get("classes", [])],
            functions=[FunctionInfo.from_dict(f) for f in data.get("functions", [])],
            enums=[EnumInfo.from_dict(e) for e in data.get("enums", [])],
            aliases=[AliasInfo.from_dict(a) for a in data.get("aliases", [])]
        )


@dataclass
class ModuleInfo:
    """Module-level API aggregation."""

    module_id: str
    name: str
    headers: list[HeaderFileInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            module_id=data.get("module_id", ""),
            name=data.get("name", ""),
            headers=[HeaderFileInfo.from_dict(h) for h in data.get("headers", [])]
        )


@dataclass
class APIInventory:
    """Top-level API inventory used across all pipeline phases."""

    sdk_root: str
    modules: list[ModuleInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize inventory to Python dict."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize inventory to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def write_json(self, output_path: str | Path, indent: int = 2) -> None:
        """Write inventory JSON to disk."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(indent=indent), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create inventory from Python dict."""
        return cls(
            sdk_root=data.get("sdk_root", ""),
            modules=[ModuleInfo.from_dict(m) for m in data.get("modules", [])]
        )


def _asdict(obj) -> dict:
    """Helper function to convert dataclass to dict with Path handling."""
    result = asdict(obj)
    
    def convert_value(value):
        if isinstance(value, Path):
            return str(value)
        elif isinstance(value, list):
            return [convert_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: convert_value(v) for k, v in value.items()}
        return value
    
    return convert_value(result)
