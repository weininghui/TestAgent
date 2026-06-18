"""Agent definitions — simple JSON-configurable sub-agent system.

Each agent can have its own model configuration (different model name,
API endpoint, temperature, etc.).  Configuration is resolved in cascade:

1. Built-in defaults (this file — 8 agents ready out of the box)
2. ``agent_config.json`` file (project root — optional)
3. ``SDK_AGENT_CONFIG_JSON`` environment variable (OpenCode embedding)

JSON formats — all of these work:

**Shorthand** — just set the default model::

    {
      "model": "gpt-4o",
      "base_url": "https://api.openai.com/v1",
      "api_key_env": "OPENAI_API_KEY"
    }

**Per-agent overrides**::

    {
      "default": "longcat",                    # all agents use longcat
      "code_gen": { "temperature": 0.2 },      # override specific fields
      "scanner": "gpt-4o-mini"                 # scanner uses a different model
    }

**Wrapped format** (for OpenCode embedding that needs extra presets)::

    {
      "models": {
        "my-model": { "model": "...", "base_url": "..." }
      },
      "agents": {
        "default": "longcat",
        "code_gen": { "temperature": 0.2 }
      }
    }

Top-level keys that match model-config field names (``model``, ``base_url``,
``api_key_env``, ``api_key``, ``temperature``, ``max_tokens``, ``timeout``)
are automatically treated as ``default`` overrides — no need to wrap them
in ``"default": { ... }``.
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class AgentConfig:
    """Configuration for a single agent — including its own LLM model settings.

    Every agent is self-contained: it carries its own model name, API
    endpoint, temperature, etc. so different agents can use different LLMs.

    ``api_key`` is an optional literal key override.  When set, it takes
    precedence over the env var named by ``api_key_env`` (but the in-memory
    keychain still wins).
    """

    name: str = ""
    role: str = ""
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    model: str = "LongCat-2.0-Preview"
    base_url: str = "https://api.longcat.chat/openai/v1"
    api_key_env: str = "OPENAI_API_KEY"
    api_key: str = ""           # optional literal key override
    temperature: float = 0.1
    max_tokens: int = 16_000
    timeout: int = 1200
    prompt_stage: str = ""
    tools: list[str] = field(default_factory=list)

    def to_llm_config(self) -> dict:
        """Return a config dict compatible with ``LLMWrapper(config)``.

        The returned dict uses ``llm_*`` keys to match what
        :class:`agents.llm.LLMWrapper` expects.
        """
        cfg = {
            "llm_model": self.model,
            "llm_base_url": self.base_url,
            "llm_api_key_env": self.api_key_env,
            "llm_temperature": self.temperature,
            "llm_max_tokens": self.max_tokens,
            "llm_timeout_sec": self.timeout,
        }
        if self.api_key:
            cfg["llm_api_key"] = self.api_key
        return cfg


# ---------------------------------------------------------------------------
# Built-in agent defaults  (8 agents — works without any config file)
# ---------------------------------------------------------------------------

_BUILTIN_AGENTS: dict[str, AgentConfig] = {
    "main": AgentConfig(
        name="main",
        role="main",
        description="Main orchestrator that parses goals and dispatches sub-agents",
        capabilities=["orchestration"],
    ),
    "scanner": AgentConfig(
        name="scanner",
        role="scanner",
        description="Scans SDK header files to extract API inventory",
        capabilities=["header_scanning"],
        prompt_stage="scanner",
        tools=["read_file", "list_directory", "grep_in_files"],
    ),
    "analysis": AgentConfig(
        name="analysis",
        role="analysis",
        description="Analyses the API inventory and identifies testable patterns",
        capabilities=["api_analysis"],
        prompt_stage="analysis",
    ),
    "test_design": AgentConfig(
        name="test_design",
        role="test_design",
        description="Designs GTest test cases based on API analysis",
        capabilities=["test_design"],
        prompt_stage="test_design",
        temperature=0.3,
    ),
    "code_gen": AgentConfig(
        name="code_gen",
        role="code_gen",
        description="Generates compilable GTest C++ code from test designs",
        capabilities=["code_generation"],
        prompt_stage="code_gen",
        temperature=0.2,
        max_tokens=32_000,
    ),
    "ci_gen": AgentConfig(
        name="ci_gen",
        role="ci_gen",
        description="Generates CI/CD workflow configuration for the test suite",
        capabilities=["ci_configuration"],
        prompt_stage="ci_gen",
    ),
    "report": AgentConfig(
        name="report",
        role="report",
        description="Synthesises a final markdown report of test generation results",
        capabilities=["report_synthesis"],
        prompt_stage="report",
    ),
    "error_fixer": AgentConfig(
        name="error_fixer",
        role="error_fixer",
        description="Analyzes compilation errors and fixes generated test code",
        capabilities=["error_fixing"],
        prompt_stage="code_gen",
        temperature=0.1,
    ),
}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_CONFIG_FILENAME = "agent_config.json"


def _find_config_root() -> Path:
    """Walk up from ``agents/`` to find the project root."""
    start = Path(__file__).resolve().parent  # agents/
    for parent in (start, start.parent):
        if (parent / _CONFIG_FILENAME).exists():
            return parent
    return Path.cwd()


# Model-config field names — keys that look like model settings rather than
# agent-specific overrides.  When found at the top level of a JSON config,
# they are treated as ``default`` overrides automatically.
_MODEL_FIELDS = frozenset({
    "model", "base_url", "api_key_env", "api_key",
    "temperature", "max_tokens", "timeout",
})


def _is_model_field(key: str) -> bool:
    """Return ``True`` if *key* looks like a model-config field name."""
    return key in _MODEL_FIELDS


def _resolve_preset(value: str | dict) -> dict:
    """Resolve a value to a field dict.

    * If *value* is a string — treat it as a model preset name, look up
      the preset from ``agents.models``, and return all its fields.
    * If *value* is a dict — return as-is.
    """
    if isinstance(value, str):
        from agents.models import get_model

        preset = get_model(value)
        return {
            "model": preset.model,
            "base_url": preset.base_url,
            "api_key_env": preset.api_key_env,
            "api_key": "",
            "temperature": preset.temperature,
            "max_tokens": preset.max_tokens,
            "timeout": preset.timeout,
        }
    if isinstance(value, dict):
        return value
    return {}


def _merge_from(agents: dict[str, AgentConfig], data: dict) -> None:
    """Merge a JSON config dict into the agents dict.

    Handles:
    * ``default`` section — applied as baseline for all agents
    * Top-level model-field keys — shorthand for ``default``
    * Per-agent overrides (both dict and string=preset-name forms)
    * Wrapped format: ``{"models":..., "agents":{...}}``
    """

    # --- Unwrap if the data has an "agents" wrapper ---
    if "agents" in data and isinstance(data["agents"], dict):
        # Load model presets from the "models" section first
        if "models" in data and isinstance(data["models"], dict):
            from agents.models import load_presets_from_json

            load_presets_from_json(data)
        data = data["agents"]

    # ── Extract top-level model-field keys as implicit "default" ──────
    defaults_data = {}

    # Start with explicit "default" key if present
    if "default" in data:
        raw_default = data.pop("default")
        if isinstance(raw_default, dict):
            defaults_data.update(raw_default)
        elif isinstance(raw_default, str):
            defaults_data.update(_resolve_preset(raw_default))

    # Scoop up any remaining top-level keys that look like model fields
    for key in list(data.keys()):
        if _is_model_field(key) and key not in ("default",):
            defaults_data[key] = data.pop(key)

    defaults = _resolve_preset(defaults_data)

    for name, overrides in data.items():
        if name == "default":
            continue

        overrides = _resolve_preset(overrides)
        if not isinstance(overrides, dict):
            continue

        # Default + override merge
        resolved = {**defaults, **overrides}

        if name in agents:
            agent = agents[name]
            for key, value in resolved.items():
                if hasattr(agent, key):
                    setattr(agent, key, value)
        else:
            # Brand-new agent from config
            agents[name] = AgentConfig(
                name=name,
                role=str(resolved.get("role", name)),
                description=str(resolved.get("description", "")),
                capabilities=list(resolved.get("capabilities", [])),
                model=str(resolved.get("model", "LongCat-2.0-Preview")),
                base_url=str(resolved.get("base_url", "https://api.longcat.chat/openai/v1")),
                api_key_env=str(resolved.get("api_key_env", "OPENAI_API_KEY")),
                api_key=str(resolved.get("api_key", "")),
                temperature=float(resolved.get("temperature", 0.1)),
                max_tokens=int(resolved.get("max_tokens", 16_000)),
                timeout=int(resolved.get("timeout", 1200)),
                prompt_stage=str(resolved.get("prompt_stage", "")),
                tools=list(resolved.get("tools", [])),
            )


def load_agents() -> dict[str, AgentConfig]:
    """Build the agent registry: built-ins → JSON file → JSON env var.

    Returns a ``dict`` keyed by agent name (e.g. ``"scanner"``,
    ``"code_gen"``).  The returned dict is a **copy** — modifying it will
    *not* affect other callers.
    """
    agents = deepcopy(_BUILTIN_AGENTS)

    # 1 — JSON config file
    config_path = _find_config_root() / _CONFIG_FILENAME
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            _merge_from(agents, data)
            count = sum(1 for k in data if k != "default" and isinstance(data[k], dict))
            logger.info("Loaded %d agent(s) from %s", count, config_path)
        except Exception as exc:
            logger.warning("Failed to load %s: %s", config_path, exc)

    # 2 — JSON environment variable (OpenCode embedding)
    raw = os.environ.get("SDK_AGENT_CONFIG_JSON")
    if raw:
        try:
            # Support: raw JSON string OR file path ending in .json
            if raw.endswith(".json") and Path(raw).is_file():
                with open(raw, encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = json.loads(raw)
            _merge_from(agents, data)
            logger.info("Loaded agent config from SDK_AGENT_CONFIG_JSON")
        except Exception as exc:
            logger.warning("Failed to parse SDK_AGENT_CONFIG_JSON: %s", exc)

    return agents
