"""CI/CD Config Generator Chain — generates CMakeLists.txt and GitHub Actions
workflow files for compiling and running GTest tests using an LLM.

Takes an ``APIInventory`` (from the scanner stage) and a
``TestCaseCollection`` (from the test-design stage) and produces:

- ``CMakeLists.txt`` — CMake project that fetches GTest and builds a
  single test executable from all generated ``.cc`` files.
- ``.github/workflows/ci.yml`` — GitHub Actions workflow that installs
  build tools, configures with CMake, builds, and runs tests.
- (optionally) ``CMakePresets.json`` — CMake presets for Ninja.

The chain handles edge cases such as zero test cases (minimal framework
check) and multiple SDK modules (proper ``target_link_libraries``).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.prompts import PromptTemplate

from schemas.api_schema import APIInventory
from schemas.testcase_schema import TestCaseCollection
from agents.llm import LLMWrapper
from agents.tools.code_gen_tools import (
    ensure_output_dir,
    raw_write_cmake_file as write_cmake_file,
    raw_write_workflow_file as write_workflow_file,
)
from agents.prompts import PromptBuilder
from agents.prompts.ci_gen_prompt import HUMAN_TEMPLATE, SYSTEM_PROMPT
from agents.cache import LLMCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OUTPUT_ROOT: str = "output"
"""Default output root directory for generated CI files."""

_DEFAULT_PROJECT: str = "TestProject"
"""Fallback project name when no modules exist and SDK root is empty."""

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences and leading/trailing whitespace from LLM
    output.

    The system prompt asks for pure JSON, but some LLMs still wrap output
    in `````json … ````` fences.  This helper normalises the text so
    downstream ``json.loads`` does not choke.
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


# ---------------------------------------------------------------------------
# CI/CD Config Generator Chain
# ---------------------------------------------------------------------------


class CIGenChain:
    """Generate CI/CD configuration files for GTest-based test suites.

    The chain follows this flow:

    1. **Derive** — extract a project name and module structure from
       ``inventory``, and a formatted test file list from
       ``test_collection``.
    2. **Prompt** — build a structured prompt with test metadata and send
       it to the LLM.
    3. **Parse** — deserialise the LLM's JSON response (expected to match
       ``{ "files": { "CMakeLists.txt": "...", ".github/workflows/ci.yml":
       "..." }, "notes": [...] }``).
    4. **Write** — create all generated files on disk using the
       ``write_cmake_file`` and ``write_workflow_file`` tools.
    5. **Return** — the absolute path to the output directory.
    """

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
        cache: LLMCache | None = None,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        """Initialise the CI/CD config generator chain.

        Args:
            llm: An ``LLMWrapper`` instance used for all LLM invocations.
            tools: A list of LangChain ``Tool`` objects (specifically the
                code-gen tools from ``agents.tools.code_gen_tools``).  The
                chain also imports the underlying functions directly for
                convenience.
            prompt: A ``PromptTemplate`` instance whose ``input_variables``
                include ``test_files`` and ``project_name``.  Defaults to
                ``HUMAN_TEMPLATE`` from ``ci_gen_prompt``.
            cache: Optional ``LLMCache`` for caching generated configs
                keyed by inventory + test-collection content hash.
        """
        self.llm = llm
        self.tools = tools
        self.prompt = prompt
        self.cache = cache
        self.prompt_builder = prompt_builder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        inventory: APIInventory,
        test_collection: TestCaseCollection,
    ) -> str:
        """Generate CI/CD config files for the given SDK and test suite.

        Args:
            inventory: The ``APIInventory`` produced by the scanner stage.
                Used to derive the project name and module structure for
                proper ``target_link_libraries`` generation.
            test_collection: The ``TestCaseCollection`` produced by the
                test-design stage.  Used to enumerate generated ``.cc``
                files and their test metadata.

        Returns:
            Absolute path to the output directory containing the generated
            files (``CMakeLists.txt``, ``.github/workflows/ci.yml``, and
            optionally ``CMakePresets.json``).

        Raises:
            RuntimeError: If all LLM retries are exhausted without a valid
                JSON response.
            OSError: If file writing fails due to permission or disk errors.
        """
        # --- Step 1: Derive project metadata --------------------------------
        project_name = self._derive_project_name(inventory)
        test_files_str = self._format_test_files(test_collection)
        module_summary_str = self._format_module_summary(inventory)

        logger.info(
            "CIGenChain.run: project=%s, test_cases=%d, modules=%d",
            project_name,
            len(test_collection.cases),
            len(inventory.modules),
        )

        # --- Step 2: Edge case — zero test cases ---------------------------
        if not test_collection.cases:
            logger.info("Zero test cases — generating minimal CI config")
            return self._generate_minimal(project_name)

        # --- Step 3: Check cache -------------------------------------------
        cache_key = self._build_cache_key(inventory, test_collection)
        if self.cache is not None:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.info("CI gen cache hit (key=%s…)", cache_key[:12])
                return self._write_files(cached, project_name)

        # --- Step 4: Build messages and invoke LLM -------------------------
        messages = self._build_messages(
            project_name=project_name,
            test_files_str=test_files_str,
            module_summary_str=module_summary_str,
        )

        file_data = self._invoke_with_retry(messages)

        # --- Step 5: Write files to disk -----------------------------------
        output_dir = self._write_files(file_data, project_name)

        # --- Step 6: Update cache ------------------------------------------
        if self.cache is not None:
            self.cache.set(cache_key, file_data)
            logger.debug("CI gen result cached (key=%s…)", cache_key[:12])

        logger.info("CI config generation complete — output: %s", output_dir)
        return output_dir

    # ------------------------------------------------------------------
    # Internal helpers — project name derivation
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_project_name(inventory: APIInventory) -> str:
        """Derive a sensible project name from the inventory.

        Preference order:
        1. First module's ``name`` (most representative).
        2. SDK root directory basename.
        3. ``TestProject`` fallback.
        """
        if inventory.modules:
            return inventory.modules[0].name

        root_path = Path(inventory.sdk_root)
        name = root_path.name
        if name and name != ".":
            return name

        return _DEFAULT_PROJECT

    # ------------------------------------------------------------------
    # Internal helpers — input formatting for the LLM prompt
    # ------------------------------------------------------------------

    @staticmethod
    def _format_test_files(test_collection: TestCaseCollection) -> str:
        """Format test case information for the LLM prompt.

        Produces a structured text block with test file names, categories,
        and metadata so the LLM can generate appropriate CMake entries.
        """
        if not test_collection.cases:
            return "No test cases."

        lines: list[str] = []
        for case in test_collection.cases:
            # Derive a file name from the test_id
            sanitised = case.test_id.replace("::", "_").replace(":", "_")
            file_name = f"test_{sanitised}.cc"
            lines.append(
                f"- {file_name}  "
                f"// {case.test_name}  "
                f"[{case.category}/{case.subtype}]  "
                f"priority={case.priority}  "
                f"fixture={case.needs_fixture}  "
                f"mock={case.needs_mock}  "
                f"assert={case.assertion_type}"
            )

        return "\n".join(lines)

    @staticmethod
    def _format_module_summary(inventory: APIInventory) -> str:
        """Format the module summary for the LLM prompt.

        Provides module-level context so the LLM can generate correct
        ``target_link_libraries`` entries for multi-module SDKs.
        """
        if not inventory.modules:
            return "No SDK modules detected."

        lines: list[str] = []
        for mod in inventory.modules:
            header_count = len(mod.headers)
            function_count = sum(len(h.functions) for h in mod.headers)
            class_count = sum(len(h.classes) for h in mod.headers)
            lines.append(
                f"- {mod.name} (id={mod.module_id}): "
                f"{header_count} headers, "
                f"{function_count} functions, "
                f"{class_count} classes"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers — cache key
    # ------------------------------------------------------------------

    @staticmethod
    def _build_cache_key(
        inventory: APIInventory,
        test_collection: TestCaseCollection,
    ) -> str:
        """Generate a SHA-256 cache key from the combined input data."""
        raw = inventory.to_json() + "\n---\n" + test_collection.to_json()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Internal helpers — LLM message construction
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        project_name: str,
        test_files_str: str,
        module_summary_str: str,
    ) -> list[dict[str, str]]:
        """Build the system + user message list for the LLM call.

        The system prompt (from ``ci_gen_prompt.SYSTEM_PROMPT``) sets the
        LLM's role as a build-and-CI engineer.  The human message (formatted
        via ``self.prompt``) provides the test file list and project name,
        augmented with module context.
        """
        # The base prompt template expects ``test_files`` and ``project_name``.
        # We append module context to ``test_files`` so the LLM has the
        # full picture.
        enriched = (
            f"Test Files:\n{test_files_str}\n\n"
            f"SDK Modules:\n{module_summary_str}"
        )

        human_message = self.prompt.format(
            test_files=enriched,
            project_name=project_name,
        )

        system_content = (
            self.prompt_builder.build_system_only("ci_gen")
            if self.prompt_builder is not None
            else SYSTEM_PROMPT
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": human_message},
        ]

    # ------------------------------------------------------------------
    # Internal helpers — LLM invocation with retry
    # ------------------------------------------------------------------

    def _invoke_with_retry(
        self,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Invoke the LLM and parse the response, with retry on failure.

        Tries up to ``MAX_RETRIES`` times.  On each failure, an escalating
        instruction is appended to guide the LLM toward valid JSON output.
        """
        last_exception: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self.llm.invoke(messages)
                return self._parse_response(response)

            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                last_exception = exc
                logger.warning(
                    "LLM response parse failed (attempt %d/%d): %s",
                    attempt,
                    self.MAX_RETRIES,
                    exc,
                )

                if attempt < self.MAX_RETRIES:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your previous response was **not** valid JSON "
                            "matching the required schema.  Return ONLY a "
                            "single valid JSON object with the 'files' and "
                            "'notes' keys — no markdown fences, no "
                            "commentary, no extra text."
                        ),
                    })

        # All retries exhausted
        raise RuntimeError(
            f"Failed to obtain a valid LLM response after "
            f"{self.MAX_RETRIES} retries.  "
            f"Last error: {last_exception}"
        )

    # ------------------------------------------------------------------
    # Internal helpers — response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response_text: str) -> dict[str, Any]:
        """Parse the LLM's JSON response into a file-data dictionary.

        Expected response format (as defined by the system prompt):

        .. code-block:: json

            {
              "files": {
                "CMakeLists.txt": "... full CMake content ...",
                ".github/workflows/ci.yml": "... full workflow YAML ...",
                "CMakePresets.json": "... full preset JSON ..."
              },
              "notes": [
                "Update SDK_INCLUDE_DIRS ...",
                "Install Ninja via: choco install ninja"
              ]
            }

        Args:
            response_text: Raw text from the LLM, possibly with markdown
                code fences.

        Returns:
            Dictionary with keys ``files`` (dict of path → content) and
            ``notes`` (list of strings).

        Raises:
            json.JSONDecodeError: If the response is not valid JSON.
            ValueError: If the parsed structure does not contain a ``files``
                dict.
        """
        cleaned = _clean_json_response(response_text)
        data: dict[str, Any] = json.loads(cleaned)

        # The LLM might return files at top level or nested under "files"
        raw_files = data.get("files")
        if isinstance(raw_files, dict):
            files = raw_files
        else:
            # Attempt to treat the entire response as a files dict
            files = {k: v for k, v in data.items() if isinstance(v, str) and len(v) > 10}
            if not files:
                raise ValueError(
                    "LLM response does not contain a 'files' dict or "
                    "recognisable file entries.  Response keys: "
                    f"{list(data.keys())}"
                )

        return {
            "files": files,
            "notes": data.get("notes", []),
        }

    # ------------------------------------------------------------------
    # Internal helpers — file writing
    # ------------------------------------------------------------------

    def _write_files(
        self,
        file_data: dict[str, Any],
        project_name: str,
    ) -> str:
        """Write generated config files to disk using the code-gen tools.

        Args:
            file_data: Dictionary with a ``files`` key containing
                ``{file_path: content_string}`` mappings.
            project_name: Used to determine the output directory name.

        Returns:
            Absolute path to the output directory.
        """
        files: dict[str, str] = file_data.get("files", {})
        if not files:
            logger.warning("No files to write — file_data=%s", file_data)
            output_dir = Path(_OUTPUT_ROOT) / f"{project_name}_ci"
            ensure_output_dir(str(output_dir))
            return str(output_dir.absolute())

        output_dir = Path(_OUTPUT_ROOT) / f"{project_name}_ci"
        output_root = str(output_dir)

        for file_path, content in files.items():
            # Normalise: strip leading separators so the tools' security
            # check (rejects paths starting with "/") does not fire.
            normalised = file_path.lstrip("/").lstrip("\\")

            if not content or not content.strip():
                logger.debug("Skipping empty file: %s", normalised)
                continue

            try:
                if normalised.endswith("CMakeLists.txt"):
                    written = write_cmake_file(
                        file_path=normalised,
                        content=content,
                        output_root=output_root,
                    )
                    logger.info("Written CMake file: %s", written)

                elif normalised.endswith((".yml", ".yaml")):
                    written = write_workflow_file(
                        file_path=normalised,
                        content=content,
                        output_root=output_root,
                    )
                    logger.info("Written workflow file: %s", written)

                else:
                    # Other files (CMakePresets.json, etc.) — write directly
                    full_path = output_dir / normalised
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                    logger.info("Written file: %s", full_path)

            except (OSError, PermissionError, ValueError) as exc:
                logger.error("Failed to write '%s': %s", normalised, exc)
                raise

        return str(output_dir.absolute())

    # ------------------------------------------------------------------
    # Internal helpers — minimal config for zero test cases
    # ------------------------------------------------------------------

    def _generate_minimal(self, project_name: str) -> str:
        """Generate a minimal but functional CI config when there are zero
        test cases.

        Produces a skeleton ``CMakeLists.txt`` that verifies GTest can be
        fetched and compiled (a "framework check"), and a corresponding
        GitHub Actions workflow.

        This avoids sending an empty prompt to the LLM and produces
        predictable, correct output for the degenerate case.
        """
        cmake_content = (
            f"cmake_minimum_required(VERSION 3.14)\n"
            f"project({project_name}_tests LANGUAGES CXX)\n"
            f"\n"
            f"set(CMAKE_CXX_STANDARD 17)\n"
            f"set(CMAKE_CXX_STANDARD_REQUIRED ON)\n"
            f"\n"
            f"# ------------------------------------------------------------------\n"
            f"# Fetch Google Test\n"
            f"# ------------------------------------------------------------------\n"
            f"include(FetchContent)\n"
            f"FetchContent_Declare(\n"
            f"    googletest\n"
            f"    GIT_REPOSITORY https://github.com/google/googletest.git\n"
            f"    GIT_TAG        release-1.12.1\n"
            f")\n"
            f"set(gtest_force_shared_crt ON CACHE BOOL \"\" FORCE)\n"
            f"FetchContent_MakeAvailable(googletest)\n"
            f"\n"
            f"enable_testing()\n"
            f"\n"
            f"# ------------------------------------------------------------------\n"
            f"# Framework check — verify GTest compiles and runs\n"
            f"# ------------------------------------------------------------------\n"
            f"add_executable(framework_check framework_check.cc)\n"
            f"target_link_libraries(framework_check PRIVATE gtest_main gmock)\n"
            f"add_test(NAME framework_check COMMAND framework_check)\n"
        )

        workflow_content = (
            f"name: {project_name} Tests\n"
            f"\n"
            f"on:\n"
            f"  push:\n"
            f"    branches: [main, develop]\n"
            f"  pull_request:\n"
            f"    branches: [main]\n"
            f"  workflow_dispatch:\n"
            f"\n"
            f"jobs:\n"
            f"  test:\n"
            f"    runs-on: ubuntu-latest\n"
            f"\n"
            f"    steps:\n"
            f"      - uses: actions/checkout@v4\n"
            f"\n"
            f"      - name: Install Build Dependencies\n"
            f"        run: |\n"
            f"          sudo apt-get update\n"
            f"          sudo apt-get install -y cmake ninja-build g++\n"
            f"\n"
            f"      - name: Configure\n"
            f"        run: cmake -B build -G Ninja -DCMAKE_CXX_STANDARD=17\n"
            f"\n"
            f"      - name: Build\n"
            f"        run: cmake --build build\n"
            f"\n"
            f"      - name: Test\n"
            f"        run: ctest --test-dir build --output-on-failure\n"
            f"\n"
            f"      - name: Upload Test Results\n"
            f"        if: failure()\n"
            f"        uses: actions/upload-artifact@v4\n"
            f"        with:\n"
            f"          name: test-results-${{{{ github.run_id }}}}\n"
            f"          path: build/Testing/Temporary/\n"
        )

        file_data: dict[str, Any] = {
            "files": {
                "CMakeLists.txt": cmake_content,
                ".github/workflows/ci.yml": workflow_content,
            },
        }

        return self._write_files(file_data, project_name)
