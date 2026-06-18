"""LLM model presets — built-in + JSON override.

Usage:
    from agents.models import get_llm, list_models

    # Create an LLM wrapper from a preset
    llm = get_llm("longcat")

    # Register a custom preset at runtime
    from agents.models import ModelConfig, add_preset
    add_preset("my-model", ModelConfig(model="gpt-4o", base_url="..."))

For per-agent model configuration (each agent using a different LLM), see
``agent_config.json`` or the ``SDK_AGENT_CONFIG_JSON`` env var.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agents.llm import LLMWrapper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelConfig:
    """Describes a single LLM endpoint.

    Fields
    ------
    model:
        Model name sent to the provider (e.g. ``"LongCat-2.0-Preview"``).
    base_url:
        OpenAI-compatible API base URL.
    api_key_env:
        Name of the environment variable that holds the API key.
        Defaults to ``"OPENAI_API_KEY"``.
    temperature:
        Generation temperature.  Defaults to ``0.1``.
    max_tokens:
        Maximum output tokens.  Defaults to ``16_000``.
    timeout:
        Request timeout in seconds.  Defaults to ``1200``.
    """

    model: str
    base_url: str
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.1
    max_tokens: int = 16_000
    timeout: int = 1200

    def to_llm_config(self) -> dict:
        """Return a config dict whose keys match what ``LLMWrapper`` expects.

        The returned dict uses the ``llm_*`` key naming convention so it
        can be passed directly to ``LLMWrapper(config)``.
        """
        return {
            "llm_model": self.model,
            "llm_base_url": self.base_url,
            "llm_api_key_env": self.api_key_env,
            "llm_temperature": self.temperature,
            "llm_max_tokens": self.max_tokens,
            "llm_timeout_sec": self.timeout,
        }


# ---------------------------------------------------------------------------
# Predefined model presets (built-in defaults)
# ---------------------------------------------------------------------------

LONG_CAT = ModelConfig(
    model="LongCat-2.0-Preview",
    base_url="https://api.longcat.chat/openai/v1",
    api_key_env="OPENAI_API_KEY",
    temperature=0.1,
    max_tokens=16_000,
)

DASHSCOPE = ModelConfig(
    model="kimi-k2.5",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key_env="OPENAI_API_KEY",
    temperature=0.2,
    max_tokens=30_000,
)

# ---------------------------------------------------------------------------
# In-memory registry (populated from built-ins + external config)
# ---------------------------------------------------------------------------

_MODELS: dict[str, ModelConfig] = {
    "longcat": LONG_CAT,
    "dashscope": DASHSCOPE,
    "default": LONG_CAT,
}


# ---------------------------------------------------------------------------
# Shared merge helper
# ---------------------------------------------------------------------------


def _merge_presets(
    presets: dict[str, Any],
    source: str = "<unknown>",
) -> int:
    """Merge model presets from a parsed config dict into ``_MODELS``.

    Returns the number of successfully loaded presets.
    """
    loaded = 0
    for name, cfg in presets.items():
        if not isinstance(cfg, dict):
            continue
        try:
            _MODELS[name] = ModelConfig(
                model=str(cfg["model"]),
                base_url=str(cfg["base_url"]),
                api_key_env=str(cfg.get("api_key_env", "OPENAI_API_KEY")),
                temperature=float(cfg.get("temperature", 0.1)),
                max_tokens=int(cfg.get("max_tokens", 16_000)),
                timeout=int(cfg.get("timeout", 1200)),
            )
            loaded += 1
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping preset %r in %s: %s", name, source, exc)
    if loaded:
        logger.info("Loaded %d preset(s) from %s (total registry: %d)", loaded, source, len(_MODELS))
    return loaded


# ---------------------------------------------------------------------------
# JSON loader (for OpenCode embedding / runtime use)
# ---------------------------------------------------------------------------


def load_presets_from_json(data: dict) -> int:
    """Load model presets from a JSON dict (for OpenCode embedding).

    This is a **public** function intended to be called by
    :class:`agents.agent_defs.AgentRegistry` when parsing JSON config.

    Returns the number of presets loaded.
    """
    models_section = data.get("models", {})
    if not isinstance(models_section, dict):
        return 0
    return _merge_presets(models_section, source="json")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_model(name: str = "default") -> ModelConfig:
    """Look up a :class:`ModelConfig` by name.

    Falls back to the default preset when *name* is unknown (with a
    warning).
    """
    if name in _MODELS:
        return _MODELS[name]
    logger.warning("Unknown model preset %r — falling back to 'default'", name)
    return _MODELS["default"]


def get_llm(name: str = "default") -> LLMWrapper:
    """Create a fully-configured :class:`LLMWrapper` from a model preset.

    This is the primary entry-point for obtaining an LLM instance::

        from agents.models import get_llm
        llm = get_llm("longcat")
    """
    cfg = get_model(name)
    logger.info(
        "LLM: model=%s  endpoint=%s  temperature=%.2f  max_tokens=%d",
        cfg.model,
        cfg.base_url,
        cfg.temperature,
        cfg.max_tokens,
    )
    return LLMWrapper(cfg.to_llm_config())


def list_models() -> list[str]:
    """Return the names of all registered model presets."""
    return list(_MODELS.keys())


def add_preset(name: str, config: ModelConfig) -> None:
    """Register (or override) a model preset at runtime."""
    _MODELS[name] = config
    logger.info("Runtime preset added: %s → %s", name, config.model)
