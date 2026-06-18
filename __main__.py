"""Module entry point — allow ``python -m auto_test_agent``.

Dispatches to the appropriate entry based on command-line arguments:

- If ``--goal`` / ``-g`` is provided → run as agent (``agent.clicli_main``)
- Otherwise → show help banner with all available entry points.

This module is invoked automatically when OpenCode loads the skill and
dispatches the agent via ``task(category="deep", load_skills=["test-agent"],
prompt="...")``.
"""

from __future__ import annotations

import sys


def main() -> None:
    """Detect invocation mode and dispatch accordingly."""

    # Forward to agent if goal-like args present
    if any(a in sys.argv for a in ("--goal", "-g", "--sdk-root")):
        from agent import clicli_main

        clicli_main()
        return

    # Show help banner
    print(
        "\n".join(
            [
                "SDK Test Generation Agent  v1.0.0",
                "=" * 40,
                "",
                "Available entry points:",
                "  python -m auto_test_agent --goal 'generate tests for /path'   Run agent",
                "  python -m auto_test_agent --help                            Agent help",
                "  python app.py                                                CLI mode",
                "  python mcp_server.py                                         MCP server",
                "  python agent.py --goal '...'                                 Agent CLI",
                "",
                "Or use the skill in OpenCode:",
                "  /test-agent  generate --sdk-root /path",
                "",
            ],
        ),
    )


if __name__ == "__main__":
    main()
