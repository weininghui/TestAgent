"""Simplified model config — no built-in presets, uses ~/.sdk-test-agent/config.json.

Usage:
    # First-time setup (interactive):
    from agents.models import save_config
    save_config(url="https://api.openai.com/v1", model="gpt-4o", api_key="sk-...")

    # Later runs:
    from agents.models import get_llm
    llm = get_llm()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.llm import LLMWrapper

logger = logging.getLogger(__name__)

# ── Config file path ────────────────────────────────────────────────────────
_CONFIG_DIR = Path.home() / ".sdk-test-agent"
_CONFIG_PATH = _CONFIG_DIR / "config.json"

# ── Best defaults ───────────────────────────────────────────────────────────
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 16_000
DEFAULT_TIMEOUT = 1200


@dataclass(frozen=True)
class ModelConfig:
    """Describes a single LLM endpoint."""

    model: str
    base_url: str
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout: int = DEFAULT_TIMEOUT

    def to_llm_config(self) -> dict:
        """Return a config dict consumable by ``LLMWrapper(config)``."""
        return {
            "llm_model": self.model,
            "llm_base_url": self.base_url,
            "llm_api_key_env": self.api_key_env,
            "llm_temperature": self.temperature,
            "llm_max_tokens": self.max_tokens,
            "llm_timeout_sec": self.timeout,
        }


# ── Config file I/O ─────────────────────────────────────────────────────────


def config_path() -> Path:
    return _CONFIG_PATH


def load_config() -> dict[str, Any]:
    """Load saved config, returning ``{}`` if none."""
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read config: %s", exc)
    return {}


def save_config(
    url: str,
    model: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Save model settings to ``~/.sdk-test-agent/config.json``.

    If *api_key* is provided it is stored in the in-memory keychain
    (never written to disk in plain text).
    """
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"base_url": url.rstrip("/"), "model": model}
    if api_key:
        data["api_key_env"] = "OPENAI_API_KEY"
        from agents.keychain import set_key  # noqa: late import avoids cycle

        set_key("OPENAI_API_KEY", api_key)
    _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Config saved to %s", _CONFIG_PATH)
    return data


def get_model_config() -> ModelConfig | None:
    """Build a :class:`ModelConfig` from saved settings, or ``None``."""
    cfg = load_config()
    if not cfg or "model" not in cfg or "base_url" not in cfg:
        return None
    return ModelConfig(
        model=cfg["model"],
        base_url=cfg["base_url"],
        api_key_env=cfg.get("api_key_env", "OPENAI_API_KEY"),
    )


# ── Public API ──────────────────────────────────────────────────────────────


def get_llm(name: str | None = None) -> LLMWrapper:
    """Create a fully-configured :class:`LLMWrapper` from saved config.

    Raises :class:`ValueError` if no model has been configured yet.
    """
    cfg = get_model_config()
    if cfg is None:
        raise ValueError(
            "No model configured.  Run the interactive session and use "
            "/config set, or create ~/.sdk-test-agent/config.json manually:\n"
            '  {"base_url": "https://...", "model": "..."}'
        )
    logger.info("LLM: model=%s  endpoint=%s", cfg.model, cfg.base_url)
    return LLMWrapper(cfg.to_llm_config())


def get_model(name: str | None = None) -> ModelConfig:
    """Return the current :class:`ModelConfig` (ignores *name*).

    Returns the single saved config from ``~/.sdk-test-agent/config.json``.
    """
    cfg = get_model_config()
    if cfg is None:
        raise ValueError("No model configured")
    return cfg


def list_models() -> list[str]:
    """Return ``["default"]`` when a config exists, else ``[]``."""
    return ["default"] if get_model_config() else []
