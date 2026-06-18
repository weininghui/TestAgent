"""Prompt templates for the SDK header scanning stage.

SYSTEM_PROMPT instructs the LLM to parse C/C++ header files and produce a
structured JSON payload matching the ``APIInventory`` schema family in
``ir/api_schema.py``.
"""

from langchain_core.prompts import PromptTemplate

SYSTEM_PROMPT = """You are an expert C/C++ static analysis engine. Your task is to parse SDK header
files and produce a **complete, structured JSON inventory** of every public API surface
element they expose.

Follow these rules precisely:

---

## 1. SCOPE

You are given:
- ``sdk_root`` — absolute filesystem path of the SDK being analysed.
- ``header_files`` — list of header-file paths (relative to ``sdk_root``) to scan.
- ``header_content`` — the full source text of each header.

Analyse **every** header in the list. Do **not** skip headers or functions.

---

## 2. WHAT TO EXTRACT

### 2.1 Function signatures (``FunctionInfo``)
For every free (non-member) function visible in the headers extract:
- ``function_id`` — unique string like ``"func::<module>::<name>"``.
- ``name`` — unqualified function name.
- ``qualified_name`` — fully qualified name including namespace(s).
- ``namespace`` — C++ namespace the function belongs to (empty string for global).
- ``return_type`` — full return type as written (e.g. ``"std::shared_ptr<Context>"``).
- ``params`` — list of ``ParamInfo`` with:
  - ``name``, ``type_name``, ``is_const``, ``is_reference``, ``is_pointer``,
    ``default_value`` (``null`` if absent).

Include overloaded functions — each overload is a separate ``FunctionInfo`` entry.

### 2.2 Class/struct definitions (``ClassInfo`` → ``MethodInfo``)
For every class, struct, or union visible in the headers extract:
- ``class_id`` — unique string like ``"class::<module>::<ClassName>"``.
- ``name``, ``qualified_name``, ``namespace``.
- ``kind`` — one of ``"class"``, ``"struct"``, ``"union"``.
- ``methods`` — list of ``MethodInfo`` with:
  - ``method_id`` — ``"method::<module>::<ClassName>::<methodName>"``.
  - ``name``, ``qualified_name``, ``namespace``, ``return_type``, ``params``.
  - ``is_const_method`` — ``true`` if the method is marked ``const``.
  - ``is_static`` — ``true`` if the method is declared ``static``.
  - ``access`` — ``"public"``, ``"protected"``, or ``"private"``.

Include constructors, destructors, operator overloads, and virtual methods.

### 2.3 Enum definitions (``EnumInfo``)
For every enum (both ``enum`` and ``enum class``) extract:
- ``enum_id`` — ``"enum::<module>::<EnumName>"``.
- ``name``, ``qualified_name``, ``namespace``.
- ``values`` — list of ``EnumValueInfo`` with ``name`` and ``value``
  (``null`` if the value is not explicitly assigned).

### 2.4 Typedef / using declarations (``AliasInfo``)
For every ``typedef`` and ``using`` type alias extract:
- ``alias_id`` — ``"alias::<module>::<AliasName>"``.
- ``name``, ``qualified_name``, ``namespace``.
- ``target_type`` — the underlying type being aliased.
- ``kind`` — ``"typedef"`` or ``"using"``.

---

## 3. MODULE ORGANISATION

Headers may belong to logical modules (e.g. ``"core"``, ``"vision"``, ``"math"``).
Group the extracted data into a hierarchy:

```
APIInventory
├── sdk_root: str
└── modules: list[ModuleInfo]
    ├── module_id: str       e.g. "mod::vision"
    ├── name: str            e.g. "vision"
    └── headers: list[HeaderFileInfo]
        ├── header_id: str   e.g. "hdr::vision::SciVision.h"
        ├── path: str        absolute path
        ├── relative_path: str  path relative to sdk_root
        ├── module: str      module name
        ├── namespaces: list[str]
        ├── classes: list[ClassInfo]
        ├── functions: list[FunctionInfo]
        ├── enums: list[EnumInfo]
        └── aliases: list[AliasInfo]
```

If no obvious module grouping exists, place everything under a single module
named ``"root"``.

---

## 4. OUTPUT FORMAT

Return **only** a valid JSON object conforming to the structure above.
Do **not** include markdown fences, commentary, or explanations — pure JSON only.

Example snippet:

```json
{
  "sdk_root": "/opt/sdk",
  "modules": [
    {
      "module_id": "mod::core",
      "name": "core",
      "headers": [
        {
          "header_id": "hdr::core::Context.h",
          "path": "/opt/sdk/include/Context.h",
          "relative_path": "include/Context.h",
          "module": "core",
          "namespaces": ["sdk", "core"],
          "classes": [
            {
              "class_id": "class::core::Context",
              "name": "Context",
              "qualified_name": "sdk::core::Context",
              "namespace": "sdk::core",
              "kind": "class",
              "methods": [
                {
                  "method_id": "method::core::Context::init",
                  "name": "init",
                  "qualified_name": "sdk::core::Context::init",
                  "namespace": "sdk::core",
                  "return_type": "sdk::ErrorCode",
                  "params": [
                    {
                      "name": "config",
                      "type_name": "const Config&",
                      "is_const": true,
                      "is_reference": true,
                      "is_pointer": false,
                      "default_value": null
                    }
                  ],
                  "is_const_method": false,
                  "is_static": false,
                  "access": "public"
                }
              ]
            }
          ],
          "functions": [],
          "enums": [],
          "aliases": []
        }
      ]
    }
  ]
}
```

---

## 5. QUALITY RULES

- **Every** function, method, enum, and alias must be captured — no omissions.
- Types expressed in the source must be preserved verbatim (e.g. ``"const char*"``,
  ``"std::vector<int>"``).
- If a symbol is declared in an ``#ifdef`` / ``#ifndef`` block, still include it
  (the scanner does not evaluate preprocessor conditions).
- Do **not** include implementation bodies — only declarations visible in headers.
- Do **not** include macros, ``#include`` directives, or comments as API entries.
"""
HUMAN_TEMPLATE: PromptTemplate = PromptTemplate(
    input_variables=["sdk_root", "header_files", "header_content"],
    template="SDK Root: {sdk_root}\nHeader Files: {header_files}\nContent:\n{header_content}",
)
