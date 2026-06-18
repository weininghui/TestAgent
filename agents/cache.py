"""Content-hash based LLM result cache with disk persistence."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LLMCache:
    """
    Disk-persisted LLM result cache.
    Cache key = SHA256 hash of (model + prompt + temperature + tools signature).
    Cache location: {cache_dir}/ (default: output/cache/)
    """

    def __init__(self, cache_dir: str = "output/cache", enabled: bool = True):
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        if enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _make_key(self, model: str, prompt: str, temperature: float, tools_sig: str = "") -> str:
        """Generate SHA256 cache key from call parameters."""
        raw = f"{model}|{prompt}|{temperature}|{tools_sig}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _key_path(self, key: str) -> Path:
        """Return filesystem path for a cache key."""
        # Use subdirectories to avoid too many files in one dir
        subdir = key[:2]
        return self.cache_dir / subdir / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve cached result. Returns None on miss."""
        if not self.enabled:
            return None
        path = self._key_path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Check expiry (default: 7 days)
            cached_at = data.get("_cached_at", 0)
            if time.time() - cached_at > 604800:  # 7 days
                path.unlink(missing_ok=True)
                return None
            return data.get("value")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Cache read error for key %s: %s", key[:8], e)
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        """Store result in cache."""
        if not self.enabled:
            return
        path = self._key_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "value": value,
            "_cached_at": time.time(),
            "_key": key,
        }
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("Cache write error for key %s: %s", key[:8], e)

    def make_and_get(self, model: str, prompt: str, temperature: float, tools_sig: str = "") -> dict[str, Any] | None:
        """Convenience: make key and get in one call."""
        key = self._make_key(model, prompt, temperature, tools_sig)
        return self.get(key)

    def make_and_set(self, model: str, prompt: str, temperature: float, value: dict[str, Any], tools_sig: str = "") -> None:
        """Convenience: make key and set in one call."""
        key = self._make_key(model, prompt, temperature, tools_sig)
        self.set(key, value)

    def invalidate(self, pattern: str = "") -> int:
        """Clear cache entries matching pattern (empty = clear all). Returns count cleared."""
        count = 0
        if not self.cache_dir.exists():
            return 0
        for root, _dirs, files in os.walk(str(self.cache_dir)):
            for f in files:
                if f.endswith(".json"):
                    if not pattern or pattern in f:
                        try:
                            (Path(root) / f).unlink()
                            count += 1
                        except OSError:
                            pass
        logger.info("Cache invalidated: %d entries removed (pattern=%r)", count, pattern)
        return count

    def clear(self) -> None:
        """Wipe entire cache directory."""
        if self.cache_dir.exists():
            import shutil
            shutil.rmtree(str(self.cache_dir))
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Cache cleared: %s", self.cache_dir)
