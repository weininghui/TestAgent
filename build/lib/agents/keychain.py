"""In-memory API key store — set keys interactively, no env vars needed.

Usage::

    from agents.keychain import set_key, get_key

    set_key("OPENAI_API_KEY", "sk-xxx")   # store in memory
    key = get_key("OPENAI_API_KEY")        # keychain → os.environ → fallback

Keys set here are kept **only for the current session** — they are never
written to disk unless the user explicitly asks to save them to ``.env``.

Fallback hierarchy (highest precedence first):

1. In-memory keychain  (``set_key()`` or interactive ``/key set``)
2. Environment variable (e.g. ``OPENAI_API_KEY``)
3. ``SDK_FALLBACK_KEY`` environment variable
4. ``_FALLBACK_API_KEY`` constant (compile-time fallback — see below)
"""

from __future__ import annotations

import os

_keys: dict[str, str] = {}

# ═══════════════════════════════════════════════════════════════════════════
# Built-in fallback API key  (lowest-priority fallback)
# ═══════════════════════════════════════════════════════════════════════════
#
# Set this to a demo / trial key so the tool works out-of-the-box.
# Users should replace this with their own key for production use.
#
# You can also set the ``SDK_FALLBACK_KEY`` environment variable at runtime
# to override this constant without modifying the source code.
#
# Examples:
#   set SDK_FALLBACK_KEY=sk-your-key-here
#   export SDK_FALLBACK_KEY=sk-your-key-here
# ═══════════════════════════════════════════════════════════════════════════

_FALLBACK_API_KEY: str | None = None
"""Compile-time fallback key.  Override this value in source or set the
``SDK_FALLBACK_KEY`` env var at runtime to provide a built-in fallback
that lets the tool work without any user configuration."""


def _get_fallback() -> str | None:
    """Return the effective fallback key: env var → source constant."""
    return os.environ.get("SDK_FALLBACK_KEY") or _FALLBACK_API_KEY


def set_key(name: str, value: str) -> None:
    """Store an API key in memory for the current session.

    Also sets the corresponding ``os.environ`` variable so that any
    downstream library (e.g. ``openai``) can find it without changes.
    """
    _keys[name] = value
    os.environ[name] = value


def get_key(name: str) -> str | None:
    """Return an API key with the fallback hierarchy:

    1. In-memory keychain (``set_key()``)
    2. Environment variable *name*
    3. ``SDK_FALLBACK_KEY`` env var / ``_FALLBACK_API_KEY`` constant
    """
    if name in _keys:
        return _keys[name]
    val = os.environ.get(name)
    if val:
        return val
    # Lowest-priority fallback
    return _get_fallback()


def has_key(name: str) -> bool:
    """Return ``True`` if a key is available (keychain, env var, or fallback)."""
    return get_key(name) is not None and len(get_key(name)) > 0


def list_keys() -> list[str]:
    """Return the names of all keys currently stored in the keychain."""
    return sorted(_keys.keys())


def clear_keys() -> None:
    """Remove all keys from the in-memory store (session end / reset)."""
    _keys.clear()
