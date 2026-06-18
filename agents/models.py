"""LLM model presets — with external YAML config support.

Usage:
    from agents.models import get_llm, list_models

    # Create an LLM wrapper from a preset
    llm = get_llm("longcat")

    # Or just inspect a config
    from agents.models import LONG_CAT
    print(LONG_CAT.base_url)

Config file (optional):
    ``model_config.yaml`` at the project root can define or override presets.
    A local-only ``model_config.local.yaml`` is also loaded on top (not tracked
    in git) for user-specific overrides.
"""

from __future__ import annotations

import logging
import os
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
# In-memory registry (populated from built-ins + YAML overrides)
# ---------------------------------------------------------------------------

_MODELS: dict[str, ModelConfig] = {
    "longcat": LONG_CAT,
    "dashscope": DASHSCOPE,
    "default": LONG_CAT,
}


def _find_config_root() -> str:
    """Return the project root directory.

    Walk up from ``agents/models.py`` looking for ``model_config.yaml``,
    falling back to the current working directory.
    """
    start = os.path.dirname(os.path.abspath(__file__))  # agents/
    parent = os.path.dirname(start)  # project root
    candidate = os.path.join(parent, "model_config.yaml")
    if os.path.isfile(candidate):
        return parent
    return os.getcwd()


def _load_presets_from_yaml(root: str) -> int:
    """Load model presets from ``model_config.yaml`` (and local overrides).

    Parameters
    ----------
    root:
        Directory to search for the YAML files.

    Returns
    -------
    int
        Number of presets loaded from external files.
    """
    try:
        import yaml  # lazy import — only needed when config files exist
    except ImportError:
        return 0

    loaded = 0
    for fname in ("model_config.yaml", "model_config.local.yaml"):
        path = os.path.join(root, fname)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data: dict[str, Any] = yaml.safe_load(fh)
        except Exception as exc:
            logger.warning("Failed to load %s: %s", fname, exc)
            continue

        presets = data.get("presets", {}) if isinstance(data, dict) else {}
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
                logger.warning("Skipping preset %r in %s: %s", name, fname, exc)

        logger.info(
            "Loaded %d preset(s) from %s (total registry: %d)",
            loaded,
            fname,
            len(_MODELS),
        )
    return loaded


# ── Auto-load YAML presets at import time ──────────────────────────────────
_root = _find_config_root()
_load_presets_from_yaml(_root)
del _root


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
