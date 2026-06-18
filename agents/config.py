#!/usr/bin/env python3
"""Pipeline configuration — pure Python dataclass, no YAML."""

from __future__ import annotations

import dataclasses
import os


@dataclasses.dataclass(frozen=True)
class PipelineConfig:
    """Immutable pipeline settings.

    Defaults are suitable for most local runs; override via CLI flags
    (``--sdk-root``, ``--output-root``, etc.).
    """

    #: Absolute path to the SDK root directory (the directory scanned for
    #: ``.h`` header files).
    sdk_root: str = ""

    #: Directory for generated test code, reports, and cache files.
    output_root: str = "./output"

    #: Build directory (relative to *output_root* or absolute).
    build_dir: str = "build"

    #: Logging verbosity (``"DEBUG"``, ``"INFO"``, ``"WARNING"``, …).
    log_level: str = "INFO"

    #: Disable LLM call caching (useful during prompt development).
    no_cache: bool = False

    #: Enable LLM pipeline mode (otherwise stages are no-ops).
    llm_enabled: bool = False

    #: Short name of the LLM model preset (used for display; actual
    #: model config lives in ``agents/models.py``).
    model: str = "longcat"

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    def as_dict(self) -> dict[str, object]:
        """Return a plain dictionary consumable by ``Pipeline.__init__``."""
        return {
            "sdk_root": self.sdk_root,
            "output_root": self.output_root,
            "build_dir": self.build_dir,
            "log_level": self.log_level,
            "no_cache": self.no_cache,
            "llm_enabled": self.llm_enabled,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> PipelineConfig:
        """Construct from a dictionary (e.g. parsed from environment)."""
        return cls(
            sdk_root=str(d.get("sdk_root", "")),
            output_root=str(d.get("output_root", "./output")),
            build_dir=str(d.get("build_dir", "build")),
            log_level=str(d.get("log_level", "INFO")),
            no_cache=bool(d.get("no_cache", False)),
            llm_enabled=bool(d.get("llm_enabled", False)),
            model=str(d.get("model", "longcat")),
        )

    # ------------------------------------------------------------------
    # Env-var convenience (optional — not used by app.py today)
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> PipelineConfig:
        """Read settings from environment variables with ``SDK_`` prefix.

        Examples
        --------
        ``SDK_ROOT=/opt/sdk``, ``SDK_OUTPUT_ROOT=./out``,
        ``SDK_LOG_LEVEL=DEBUG``, ``SDK_NO_CACHE=1``.
        """
        return cls(
            sdk_root=os.environ.get("SDK_ROOT", ""),
            output_root=os.environ.get("SDK_OUTPUT_ROOT", "./output"),
            build_dir=os.environ.get("SDK_BUILD_DIR", "build"),
            log_level=os.environ.get("SDK_LOG_LEVEL", "INFO"),
            no_cache=bool(os.environ.get("SDK_NO_CACHE", "")),
            llm_enabled=bool(os.environ.get("SDK_LLM_ENABLED", "")),
            model=os.environ.get("SDK_MODEL", "longcat"),
        )
