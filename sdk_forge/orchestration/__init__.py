"""Orchestration layer — workflow state, stage planning, and autopilot."""

import importlib as _importlib


def __getattr__(name: str):
    mod = _importlib.import_module("sdk_forge.orchestration.core")
    return getattr(mod, name)


def __dir__() -> list[str]:
    mod = _importlib.import_module("sdk_forge.orchestration.core")
    return sorted(set(dir(mod)))
