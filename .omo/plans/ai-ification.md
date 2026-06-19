# Plan: Full AI-ification with LangChain

## TL;DR

> **Quick Summary**: Completely rewrite the aiagent-main project as a pure LangChain-driven pipeline. Remove all non-AI code (build artifacts, parsers, generators, runners, repair, templates, WebUI, docs, packaging). Replace the current custom urllib-based agent framework with LangChain agents. The pipeline becomes: LangChain agents read SDK headers → analyze APIs → design tests → generate GTest code + CMake + CI/CD workflow → produce a compilable test package. Actual compilation and test execution are handled by CI/CD (GitHub Actions) or local Docker, not locally.
>
> **Deliverables**:
> - Cleaned project with only: `agents/` (LangChain), `ir/` (schemas), `config/`, `app.py`, `.github/workflows/`
> - 6 LangChain Agent pipelines for: SDK scanning, API analysis, test case design, GTest code generation, CI/CD config generation, report generation
> - GitHub Actions workflow for CI/CD compilation and test execution
> - Dockerfile for local build verification
> - Updated `requirements.txt` with LangChain dependencies
>
> **Estimated Effort**: XL (large - 25+ files touched, ~3,000 lines new code)
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Cleanup → LangChain Setup → Agent Infrastructure → Pipeline Agents → CI/CD → Report Agent

---

## Context

### Original Request
"项目中垃圾多余的垃圾文件去掉，本地代码修复的也去掉，全部为AI在线。AI部分用Langchain重构一下。"

### Interview Summary
**Key Discussions**:
- **Junk cleanup**: Prometheus decides what's junk
- **Non-AI removal**: ALL non-AI parts removed ("非AI部分全部移除")
- **LangChain scope**: Full project AI-ification ("整个项目AI化改造")
- **Compilation strategy**: CI/CD pipeline mode — AI generates GTest code + CMake + CI workflow config, CI/CD handles compilation and test execution

**Current Architecture** (to be replaced):
- `agents/` (2,587 lines, 7 files): Custom urllib-based LLM integration — ReAct agent loop, tool execution, context management, shared memory
- `parsers/` (4 files): libclang-based SDK header parsing
- `generators/` (11 files): GTest code, CMake, report generation
- `planners/` (4 files): Test case design
- `runners/` (4 files): Build/test execution
- `repair/` (5 files): Compile error analysis and patching
- `WebUI/` (25+ files): FastAPI web interface
- `utils/` (18 files): Config, paths, logging, etc.
- `ir/` (4 files): Data schemas (to keep)

**New LangChain Architecture**:
- `agents/llm.py` — LangChain ChatOpenAI wrapper
- `agents/tools/` — LangChain tool definitions (read headers, write files, etc.)
- `agents/chains/` — 6 LangChain pipeline chains
- `agents/memory.py` — Cross-stage memory with LangChain
- `agents/cache.py` — Cache layer (preserved from existing)
- `agents/pipeline.py` — Pipeline orchestrator
- `agents/prompts/` — LangChain PromptTemplate files
- `.github/workflows/ci.yml` — CI/CD pipeline
- `Dockerfile` — Local build environment

---

## Work Objectives

### Core Objective
Transform aiagent-main from a mixed local-code + AI hybrid into a pure LangChain-driven AI pipeline. All pipeline stages (SDK scanning, API analysis, test design, code generation) are performed by LangChain agents. Compilation moves to CI/CD infrastructure.

### Concrete Deliverables
- [x] Cleaned repository: only `agents/`, `ir/`, `config/`, `app.py`, `.github/`, `Dockerfile`, `requirements.txt`, `.gitignore`
- [x] 6 LangChain pipeline agents in `agents/chains/`
- [x] LangChain tool definitions in `agents/tools/`
- [x] Prompt templates in `agents/prompts/`
- [x] Cache and memory modules in `agents/`
- [x] Pipeline orchestrator in `agents/pipeline.py`
- [x] New `app.py` with CLI interface
- [x] `.github/workflows/ci.yml` for GitHub Actions
- [x] `Dockerfile` for local build verification
- [x] Updated `requirements.txt`

### Definition of Done
```bash
# 1. Clean project structure check
ls -la  # No GoogleTest, ninja, WebUI, generators, runners, parsers, etc.

# 2. Pipeline runs end-to-end (no-cache, dry-run mode)
python app.py --config config/scivision_config.yaml --llm-enabled --no-cache --dry-run
# Expected: Pipeline initializes all 6 agents, prints stage plan, exits cleanly

# 3. Test with real SDK
python app.py --config config/scivision_config.yaml --llm-enabled --output-root ./output
# Expected: Generates ./output/ with gtest_cases/*.cpp, CMakeLists.txt, .github/workflows/, report.md

# 4. All agents respond with structured output
# Expected: Each pipeline stage produces valid JSON conforming to ir/ schemas
```

### Must Have
- Pipeline stages produce valid `APIInventory`, `ContractInfo`, `TestCaseCollection` (from `ir/` schemas)
- LangChain agents handle: SDK header reading, API analysis, test case design, GTest code generation, CI/CD config generation, report generation
- Cache layer preserved (content-hash based, configurable via `--no-cache`)
- CLI interface preserved (`--config`, `--sdk-root`, `--output-root`, `--llm-enabled`, `--no-cache`, `--no-build`, `--no-test`)
- Cross-stage context preserved (each agent knows what previous stages produced)
- Generated GTest code compiles (verified by CI/CD)
- Output format backward compatible (`LLM_TESTCASES.json`, `LLM_TESTCASES.md`, `test_results.json`)

### Must NOT Have (Guardrails)
- NO precompiled binary artifacts (GoogleTest, ninja) in repository
- NO local build/execution of C++ code (moved to CI/CD)
- NO libclang dependency (AI reads .h files directly)
- NO Jinja2 templates (AI generates complete code)
- NO FastAPI/WebUI (all interaction via CLI)
- NO manual test case confirmation dialog (AI-driven)
- NO tkinter dependency
- NO packaging scripts (exe_pack)
- NO documentation files (docs/)
- NO scope creep: no new chains beyond the 6 pipeline stages
- NO multi-model support (single LangChain ChatOpenAI with configured model)

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (project refactored from scratch)
- **Automated tests**: Tests-after (implement pipeline, then verify with end-to-end test)
- **Framework**: pytest for Python tests, GitHub Actions for C++ compilation test
- **If TDD**: NOT applicable (this is a rewrite; test after implementation via end-to-end integration test)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.omo/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Python modules**: Use Bash (python -c "import ...; ...") — Import and call modules, validate outputs
- **CLI pipeline**: Use interactive_bash (tmux) — Run `python app.py` with various flags, validate stdout and output files
- **File outputs**: Use Bash — Check generated files exist, parse JSON, validate schema compliance
- **CI/CD config**: Validate YAML syntax, check GitHub Actions workflow parses

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — 6 parallel tasks):
├── Task 1: Project cleanup (delete junk/non-AI files)
├── Task 2: LangChain dependency setup (requirements.txt, config)
├── Task 3: ir/ schemas preservation + enhancement
├── Task 4: agents/llm.py — LangChain LLM wrapper
├── Task 5: agents/cache.py — Cache layer
├── Task 6: agents/memory.py — Cross-stage memory

Wave 2 (LangChain Infrastructure — 6 parallel tasks):
├── Task 7: agents/tools/ — SDK reading tools
├── Task 8: agents/tools/ — Code generation tools
├── Task 9: agents/tools/ — File I/O tools
├── Task 10: agents/prompts/ — All prompt templates
├── Task 11: agents/chains/scanner_chain.py
├── Task 12: agents/chains/analysis_chain.py

Wave 3 (Pipeline Agents — 5 parallel tasks):
├── Task 13: agents/chains/test_design_chain.py
├── Task 14: agents/chains/code_gen_chain.py
├── Task 15: agents/chains/ci_gen_chain.py
├── Task 16: agents/chains/report_chain.py
├── Task 17: agents/pipeline.py — Pipeline orchestrator

Wave 4 (Integration + CI/CD — 4 parallel tasks):
├── Task 18: app.py — New CLI entry point
├── Task 19: .github/workflows/ci.yml — CI/CD pipeline
├── Task 20: Dockerfile — Build environment
├── Task 21: End-to-end integration test

Wave FINAL (Review — 4 parallel reviewers):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality + build verification (unspecified-high)
├── Task F3: Real manual QA — pipeline execution (unspecified-high)
├── Task F4: Scope fidelity + cleanup verification (deep)

Critical Path: Task 1 → 2 → (Wave 2) → (Wave 3) → Task 18 → Task 21 → F1-F4
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 7 (Wave 2)
```

### Dependency Matrix
- Tasks 1-6: none — start immediately
- Task 7-10: Tasks 2, 4 — LangChain infrastructure
- Task 11: Tasks 7, 8, 10 — needs tools + prompts + schemas
- Task 12: Tasks 7, 10 — needs tools + prompts
- Task 13: Tasks 10, 12 — needs analysis prompts + analysis results
- Task 14: Tasks 8, 10, 11 — needs tools + prompts + scanner results
- Task 15: Tasks 7, 10 — needs tools + prompts
- Task 16: Tasks 7, 10 — needs tools + prompts
- Task 17: Tasks 11, 12, 13, 14, 15, 16 — orchestrator needs all agents
- Task 18: Task 17 — needs pipeline orchestrator
- Task 19: Task 14 — needs code gen
- Task 20: Task 14 — needs code gen
- Task 21: Tasks 18, 19, 20 — integration
- F1-F4: Task 21 — final verification

### Agent Dispatch Summary
- Wave 1: 6 tasks → 6× quick
- Wave 2: 6 tasks → 4× deep, 2× quick
- Wave 3: 5 tasks → 5× deep
- Wave 4: 4 tasks → 2× deep, 2× unspecified-high
- FINAL: 4 tasks → oracle, unspecified-high, unspecified-high, deep

---

## TODOs

- [x] 1. **Project Cleanup — Delete all non-AI code and junk files**

  **What to do**:
  - Delete these directories and files (non-AI code):
    - `GoogleTest1.17.0/`, `GoogleTest1.8.1/` — Precompiled GTest binaries
    - `ninja/` — Precompiled build tool
    - `parsers/` — libclang-based header parsers (AI reads headers directly)
    - `generators/` — Code generators (LangChain agents generate)
    - `planners/` — Test case planners (LangChain agent designs)
    - `runners/` — Build/test executors (CI/CD handles)
    - `repair/` — Error repair (LangChain agent loop handles)
    - `knowledge/` — Knowledge base (LangChain built-in knowledge)
    - `utils/` — Utilities (most removed; config/path utilities folded into agents)
    - `WebUI/` — FastAPI web interface (no longer needed)
    - `templates/` — Jinja2 templates (AI generates directly)
    - `exe_pack/` — Packaging scripts
    - `docs/` — Documentation
    - `project_architecture.md`, `INTEGRATION_VERIFICATION.md`, `start_webui.bat`, `LICENSE`
  - Keep: `ir/`, `config/`, `__init__.py`, `.gitignore`
  - Verify no imports from deleted modules remain in kept files
  - Create a cleanup manifest file (`CLEANUP_MANIFEST.md`) listing all deleted items

  **Must NOT do**:
  - Do NOT delete `ir/` (data schemas still needed)
  - Do NOT delete `config/` (configuration still needed)
  - Do NOT delete `.gitignore`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: File deletion is mechanical, not creative
  - **Skills**: `[]`
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: ALL subsequent tasks (clean foundation needed)
  - **Blocked By**: None

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Verify deleted directories no longer exist
    Tool: Bash
    Preconditions: Cleanup script has been run
    Steps:
      1. ls -d GoogleTest1.17.0 GoogleTest1.8.1 ninja WebUI generators parsers planners runners repair knowledge templates docs exe_pack 2>&1
    Expected Result: ls: cannot access '...': No such file or directory (for each deleted dir)
    Evidence: .omo/evidence/task-1-cleanup.txt

  Scenario: Verify kept directories still exist
    Tool: Bash
    Preconditions: Cleanup complete
    Steps:
      1. ls -d ir config __init__.py .gitignore
    Expected Result: All 4 exist
    Evidence: .omo/evidence/task-1-kept.txt

  Scenario: Verify no stale imports in kept files
    Tool: Bash
    Preconditions: Cleanup complete
    Steps:
      1. grep -r "from generators\|from parsers\|from runners\|from repair\|from planners\|from knowledge\|from utils\|from WebUI" ir/ app.py agents/ 2>&1 || echo "No stale imports found"
    Expected Result: No stale imports found
    Evidence: .omo/evidence/task-1-imports.txt
  ```

  **Commit**: YES
  - Message: `cleanup: remove all non-AI code and junk files`
  - Files: All deleted + CLEANUP_MANIFEST.md

- [x] 2. **LangChain Dependency Setup**

  **What to do**:
  - Update `requirements.txt` with LangChain dependencies:
    ```
    langchain>=0.3.0
    langchain-openai>=0.2.0
    langchain-community>=0.3.0
    pydantic>=2.0
    pyyaml>=6.0
    ```
  - Remove old dependencies no longer needed (libclang, tkinter, fastapi, uvicorn, jinja2, aiofiles, etc.)
  - Create `agents/__init__.py`
  - Create `agents/tools/__init__.py`
  - Create `agents/chains/__init__.py`
  - Create `agents/prompts/__init__.py`

  **Must NOT do**:
  - Do NOT pin LangChain to exact versions (allow minor updates)
  - Do NOT add dependencies that are not needed

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple file creation and update
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 7-10 (LangChain infrastructure needs deps)
  - **Blocked By**: None

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Verify pip install works
    Tool: Bash
    Preconditions: requirements.txt updated
    Steps:
      1. pip install -r requirements.txt --dry-run 2>&1 | tail -5
    Expected Result: All dependencies resolved successfully
    Evidence: .omo/evidence/task-2-pip.txt

  Scenario: Verify langchain import works
    Tool: Bash
    Preconditions: Dependencies installed
    Steps:
      1. python -c "from langchain_openai import ChatOpenAI; print('OK')"
    Expected Result: OK
    Evidence: .omo/evidence/task-2-import.txt
  ```

  **Commit**: YES (groups with Task 1)
  - Message: `cleanup: remove all non-AI code and junk files`
  - Files: requirements.txt, agents/__init__.py, agents/tools/__init__.py, agents/chains/__init__.py, agents/prompts/__init__.py

- [x] 3. **Preserve and Enhance ir/ Data Schemas**

  **What to do**:
  - Keep existing `ir/api_schema.py`, `ir/contract_schema.py`, `ir/testcase_schema.py` as-is
  - Add JSON serialization/deserialization methods to each schema class for use by LangChain output parsers
  - Add `to_dict()` and `from_dict()` class methods to each dataclass
  - Add a new `ir/__init__.py` that re-exports all schemas for easy importing

  **Must NOT do**:
  - Do NOT change existing field names (backward compatibility with output files)
  - Do NOT remove any existing fields

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small focused updates to existing data classes
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 11-16 (all chains need schemas)
  - **Blocked By**: None

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Verify schemas import and serialize correctly
    Tool: Bash
    Preconditions: ir/ files updated
    Steps:
      1. python -c "from ir.api_schema import APIInventory, FunctionInfo, ParamInfo; f=FunctionInfo(function_id='f1', name='test', qualified_name='ns::test', namespace='ns', return_type='void'); print(f.to_dict())"
    Expected Result: Valid JSON dict printed
    Evidence: .omo/evidence/task-3-schema.txt

  Scenario: Verify existing schema backward compatibility
    Tool: Bash
    Preconditions: None
    Steps:
      1. python -c "from ir.api_schema import *; from ir.contract_schema import *; from ir.testcase_schema import *; print('All schemas imported')"
    Expected Result: All schemas imported
    Evidence: .omo/evidence/task-3-import.txt
  ```

  **Commit**: YES
  - Message: `feat(ir): add JSON serialization to data schemas`
  - Files: ir/*.py

- [x] 4. **agents/llm.py — LangChain ChatOpenAI Wrapper**

  **What to do**:
  - Create `agents/llm.py` that wraps `langchain_openai.ChatOpenAI`
  - Support the existing config schema from `config/scivision_config.yaml`:
    - `llm_provider`: "openai-compatible"
    - `llm_model`: model name (e.g., "kimi-k2.5")
    - `llm_base_url`: custom base URL (e.g., Aliyun DashScope)
    - `llm_api_key_env`: env var name for API key
    - `llm_temperature`: generation temperature
    - `llm_max_tokens`: max output tokens
    - `llm_timeout_sec`: request timeout
  - Implement `LLMWrapper` class with:
    - `__init__(config: dict)` — Initialize ChatOpenAI from config
    - `get_chat_model() -> ChatOpenAI` — Returns configured model
    - `invoke(messages, **kwargs)` — Direct call (replaces old llm_client.invoke)
    - `invoke_with_tools(messages, tools, **kwargs)` — Function calling call
    - `invoke_structured(messages, output_schema, **kwargs)` — Structured output via `.with_structured_output()`
  - Handle: retry logic (3 retries with exponential backoff), timeout, API errors
  - Use `langchain_openai.ChatOpenAI` with `openai_api_key` from env var

  **Must NOT do**:
  - Do NOT store API key in code (must read from env var)
  - Do NOT use raw urllib or httpx directly
  - Do NOT implement custom ReAct loop (LangChain handles it)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Wrapping LangChain while preserving config compatibility requires careful design
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 7-17 (everything needs the LLM wrapper)
  - **Blocked By**: Task 2

  **References**:
  - `config/scivision_config.yaml` — Config schema for all LLM settings
  - LangChain docs: `https://python.langchain.com/docs/integrations/chat/openai/` — ChatOpenAI configuration

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: LLM wrapper initializes from config dict
    Tool: Bash
    Preconditions: requirements.txt installed
    Steps:
      1. python -c "from agents.llm import LLMWrapper; cfg={'llm_model': 'kimi-k2.5', 'llm_base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'llm_temperature': 0.2, 'llm_max_tokens': 30000, 'llm_timeout_sec': 1200, 'llm_api_key_env': 'OPENAI_API_KEY'}; llm=LLMWrapper(cfg); print(type(llm.get_chat_model()).__name__)"
    Expected Result: ChatOpenAI
    Evidence: .omo/evidence/task-4-init.txt

  Scenario: LLM wrapper handles missing API key gracefully
    Tool: Bash
    Preconditions: OPENAI_API_KEY env var unset
    Steps:
      1. python -c "from agents.llm import LLMWrapper; cfg={'llm_model': 'test'}; llm=LLMWrapper(cfg); print('OK')"
    Expected Result: Does not crash (defers auth error to actual call)
    Evidence: .omo/evidence/task-4-no-key.txt

  Scenario: Structured output with Pydantic schema
    Tool: Bash
    Preconditions: None
    Steps:
      1. python -c "from agents.llm import LLMWrapper; from pydantic import BaseModel; cfg={'llm_model': 'test', 'llm_base_url': 'https://test'}; llm=LLMWrapper(cfg); has=hasattr(llm, 'invoke_structured'); print(f'has_structured={has}')"
    Expected Result: has_structured=True
    Evidence: .omo/evidence/task-4-structured.txt
  ```

  **Commit**: YES
  - Message: `feat(agents): add LangChain ChatOpenAI wrapper`
  - Files: agents/llm.py

- [x] 5. **agents/cache.py — Cache Layer Preservation**

  **What to do**:
  - Create `agents/cache.py` that provides a content-hash based LLM result cache
  - Adapt the caching logic from the old `test_agent.py`'s `_llm_cache_hit` / `_llm_cache_store` patterns
  - Cache key = SHA256 hash of (model + prompt + temperature + tools signature)
  - Cache value = serialized LLM response
  - Cache location: `output/cache/` (same as before)
  - Support `--no-cache` flag to disable caching
  - `LLMCache` class with:
    - `get(key: str) -> dict | None` — Retrieve cached result
    - `set(key: str, value: dict)` — Store result
    - `invalidate(pattern: str)` — Clear matching cache entries
    - `clear()` — Wipe entire cache

  **Must NOT do**:
  - Do NOT use memory-only cache (must persist to disk)
  - Do NOT cache sensitive data (API keys, etc.)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple key-value cache implementation, well-understood pattern
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 2, 4 (needs LLM wrapper + deps)
  - **Blocked By**: None (self-contained)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Cache set and get round-trip
    Tool: Bash
    Preconditions: Cache directory does not exist
    Steps:
      1. python -c "from agents.cache import LLMCache; c=LLMCache(cache_dir='test_cache'); c.set('test_key', {'result': 'hello'}); v=c.get('test_key'); print(v)"
    Expected Result: {'result': 'hello'}
    Evidence: .omo/evidence/task-5-cache.txt

  Scenario: Cache miss returns None
    Tool: Bash
    Preconditions: Clean cache
    Steps:
      1. python -c "from agents.cache import LLMCache; c=LLMCache(cache_dir='test_cache'); v=c.get('nonexistent_key'); print(v)"
    Expected Result: None
    Evidence: .omo/evidence/task-5-miss.txt

  Scenario: Cache clear works
    Tool: Bash
    Preconditions: Cache contains entries
    Steps:
      1. python -c "from agents.cache import LLMCache; import os; c=LLMCache(cache_dir='test_cache'); c.set('k', 'v'); c.clear(); print(os.path.exists('test_cache'))"
    Expected Result: False (or cache dir is empty)
    Evidence: .omo/evidence/task-5-clear.txt
  ```

  **Commit**: YES (groups with Task 4)
  - Message: `feat(agents): add LangChain ChatOpenAI wrapper and cache layer`

- [x] 6. **agents/memory.py — Cross-Stage Memory with LangChain**

  **What to do**:
  - Create `agents/memory.py` that provides cross-stage context passing between pipeline agents
  - Each pipeline stage needs to know what the previous stages produced
  - Implement `PipelineMemory` class:
    - `store_stage_output(stage_name: str, output: dict)` — Save stage output
    - `get_stage_output(stage_name: str) -> dict | None` — Retrieve stage output
    - `get_all_outputs() -> dict[str, dict]` — Get all stage outputs for final report
    - `summarize_for_next_stage(stage_name: str) -> str` — Generate LLM-friendly context summary
  - Use LangChain's `BaseChatMemory` if needed, or keep custom (simpler for this use case)
  - Persist to disk: `output/pipeline_memory.json` for debugging and resumability

  **Must NOT do**:
  - Do NOT use LangChain ConversationBufferMemory (too simplistic for cross-stage context)
  - Do NOT store raw message history (stores structured stage outputs)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple dictionary-based storage with serialization
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 17 (pipeline orchestrator needs memory)
  - **Blocked By**: None

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Pipeline memory stores and retrieves stage outputs
    Tool: Bash
    Preconditions: None
    Steps:
      1. python -c "from agents.memory import PipelineMemory; m=PipelineMemory(); m.store_stage_output('scanner', {'apis': ['func1', 'func2']}); v=m.get_stage_output('scanner'); print(v)"
    Expected Result: {'apis': ['func1', 'func2']}
    Evidence: .omo/evidence/task-6-memory.txt

  Scenario: Summarize for next stage creates context string
    Tool: Bash
    Preconditions: Multiple stages stored
    Steps:
      1. python -c "from agents.memory import PipelineMemory; m=PipelineMemory(); m.store_stage_output('scanner', {'functions': 5}); m.store_stage_output('analysis', {'complexity': 'high'}); s=m.summarize_for_next_stage('test_design'); print(len(s) > 0)"
    Expected Result: True (summary has content)
    Evidence: .omo/evidence/task-6-summary.txt
  ```

  **Commit**: YES (groups with Task 5)
  - Message: `feat(agents): add cache layer and cross-stage memory`

- [x] 7. **agents/tools/ — SDK Header Reading Tools**

  **What to do**:
  - Create `agents/tools/sdk_tools.py` with LangChain `@tool`-decorated functions:
    - `list_header_files(sdk_root: str) -> list[str]` — Lists all .h files under sdk_root/include/
    - `read_header_file(file_path: str) -> str` — Reads and returns content of a .h file
    - `extract_function_signatures(header_content: str) -> list[dict]` — Uses LLM to extract function signatures from header text (replaces old libclang parsing)
    - `extract_class_definitions(header_content: str) -> list[dict]` — Extracts class/struct definitions
    - `extract_enum_definitions(header_content: str) -> list[dict]` — Extracts enum definitions
  - All tools return structured dicts that can be parsed into `ir/` schema objects
  - Implement path security (only allow access under configured sdk_root)

  **Must NOT do**:
  - Do NOT depend on libclang (pure AI-driven header analysis)
  - Do NOT allow arbitrary file access (path traversal protection)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Must carefully wrap file I/O + LLM analysis into usable tools
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 11 (scanner chain needs these tools)
  - **Blocked By**: Tasks 2, 4 (needs deps + LLM wrapper)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: List header files returns valid paths
    Tool: Bash
    Preconditions: SDK exists at configured path
    Steps:
      1. python -c "from agents.tools.sdk_tools import list_header_files; files=list_header_files('E:\\wj_projects\\SciVision_4000'); print(len(files) > 0)"
    Expected Result: True (finds header files)
    Evidence: .omo/evidence/task-7-list.txt

  Scenario: Path security blocks traversal
    Tool: Bash
    Preconditions: None
    Steps:
      1. python -c "from agents.tools.sdk_tools import read_header_file; read_header_file('../../../etc/passwd')" 2>&1
    Expected Result: Error about path not allowed
    Evidence: .omo/evidence/task-7-security.txt
  ```

  **Commit**: YES
  - Message: `feat(tools): add SDK header reading and analysis tools`

- [x] 8. **agents/tools/ — Code Generation Tools**

  **What to do**:
  - Create `agents/tools/code_gen_tools.py` with LangChain `@tool`-decorated functions:
    - `write_gtest_file(file_path: str, content: str) -> str` — Write a generated .cpp file to output directory
    - `write_cmake_file(file_path: str, content: str) -> str` — Write CMakeLists.txt
    - `write_workflow_file(file_path: str, content: str) -> str` — Write CI/CD workflow YAML
    - `write_report_file(file_path: str, content: str, fmt: str) -> str` — Write report (md/json)
    - `ensure_output_dir(path: str) -> bool` — Create directory if not exists
  - All write operations scoped under `output_root/` (path security)
  - Files should be written with UTF-8 encoding

  **Must NOT do**:
  - Do NOT allow writes outside `output_root/`
  - Do NOT overwrite existing files without warning

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: File I/O wrapper tools, well-understood pattern
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 14, 15, 16 (code gen, CI/CD gen, report gen chains)
  - **Blocked By**: Tasks 2, 4

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Write and verify gtest file
    Tool: Bash
    Preconditions: None
    Steps:
      1. python -c "from agents.tools.code_gen_tools import write_gtest_file, ensure_output_dir; ensure_output_dir('output/test'); write_gtest_file('output/test/test_case.cpp', 'int main(){}'); print(open('output/test/test_case.cpp').read())"
    Expected Result: int main(){}
    Evidence: .omo/evidence/task-8-write.txt

  Scenario: Path security blocks write outside output_root
    Tool: Bash
    Preconditions: None
    Steps:
      1. python -c "from agents.tools.code_gen_tools import write_gtest_file; write_gtest_file('../outside_test.cpp', 'test')" 2>&1
    Expected Result: Error about path not allowed
    Evidence: .omo/evidence/task-8-security.txt
  ```

  **Commit**: YES (groups with Task 7)
  - Message: `feat(tools): add SDK reading and code generation tools`

- [x] 9. **agents/tools/ — File I/O and Utility Tools**

  **What to do**:
  - Create `agents/tools/file_tools.py` with general-purpose file tools:
    - `read_file(path: str) -> str` — Read any text file (scoped to project/output dirs)
    - `list_directory(path: str) -> list[str]` — List files in directory
    - `file_exists(path: str) -> bool` — Check if file exists
    - `read_json(path: str) -> dict` — Read and parse JSON file
    - `write_json(path: str, data: dict) -> None` — Write JSON file
  - All tools scoped to project root and output directories for safety

  **Must NOT do**:
  - Do NOT expose write access to system directories
  - Do NOT expose delete/rename/move (read-only + controlled write only)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple file utility wrappers
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 11-16 (all chains may need file operations)
  - **Blocked By**: Tasks 2, 4

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Read file returns correct content
    Tool: Bash
    Preconditions: None
    Steps:
      1. echo "hello" > test_file.txt; python -c "from agents.tools.file_tools import read_file; print(read_file('test_file.txt'))"
    Expected Result: hello
    Evidence: .omo/evidence/task-9-read.txt

  Scenario: List directory works
    Tool: Bash
    Preconditions: None
    Steps:
      1. python -c "from agents.tools.file_tools import list_directory; print(len(list_directory('.')) > 0)"
    Expected Result: True
    Evidence: .omo/evidence/task-9-list.txt
  ```

  **Commit**: YES (groups with Tasks 7-8)
  - Message: `feat(tools): add SDK reading, code generation, and file utility tools`

- [x] 10. **agents/prompts/ — All Pipeline Prompt Templates**

  **What to do**:
  - Create 6 LangChain `PromptTemplate` files in `agents/prompts/`:
    - `scanner_prompt.py` — SYSTEM_PROMPT for SDK scanner agent:
      - Context: SDK root path, what to look for
      - Expected output: structured API inventory matching `ir/api_schema.py`
      - Instructions: focus on public APIs, extract function signatures, classes, enums
    - `analysis_prompt.py` — SYSTEM_PROMPT for API analysis agent:
      - Context: API inventory from scanner
      - Expected output: analysis report with complexity, dependencies, recommendations
    - `test_design_prompt.py` — SYSTEM_PROMPT for test case designer:
      - Context: API inventory + analysis report
      - Expected output: structured test cases matching `ir/testcase_schema.py`
      - Instructions: cover happy path, edge cases, error conditions
    - `code_gen_prompt.py` — SYSTEM_PROMPT for GTest code generator:
      - Context: test cases from designer
      - Expected output: complete, compilable C++ GTest source code
      - Instructions: use proper GTest macros (TEST_F, EXPECT_EQ, etc.), include headers
    - `ci_gen_prompt.py` — SYSTEM_PROMPT for CI/CD config generator:
      - Context: test source files that were generated
      - Expected output: GitHub Actions workflow YAML + CMakeLists.txt
      - Instructions: docker setup, GTest fetch, compile, run tests
    - `report_prompt.py` — SYSTEM_PROMPT for report generator:
      - Context: all pipeline stage outputs
      - Expected output: Markdown report + JSON summary
  - Each file exports `SYSTEM_PROMPT` (str) and optionally `HUMAN_TEMPLATE` (PromptTemplate)
  - Prompts should be detailed enough for reliable structured output

  **Must NOT do**:
  - Do NOT hardcode API keys or secrets in prompts
  - Do NOT make prompts too generic (must be tailored to this pipeline)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Prompt quality directly determines pipeline reliability; need careful design
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 11-16 (all chains need prompts)
  - **Blocked By**: Tasks 3 (schemas), 4 (LLM wrapper)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: All prompt files exist and export SYSTEM_PROMPT
    Tool: Bash
    Preconditions: None
    Steps:
      1. python -c "from agents.prompts.scanner_prompt import SYSTEM_PROMPT; from agents.prompts.analysis_prompt import SYSTEM_PROMPT; from agents.prompts.test_design_prompt import SYSTEM_PROMPT; from agents.prompts.code_gen_prompt import SYSTEM_PROMPT; from agents.prompts.ci_gen_prompt import SYSTEM_PROMPT; from agents.prompts.report_prompt import SYSTEM_PROMPT; print('All 6 prompts loaded')"
    Expected Result: All 6 prompts loaded
    Evidence: .omo/evidence/task-10-prompts.txt

  Scenario: Prompts contain expected section keywords
    Tool: Bash
    Preconditions: None
    Steps:
      1. python -c "from agents.prompts.scanner_prompt import SYSTEM_PROMPT; print('API' in SYSTEM_PROMPT or 'function' in SYSTEM_PROMPT)"
    Expected Result: True
    Evidence: .omo/evidence/task-10-prompt-content.txt
  ```

  **Commit**: YES
  - Message: `feat(prompts): add 6 LangChain prompt templates for pipeline stages`

- [x] 11. **agents/chains/scanner_chain.py — SDK Scanner Agent**

  **What to do**:
  - Create `agents/chains/scanner_chain.py` as a LangChain `Chain` (or Runnable)
  - SDK Scanner Agent pipeline:
    1. Receives `sdk_root` path from config
    2. Calls `list_header_files` tool to discover all .h files
    3. For each header file, calls `read_header_file` to get content
    4. For large SDKs, process headers in batches (LLM context window limit)
    5. Calls LLM with scanner prompt to extract function signatures, classes, enums
    6. Returns structured data parseable into `ir.api_schema.APIInventory`
  - `SDKScannerChain` class:
    - `__init__(llm: ChatOpenAI, tools: list, prompt: PromptTemplate)`
    - `run(sdk_root: str, include_dirs: list[str]) -> APIInventory`
  - Handle: large SDKs (batch processing), malformed headers, empty SDK

  **Must NOT do**:
  - Do NOT depend on libclang or any C parser
  - Do NOT attempt to compile headers (reading only)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core pipeline chain with batching and structured output parsing
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 12, 14 (analysis and code gen need scanner output)
  - **Blocked By**: Tasks 7, 8, 10 (tools + prompts)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Scanner chain produces valid APIInventory
    Tool: Bash
    Preconditions: SDK headers available, LLM configured
    Steps:
      1. python -c "from agents.chains.scanner_chain import SDKScannerChain; from agents.llm import LLMWrapper; from ir.api_schema import APIInventory; cfg={'llm_model':'kimi-k2.5'}; llm=LLMWrapper(cfg); chain=SDKScannerChain(llm=llm); result=chain.run(sdk_root='E:\\wj_projects\\SciVision_4000'); print(f'functions={len(result.functions)}, classes={len(result.classes)}')"
    Expected Result: Functions and classes found > 0
    Evidence: .omo/evidence/task-11-scanner.txt
  ```

  **Commit**: YES
  - Message: `feat(chains): add SDK scanner agent chain`

- [x] 12. **agents/chains/analysis_chain.py — API Analysis Agent**

  **What to do**:
  - Create `agents/chains/analysis_chain.py` as a LangChain chain
  - API Analysis Agent pipeline:
    1. Receives `APIInventory` from scanner
    2. Calls LLM with analysis prompt to:
       - Analyze function signatures (parameters, return types, complexity)
       - Identify class hierarchies and dependencies
       - Detect patterns (factory, singleton, observer)
       - Flag potential issues (memory management, threading)
       - Suggest test priorities
    3. Returns structured analysis report

  - `APIAnalysisChain` class:
    - `__init__(llm: ChatOpenAI, prompt: PromptTemplate)`
    - `run(inventory: APIInventory) -> dict` — Returns analysis report

  **Must NOT do**:
  - Do NOT make assumptions about SDK domain (let LLM infer)
  - Do NOT hardcode API patterns

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: LLM-driven analysis with complex output structure
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 13 (test design needs analysis)
  - **Blocked By**: Tasks 7, 10 (tools + prompts)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Analysis produces structured report
    Tool: Bash
    Preconditions: Scanner output available
    Steps:
      1. python -c "from agents.chains.analysis_chain import APIAnalysisChain; from agents.llm import LLMWrapper; from ir.api_schema import APIInventory, FunctionInfo; inv=APIInventory(functions=[FunctionInfo(function_id='f1',name='open',qualified_name='ns::open',namespace='ns',return_type='int')]); llm=LLMWrapper({'llm_model':'kimi-k2.5'}); chain=APIAnalysisChain(llm); result=chain.run(inventory=inv); print(f'complexity={result.get(\"complexity\")}')"
    Expected Result: Complexity assessment returned
    Evidence: .omo/evidence/task-12-analysis.txt
  ```

  **Commit**: YES
  - Message: `feat(chains): add API analysis agent chain`

- [x] 13. **agents/chains/test_design_chain.py — Test Case Designer Agent**

  **What to do**:
  - Create `agents/chains/test_design_chain.py` as a LangChain chain
  - Test Case Designer pipeline:
    1. Receives `APIInventory` (from scanner) + Analysis Report (from analyzer)
    2. Calls LLM with test design prompt to generate comprehensive test cases:
       - For each function: happy path, null input, boundary values, error codes
       - For each class: construction, method calls, edge cases, destruction
       - For each enum: all valid values, out-of-range
       - Multi-API integration tests
    3. Returns `TestCaseCollection` (from `ir.testcase_schema`)
  - `TestDesignChain` class:
    - `__init__(llm: ChatOpenAI, prompt: PromptTemplate)`
    - `run(inventory: APIInventory, analysis: dict) -> TestCaseCollection`

  **Must NOT do**:
  - Do NOT generate more than 100 test cases per run (keep scope manageable)
  - Do NOT generate test cases for internal/private APIs

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Complex multi-constraint test generation logic
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 14 (code gen needs test cases)
  - **Blocked By**: Tasks 10, 12 (prompts + analysis)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Test design produces valid TestCaseCollection
    Tool: Bash
    Preconditions: Scanner + analysis output available
    Steps:
      1. python -c "from agents.chains.test_design_chain import TestDesignChain; from agents.llm import LLMWrapper; from ir.testcase_schema import TestCaseCollection; llm=LLMWrapper({'llm_model':'kimi-k2.5'}); chain=TestDesignChain(llm); result=chain.run(inventory={...}, analysis={...}); print(f'test_cases={len(result.test_cases)}')"
    Expected Result: Test cases generated
    Evidence: .omo/evidence/task-13-design.txt
  ```

  **Commit**: YES
  - Message: `feat(chains): add test case designer agent chain`

- [x] 14. **agents/chains/code_gen_chain.py — GTest Code Generator Agent**

  **What to do**:
  - Create `agents/chains/code_gen_chain.py` as a LangChain chain
  - GTest Code Generator pipeline:
    1. Receives `TestCaseCollection` from designer
    2. Calls LLM with code gen prompt to generate complete C++ GTest source files:
       - Proper `#include` directives (gtest/gtest.h, SDK headers)
       - Test fixtures for classes (TEST_F), standalone tests for functions (TEST)
       - Correct GTest macros (EXPECT_EQ, EXPECT_TRUE, ASSERT_NE, etc.)
       - Proper `main()` function (or link gtest_main)
       - Comment each test with what it tests
    3. Uses `write_gtest_file` tool to save files to output directory
    4. Returns list of generated file paths
  - `CodeGenChain` class:
    - `__init__(llm: ChatOpenAI, tools: list, prompt: PromptTemplate)`
    - `run(test_cases: TestCaseCollection, output_dir: str) -> list[str]`

  **Must NOT do**:
  - Do NOT generate code with syntax errors (use structured output + validation)
  - Do NOT use templates (AI generates complete code inline)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Must generate compilable C++ code with GTest — syntax-critical
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: Tasks 15, 18, 19, 20 (CI/CD, app.py, Dockerfile need code gen output)
  - **Blocked By**: Tasks 8, 10, 13 (tools + prompts + test cases)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Code generation produces syntactically valid C++ file
    Tool: Bash
    Preconditions: Test cases available
    Steps:
      1. python -c "from agents.chains.code_gen_chain import CodeGenChain; from agents.llm import LLMWrapper; llm=LLMWrapper({'llm_model':'kimi-k2.5'}); chain=CodeGenChain(llm); files=chain.run(test_cases={...}, output_dir='output/tests'); print(f'files={files}')"
    Expected Result: Files written to output/tests/
    Evidence: .omo/evidence/task-14-codegen.txt

  Scenario: Generated C++ file includes GTest header
    Tool: Bash
    Preconditions: Code gen has completed
    Steps:
      1. head -5 output/tests/test_case_1.cpp
    Expected Result: #include "gtest/gtest.h" present
    Evidence: .omo/evidence/task-14-header.txt
  ```

  **Commit**: YES
  - Message: `feat(chains): add GTest code generator agent chain`

- [x] 15. **agents/chains/ci_gen_chain.py — CI/CD Config Generator Agent**

  **What to do**:
  - Create `agents/chains/ci_gen_chain.py` as a LangChain chain
  - CI/CD Config Generator pipeline:
    1. Receives list of generated test files + project metadata from code gen
    2. Calls LLM with CI/CD prompt to generate:
       - `.github/workflows/ci.yml` — GitHub Actions workflow:
         - Checkout code
         - Install CMake + Ninja
         - Fetch GTest (via FetchContent or apt)
         - Configure CMake
         - Build tests
         - Run tests with CTest
         - Upload test results as artifacts
       - `CMakeLists.txt` — Root CMake configuration:
         - C++17 standard
         - GTest via FetchContent (no precompiled binaries needed)
         - All test source files
         - CTest integration
    3. Uses `write_cmake_file` and `write_workflow_file` tools to save files
    4. Returns dict with paths to generated files
  - `CIGenChain` class:
    - `__init__(llm: ChatOpenAI, tools: list, prompt: PromptTemplate)`
    - `run(test_files: list[str], project_name: str, output_dir: str) -> dict[str, str]`

  **Must NOT do**:
  - Do NOT assume GitHub Actions runner has specific software (use setup-* actions)
  - Do NOT generate platform-specific paths (use CMake's platform detection)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Must generate valid CI/CD configs with correct GitHub Actions syntax
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: Tasks 18, 19 (app.py, CI/CD verification)
  - **Blocked By**: Tasks 8, 10, 14 (tools + prompts + code gen output)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: CI workflow YAML is valid
    Tool: Bash
    Preconditions: CI/CD gen chain run
    Steps:
      1. python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('Valid YAML')"
    Expected Result: Valid YAML
    Evidence: .omo/evidence/task-15-ci-yaml.txt

  Scenario: CMakeLists.txt includes GTest FetchContent
    Tool: Bash
    Preconditions: CI/CD gen chain run
    Steps:
      1. grep -q "FetchContent\|find_package(GTest\|find_package(gtest" CMakeLists.txt && echo "GTest included"
    Expected Result: GTest included
    Evidence: .omo/evidence/task-15-cmake.txt
  ```

  **Commit**: YES
  - Message: `feat(chains): add CI/CD config generator agent chain`

- [x] 16. **agents/chains/report_chain.py — Report Generator Agent**

  **What to do**:
  - Create `agents/chains/report_chain.py` as a LangChain chain
  - Report Generator pipeline:
    1. Receives all previous stage outputs from PipelineMemory
    2. Calls LLM with report prompt to generate:
       - `report.md` — Human-readable markdown report:
         - SDK overview (headers scanned, APIs found)
         - Analysis summary (complexity, patterns)
         - Test case summary (counts, coverage estimates)
         - Generated files manifest
         - CI/CD build instructions
       - `report.json` — Machine-readable JSON report:
         - All stage outputs serialized
         - Metadata (timestamp, model used, config hash)
    3. Uses `write_report_file` tool to save files
    4. Returns dict with report paths
  - `ReportChain` class:
    - `__init__(llm: ChatOpenAI, tools: list, prompt: PromptTemplate)`
    - `run(stage_outputs: dict, output_dir: str) -> dict[str, str]`

  **Must NOT do**:
  - Do NOT generate screenshots or HTML (Markdown + JSON only)
  - Do NOT repeat raw data verbatim (synthesize insights)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Needs to synthesize multi-stage data into clear reports
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 18 (app.py needs report output)
  - **Blocked By**: Tasks 8, 10, 14 (tools + prompts + code gen output)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Report generates valid Markdown
    Tool: Bash
    Preconditions: All prior stages complete
    Steps:
      1. python -c "from agents.chains.report_chain import ReportChain; from agents.llm import LLMWrapper; llm=LLMWrapper({'llm_model':'kimi-k2.5'}); chain=ReportChain(llm); paths=chain.run({'scanner':{},'analyzer':{},'designer':{},'code_gen':{}}, output_dir='output/report'); print(f'report paths: {paths}')"
    Expected Result: Paths to report.md and report.json
    Evidence: .omo/evidence/task-16-report.txt

  Scenario: report.json is valid JSON
    Tool: Bash
    Preconditions: Report generated
    Steps:
      1. python -c "import json; json.load(open('output/report/report.json')); print('Valid JSON')"
    Expected Result: Valid JSON
    Evidence: .omo/evidence/task-16-json.txt
  ```

  **Commit**: YES
  - Message: `feat(chains): add report generator agent chain`

- [x] 17. **agents/pipeline.py — Pipeline Orchestrator**

  **What to do**:
  - Create `agents/pipeline.py` as the main LangChain pipeline orchestrator
  - `Pipeline` class:
    - `__init__(config: dict)` — Initialize LLM, memory, cache, all 6 chains
    - `get_stages() -> list[str]` — Returns stage names in order
    - `run(sdk_root: str, output_root: str, no_cache: bool = False) -> dict` — Execute full pipeline:
      1. Scanner → APIInventory
      2. Analyzer → AnalysisReport
      3. Designer → TestCaseCollection
      4. CodeGen → list[file_paths]
      5. CIGen → CI/CD config files
      6. Report → report paths
    - `run_stage(stage_name: str, **kwargs) -> dict` — Execute single stage (for resumability)
    - Error handling: if a stage fails, log error and allow retry
    - Progress reporting: callback/invoke hook for CLI output
  - Each stage result is stored in PipelineMemory
  - Cache check before each stage (skip if cached)

  **Must NOT do**:
  - Do NOT run stages in parallel (sequential pipeline with data dependencies)
  - Do NOT swallow errors (each stage failure should be reported clearly)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Main orchestrator coordinating all 6 agents with proper error handling
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (orchestrator unifies all chains)
  - **Parallel Group**: Sequential (after all chains built)
  - **Blocks**: Task 18 (app.py needs pipeline)
  - **Blocked By**: Tasks 11, 12, 13, 14, 15, 16 (all chains)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: Pipeline initializes all 6 stages
    Tool: Bash
    Preconditions: All chains implemented
    Steps:
      1. python -c "from agents.pipeline import Pipeline; p=Pipeline({'llm_model':'kimi-k2.5'}); stages=p.get_stages(); print(f'stages={stages}')"
    Expected Result: 6 stages listed
    Evidence: .omo/evidence/task-17-stages.txt

  Scenario: Pipeline dry-run reports readiness
    Tool: Bash
    Preconditions: All chains implemented
    Steps:
      1. python -c "from agents.pipeline import Pipeline; p=Pipeline({'llm_model':'kimi-k2.5'}); status=p.dry_run(); print(f'ready={all(status.values())}')"
    Expected Result: True (all stages report ready)
    Evidence: .omo/evidence/task-17-dryrun.txt
  ```

  **Commit**: YES
  - Message: `feat(pipeline): add pipeline orchestrator with 6 stages`

- [x] 18. **app.py — New CLI Entry Point**

  **What to do**:
  - Rewrite `app.py` as the CLI entry point for the LangChain pipeline
  - Preserve CLI interface from old app.py:
    - `--config` (path to YAML config)
    - `--sdk-root` (override SDK root)
    - `--output-root` (override output root)
    - `--llm-enabled` (enable LLM)
    - `--no-cache` (disable cache)
    - `--no-build` (skip CI/CD generation — only generate test code)
    - `--no-test` (skip report generation)
    - `--dry-run` (validate pipeline without executing LLM calls)
    - `--stage` (run specific stage, for resumability)
  - New functionality:
    - Initialize Pipeline from config
    - Execute pipeline stages with progress output
    - Handle errors gracefully with clear messages
    - Print summary at end with output paths

  **Must NOT do**:
  - Do NOT import from deleted modules (generators, parsers, runners, etc.)
  - Do NOT include WebUI integration or tkinter dialogs

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Main entry point that must handle all CLI args, config loading, and pipeline execution
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs pipeline orchestrator)
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 21 (integration test)
  - **Blocked By**: Task 17 (pipeline orchestrator)

  **Acceptance Criteria**:

  **QA Scenarios**:
  ```
  Scenario: CLI help displays all options
    Tool: Bash
    Preconditions: app.py exists
    Steps:
      1. python app.py --help
    Expected Result: Shows all CLI arguments with descriptions
    Evidence: .omo/evidence/task-18-help.txt

  Scenario: Dry-run validates without LLM calls
    Tool: Bash
    Preconditions: All pipeline code exists
    Steps:
      1. python app.py --config config/scivision_config.yaml --dry-run
    Expected Result: Pipeline validates, exit code 0, no LLM calls made
    Evidence: .omo/evidence/task-18-dryrun.txt

  Scenario: No imports from deleted modules
    Tool: Bash
    Preconditions: app.py written
    Steps:
      1. grep -c "from generators\|from parsers\|from runners\|from repair\|from planners\|from knowledge\|from utils\|from WebUI\|tkinter\|fastapi\|uvicorn\|jinja2" app.py
    Expected Result: 0 (zero imports from deleted code)
    Evidence: .omo/evidence/task-18-imports.txt
  ```

  **Commit**: YES
  - Message: `feat(cli): add new LangChain pipeline CLI entry point`

- [x] 19. **.github/workflows/ci.yml — GitHub Actions CI/CD Pipeline**

  **What to do**:
  - Create `.github/workflows/ci.yml` with a GitHub Actions workflow:
    ```yaml
    name: GTest Compilation and Test
    on: [push, pull_request, workflow_dispatch]
    jobs:
      build-and-test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - name: Install deps
            run: sudo apt-get update && sudo apt-get install -y cmake ninja-build g++
          - name: Configure
            run: cmake -B build -G Ninja -DCMAKE_CXX_STANDARD=17
          - name: Build
            run: cmake --build build
          - name: Test
            run: ctest --test-dir build --output-on-failure
          - name: Upload results
            uses: actions/upload-artifact@v4
            with:
              name: test-results
              path: build/Testing/
    ```
  - GTest fetched via CMake FetchContent (no precompiled binaries)
  - Include `workflow_dispatch` trigger for manual runs

  **Must NOT do**:
  - Do NOT use Windows-specific paths/actions

  **Recommended Agent Profile**: Category: quick. Skills: []
  **Parallelization**: Wave 4, Blocked By: Task 14

  **QA Scenarios**:
  ```
  Scenario: CI workflow is valid YAML
    Tool: Bash
    Steps: python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('Valid')"
    Evidence: .omo/evidence/task-19-yaml.txt

  Scenario: Workflow has cmake and ctest
    Tool: Bash
    Steps: grep -q "cmake\|ctest" .github/workflows/ci.yml && echo "OK"
    Evidence: .omo/evidence/task-19-steps.txt
  ```
  **Commit**: YES (groups with Task 20), Message: `feat(ci): add GitHub Actions workflow and Dockerfile`

- [x] 20. **Dockerfile — Local Build Environment**

  **What to do**:
  - Create Dockerfile for local build verification:
    ```dockerfile
    FROM ubuntu:22.04
    RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y cmake ninja-build g++ python3 python3-pip git
    WORKDIR /app
    COPY . .
    RUN pip install -r requirements.txt
    ENTRYPOINT ["python3", "app.py"]
    ```
  - Usable for: `docker build -t sdk-test-agent .` and `docker run sdk-test-agent --config config/scivision_config.yaml --llm-enabled`

  **Recommended Agent Profile**: Category: quick. Skills: []
  **Parallelization**: Wave 4, Blocked By: Task 14

  **QA Scenarios**:
  ```
  Scenario: Dockerfile builds without error
    Tool: Bash
    Steps: docker build -t sdk-test-agent:test . 2>&1 | tail -5
    Expected: Image built successfully
    Evidence: .omo/evidence/task-20-docker.txt
  ```
  **Commit**: YES (groups with Task 19)

- [x] 21. **End-to-End Integration Test**

  **What to do**:
  - Create test script that validates full pipeline:
    1. Clean project structure (no deleted files remain)
    2. All Python files compile
    3. Pipeline initializes with 6 stages
    4. CLI accepts all expected arguments
    5. Dry-run mode works without LLM calls
    6. Cache layer works (set + get + miss)
    7. PipelineMemory stores/retrieves all stage outputs
    8. ir/ schemas serialize/deserialize correctly
    9. No imports from deleted modules
    10. LangChain-based (no urllib references)

  **Recommended Agent Profile**: Category: unspecified-high. Skills: []
  **Parallelization**: Wave 4, Blocked By: Tasks 18, 19, 20
  **Commit**: YES, Message: `test: add end-to-end integration tests`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`

  **What to do**: Read the plan end-to-end. Verify all "Must Have" items are implemented. Check all "Must NOT Have" items are absent. Verify cleanup was done correctly (no GTest, ninja, WebUI, generators, etc. left behind). Check evidence files exist in `.omo/evidence/`.

  **Output**: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality + Build Verification** — `unspecified-high`

  **What to do**: Run `python -m py_compile *.py agents/**/*.py` for syntax check. Verify there are no imports from deleted modules. Check for any remaining references to generators, runners, parsers, etc. Verify `requirements.txt` has valid LangChain dependencies.

  **Output**: `Syntax [PASS/FAIL] | Imports [CLEAN/ISSUES] | Deps [PASS/FAIL] | VERDICT`

- [x] F3. **Real Manual QA — Pipeline Execution** — `unspecified-high`

  **What to do**: Run `python app.py --help` to verify CLI works. Run Python verification: `python -c "from agents.pipeline import Pipeline; p = Pipeline(); print(p.get_stages())"`. Check generated output files have correct structure. Verify LangChain agents can initialize and produce structured output.

  **Output**: `CLI [PASS/FAIL] | Pipeline Init [PASS/FAIL] | Stage Generation [N/N] | VERDICT`

- [x] F4. **Scope Fidelity + Cleanup Verification** — `deep`

  **What to do**: For each task in TODOs: read "What to do", verify actual implementation matches. Check no deleted directories remain. Confirm CI/CD workflow references correct files and is runnable. Detect any cross-task contamination.

  **Output**: `Tasks [N/N compliant] | Cleanup [CLEAN/ISSUES] | CI/CD [VALID/INVALID] | VERDICT`

---

## Commit Strategy

- **Task 1**: `cleanup: remove all non-AI code and junk files`
- **Tasks 2-6**: `feat(langchain): add LLM wrapper, cache, memory, and dependencies`
- **Tasks 7-10**: `feat(agents): add tools, prompts, and agent infrastructure`
- **Tasks 11-17**: `feat(agents): add 6 LangChain pipeline agents and orchestrator`
- **Tasks 18-21**: `feat(pipeline): add CLI entry point, CI/CD, Dockerfile, and integration tests`

---

## Success Criteria

### Verification Commands
```bash
# Clean project structure
ls -d GoogleTest* ninja WebUI generators parsers planners runners repair knowledge templates docs exe_pack start_webui.bat 2>&1 | wc -l
# Expected: 0 (none of these exist)

# Pipeline imports cleanly
python -c "from agents.llm import LLMWrapper; from agents.pipeline import Pipeline; print('OK')"
# Expected: OK

# CLI works
python app.py --help
# Expected: Shows all CLI options

# Pipeline stages defined
python -c "from agents.pipeline import Pipeline; p = Pipeline(); print(len(p.get_stages()))"
# Expected: 6

# Full pipeline dry-run
python app.py --config config/scivision_config.yaml --llm-enabled --no-cache --dry-run
# Expected: All 6 stages reported as ready, exit code 0
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] Pipeline produces valid APIInventory, TestCaseCollection, GTest code
- [x] CI/CD workflow parses as valid YAML
- [x] No imports from deleted modules
- [x] LangChain-based (no urllib/raw HTTP calls)
- [x] All old agent code (tool_chat.py, session_manager.py, etc.) replaced
