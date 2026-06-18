"""SDK Scanner Chain — LangChain agent for discovering and analysing SDK header files.

Uses an LLM to extract a structured ``APIInventory`` from C/C++ ``.h`` files
found under an SDK root directory.  Handles batching for large SDKs, retry with
escalating instructions on parse failures, and caching of LLM responses.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.prompts import PromptTemplate

from ir.api_schema import APIInventory, ModuleInfo
from agents.llm import LLMWrapper
from agents.tools.sdk_tools import list_header_files, read_header_file
from agents.prompts.scanner_prompt import SYSTEM_PROMPT, HUMAN_TEMPLATE
from agents.cache import LLMCache

logger = logging.getLogger(__name__)


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences and leading/trailing whitespace from LLM output.

    The system prompt asks for pure JSON, but some LLMs still wrap output
    in ```json … ``` fences.  This helper normalises the text so downstream
    ``json.loads`` does not choke.
    """
    text = text.strip()
    # Remove leading ```json or ``` (possibly with language hint)
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline:].strip()
    # Remove trailing ```
    if text.endswith("```"):
        text = text[:-3].strip()
    # Defensive: also strip a second round of unmarked fences
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def _merge_inventories(sdk_root: str, inventories: list[APIInventory]) -> APIInventory:
    """Merge multiple partial ``APIInventory`` results into one.

    When an SDK is too large to fit in a single LLM call, each batch produces a
    separate ``APIInventory``.  This function merges them by deduplicating
    ``ModuleInfo`` entries (matched by ``module_id``) and extending their header
    lists.
    """
    merged = APIInventory(sdk_root=sdk_root)
    seen: dict[str, ModuleInfo] = {}

    for inv in inventories:
        for mod in inv.modules:
            existing = seen.get(mod.module_id)
            if existing is not None:
                # Merge headers — avoid duplicates by header_id
                seen_header_ids = {h.header_id for h in existing.headers}
                for h in mod.headers:
                    if h.header_id not in seen_header_ids:
                        existing.headers.append(h)
                        seen_header_ids.add(h.header_id)
            else:
                seen[mod.module_id] = mod

    merged.modules = list(seen.values())
    return merged


class SDKScannerChain:
    """Scan SDK headers and produce a structured ``APIInventory`` via LLM extraction.

    The chain follows this high-level flow:

    1. **Discover** – enumerate all ``.h`` files under ``sdk_root`` (and optional
       extra ``include_dirs``).
    2. **Batch** – if the total exceeds 50 headers, split into groups of 20.
       If it exceeds 100, use an extra summary-merge pass.
    3. **Read** – load every header in the current batch (skipping files that
       fail to read with a logged warning).
    4. **Prompt** – build a structured prompt with all header content and send
       it to the LLM.
    5. **Parse** – deserialise the LLM's JSON response into ``APIInventory``.
       Retry with escalating instruction on parse failure.
    6. **Merge** – combine per-batch inventories into a single result.
    """

    #: Default batch size — keeps prompt token counts manageable.
    BATCH_SIZE: int = 20

    #: Headers above this threshold trigger the large-SDK code path
    #: (which adds a summary-merge pass).
    LARGE_SDK_THRESHOLD: int = 100

    #: Max retry attempts when the LLM response cannot be parsed as JSON.
    MAX_RETRIES: int = 2

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------
    def __init__(
        self,
        llm: LLMWrapper,
        tools: list[Any],
        prompt: PromptTemplate = HUMAN_TEMPLATE,
    ) -> None:
        """Initialise the scanner chain.

        Args:
            llm: An ``LLMWrapper`` instance used for all LLM invocations.
            tools: A list of LangChain ``Tool`` objects (specifically the
                SDK tools from ``agents.tools.sdk_tools``).  The chain also
                imports the underlying functions directly for convenience.
            prompt: A ``PromptTemplate`` instance whose ``input_variables``
                include ``sdk_root``, ``header_files``, and ``header_content``.
                Defaults to ``HUMAN_TEMPLATE`` from ``scanner_prompt``.
        """
        self.llm = llm
        self.tools = tools
        self.prompt = prompt
        self.cache = LLMCache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(
        self,
        sdk_root: str,
        include_dirs: list[str] | None = None,
    ) -> APIInventory:
        """Discover headers and extract a structured API inventory.

        Args:
            sdk_root: Absolute filesystem path to the SDK root directory.
            include_dirs: Optional list of subdirectory names (relative to
                ``sdk_root``) to search for header files in addition to the
                default ``include/`` directory.

        Returns:
            A populated ``APIInventory`` instance.

        Raises:
            RuntimeError: If all retries are exhausted without a valid LLM
                response.
        """
        # Step 1 — discover headers
        header_paths = self._discover_headers(sdk_root, include_dirs)
        if not header_paths:
            logger.info("No header files found under sdk_root=%s", sdk_root)
            return APIInventory(sdk_root=sdk_root)

        logger.info(
            "Discovered %d header file(s) under sdk_root=%s",
            len(header_paths),
            sdk_root,
        )

        # Step 2 — determine batching strategy
        if len(header_paths) <= self.BATCH_SIZE:
            return self._process_batch(sdk_root, header_paths)

        # Large SDK — batch + merge
        return self._run_batched(sdk_root, header_paths)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _discover_headers(
        self,
        sdk_root: str,
        include_dirs: list[str] | None = None,
    ) -> list[str]:
        """Enumerate all ``.h`` files reachable from *sdk_root*.

        Uses the :func:`list_header_files` tool for the default ``include/``
        directory and additionally searches any extra *include_dirs*.
        """
        discovered: list[str] = list_header_files.invoke({"sdk_root": sdk_root})

        if include_dirs:
            for subdir in include_dirs:
                search_path = Path(sdk_root) / subdir
                if not search_path.exists() or not search_path.is_dir():
                    logger.debug("Include dir '%s' does not exist, skipping", search_path)
                    continue
                for h_path in sorted(search_path.rglob("*.h")):
                    if h_path.is_file():
                        resolved = str(h_path.resolve(strict=False))
                        if resolved not in discovered:
                            discovered.append(resolved)

        return sorted(set(discovered))

    def _read_batch(
        self,
        sdk_root: str,
        header_paths: list[str],
    ) -> dict[str, str]:
        """Read the content of every header in *header_paths*.

        Files that fail to read (permission, encoding, or not-found errors) are
        skipped with a warning — the chain degrades gracefully.
        """
        contents: dict[str, str] = {}
        for path in header_paths:
            try:
                content = read_header_file.invoke({"file_path": path, "sdk_root": sdk_root})
                contents[path] = content
            except FileNotFoundError:
                logger.warning("Header file not found (skipping): %s", path)
            except PermissionError:
                logger.warning("Permission denied (skipping): %s", path)
            except UnicodeDecodeError:
                logger.warning("Non-UTF-8 encoding (skipping): %s", path)
            except ValueError as exc:
                logger.warning("Invalid header path (skipping): %s — %s", path, exc)
            except Exception as exc:
                logger.warning(
                    "Unexpected error reading header (skipping): %s — %s",
                    path,
                    exc,
                )
        return contents

    def _build_prompt(
        self,
        sdk_root: str,
        header_paths: list[str],
        contents: dict[str, str],
    ) -> str:
        """Build the user-side prompt for the current batch.

        Concatenates header contents with file-path markers so the LLM can
        correlate symbols to their source files.
        """
        header_files_str = "\n".join(header_paths)

        # Build a readable concatenation of all header content
        content_parts: list[str] = []
        for path in header_paths:
            text = contents.get(path, "")
            marker = f"=== {path} ==="
            content_parts.append(f"{marker}\n{text}")

        header_content_str = "\n\n".join(content_parts)

        return self.prompt.format(
            sdk_root=sdk_root,
            header_files=header_files_str,
            header_content=header_content_str,
        )

    def _parse_response(self, response_text: str) -> APIInventory:
        """Parse the LLM's JSON response into an ``APIInventory``.

        Cleans markdown fences from the text, deserialises JSON, and
        constructs the dataclass tree via ``APIInventory.from_dict()``.

        Raises:
            json.JSONDecodeError: If the response is not valid JSON.
            KeyError / TypeError: If the JSON structure does not match the
                expected schema.
        """
        cleaned = _clean_json_response(response_text)
        data: dict[str, Any] = json.loads(cleaned)
        return APIInventory.from_dict(data)

    def _process_batch(
        self,
        sdk_root: str,
        header_paths: list[str],
    ) -> APIInventory:
        """Process a single batch of header files through the LLM.

        1. Read all headers in the batch.
        2. Build a prompt with their contents.
        3. Invoke the LLM.
        4. Parse the response.
        5. Retry up to ``MAX_RETRIES`` times on parse failures.
        """
        # Read batch contents
        contents = self._read_batch(sdk_root, header_paths)
        if not contents:
            logger.warning("All headers in batch failed to read — returning empty inventory")
            return APIInventory(sdk_root=sdk_root)

        # Build messages
        user_prompt = self._build_prompt(sdk_root, header_paths, contents)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Invoke with retry
        last_exception: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self.llm.invoke(messages)
                inventory = self._parse_response(response)
                logger.info(
                    "Batch processed successfully: %d modules, %d headers",
                    len(inventory.modules),
                    len(header_paths),
                )
                return inventory
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                last_exception = exc
                logger.warning(
                    "LLM response parse failed (attempt %d/%d): %s",
                    attempt,
                    self.MAX_RETRIES,
                    exc,
                )
                if attempt < self.MAX_RETRIES:
                    # Append escalating instruction for the retry
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your previous response was **not** valid JSON matching "
                            "the required APIInventory schema.  Return ONLY a single "
                            "valid JSON object conforming to the schema above — no "
                            "markdown fences, no commentary, no extra text."
                        ),
                    })

        # All retries exhausted
        raise RuntimeError(
            f"Failed to obtain a valid LLM response after {self.MAX_RETRIES} "
            f"retries.  Last error: {last_exception}"
        )

    def _run_batched(
        self,
        sdk_root: str,
        header_paths: list[str],
    ) -> APIInventory:
        """Process a large SDK by splitting headers into batches and merging.

        For extremely large SDKs (``> LARGE_SDK_THRESHOLD``), after all batch
        inventories are collected, a final summary LLM call is made to
        reconcile cross-module references if needed.
        """
        inventories: list[APIInventory] = []

        for i in range(0, len(header_paths), self.BATCH_SIZE):
            batch = header_paths[i : i + self.BATCH_SIZE]
            logger.info(
                "Processing batch %d/%d (%d headers)",
                i // self.BATCH_SIZE + 1,
                (len(header_paths) + self.BATCH_SIZE - 1) // self.BATCH_SIZE,
                len(batch),
            )
            batch_inv = self._process_batch(sdk_root, batch)
            inventories.append(batch_inv)

        merged = _merge_inventories(sdk_root, inventories)

        # For very large SDKs, do an extra summary-merge pass to reconcile
        # cross-module references that span batches.
        if len(header_paths) > self.LARGE_SDK_THRESHOLD:
            merged = self._summarise_merge(sdk_root, merged, inventories)

        logger.info(
            "Batched processing complete: %d modules across %d headers",
            len(merged.modules),
            len(header_paths),
        )
        return merged

    def _summarise_merge(
        self,
        sdk_root: str,
        preliminary: APIInventory,
        _batch_inventories: list[APIInventory],
    ) -> APIInventory:
        """Optional LLM pass that reconciles cross-batch module data.

        For SDKs with ``> LARGE_SDK_THRESHOLD`` headers, individual batches
        may produce modules with incomplete cross-references (e.g. a function
        in batch 1 references a type defined in batch 3).  This method sends
        a summary of all discovered modules to the LLM for reconciliation.

        If the LLM call fails, the preliminary merge is returned as-is
        (graceful degradation).
        """
        # Build a compact summary of what each module contains
        summary_lines: list[str] = []
        for mod in preliminary.modules:
            header_count = len(mod.headers)
            func_count = sum(len(h.functions) for h in mod.headers)
            class_count = sum(len(h.classes) for h in mod.headers)
            enum_count = sum(len(h.enums) for h in mod.headers)
            summary_lines.append(
                f"Module '{mod.name}' ({mod.module_id}): "
                f"{header_count} headers, {func_count} functions, "
                f"{class_count} classes, {enum_count} enums"
            )

        summary_text = "\n".join(summary_lines)

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are an SDK deduplication and reconciliation engine. "
                    "You are given a preliminary inventory of C/C++ API modules "
                    "extracted from header files.  Your job is to:\n"
                    "1. Merge any modules that were split across batches.\n"
                    "2. Ensure each module has a coherent set of headers.\n"
                    "3. Return exactly the same JSON structure as the original "
                    "APIInventory schema.\n\n"
                    "Return ONLY valid JSON — no markdown fences, no commentary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"SDK Root: {sdk_root}\n\n"
                    f"Preliminary module summary:\n{summary_text}\n\n"
                    f"Full preliminary inventory (JSON):\n"
                    f"{preliminary.to_json(indent=2)}"
                ),
            },
        ]

        try:
            response = self.llm.invoke(messages)
            return self._parse_response(response)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "Summary-merge LLM call failed, using preliminary merge: %s",
                exc,
            )
            return preliminary
