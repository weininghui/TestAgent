"""Pipeline layer — scan, plan, scaffold, enrich, build, and test execution."""

import importlib as _importlib


def __getattr__(name: str):
    mod = _importlib.import_module("sdk_forge.pipeline.core")
    return getattr(mod, name)


def __dir__() -> list[str]:
    mod = _importlib.import_module("sdk_forge.pipeline.core")
    return sorted(set(dir(mod)))
