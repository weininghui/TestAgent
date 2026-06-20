"""Delegation layer — task() tracking, dispatch plans, and session navigation."""

import importlib as _importlib


def __getattr__(name: str):
    mod = _importlib.import_module("sdk_forge.delegation.core")
    return getattr(mod, name)


def __dir__() -> list[str]:
    mod = _importlib.import_module("sdk_forge.delegation.core")
    return sorted(set(dir(mod)))
