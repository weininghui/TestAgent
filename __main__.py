#!/usr/bin/env python3
"""SDK Test Generation Agent — terminal CLI.

Usage::

    python -m auto_test_agent run --goal "generate tests for C:/SDK"
    python -m auto_test_agent list-agents
    python -m auto_test_agent list-models
    python -m auto_test_agent show-config
    python -m auto_test_agent chat              # interactive mode
    python -m auto_test_agent run --help
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from agents.agent_defs import load_agents
from agents.models import list_models, get_model


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Sub-command:  run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> None:
    """Run the agent with a natural language goal."""
    _setup_logging(args.verbose)

    from agent import TestGenAgent

    agent = TestGenAgent(model=args.model, output_root=args.output_root)

    # Build goal string
    goal_parts: list[str] = []
    if args.goal:
        goal_parts.append(args.goal)
    if args.sdk_root:
        goal_parts.append(f"sdk root: {args.sdk_root}")
    goal = " ".join(goal_parts) if goal_parts else ""

    if not goal:
        goal = input("Enter goal for the test generation agent: ").strip()
        if not goal:
            print("No goal provided.  Use --help for usage.")
            sys.exit(1)

    if args.dry_run:
        plan = agent.plan(goal)
        print(json.dumps(plan, indent=2, default=str, ensure_ascii=False))
        return

    print(f"  goal: {goal}\n")
    result = agent.run(goal)
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))

    if result.get("status") == "error":
        sys.exit(1)


def _add_run_parser(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--goal", "-g", default=None, help="Natural language goal")
    sub.add_argument("--sdk-root", default=None, help="SDK root path")
    sub.add_argument("--model", "-m", default="longcat", help="Model preset name")
    sub.add_argument("--output-root", "-o", default="./output", help="Output directory")
    sub.add_argument("--dry-run", "-n", action="store_true", help="Show plan only")
    sub.add_argument("--verbose", "-v", action="store_true", help="Debug logging")


# ---------------------------------------------------------------------------
# Sub-command:  list-agents
# ---------------------------------------------------------------------------


def cmd_list_agents(args: argparse.Namespace) -> None:
    """List all registered sub-agents with their model config."""
    agents = load_agents()

    header = f"{'Name':<16} {'Role':<16} {'Model':<28} {'Temp':<6} {'Prompt Stage':<16}"
    sep = "-" * len(header)

    print(f"\n  Registered Agents  ({len(agents)} total)\n")
    print(f"  {header}")
    print(f"  {sep}")

    for name in sorted(agents):
        a = agents[name]
        if args.role and a.role != args.role:
            continue
        model_short = a.model[:26] + ".." if len(a.model) > 28 else a.model
        print(
            f"  {name:<16} {a.role:<16} {model_short:<28} "
            f"{a.temperature:<6} {a.prompt_stage or '-':<16}"
        )

    print(f"\n  Tip: python -m auto_test_agent show-config  for full details\n")


def _add_list_agents_parser(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--role", default=None, help="Filter by role")


# ---------------------------------------------------------------------------
# Sub-command:  chat  (interactive mode)
# ---------------------------------------------------------------------------


def cmd_chat(args: argparse.Namespace) -> None:
    """Start an interactive terminal session (like OpenCode)."""
    _setup_logging(args.verbose)

    from agents.interactive import InteractiveSession

    session = InteractiveSession(model=args.model)
    session.start()


def _add_chat_parser(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--model", "-m", default="longcat", help="Model preset name")
    sub.add_argument("--verbose", "-v", action="store_true", help="Debug logging")


# ---------------------------------------------------------------------------
# Sub-command:  list-models
# ---------------------------------------------------------------------------


def cmd_list_models(args: argparse.Namespace) -> None:
    """Show all available model presets."""
    models = list_models()

    print(f"\n  Available Model Presets  ({len(models)})\n")
    for name in sorted(models):
        cfg = get_model(name)
        print(f"  {name:<24}  {cfg.model:<30}  {cfg.base_url}")
    print()


def _add_list_models_parser(sub: argparse.ArgumentParser) -> None:
    pass  # no extra args


# ---------------------------------------------------------------------------
# Sub-command:  show-config
# ---------------------------------------------------------------------------


def cmd_show_config(args: argparse.Namespace) -> None:
    """Show full agent configuration details."""
    agents = load_agents()

    for name in sorted(agents):
        a = agents[name]
        print(f"\n  {name}  ({a.role})")
        print(f"  {'-' * (len(name) + len(a.role) + 5)}")
        print(f"    description   {a.description}")
        print(f"    model         {a.model}")
        print(f"    base_url      {a.base_url}")
        print(f"    api_key_env   {a.api_key_env}")
        print(f"    temperature   {a.temperature}")
        print(f"    max_tokens    {a.max_tokens}")
        print(f"    timeout       {a.timeout}s")
        print(f"    prompt_stage  {a.prompt_stage or '-'}")
        print(f"    capabilities  {', '.join(a.capabilities) if a.capabilities else '-'}")
        print(f"    tools         {', '.join(a.tools) if a.tools else '-'}")
    print()


def _add_show_config_parser(sub: argparse.ArgumentParser) -> None:
    pass  # no extra args


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sdk-test-agent",
        description="SDK Test Generation Agent — AI-powered C/C++ GTest generator",
    )
    sub = parser.add_subparsers(dest="command", help="Sub-command (default: run)")

    # run
    p_run = sub.add_parser("run", help="Run the agent with a goal")
    _add_run_parser(p_run)

    # chat (interactive)
    p_chat = sub.add_parser("chat", help="Start interactive terminal session")
    _add_chat_parser(p_chat)

    # list-agents
    p_agents = sub.add_parser("list-agents", help="List registered sub-agents")
    _add_list_agents_parser(p_agents)

    # list-models
    p_models = sub.add_parser("list-models", help="Show available model presets")
    _add_list_models_parser(p_models)

    # show-config
    p_config = sub.add_parser("show-config", help="Show full agent configuration")
    _add_show_config_parser(p_config)

    args = parser.parse_args()

    # ── Dispatch ────────────────────────────────────────────────────────
    if args.command == "run":
        cmd_run(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "list-agents":
        cmd_list_agents(args)
    elif args.command == "list-models":
        cmd_list_models(args)
    elif args.command == "show-config":
        cmd_show_config(args)
    else:
        # No sub-command → show help
        parser.print_help()
        print("\n  Example:\n    python -m auto_test_agent run --goal \"generate tests for C:/SDK\"\n")


if __name__ == "__main__":
    main()
