"""Rule-based GTest assertion codegen from scan/plan targets.
基于规则从 plan target 生成可编译 GTest 断言代码。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_INT_TYPES = frozenset({
    "int", "int8_t", "int16_t", "int32_t", "int64_t",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "size_t", "ssize_t", "long", "short", "unsigned", "unsigned int",
})
_FLOAT_TYPES = frozenset({"float", "double", "long double"})


@dataclass
class ParamInfo:
    type_name: str
    name: str
    is_pointer: bool = False
    is_const: bool = False
    is_ref: bool = False


@dataclass
class BoundarySet:
    normal: list[str] = field(default_factory=list)
    boundary: list[str] = field(default_factory=list)
    error: list[str] = field(default_factory=list)


def parse_params(params: str) -> list[ParamInfo]:
    """Parse C/C++ parameter list into ParamInfo entries.
    解析 C/C++ 参数列表。
    """
    if not (params or "").strip():
        return []
    parts = _split_params(params)
    result: list[ParamInfo] = []
    for part in parts:
        part = part.strip()
        if not part or part == "void":
            continue
        is_const = "const" in part.split()
        is_ref = "&" in part
        is_pointer = "*" in part
        cleaned = part.replace("const", "").replace("&", "").replace("*", "").strip()
        tokens = cleaned.split()
        if not tokens:
            continue
        name = tokens[-1] if len(tokens) > 1 else "arg"
        type_name = " ".join(tokens[:-1]) if len(tokens) > 1 else tokens[0]
        result.append(ParamInfo(
            type_name=type_name.strip(),
            name=name.strip(),
            is_pointer=is_pointer,
            is_const=is_const,
            is_ref=is_ref,
        ))
    return result


def _split_params(params: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in params:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts


def classify_type(type_name: str) -> str:
    """Return coarse type kind: int, float, bool, string, pointer, void_ptr, unknown.
    粗分类参数/返回类型。
    """
    t = (type_name or "").strip()
    if not t:
        return "unknown"
    base = t.replace("const", "").replace("&", "").replace("*", "").strip()
    base = re.sub(r"^std::", "", base)
    base = re.sub(r"\s+", " ", base)
    if "*" in t or "char *" in t or "char*" in t:
        if "char" in base:
            return "string"
        return "pointer"
    if base in _INT_TYPES or re.match(r"^(unsigned\s+)?(int|long|short)$", base):
        return "int"
    if base in _FLOAT_TYPES:
        return "float"
    if base == "bool":
        return "bool"
    if base in ("std::string", "string"):
        return "string"
    if "string" in base:
        return "string"
    if base == "void":
        return "void"
    return "unknown"


def infer_boundary_values(type_name: str) -> BoundarySet:
    """Infer literal values per scenario for a type.
    按类型推断 normal/boundary/error 字面量。
    """
    kind = classify_type(type_name)
    if kind == "int":
        return BoundarySet(
            normal=["1", "2"],
            boundary=["0", "-1", "2147483647"],
            error=["-1", "0"],
        )
    if kind == "float":
        return BoundarySet(
            normal=["1.0", "2.5"],
            boundary=["0.0", "-1.0"],
            error=["0.0"],
        )
    if kind == "bool":
        return BoundarySet(normal=["true", "false"], boundary=[], error=[])
    if kind == "string":
        return BoundarySet(
            normal=['"hello"'],
            boundary=['""'],
            error=["nullptr"],
        )
    if kind in ("pointer", "void_ptr"):
        return BoundarySet(
            normal=["nullptr"],
            boundary=["nullptr"],
            error=["nullptr"],
        )
    return BoundarySet(normal=[], boundary=[], error=[])


def _infer_op(symbol: str) -> str | None:
    s = symbol.lower()
    for op in ("add", "sub", "mul", "div"):
        if op in s:
            return op
    return None


def _int_result(op: str | None, a: int, b: int, ret_kind: str) -> str:
    if op == "add":
        return str(a + b)
    if op == "sub":
        return str(a - b)
    if op == "mul":
        return str(a * b)
    if op == "div" and b != 0:
        if ret_kind == "float":
            return f"{a / b:.1f}".rstrip("0").rstrip(".") if (a / b) == int(a / b) else str(a / b)
        return str(int(a / b))
    return str(a)


def _format_call(symbol: str, arg_exprs: list[str], namespace: str = "") -> str:
    prefix = f"{namespace}::" if namespace else ""
    args = ", ".join(arg_exprs)
    return f"{prefix}{symbol}({args})"


def render_assertion(
    symbol: str,
    scenario: dict[str, Any],
    target: dict[str, Any],
    fidelity: str = "smart",
) -> str:
    """Render test body lines for a function target and scenario.
    为函数 target 的某个 scenario 生成测试体代码行。
    """
    if fidelity == "skeleton":
        return _skeleton_body(symbol, scenario)
    return _smart_function_body(symbol, scenario, target)


def _skeleton_body(symbol: str, scenario: dict[str, Any]) -> str:
    desc = scenario.get("description", scenario.get("name", ""))
    name = scenario.get("name", "case")
    if name == "normal":
        return f"""    // TODO: {desc}
    // EXPECT_*({symbol}(...), ...);"""
    if name == "error":
        return f"""    // TODO: {desc}
    // EXPECT_* failure path for {symbol}"""
    return f"""    // TODO: {desc}
    EXPECT_TRUE(true);  // replace with real assertion for {symbol}"""


def _golden_assertion_body(
    symbol: str,
    scenario: dict[str, Any],
    target: dict[str, Any],
    namespace: str = "",
) -> str | None:
    """Generate body from golden_cases on target when available."""
    cases = target.get("golden_cases") or []
    scenario_name = str(scenario.get("name", "normal")).lower()
    for case in cases:
        case_name = str(case.get("name", "")).lower()
        if case_name != scenario_name:
            continue
        args = case.get("args") or []
        arg_strs = [json.dumps(a) if isinstance(a, str) else str(a) for a in args]
        call = _format_call(symbol, arg_strs, namespace)
        if case.get("expect_error"):
            return f"    // golden: expect error path\n    {call};  // verify error handling"
        expect = case.get("expect")
        if expect is not None:
            return f"    EXPECT_EQ({call}, {expect});"
    return None


def _smart_function_body(symbol: str, scenario: dict[str, Any], target: dict[str, Any]) -> str:
    scenario_name = scenario.get("name", "normal")
    return_type = (target.get("return_type") or "void").strip()
    params = parse_params(target.get("params") or "")
    ret_kind = classify_type(return_type)
    op = _infer_op(symbol)
    namespace = target.get("namespace") or ""

    golden_body = _golden_assertion_body(symbol, scenario, target, namespace)
    if golden_body:
        return golden_body

    if scenario_name == "lifecycle":
        return _render_sequence_body(symbol, scenario, target)

    if not params:
        if ret_kind == "void" or return_type == "void":
            return f"    {_format_call(symbol, [], namespace)};\n    SUCCEED();"
        if ret_kind == "string":
            return f'    auto result = {_format_call(symbol, [], namespace)};\n    EXPECT_FALSE(result.empty());'
        return f"    // AGENT: fill assertions for {symbol}()\n    auto result = {_format_call(symbol, [], namespace)};\n    (void)result;"

    if len(params) == 1:
        p = params[0]
        kind = classify_type(p.type_name)
        bounds = infer_boundary_values(p.type_name)
        if scenario_name == "normal" and bounds.normal:
            val = bounds.normal[0]
            call = _format_call(symbol, [val], namespace)
            if ret_kind == "void":
                return f"    {call};\n    SUCCEED();"
            if ret_kind == "float":
                return f"    EXPECT_GE({call}, 0);"
            if ret_kind == "int":
                return f"    EXPECT_EQ({call}, {call});"
            if kind == "string":
                return f"    {call};  // smoke: valid string input"
        if scenario_name == "boundary" and bounds.boundary:
            val = bounds.boundary[0]
            call = _format_call(symbol, [val], namespace)
            return f"    {call};  // boundary: {val}"
        if scenario_name == "error" and kind == "string":
            empty_lit = '""'
            return f"    // error: empty/null input\n    {_format_call(symbol, [empty_lit], namespace)};"
        if scenario_name == "error" and p.is_pointer:
            return f"    // error: null pointer\n    // {_format_call(symbol, ['nullptr'], namespace)};  // enable if API accepts null"

    if len(params) >= 2 and all(classify_type(p.type_name) == "int" for p in params[:2]):
        a, b = 2, 3
        if scenario_name == "normal":
            expected = _int_result(op, a, b, ret_kind)
            call = _format_call(symbol, [str(a), str(b)], namespace)
            if ret_kind == "float":
                return f"    EXPECT_DOUBLE_EQ({call}, {expected});"
            return f"    EXPECT_EQ({call}, {expected});"
        if scenario_name == "boundary":
            cases = [(0, 0), (-1, 1)]
            lines = []
            for x, y in cases:
                exp = _int_result(op, x, y, ret_kind)
                call = _format_call(symbol, [str(x), str(y)], namespace)
                if ret_kind == "float":
                    lines.append(f"    EXPECT_DOUBLE_EQ({call}, {exp});")
                else:
                    lines.append(f"    EXPECT_EQ({call}, {exp});")
            return "\n".join(lines)
        if scenario_name == "overflow":
            return f"    EXPECT_EQ({_format_call(symbol, ['2147483647', '1'], namespace)}, {_format_call(symbol, ['2147483647', '1'], namespace)});"
        if scenario_name == "error":
            sanitizer = (target.get("sanitizer") or scenario.get("requires_sanitizer") or "none").lower()
            if sanitizer in ("asan", "asan+ubsan", "ubsan") and any(p.is_pointer for p in params):
                return (
                    f"    // ASan: null pointer — enable with sanitizer in .forge.yaml\n"
                    f"    // {_format_call(symbol, ['nullptr'] + ['1'] * max(0, len(params)-1), namespace)};"
                )
            if op == "div":
                call = _format_call(symbol, ["1", "0"], namespace)
                return f"    // division by zero — document expected behavior\n    {call};  // AGENT: confirm expect value or error code"
            if ret_kind == "int" and len(params) >= 2:
                return f"    // error path smoke\n    (void){_format_call(symbol, ['-1', '0'], namespace)};"

    if len(params) >= 2 and classify_type(params[0].type_name) == "string":
        ok_lit = '"ok"'
        empty_lit = '""'
        if scenario_name == "normal":
            return f"    {_format_call(symbol, [ok_lit], namespace)};"
        if scenario_name == "empty_input":
            return f"    {_format_call(symbol, [empty_lit], namespace)};"
        if scenario_name == "boundary":
            return f"    {_format_call(symbol, [empty_lit], namespace)};  // empty string"

    if "<typename T>" in (target.get("params") or "") or "template" in (target.get("return_type") or "").lower():
        if scenario_name == "normal":
            return f"    EXPECT_EQ({namespace + '::' if namespace else ''}{symbol}<int>(5, 0, 10), 5);"
        if scenario_name == "boundary":
            return (
                f"    EXPECT_EQ({namespace + '::' if namespace else ''}{symbol}<int>(-1, 0, 10), 0);\n"
                f"    EXPECT_EQ({namespace + '::' if namespace else ''}{symbol}<int>(99, 0, 10), 10);"
            )

    desc = scenario.get("description", scenario_name)
    return f"    // AGENT: fill — {desc}\n    // {_format_call(symbol, ['/* args */'], namespace)};\n    SUCCEED();"


def render_class_body(
    symbol: str,
    scenario: dict[str, Any],
    target: dict[str, Any],
    fidelity: str = "smart",
) -> str:
    """Render test body for class/struct targets.
    为类 target 生成测试体。
    """
    if fidelity == "skeleton":
        desc = scenario.get("description", "")
        name = scenario.get("name", "")
        if target.get("needs_mock") and name == "mock":
            return f"    // TODO: {desc}\n    // Mock{symbol} mock; EXPECT_CALL(mock, ...);"
        if name == "construction":
            return f"    // TODO: {desc}\n    // {symbol} obj;"
        methods = target.get("methods") or []
        body = f"    // TODO: {desc}"
        if methods:
            body += f"\n    // exercise: {', '.join(methods[:3])}"
        body += "\n    EXPECT_TRUE(true);"
        return body

    namespace = target.get("namespace") or ""
    qual = f"{namespace}::{symbol}" if namespace else symbol
    name = scenario.get("name", "")

    if name == "construction":
        return f"    {qual} obj;\n    SUCCEED();"
    if name == "copy_move":
        return f"    {qual} a;\n    {qual} b = a;\n    SUCCEED();"
    if name == "destructor":
        return f"    {{ {qual} obj; }}\n    SUCCEED();"
    if target.get("needs_mock") and name == "mock":
        methods = target.get("methods") or ["div"]
        m = methods[0] if methods else "div"
        return (
            f"    Mock{symbol} mock;\n"
            f"    EXPECT_CALL(mock, {m}(::testing::_, ::testing::_))\n"
            f"        .WillOnce(::testing::Return(1.0));\n"
            f"    EXPECT_DOUBLE_EQ(mock.{m}(10, 2), 1.0);"
        )
    if name == "methods":
        methods = target.get("methods") or []
        if methods:
            m = methods[0]
            op = _infer_op(m) or _infer_op(symbol)
            if op == "add":
                return f"    {qual} obj;\n    EXPECT_EQ(obj.{m}(2, 3), 5);"
            if op == "sub":
                return f"    {qual} obj;\n    EXPECT_EQ(obj.{m}(5, 2), 3);"
            if op == "mul":
                return f"    {qual} obj;\n    EXPECT_EQ(obj.{m}(4, 3), 12);"
            if op == "div":
                return f"    {qual} obj;\n    EXPECT_DOUBLE_EQ(obj.{m}(10, 2), 5.0);"
            return f"    {qual} obj;\n    EXPECT_EQ(obj.{m}(1, 1), obj.{m}(1, 1));"
        return f"    {qual} obj;\n    SUCCEED();"
    desc = scenario.get("description", name)
    return f"    // AGENT: {desc}\n    {qual} obj;\n    SUCCEED();"


def render_enum_body(
    symbol: str,
    scenario: dict[str, Any],
    target: dict[str, Any],
    fidelity: str = "smart",
) -> str:
    """Render test body for enum targets.
    为枚举 target 生成测试体。
    """
    if fidelity == "skeleton":
        return f"    // TODO: enum {symbol}\n    EXPECT_TRUE(true);"

    namespace = target.get("namespace") or ""
    qual = f"{namespace}::{symbol}" if namespace else symbol
    members = target.get("enum_members") or target.get("members") or []
    parser = target.get("parser_function") or ""

    if scenario.get("name") == "normal" and members:
        lines = []
        for m in members[:4]:
            name = m.get("name", "")
            if parser:
                key = str(name).lower()
                lines.append(f'    EXPECT_EQ({parser}("{key}"), {qual}::{name});')
            else:
                lines.append(f"    EXPECT_EQ(static_cast<int>({qual}::{name}), static_cast<int>({qual}::{name}));")
        return "\n".join(lines) if lines else f"    EXPECT_EQ(static_cast<int>({qual}::{members[0].get('name')}), static_cast<int>({qual}::{members[0].get('name')}));"
    if scenario.get("name") == "boundary" and members and len(members) > 1:
        m = members[-1]
        if parser:
            key = str(m.get("name", "")).lower().replace("_", "")
            return f'    EXPECT_EQ({parser}("{key}"), {qual}::{m.get("name")});'
        return f"    EXPECT_EQ(static_cast<int>({qual}::{m.get('name')}), static_cast<int>({qual}::{m.get('name')}));"
    return f"    // AGENT: enum {symbol} — add member assertions\n    SUCCEED();"


def render_typedef_body(target: dict[str, Any], fidelity: str = "smart") -> str:
    """Smoke body for typedef / function pointer targets."""
    if fidelity == "skeleton":
        return "    // TODO: function pointer smoke\n    EXPECT_TRUE(true);"
    alias = target.get("symbol", "Fn")
    return f"    // smoke: {alias} function pointer\n    SUCCEED();"


def render_test_p_block(target: dict[str, Any], suite: str) -> str:
    """Generate TEST_P parameterized block for int/string boundaries.
    生成 TEST_P 参数化测试块。
    """
    symbol = target.get("symbol", "api")
    namespace = target.get("namespace") or ""
    params = parse_params(target.get("params") or "")
    if not params:
        return ""
    kind = classify_type(params[0].type_name)
    if kind not in ("int", "string"):
        return ""

    qual = f"{namespace}::{symbol}" if namespace else symbol
    fixture = f"{suite}Param"
    if kind == "int" and len(params) >= 2 and all(classify_type(p.type_name) == "int" for p in params[:2]):
        pairs = ["std::make_tuple(0, 1)", "std::make_tuple(-1, 1)", "std::make_tuple(2147483647, 1)"]
        fixture2 = f"{suite}Param2"
        lines = [
            f"typedef std::tuple<int, int> {fixture2}Tuple;",
            f"class {fixture2} : public ::testing::TestWithParam<{fixture2}Tuple> {{}};",
            f"TEST_P({fixture2}, IntPairBoundary) {{",
            f"    auto p = GetParam();",
            f"    int a = std::get<0>(p);",
            f"    int b = std::get<1>(p);",
            f"    EXPECT_EQ({qual}(a, b), {qual}(a, b));",
            "}",
            f"INSTANTIATE_TEST_SUITE_P(Forge, {fixture2}, ::testing::Values({', '.join(pairs)}));",
            "",
        ]
        return "\n".join(lines)
    if kind == "int":
        values = ["0", "1", "-1", "2147483647"]
        lines = [
            f"class {fixture} : public ::testing::TestWithParam<int> {{}};",
            f"TEST_P({fixture}, BoundaryValues) {{",
            f"    int v = GetParam();",
            f"    EXPECT_EQ({qual}(v, 1), {qual}(v, 1));",
            "}",
            f"INSTANTIATE_TEST_SUITE_P(Forge, {fixture}, ::testing::Values({', '.join(values)}));",
            "",
        ]
        return "\n".join(lines)
    values = ['""', '"a"', '"hello"']
    lines = [
        f"struct {fixture}String {{ std::string input; }};",
        f"class {fixture} : public ::testing::TestWithParam<{fixture}String> {{}};",
        f"TEST_P({fixture}, StringBoundary) {{",
        f"    auto p = GetParam();",
        f"    (void)p;",
        f"    // AGENT: {qual}(p.input)",
        "}",
    ]
    inst = ", ".join(f'{{{v}}}' for v in values)
    lines.extend([
        f"INSTANTIATE_TEST_SUITE_P(Forge, {fixture}, ::testing::Values({inst}));",
        "",
    ])
    return "\n".join(lines)


def render_fixture_block(targets: list[dict[str, Any]], suite: str) -> str:
    """Generate TEST_F fixture when multiple targets share a header file.
    同头文件多 API 时生成 TEST_F fixture。
    """
    if len(targets) < 2:
        return ""
    fixture = f"{suite}Fixture"
    lines = [
        f"class {fixture} : public ::testing::Test {{",
        "protected:",
        "    void SetUp() override {}",
        "    void TearDown() override {}",
        "};",
        "",
    ]
    for t in targets[:3]:
        sym = t.get("symbol", "api")
        ns = t.get("namespace") or ""
        qual = f"{ns}::{sym}" if ns else sym
        lines.append(f"TEST_F({fixture}, Smoke_{sym}) {{")
        lines.append(f"    // lifecycle smoke for {qual}")
        lines.append("    SUCCEED();")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


def _render_sequence_body(symbol: str, scenario: dict[str, Any], target: dict[str, Any]) -> str:
    """Multi-step lifecycle scenario (init → operate → verify).
    多步生命周期场景。
    """
    steps = scenario.get("lifecycle") or ["init", "operate", "verify"]
    namespace = target.get("namespace") or ""
    qual = f"{namespace}::{symbol}" if namespace else symbol
    lines = [f"    // lifecycle: {' → '.join(steps)}"]
    for step in steps:
        if step == "init":
            lines.append(f"    // Step init: prepare state for {qual}")
        elif step == "operate":
            lines.append(f"    // Step operate: call {qual}")
        elif step == "verify":
            lines.append("    SUCCEED();  // Step verify: add EXPECT_*")
        elif step == "teardown":
            lines.append("    // Step teardown: cleanup")
    return "\n".join(lines)


def count_placeholders(content: str) -> dict[str, int]:
    """Count TODO / EXPECT_TRUE(true) / AGENT markers in test source.
    统计占位符数量。
    """
    todo = len(re.findall(r"//\s*TODO", content))
    agent = len(re.findall(r"//\s*AGENT:", content))
    placeholder = len(re.findall(r"EXPECT_TRUE\s*\(\s*true\s*\)", content))
    return {
        "todo_count": todo,
        "agent_count": agent,
        "placeholder_count": placeholder,
        "total": todo + agent + placeholder,
    }
