"""SDK Test Generation Agent.

An AI-powered agent that analyses C/C++ SDK header files and automatically
produces comprehensive GoogleTest (GTest) test suites with CMake build
integration.

The agent runs a 6-stage LangChain pipeline:

    1. **Scanner**  — discover and extract API signatures from ``.h`` files
    2. **Analysis** — analyse complexity, patterns, and integration risks
    3. **Test Design**  — design up to 100 targeted test cases
    4. **Code Gen**   — write compilable C++ GoogleTest source files
    5. **CI Gen**     — generate CMake and GitHub Actions workflow
    6. **Report**   — synthesise Markdown report and JSON summary

Package
-------
    auto_test_agent  v1.0.0
"""

from __future__ import annotations

__all__ = [
    "__version__",
    "TestGenAgent",
    "clicli_main",
]

__version__ = "1.0.0"

# Import the agent class so it's available as ``from auto_test_agent import TestGenAgent``
from agent import TestGenAgent, clicli_main  # noqa: E402 — agent import is safe
