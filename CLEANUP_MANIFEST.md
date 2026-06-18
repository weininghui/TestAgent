# Cleanup Manifest — AI Agent Project

## Deleted Non-AI Directories

| Directory | Size | Reason |
|-----------|------|--------|
| `GoogleTest1.17.0/` | ~600 MB | Precompiled GTest — CI/CD handles via FetchContent |
| `GoogleTest1.8.1/` | ~600 MB | Precompiled GTest — CI/CD handles via FetchContent |
| `ninja/` | ~5 MB | Build tool — CI/CD installs via apt |
| `parsers/` | ~200 KB | libclang header parser — AI reads headers directly |
| `generators/` | ~150 KB | Code/CMake/report generators — AI generates via LangChain |
| `planners/` | ~80 KB | Test case planners — AI plans via LangChain |
| `runners/` | ~120 KB | Build/test execution — CI/CD handles compilation |
| `repair/` | ~100 KB | Compile error repair — AI handles via LangChain agent loop |
| `knowledge/` | ~50 KB | Knowledge base — AI has built-in knowledge |
| `utils/` | ~400 KB | Utilities — replaced by new agents/infrastructure |
| `WebUI/` | ~500 KB | FastAPI web interface — removed per user request |
| `templates/` | ~50 KB | Jinja2 templates — AI generates directly |
| `exe_pack/` | ~30 KB | EXE packaging — removed per user request |
| `docs/` | ~200 KB | Documentation — regenerated as needed |

## Deleted Individual Files

| File | Reason |
|------|--------|
| `project_architecture.md` | Outdated architecture doc |
| `INTEGRATION_VERIFICATION.md` | Outdated verification doc |
| `start_webui.bat` | WebUI entry point |
| `LICENSE` | Removed per user request |

## Deleted Legacy Agents Files

These old `agents/` files were replaced by LangChain-based implementations:

| File | Replacement |
|------|-------------|
| `agents/agent_prompts.py` | `agents/prompts/*.py` (6 prompt templates) |
| `agents/llm_client.py` | `agents/llm.py` (LangChain ChatOpenAI wrapper) |
| `agents/readonly_tools.py` | `agents/tools/sdk_tools.py`, `agents/tools/file_tools.py` |
| `agents/session_manager.py` | LangChain context management + `agents/cache.py` |
| `agents/shared_memory.py` | `agents/memory.py` (PipelineMemory) |
| `agents/test_agent.py` | `agents/pipeline.py` (Pipeline orchestrator) |
| `agents/tool_chat.py` | LangChain @tool decorators + AgentExecutor |

## Retained Directories

| Directory | Purpose |
|-----------|---------|
| `agents/` | LangChain-based AI agents (tools, chains, prompts, LLM, cache, memory, pipeline) |
| `ir/` | Data schemas (APIInventory, TestCaseCollection, ContractInfo) |
| `output/` | Pipeline output directory |

## Post-Cleanup Changes

| Change | Date | Reason |
|--------|------|--------|
| `config/` removed | 2026-06 | Empty after `test_suggestions.md` deletion; no YAML config files remain — all config is Python-based via `PipelineConfig` |

## New Files Created

| File | Purpose |
|------|---------|
| `agents/llm.py` | LLMWrapper — LangChain ChatOpenAI with tenacity retry |
| `agents/cache.py` | LLMCache — SHA-256 disk-persisted cache |
| `agents/memory.py` | PipelineMemory — cross-stage output memory |
| `agents/pipeline.py` | Pipeline orchestrator — 6-chain sequential execution |
| `agents/tools/sdk_tools.py` | SDK header reading tools |
| `agents/tools/code_gen_tools.py` | GTest/CMake/report file writing tools |
| `agents/tools/file_tools.py` | General file I/O tools |
| `agents/chains/scanner_chain.py` | SDKScannerChain — header discovery + API extraction |
| `agents/chains/analysis_chain.py` | APIAnalysisChain — function/class pattern analysis |
| `agents/chains/test_design_chain.py` | TestDesignChain — test case generation |
| `agents/chains/code_gen_chain.py` | CodeGenChain — C++ GTest code generation |
| `agents/chains/ci_gen_chain.py` | CIGenChain — CMake + GitHub Actions generation |
| `agents/chains/report_chain.py` | ReportChain — Markdown/JSON report generation |
| `agents/prompts/*.py` | 6 prompt templates (one per pipeline stage) |
| `app.py` | Rewritten CLI entry point (LangChain Pipeline) |
| `.github/workflows/ci.yml` | GitHub Actions CI/CD workflow |
| `Dockerfile` | Build environment container |
| `tests/test_integration.py` | End-to-end integration tests |
| `requirements.txt` | Updated with LangChain dependencies |
