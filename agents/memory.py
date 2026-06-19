"""Cross-stage pipeline memory for passing context between LangChain agents."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PipelineMemory:
    """
    Stores and retrieves outputs from each pipeline stage.
    Provides LLM-friendly context summaries for the next stage.
    Persists to disk for debugging and resumability.
    """

    def __init__(self, persist_path: str = "output/pipeline_memory.json"):
        self._stages: dict[str, dict[str, Any]] = {}
        self._stage_order: list[str] = []
        self.persist_path = Path(persist_path)

    def store_stage_output(self, stage_name: str, output: Any) -> None:
        """Save a stage's output."""
        entry = {
            "stage": stage_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output": output,
        }
        self._stages[stage_name] = entry
        if stage_name not in self._stage_order:
            self._stage_order.append(stage_name)
        self._persist()
        key_count: int = (
            len(output)
            if isinstance(output, dict)
            else (output if isinstance(output, (int, float)) else 0)
        )
        logger.info("PipelineMemory: stored stage '%s' (%d keys)", stage_name, key_count)

    def get_stage_output(self, stage_name: str) -> dict[str, Any] | None:
        """Retrieve a specific stage's output dict, or None if not found."""
        entry = self._stages.get(stage_name)
        return entry["output"] if entry else None

    def get_all_outputs(self) -> dict[str, dict[str, Any]]:
        """Get all stage outputs keyed by stage name (for report generation)."""
        return {name: entry["output"] for name, entry in self._stages.items()}

    def get_stage_order(self) -> list[str]:
        """Return stages in execution order."""
        return list(self._stage_order)

    def clear(self) -> None:
        """Clear all stored memory."""
        self._stages.clear()
        self._stage_order.clear()
        self._persist()
        logger.info("PipelineMemory: cleared")

    def summarize_for_next_stage(self, next_stage: str) -> str:
        """
        Generate an LLM-friendly context string from all prior stages.
        Used to inform the next chain about what previous stages produced.
        """
        if not self._stages:
            return "No prior stage outputs available."

        parts: list[str] = []
        for stage_name in self._stage_order:
            entry = self._stages[stage_name]
            output = entry["output"]
            # Summarize concisely
            summary = self._summarize_output(stage_name, output)
            parts.append(f"=== {stage_name} ===\n{summary}")

        parts.append(f"\n---\nNext stage to execute: {next_stage}")
        return "\n\n".join(parts)

    @staticmethod
    def _summarize_output(stage_name: str, output: dict[str, Any]) -> str:
        """Create a concise summary of a stage's output for LLM context."""
        lines: list[str] = []
        if isinstance(output, dict):
            for key, value in output.items():
                if isinstance(value, list):
                    lines.append(f"- {key}: {len(value)} items")
                    if value and len(value) > 0:
                        # Show first item as example
                        first = value[0]
                        if isinstance(first, dict):
                            lines.append(f"  Example: {json.dumps(first, ensure_ascii=False)[:200]}")
                        else:
                            lines.append(f"  First: {str(first)[:200]}")
                elif isinstance(value, dict):
                    lines.append(f"- {key}: dict with {len(value)} keys")
                elif isinstance(value, str) and len(value) > 100:
                    lines.append(f"- {key}: {value[:100]}...")
                else:
                    lines.append(f"- {key}: {value}")
        else:
            lines.append(str(output)[:500])
        return "\n".join(lines) if lines else "(empty)"

    def _persist(self) -> None:
        """Write memory to disk for debugging and resumability."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            self.persist_path.write_text(
                json.dumps(self._stages, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("PipelineMemory persist error: %s", e)

    def load_from_disk(self) -> bool:
        """Load persisted memory from disk. Returns True if data was loaded."""
        if not self.persist_path.exists():
            return False
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            self._stages = data
            self._stage_order = list(data.keys())
            logger.info("PipelineMemory: loaded %d stages from disk", len(self._stages))
            return True
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("PipelineMemory load error: %s", e)
            return False
