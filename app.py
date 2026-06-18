#!/usr/bin/env python3
"""SciVision LangChain Pipeline — CLI entry point.

All configuration is handled via Python modules:
    ``agents/models.py``   — LLM model presets
    ``agents/config.py``   — Pipeline settings (``sdk_root``, ``output_root``, …)
    CLI flags              — Override individual settings at runtime

Usage
-----
    python app.py                                          # full pipeline (longcat)
    python app.py --model dashscope                        # use DashScope model
    python app.py --dry-run                                # print stages, no LLM calls
    python app.py --stage scanner                          # run one stage only
    python app.py --sdk-root /path/to/sdk --no-cache       # custom SDK, no cache
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from agents.config import PipelineConfig
from agents.memory import PipelineMemory
from agents.models import get_llm, list_models
from agents.pipeline import Pipeline

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

STAGE_CHOICES = ["scanner", "analysis", "test_design", "code_gen", "ci_gen", "report"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SciVision LangChain Pipeline — SDK test generation via LLM agents.",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="longcat",
        choices=list_models(),
        help=f"LLM model preset (default: longcat). Choices: {', '.join(list_models())}.",
    )
    parser.add_argument(
        "--sdk-root",
        type=str,
        default="",
        help="SDK root directory (overrides PipelineConfig default).",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default="",
        help="Output root directory (overrides PipelineConfig default).",
    )
    parser.add_argument(
        "--build-dir",
        type=str,
        default="",
        help="Build directory name (overrides PipelineConfig default).",
    )
    parser.add_argument(
        "--llm-enabled",
        action="store_true",
        help="Enable LLM pipeline mode.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable LLM response caching.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print pipeline stages without executing.",
    )
    parser.add_argument(
        "--stage",
        type=str,
        choices=STAGE_CHOICES,
        default=None,
        help="Run a single pipeline stage only (scanner, analysis, test_design, "
        "code_gen, ci_gen, report).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging (DEBUG level).",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Build config from Python defaults + CLI overrides
# ---------------------------------------------------------------------------


def _build_config(args: argparse.Namespace) -> PipelineConfig:
    """Merge ``PipelineConfig`` defaults with CLI overrides."""
    d: dict[str, object] = {}

    if args.sdk_root:
        d["sdk_root"] = args.sdk_root
    if args.output_root:
        d["output_root"] = args.output_root
    if args.build_dir:
        d["build_dir"] = args.build_dir
    if args.no_cache:
        d["no_cache"] = True
    if args.llm_enabled:
        d["llm_enabled"] = True

    # Model name is always set from the CLI flag (default: "longcat")
    d["model"] = args.model

    return PipelineConfig.from_dict(d)


# ---------------------------------------------------------------------------
# Stage input builder  (for ``--stage`` single-stage mode)
# ---------------------------------------------------------------------------


def _build_stage_inputs(
    stage: str,
    memory: PipelineMemory,
    config: PipelineConfig,
) -> dict:
    """Construct the keyword-arguments dict for ``Pipeline.run_stage()``."""
    if stage == "scanner":
        return {"sdk_root": config.sdk_root}

    if stage == "analysis":
        return {"inventory": memory.get_stage_output("scanner")}

    if stage == "test_design":
        return {
            "inventory": memory.get_stage_output("scanner"),
            "analysis": memory.get_stage_output("analysis"),
        }

    if stage == "code_gen":
        return {"test_collection": memory.get_stage_output("test_design")}

    if stage == "ci_gen":
        return {
            "inventory": memory.get_stage_output("scanner"),
            "test_collection": memory.get_stage_output("test_design"),
        }

    if stage == "report":
        return {
            "memory": memory,
            "output_root": config.output_root,
        }

    raise ValueError(f"Unknown stage: {stage}")


# ---------------------------------------------------------------------------
# Header printer
# ---------------------------------------------------------------------------


def _print_header(cfg: PipelineConfig) -> None:
    """Log a readable summary of the pipeline configuration."""
    logger.info("=" * 60)
    logger.info("SciVision LangChain Pipeline")
    logger.info("=" * 60)
    logger.info("Model preset : %s", cfg.model)
    logger.info("SDK root     : %s", cfg.sdk_root or "(not set)")
    logger.info("Output root  : %s", cfg.output_root)
    logger.info("Cache        : %s", "disabled" if cfg.no_cache else "enabled")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns
    -------
    int
        ``0`` on success, ``1`` on pipeline/config error, ``130`` on
        ``KeyboardInterrupt`` (Ctrl+C).
    """
    args = parse_args(argv)

    # -- Logging -----------------------------------------------------------
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

    # -- Build config from Python defaults + CLI overrides -----------------
    cfg = _build_config(args)

    if not cfg.sdk_root:
        logger.error(
            "SDK root not set. Use ``--sdk-root <path>`` or set a default "
            "in ``agents/config.py`` (:class:`PipelineConfig`)."
        )
        return 1

    # -- Initialise LLM wrapper (from model preset) ------------------------
    try:
        llm = get_llm(args.model)
    except Exception as e:
        logger.error("LLM initialisation failed: %s", e, exc_info=True)
        return 1

    # -- Initialise pipeline -----------------------------------------------
    try:
        pipeline = Pipeline(llm=llm, config=cfg.as_dict())
    except Exception as e:
        logger.error("Pipeline initialisation failed: %s", e, exc_info=True)
        return 1

    # ====== Dry-run mode ==================================================
    if args.dry_run:
        pipeline.dry_run()
        return 0

    # ====== Single-stage mode =============================================
    if args.stage:
        logger.info("Running single stage: %s", args.stage)

        memory = PipelineMemory(
            persist_path=os.path.join(
                cfg.output_root,
                "pipeline_memory.json",
            ),
        )
        loaded = memory.load_from_disk()
        if loaded:
            logger.info("Loaded prior stage outputs from disk")
        else:
            logger.info("No prior stage outputs found on disk")

        inputs = _build_stage_inputs(args.stage, memory, cfg)
        try:
            pipeline.run_stage(args.stage, inputs)
        except Exception as e:
            logger.error(
                "Stage '%s' failed: %s: %s",
                args.stage,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return 1

        logger.info("Stage '%s' completed successfully", args.stage)
        return 0

    # ====== Full pipeline mode ============================================
    _print_header(cfg)

    try:
        results = pipeline.run()
    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user (Ctrl+C)")
        return 130
    except Exception as e:
        logger.error(
            "Pipeline execution failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
        )
        return 1

    logger.info("Pipeline completed: %d stages executed", len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
