"""Interactive terminal REPL — like OpenCode, for SDK test generation.

Usage from the terminal::

    python -m auto_test_agent chat

Or programmatically::

    from agents.interactive import InteractiveSession
    session = InteractiveSession()
    session.start()
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

from agents.agent_defs import load_agents
from agents.container_env import ContainerEnv
from agents.keychain import set_key, get_key, has_key, list_keys, clear_keys
from agents.models import get_model, get_llm

logger = logging.getLogger(__name__)

# ── ANSI colour codes ──────────────────────────────────────────────────────
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_CLEAR = "\033[2J\033[H"
_BG_BLUE = "\033[44m"
_BG_GREEN = "\033[42m"
_BG_DIM = "\033[100m"
_REVERSE = "\033[7m"

# ── Mode constants ────────────────────────────────────────────────────────
MODE_EXECUTE = "execute"
MODE_PLAN = "plan"

_MODE_LABELS = {
    MODE_EXECUTE: f"{_GREEN}●{_RESET} execute",
    MODE_PLAN: f"{_YELLOW}●{_RESET} plan",
}

_MODE_HELP = {
    MODE_EXECUTE: "Goals run immediately without confirmation.",
    MODE_PLAN: "Show the plan first and ask for confirmation before executing.",
}


def _c(text: str, colour: str) -> str:
    return f"{colour}{text}{_RESET}"


def _b(text: str) -> str:
    return f"{_BOLD}{text}{_RESET}"


def _dim(text: str) -> str:
    return f"{_DIM}{text}{_RESET}"


# ────────────────────────────────────────────────────────────────────────────
# Project scanner
# ────────────────────────────────────────────────────────────────────────────


def scan_project(path: str | None = None) -> dict[str, Any]:
    """Scan a project directory and return metadata about it.

    Detects project type, source files, configs, and build systems.
    """
    root = Path(path or os.getcwd()).resolve()
    if not root.is_dir():
        return {"error": f"Not a directory: {root}", "root": str(root)}

    info: dict[str, Any] = {
        "root": str(root),
        "name": root.name,
        "language": "unknown",
        "has_cmake": False,
        "has_meson": False,
        "has_makefile": False,
        "has_conanfile": False,
        "has_vcpkg": False,
        "has_dockerfile": False,
        "has_git": False,
        "has_python_setup": False,
        "has_package_json": False,
        "header_files": [],
        "source_files": [],
        "test_files": [],
        "build_dirs": [],
        "sdk_like": False,
    }

    # Walk project (up to 3 levels deep, max 2000 entries for performance)
    try:
        for entry in root.rglob("*"):
            if entry.is_dir():
                name = entry.name
                if name in (".git", "__pycache__", "node_modules", ".venv", "build", "out"):
                    if name == ".git":
                        info["has_git"] = True
                    elif name in ("build", "out"):
                        info["build_dirs"].append(str(entry))
                    continue
                if len(info["header_files"]) + len(info["source_files"]) > 2000:
                    break
                continue

            suffix = entry.suffix.lower()
            if suffix == ".h":
                info["header_files"].append(str(entry))
                info["sdk_like"] = True
            elif suffix in (".c", ".cpp", ".cc", ".cxx"):
                info["source_files"].append(str(entry))
            elif suffix == ".py":
                info["language"] = "python"
            elif suffix in (".js", ".ts", ".tsx", ".jsx"):
                if info["language"] == "unknown":
                    info["language"] = "javascript"

            # Config files
            if entry.name == "CMakeLists.txt":
                info["has_cmake"] = True
            elif entry.name == "Makefile":
                info["has_makefile"] = True
            elif entry.name == "meson.build":
                info["has_meson"] = True
            elif entry.name == "conanfile.txt":
                info["has_conanfile"] = True
            elif entry.name == "vcpkg.json":
                info["has_vcpkg"] = True
            elif entry.name in ("Dockerfile", "docker-compose.yml"):
                info["has_dockerfile"] = True
            elif entry.name == "setup.py" or entry.name == "pyproject.toml":
                info["has_python_setup"] = True
            elif entry.name == "package.json":
                info["has_package_json"] = True

            # Test files
            if "test" in entry.name.lower() or "spec" in entry.name.lower():
                info["test_files"].append(str(entry))
    except PermissionError:
        pass

    # Determine primary language
    if info["header_files"] or info["source_files"]:
        info["language"] = "c/c++"
    elif info["has_python_setup"]:
        info["language"] = "python"

    info["is_sdk"] = info["sdk_like"] and info["has_cmake"]
    info["summary"] = _summarise_project(info)
    return info


def _summarise_project(info: dict[str, Any]) -> str:
    """Return a human-readable one-line summary."""
    parts = [f"Language: {info['language']}"]
    h = len(info["header_files"])
    s = len(info["source_files"])
    t = len(info["test_files"])
    if h:
        parts.append(f"{h} header(s)")
    if s:
        parts.append(f"{s} source(s)")
    if t:
        parts.append(f"{t} test file(s)")
    if info["has_cmake"]:
        parts.append("CMake")
    if info["has_dockerfile"]:
        parts.append("Docker")
    if info["has_git"]:
        parts.append("git")
    return " | ".join(parts)


# ────────────────────────────────────────────────────────────────────────────
# Interactive session
# ────────────────────────────────────────────────────────────────────────────


class InteractiveSession:
    """OpenCode-like interactive terminal for the SDK Test Generation Agent.

    Usage::

        session = InteractiveSession()
        session.start()
    """

    def __init__(self, model: str = "default") -> None:
        self.model = model
        self.project_info: dict[str, Any] | None = None
        self.container_env = ContainerEnv()
        self._agents = load_agents()
        self._running = True
        self._keys_prompted = False
        self._mode: str = MODE_EXECUTE

        # Import lazily to avoid circular imports at module level
        from agent import TestGenAgent
        self._agent = TestGenAgent(model=model)

    # ──────────────────────────────────────────────────────────────────────────
    # REPL loop
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Enter the main REPL loop.

        The session starts with a welcome banner, auto-scans the current
        project directory, and then enters a ``read–evaluate–print`` loop
        where the user can type natural language goals or slash commands.
        """
        self._show_welcome()
        self._auto_scan()

        while self._running:
            try:
                line = self._prompt()
                if not line:
                    continue
                self._eval(line)
            except (EOFError, KeyboardInterrupt):
                print()
                self._say("Goodbye!", _GREEN)
                break
            except Exception as exc:
                self._say(f"Error: {exc}", _RED)

        self.container_env.cleanup()

    # ──────────────────────────────────────────────────────────────────────────
    # Prompt & input
    # ──────────────────────────────────────────────────────────────────────────

    def _prompt(self) -> str:
        """Display the input prompt and return the user's line."""
        project_tag = Path.cwd().name
        mode_prompt = _MODE_LABELS.get(self._mode, self._mode)
        return input(
            f"\n{_GREEN}{_BOLD}❯{_RESET} "
            f"{_CYAN}{project_tag}{_RESET} "
            f"{_DIM}({mode_prompt}{_DIM}){_RESET} "
        ).strip()

    def _say(self, text: str, colour: str = "", indent: int = 0) -> None:
        """Print output to the user."""
        prefix = "  " * indent
        if colour:
            print(f"{prefix}{colour}{text}{_RESET}")
        else:
            print(f"{prefix}{text}")

    def _show_progress(self, message: str) -> None:
        """Show a progress indicator."""
        print(f"  {_DIM}⏳ {message}{_RESET}")

    def _show_done(self, message: str = "done") -> None:
        """Show completion indicator."""
        print(f"  {_GREEN}✔ {message}{_RESET}")

    def _show_error(self, message: str) -> None:
        """Show error message."""
        print(f"  {_RED}✘ {message}{_RESET}")

    # ──────────────────────────────────────────────────────────────────────────
    # Welcome & auto-scan
    # ──────────────────────────────────────────────────────────────────────────

    def _show_welcome(self) -> None:
        """Print the welcome banner — OpenCode-like header."""
        print(_CLEAR, end="")
        width = shutil.get_terminal_size().columns

        # Top bar
        mode_tag = _MODE_LABELS.get(self._mode, self._mode)
        bar = (
            f"{_BG_BLUE}{_BOLD}  SDK Test Generation Agent{_RESET}"
            f"{_BG_DIM}{_DIM}  {mode_tag}  {_RESET}"
        )
        print(f"\n  {bar}")
        print(f"  {_DIM}  Type a goal or /help for commands{_RESET}")
        print(f"  {_CYAN}{'─' * min(width - 2, 60)}{_RESET}")

    def _auto_scan(self) -> None:
        """Auto-scan the current project on startup."""
        self._show_progress("Scanning project directory ...")
        self.project_info = scan_project()
        if "error" in self.project_info:
            self._say(f"  {_YELLOW}⚠ {self.project_info['error']}{_RESET}")
            return

        summary = self.project_info.get("summary", "unknown")
        self._show_done(f"Project: {_b(self.project_info['name'])} — {summary}")

    # ──────────────────────────────────────────────────────────────────────────
    # Evaluator
    # ──────────────────────────────────────────────────────────────────────────

    def _eval(self, line: str) -> None:
        """Evaluate a single line of user input.

        Routes to slash commands (``/``) or natural language goals.
        """
        line = line.strip()

        # Slash commands
        if line.startswith("/"):
            parts = line[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            self._handle_command(cmd, arg)
            return

        # Empty
        if not line:
            return

        # Natural language — treat as a goal for the agent
        self._handle_nl(line)

    def _ensure_keys(self) -> bool:
        """Check if required API keys are configured; prompt interactively if not.

        Returns ``True`` if keys are available (or were just set).
        """
        from agents.models import get_model

        cfg = get_model(self.model)
        key_name = cfg.api_key_env

        if has_key(key_name):
            return True

        # Only prompt once per session
        if self._keys_prompted:
            return False
        self._keys_prompted = True

        print()
        self._say(
            f"API key {_b(key_name)} is not configured. "
            f"Enter it now (paste your key):",
            _YELLOW,
        )
        self._say(_dim("  Leave empty to skip — set later with /key set <name>"), indent=1)
        val = input(f"  {_YELLOW}❯ {_RESET}").strip()

        if val:
            set_key(key_name, val)
            self._show_done(f"{key_name} saved for this session")
            return True

        self._say(_dim("  Skipped. You can set it anytime with /key set <name>"), indent=1)
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # Commands
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_command(self, cmd: str, arg: str) -> None:
        """Dispatch a slash command."""
        handler = {
            "help": self._cmd_help,
            "h": self._cmd_help,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
            "q": self._cmd_exit,
            "agents": self._cmd_agents,
            "models": self._cmd_models,
            "key": self._cmd_key,
            "keys": self._cmd_key,
            "scan": self._cmd_scan,
            "test": self._cmd_test,
            "ci": self._cmd_ci,
            "docker": self._cmd_docker,
            "clear": self._cmd_clear,
            "project": self._cmd_project,
            "config": self._cmd_config,
            "mode": self._cmd_mode,
            "status": self._cmd_status,
        }
        fn = handler.get(cmd)
        if fn:
            fn(arg)
        else:
            self._say(f"Unknown command: /{cmd}. Try /help", _YELLOW)

    def _cmd_help(self, _arg: str = "") -> None:
        """Show available commands."""
        self._say(f"{_b('Commands')}", _CYAN)
        cmds = [
            ("/help, /h", "Show this help"),
            ("/exit, /quit, /q", "Exit the session"),
            ("/key set/list/save", "Manage API keys interactively"),
            ("/mode execute|plan", "Switch between execute / plan modes"),
            ("/status", "Show session status"),
            ("/agents", "List registered sub-agents"),
            ("/models", "Show available model presets"),
            ("/scan", "Re-scan the current project"),
            ("/project", "Show project details"),
            ("/config", "Show current agent configuration"),
            ("/test", "Compile and run tests (in Docker if available)"),
            ("/ci", "Generate CI/CD configuration"),
            ("/docker status", "Check Docker availability"),
            ("/clear", "Clear screen"),
        ]
        for cmd, desc in cmds:
            self._say(f"  {_b(f'{cmd:<24}')}{_dim(desc)}")

        self._say("")
        self._say(_dim("Or just type a goal in plain English, like:"), indent=1)
        examples = [
            '"generate tests for the SDK headers"',
            '"scan and analyse the API"',
            '"run the full pipeline"',
            '"fix compilation errors"',
        ]
        for ex in examples:
            self._say(f"  {_dim('•')} {_c(ex, _CYAN)}")

    def _cmd_exit(self, _arg: str = "") -> None:
        """Exit the session."""
        self._say("Goodbye!", _GREEN)
        self._running = False

    def _cmd_agents(self, _arg: str = "") -> None:
        """List all registered agents."""
        agents = load_agents()
        self._say(f"{_b(f'Registered Agents ({len(agents)})')}", _CYAN)
        for name in sorted(agents):
            a = agents[name]
            self._say(
                f"  {_b(name):<16} {_dim(a.role):<16} "
                f"{_c(a.model, _YELLOW):<28} T={a.temperature}"
            )

    def _cmd_models(self, _arg: str = "") -> None:
        """Show current model config."""
        from agents.models import get_model_config
        cfg = get_model_config()
        if cfg:
            self._say(f"{_b('Model Configuration')}", _CYAN)
            self._say(f"  {_b('default'):<20} {_dim(cfg.model):<30} {cfg.base_url}")
        else:
            self._say(f"  {_YELLOW}No model configured. Use /config set.{_RESET}")

    def _cmd_scan(self, _arg: str = "") -> None:
        """Re-scan the project directory."""
        self._show_progress("Scanning ...")
        self.project_info = scan_project()
        if "error" in self.project_info:
            self._show_error(self.project_info["error"])
            return
        self._show_done(self.project_info.get("summary", ""))

    def _cmd_project(self, _arg: str = "") -> None:
        """Show detailed project info."""
        if not self.project_info or "error" in self.project_info:
            self._cmd_scan()
            return
        info = self.project_info
        self._say(f"{_b('Project:')} {info['name']}", _CYAN)
        self._say(f"  Root    : {info['root']}")
        self._say(f"  Lang    : {info['language']}")
        self._say(f"  SDK-like: {'yes' if info['is_sdk'] else 'no'}")
        if info["header_files"]:
            self._say(f"  Headers : {len(info['header_files'])} file(s)")
        if info["source_files"]:
            self._say(f"  Sources : {len(info['source_files'])} file(s)")
        if info["test_files"]:
            self._say(f"  Tests   : {len(info['test_files'])} file(s)")
        flags = []
        for k in ("cmake", "meson", "makefile", "dockerfile", "git"):
            if info.get(f"has_{k}"):
                flags.append(k)
        if flags:
            self._say(f"  Build   : {', '.join(flags)}")

    def _cmd_config(self, arg: str) -> None:
        """Show or set model configuration."""
        parts = arg.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""

        from agents.models import config_path, load_config, save_config, get_model_config

        # ── /config set — interactive prompt ──────────────────────────────
        if sub == "set":
            self._say(f"{_b('Configure Model')}  {_DIM}(leave empty to keep current){_RESET}", _CYAN)

            cur = get_model_config()

            url = input(f"  Base URL [{_c(cur.base_url if cur else '(none)', _YELLOW)}]: ").strip()
            if not url and cur:
                url = cur.base_url

            model = input(f"  Model name [{_c(cur.model if cur else '(none)', _YELLOW)}]: ").strip()
            if not model and cur:
                model = cur.model

            from agents.keychain import has_key
            key_hint = "set" if has_key("OPENAI_API_KEY") else "not set"
            key_input = input(f"  API key [{_c(key_hint, _YELLOW)}] (paste or leave empty): ").strip()

            if url and model:
                save_config(url=url, model=model, api_key=key_input or None)
                self._show_done("Config saved to ~/.sdk-test-agent/config.json")
            else:
                self._show_error("URL and model name are required.")
            return

        # ── /config url <url> ─────────────────────────────────────────────
        if sub == "url" and len(parts) > 1:
            from agents.models import save_config
            cur = load_config()
            save_config(url=parts[1], model=cur.get("model", ""))
            self._show_done(f"Base URL set")
            return

        # ── /config model <model> ─────────────────────────────────────────
        if sub == "model" and len(parts) > 1:
            from agents.models import save_config
            cur = load_config()
            save_config(url=cur.get("base_url", ""), model=parts[1])
            self._show_done(f"Model set to {parts[1]}")
            return

        # ── /config key <key> ─────────────────────────────────────────────
        if sub == "key" and len(parts) > 1:
            from agents.keychain import set_key
            set_key("OPENAI_API_KEY", parts[1])
            cur = load_config()
            if cur.get("model"):
                save_config(url=cur["base_url"], model=cur["model"], api_key=parts[1])
            self._show_done("API key saved")
            return

        # ── /config — show current ────────────────────────────────────────
        self._say(f"{_b('Model Configuration')}", _CYAN)
        cfg = get_model_config()
        if cfg:
            self._say(f"  URL   : {_c(cfg.base_url, _YELLOW)}")
            self._say(f"  Model : {_c(cfg.model, _YELLOW)}")
            from agents.keychain import has_key
            if has_key(cfg.api_key_env):
                self._show_done(f"API key '{cfg.api_key_env}' configured")
            else:
                self._show_error(f"API key '{cfg.api_key_env}' NOT set")
            self._say(f"  Temp  : {cfg.temperature}")
            self._say(f"  Path  : {_dim(str(config_path()))}")
        else:
            self._say(f"  {_YELLOW}No model configured.{_RESET}")
            self._say(f"  {_DIM}Use /config set to configure.{_RESET}")

        # Also show agent-level overrides
        agents = load_agents()
        overrides = {n: a for n, a in agents.items() if a.model or a.base_url}
        if overrides:
            self._say(f"\n  {_b('Per-agent overrides')}")
            for name, a in sorted(overrides.items()):
                self._say(f"    {name:<14} model={_c(a.model or '(default)', _YELLOW)}")

    def _cmd_key(self, arg: str) -> None:
        """Manage API keys interactively: set, list, clear."""
        parts = arg.split(maxsplit=1)
        sub = parts[0].lower() if parts else ""

        if sub == "set":
            key_val = parts[1] if len(parts) > 1 else ""
            kv = key_val.split(maxsplit=1)
            if len(kv) == 2:
                set_key(kv[0], kv[1])
                self._show_done(f"Key '{kv[0]}' set for this session")
            elif len(kv) == 1:
                # Prompt for value (hide input-like)
                self._say(f"Enter value for {_b(kv[0])}:", _YELLOW)
                val = input(f"  {_YELLOW}❯ {_RESET}").strip()
                if val:
                    set_key(kv[0], val)
                    self._show_done(f"Key '{kv[0]}' set for this session")
                else:
                    self._say("Cancelled.", _DIM)
            else:
                self._say("Usage: /key set <NAME> [value]", _YELLOW)
                self._say(_dim("  If value is omitted, you'll be prompted securely"), indent=1)

        elif sub == "list":
            names = list_keys()
            if names:
                self._say(f"{_b('Session keys')}", _CYAN)
                for n in names:
                    masked = get_key(n)[:8] + "****" if get_key(n) else "****"
                    self._say(f"  {_b(n):<24} {_dim(masked)}")
            else:
                self._say("No keys set in this session.", _DIM)
            # Also show which env vars are set (without values)
            from agents.models import get_model
            cfg = get_model(self.model)
            env_key = cfg.api_key_env
            if has_key(env_key):
                self._show_done(f"Model '{self.model}' key is configured")
            else:
                self._show_error(f"Model '{self.model}' key '{env_key}' is NOT set")

        elif sub == "clear":
            clear_keys()
            self._show_done("All session keys cleared")

        elif sub == "save":
            # Save to .env
            env_path = Path.cwd() / ".env"
            names = list_keys()
            if not names:
                self._say("No keys to save.", _DIM)
                return
            try:
                existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
                with open(env_path, "a", encoding="utf-8") as f:
                    for n in names:
                        val = get_key(n)
                        if val and f"{n}=" not in existing:
                            f.write(f"\n{n}={val}\n")
                self._show_done(f"Saved {len(names)} key(s) to .env")
            except Exception as exc:
                self._show_error(f"Failed to save .env: {exc}")

        else:
            self._say("Usage:", _CYAN)
            self._say(f"  {_b('/key set <NAME> [value]')}   — set a key (omit value for prompt)")
            self._say(f"  {_b('/key list')}                — show configured keys")
            self._say(f"  {_b('/key save')}                — save session keys to .env")
            self._say(f"  {_b('/key clear')}               — clear all session keys")

    def _cmd_docker(self, arg: str) -> None:
        """Docker-related commands: status, build, clean."""
        if arg == "status":
            avail = ContainerEnv.is_available()
            if avail:
                try:
                    version = subprocess.run(
                        ["docker", "--version"], capture_output=True, text=True, timeout=5
                    ).stdout.strip()
                    self._show_done(f"Docker is available — {version}")
                except Exception:
                    self._show_done("Docker is available")
            else:
                self._show_error("Docker is not available")
        elif arg == "build":
            self._show_progress("Building test environment image ...")
            ok = self.container_env.build_image(force=True)
            if ok:
                self._show_done("Image built")
            else:
                self._show_error("Image build failed")
        elif arg == "clean":
            self.container_env.cleanup()
            self._show_done("Container cleaned up")
        else:
            self._say("Usage: /docker status|build|clean", _YELLOW)

    def _cmd_test(self, _arg: str = "") -> None:
        """Compile and run tests in Docker (if available)."""
        output_root = "./output"
        gen_dir = os.path.join(output_root, "generated")

        if not os.path.isdir(gen_dir) or not list(Path(gen_dir).rglob("*.cpp")):
            self._show_error("No generated tests found. Run `generate tests` first.")
            self._say(_dim("  Tip: type \"generate tests\" to create test files first"), indent=1)
            return

        self._say(f"{_b('Running Tests')}", _CYAN)

        if not ContainerEnv.is_available():
            self._show_error("Docker not available. Cannot compile/test.")
            self._say(_dim("  Install Docker Desktop and try again."), indent=1)
            return

        # Get SDK name from project info
        sdk_name = self.project_info["name"] if self.project_info else None

        self._show_progress("Starting Docker test environment ...")
        result = self.container_env.compile_and_run(gen_dir, sdk_name=sdk_name)

        if result["success"]:
            self._show_done("All tests passed!")
        else:
            self._show_error(f"Tests failed: {result.get('error', 'unknown error')}")

        # Show build/test output (last 30 lines)
        output = (result.get("build_output", "") + "\n" + result.get("test_output", "")).strip()
        if output:
            lines = output.splitlines()
            if len(lines) > 40:
                self._say(_dim(f"  ... ({len(lines) - 40} lines hidden)"), indent=1)
                lines = lines[-40:]
            for line in lines:
                print(f"  {_dim(line[:120])}")

    def _cmd_ci(self, _arg: str = "") -> None:
        """Generate CI/CD workflow configuration."""
        output_root = "./output"
        ci_dir = os.path.join(output_root, "ci")

        self._show_progress("Generating CI/CD configuration ...")

        try:
            from agents.chains.ci_gen_chain import CIGenChain
            from agents.prompts import ci_gen_prompt

            llm = self._agent._get_llm("ci_gen")
            from agents.tools.code_gen_tools import write_cmake_file, write_workflow_file, ensure_output_dir

            ci_chain = CIGenChain(
                llm=llm,
                tools=[write_cmake_file, write_workflow_file, ensure_output_dir],
                prompt=ci_gen_prompt.HUMAN_TEMPLATE,
            )
            # Run with whatever context we have
            result = ci_chain.run({}, {})
            self._show_done(f"CI config generated → {ci_dir}")
            self._say(_dim(f"  {result}"))

        except Exception as exc:
            self._show_error(f"CI generation failed: {exc}")

    def _cmd_clear(self, _arg: str = "") -> None:
        """Clear the terminal screen."""
        print(_CLEAR, end="")
        self._show_welcome()

    def _cmd_mode(self, arg: str) -> None:
        """Switch between execute and plan modes."""
        mode = arg.strip().lower()

        if mode == MODE_EXECUTE:
            self._mode = MODE_EXECUTE
            self._show_done(f"Switched to {_MODE_LABELS[self._mode]} mode")
            self._say(_dim(f"  {_MODE_HELP[self._mode]}"), indent=1)
        elif mode == MODE_PLAN:
            self._mode = MODE_PLAN
            self._show_done(f"Switched to {_MODE_LABELS[self._mode]} mode")
            self._say(_dim(f"  {_MODE_HELP[self._mode]}"), indent=1)
        elif not mode:
            self._say(f"Current mode: {_MODE_LABELS.get(self._mode, self._mode)}", _CYAN)
            self._say("")
            self._say(f"  {_b('/mode execute')}  — {_MODE_HELP[MODE_EXECUTE]}")
            self._say(f"  {_b('/mode plan')}     — {_MODE_HELP[MODE_PLAN]}")
        else:
            self._say(f"Unknown mode: {mode}. Use 'execute' or 'plan'.", _YELLOW)

    def _cmd_status(self, _arg: str = "") -> None:
        """Show current session status."""
        self._say(f"{_b('Session Status')}", _CYAN)
        self._say(f"  Mode    : {_MODE_LABELS.get(self._mode, self._mode)}")
        self._say(f"  Model   : {_b(self.model)}")
        if self.project_info:
            self._say(f"  Project : {_b(self.project_info['name'])} — {self.project_info.get('summary', '')}")
        else:
            self._say(f"  Project : {_dim('(not scanned)')}")
        self._say(f"  Docker  : {'available' if ContainerEnv.is_available() else 'not available'}")

        # Key status
        from agents.models import get_model
        cfg = get_model(self.model)
        key_name = cfg.api_key_env
        from agents.keychain import has_key
        if has_key(key_name):
            self._show_done(f"API key '{key_name}' is configured")
        else:
            self._show_error(f"API key '{key_name}' is NOT set")

    # ──────────────────────────────────────────────────────────────────────────
    # Natural language handler
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_nl(self, goal: str) -> None:
        """Process a natural language goal through the agent pipeline."""
        goal_lower = goal.lower()

        # ── Simple responses for common queries ──────────────────────────────
        if goal_lower in ("hi", "hello", "hey"):
            self._say("Hello! Tell me what kind of tests you'd like to generate, "
                      "or type /help to see available commands.", _CYAN)
            return

        if goal_lower in ("what can you do", "what do you do", "capabilities"):
            self._say(
                "I can:\n"
                "  • Scan C/C++ SDK headers and analyse APIs\n"
                "  • Design GTest test cases\n"
                "  • Generate compilable C++ test code\n"
                "  • Create CI/CD workflows (CMake, GitHub Actions)\n"
                "  • Compile and run tests in Docker containers\n"
                "  • Generate Markdown test reports",
                _CYAN,
            )
            return

        # ── Scan shortcuts ───────────────────────────────────────────────────
        if goal_lower in ("scan", "scan project", "scan the project"):
            self._cmd_scan()
            return

        # ── Ensure API keys before running pipeline ─────────────────────────
        if any(kw in goal_lower for kw in (
            "generate test", "run pipeline", "full pipeline",
            "create test", "generate code", "make test",
            "scan and analyse", "generate tests",
            "generate",
        )):
            if not self._ensure_keys():
                self._say(_dim("  Set a key with /key set <NAME> <value> then try again"), indent=1)
                return
            self._run_generation(goal)
            return

        # ── Docker shortcuts ─────────────────────────────────────────────────
        if goal_lower in ("docker", "docker status"):
            self._cmd_docker("status")
            return

        if goal_lower in ("test", "run tests", "run test", "compile"):
            self._cmd_test("")
            return

        if goal_lower in ("ci", "ci/cd", "workflow"):
            self._cmd_ci("")
            return

        if goal_lower in ("project", "project info"):
            self._cmd_project()
            return

        if goal_lower in ("config", "show config"):
            self._cmd_config()
            return

        # ── Fallback: try the agent ─────────────────────────────────────────
        self._show_progress("Processing your request ...")

        # Ensure keys before LLM calls
        if not self._ensure_keys():
            self._show_error("No API key configured. Set one with /key set <NAME> <value>")
            return

        # Set sdk_root from project info if available
        if self.project_info and "root" in self.project_info:
            enriched_goal = f"{goal} sdk root: {self.project_info['root']}"
        else:
            enriched_goal = goal

        try:
            result = self._agent.run(enriched_goal)
            self._show_result(result)
        except Exception as exc:
            self._show_error(f"Agent error: {exc}")

    # ──────────────────────────────────────────────────────────────────────────
    # Test generation pipeline
    # ──────────────────────────────────────────────────────────────────────────

    def _run_generation(self, goal: str) -> None:
        """Run the full test-generation pipeline."""
        # Resolve sdk_root
        sdk_root = self._resolve_sdk_root(goal)
        if not sdk_root:
            self._show_error(
                "Could not determine which project to scan.\n"
                "  Include a path in your goal, e.g.: "
                "\"generate tests for ./my_sdk\""
            )
            return

        enriched = f"{goal} sdk root: {sdk_root}"

        # Section header
        width = shutil.get_terminal_size().columns
        self._say(f"  {_CYAN}{'─' * min(width - 2, 56)}{_RESET}")
        self._say(f"  {_BOLD}{_CYAN}Test Generation Pipeline{_RESET}")
        self._say(f"  {_CYAN}{'─' * min(width - 2, 56)}{_RESET}")

        # 1 — Plan
        self._show_progress("Planning ...")
        plan = self._agent.plan(enriched)
        stages = plan.get("stages", [])
        model_name = plan.get('model', 'default')

        # Show plan details
        self._say(f"  {_b('Plan Preview')}  {_DIM}({len(stages)} stage(s), model: {model_name}){_RESET}")
        for i, s in enumerate(stages, 1):
            self._say(_dim(f"    {i}. {s}"), indent=1)

        # 2 — Plan mode: ask for confirmation
        if self._mode == MODE_PLAN:
            self._say("")
            try:
                confirm = input(
                    f"  {_YELLOW}Execute this plan?{_RESET} "
                    f"{_DIM}[Y/n]{_RESET} "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm and confirm not in ("y", "yes", ""):
                self._say(f"  {_DIM}Plan cancelled.{_RESET}")
                return

        # 3 — Execute
        self._show_progress("Running pipeline (this may take a while) ...")
        t0 = time.monotonic()
        try:
            result = self._agent.run(enriched)
            elapsed = time.monotonic() - t0
        except Exception as exc:
            self._show_error(f"Pipeline failed: {exc}")
            return

        # 4 — Show results
        self._show_result(result, elapsed)

        # 4 — Offer next steps
        if result.get("status") == "success":
            gen_dir = os.path.join(
                self._agent.output_root, "generated"
            )
            files = list(Path(gen_dir).rglob("*.cpp")) + list(Path(gen_dir).rglob("*.h"))
            if files:
                total_lines = sum(
                    len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
                    for f in files[:20]
                )
                self._say(
                    _dim(f"  Generated {len(files)} file(s), ~{total_lines} lines of test code"),
                    indent=1,
                )
                self._say("")
                self._say(_dim("  Next steps:"), indent=1)
                self._say(_dim("  • Run  /test   to compile & execute tests in Docker"), indent=1)
                self._say(_dim("  • Run  /ci     to generate CI/CD configuration"), indent=1)
                self._say(_dim("  • Run  /scan   to re-scan after changes"), indent=1)

    # ──────────────────────────────────────────────────────────────────────────
    # Result display
    # ──────────────────────────────────────────────────────────────────────────

    def _show_result(self, result: dict[str, Any], elapsed: float | None = None) -> None:
        """Display a structured agent result to the user."""
        status = result.get("status", "unknown")

        if status == "error":
            self._show_error(result.get("error", "Unknown error"))
            if "help" in result:
                self._say(_dim(f"  {result['help']}"), indent=1)
            return

        if elapsed:
            self._show_done(f"Pipeline finished in {elapsed:.1f}s")

        stages = result.get("stages_executed", [])
        self._say(f"  Stages: {_b(', '.join(stages) if stages else '(none)')}")

        # Stage results
        stage_results = result.get("stage_results", {})
        for stage, summary in stage_results.items():
            short = str(summary)[:100]
            self._say(_dim(f"    {stage}: {short}"), indent=1)

        # Generated files
        files = result.get("generated_files", [])
        if files:
            self._say(f"  Generated: {len(files)} file(s)")
            for f in files[:10]:
                self._say(_dim(f"    • {f}"), indent=1)
            if len(files) > 10:
                self._say(_dim(f"    ... and {len(files) - 10} more"), indent=1)

        # Sub-agents
        sub_agents = result.get("sub_agents", {})
        if sub_agents:
            self._say(f"  Sub-agents: {len(sub_agents)}")
            for name, info in sub_agents.items():
                self._say(_dim(f"    {name} → {info.get('model', '?')}"), indent=1)

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_sdk_root(self, goal: str) -> str | None:
        """Determine the SDK/project root from the goal or project scan."""
        # 1 — Try parsing from goal
        import re
        m = re.search(
            r"(?:sdk[-\s]?(?:root|path|dir)[-\s:]*)?"
            r"([A-Za-z]:[/\\][^\s,;'\"]+|/[^\s,;'\"]+|\.[/\\][^\s,;'\"]+)",
            goal,
        )
        if m:
            p = Path(m.group(1))
            if p.exists() or p.parent.exists():
                return str(p.resolve())

        # 2 — Use scanned project root
        if self.project_info and "root" in self.project_info:
            return self.project_info["root"]

        # 3 — Use CWD
        return os.getcwd()
