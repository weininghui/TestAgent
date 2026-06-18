"""SDK Test Generation Agent — AI-powered C/C++ GTest generator.

Install::

    pip install -e .

CLI usage::

    python -m auto_test_agent chat           # interactive REPL
    python -m auto_test_agent run --goal ...  # one-shot pipeline
    python -m auto_test_agent list-models     # show model presets

Or use a registered entry point::

    sdk-test-agent --goal "generate tests for /path"
"""

from __future__ import annotations
