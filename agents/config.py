#!/usr/bin/env python3
"""Pipeline configuration — pure Python dataclass, no YAML."""

from __future__ import annotations

import dataclasses
import os


@dataclasses.dataclass(frozen=True)
class PipelineConfig:
    """Immutable pipeline settings.

    Defaults are suitable for most local runs; override via CLI flags.
    """

    sdk_root: str = ""
    output_root: str = "./output"
    build_dir: str = "build"
    log_level: str = "INFO"
    no_cache: bool = False
    llm_enabled: bool = False
    model: str = "default"

    def as_dict(self) -> dict[str, object]:
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
        return cls(
            sdk_root=str(d.get("sdk_root", "")),
            output_root=str(d.get("output_root", "./output")),
            build_dir=str(d.get("build_dir", "build")),
            log_level=str(d.get("log_level", "INFO")),
            no_cache=bool(d.get("no_cache", False)),
            llm_enabled=bool(d.get("llm_enabled", False)),
            model=str(d.get("model", "default")),
        )

    @classmethod
    def from_env(cls) -> PipelineConfig:
        return cls(
            sdk_root=os.environ.get("SDK_ROOT", ""),
            output_root=os.environ.get("SDK_OUTPUT_ROOT", "./output"),
            build_dir=os.environ.get("SDK_BUILD_DIR", "build"),
            log_level=os.environ.get("SDK_LOG_LEVEL", "INFO"),
            no_cache=bool(os.environ.get("SDK_NO_CACHE", "")),
            llm_enabled=bool(os.environ.get("SDK_LLM_ENABLED", "")),
            model=os.environ.get("SDK_MODEL", "default"),
        )
