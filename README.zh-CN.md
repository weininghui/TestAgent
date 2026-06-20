# SDK Forge

[English](README.md) | **简体中文**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/weininghui/TestAgent)](https://github.com/weininghui/TestAgent/releases)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

面向 C/C++ SDK 的 OpenCode 插件与 **独立 CLI**（`forge`）：扫描头文件、生成 GTest 用例、链接真实 SDK 编译运行，并输出 HTML 报告。

**当前版本：[v5.14.0](docs/releases/RELEASE_NOTES_v5.14.0.md)** — 生产级可靠性：日志、audit、子 Agent 自动恢复。

上一版：[v5.10.0](docs/releases/RELEASE_NOTES_v5.10.0.md) — 仅保留 OpenCode `task()` 派发，对齐 GUI Task 卡片。

## 功能概览

1. **探测** SDK 目录结构（include / lib / pkg-config）
2. **扫描** 头文件（可选 libclang + 正则回退）
3. **规划并生成** GTest / GMock（智能 scaffold + Agent 补全）
4. **质量门禁** — 占位符比例、断言评分、Golden oracle
5. **编译运行** — CMake 构建；失败时返回结构化 JSON 与 CMake 提示

可作为 **OpenCode MCP 插件**（`sdk-forge`）或 **CLI** 用于脚本与 CI。

## 安装与更新

**分三块说明**（不要把「装 CLI」和「更新 OpenCode 插件」混在一起）：

| 场景 | 文档 |
|------|------|
| 仅 CLI（终端 / CI） | [docs/INSTALL.zh-CN.md §1](docs/INSTALL.zh-CN.md#1-仅安装-cli不用-opencode-插件) |
| OpenCode 插件 — **首次安装** | [docs/INSTALL.zh-CN.md §2](docs/INSTALL.zh-CN.md#2-opencode-插件--首次安装) |
| **更新**到最新版 | [docs/INSTALL.zh-CN.md §3](docs/INSTALL.zh-CN.md#3-更新到最新版本) |

English: [docs/INSTALL.md](docs/INSTALL.md)

**查版本（以运行时代码为准，不要只看 `pip show`）：**

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"   # 应与最新 Release 一致
forge autopilot --help                                       # v5.1+ 必须有 autopilot
```

OpenCode 插件目录（Windows）：`%APPDATA%\OpenCode\plugins\sdk-forge`

每次更新代码后：在该目录执行 `pip install -e .`，并 **完全重启 OpenCode**。

## 快速开始（CLI）

```bash
git clone https://github.com/weininghui/TestAgent.git
cd TestAgent
pip install -r requirements.txt
pip install -e .
```

完整 CLI 安装：[docs/INSTALL.zh-CN.md §1](docs/INSTALL.zh-CN.md#1-仅安装-cli不用-opencode-插件)。

**环境要求：** Python 3.10+、CMake 3.14+、C++ 编译器（g++/clang++/MSVC）。建议安装 `git` 以预拉取 GTest。

可选依赖：

```bash
pip install "sdk-forge[clang]"   # libclang 头文件解析
pip install "sdk-forge[yaml]"    # .forge.yaml（无 PyYAML 时可用 JSON）
```

## 快速开始（OpenCode Agent）

1. **安装插件** — [首次安装 §2](docs/INSTALL.zh-CN.md#2-opencode-插件--首次安装) 或 [更新 §3](docs/INSTALL.zh-CN.md#3-更新到最新版本)。
2. 在聊天窗口选择 Agent **`forge`**。
3. 输入：*「测试 `./examples/test_sdk_cpp`，给我 HTML 报告。」*

或使用 v5.1 Autopilot：*「对 `./examples/test_sdk_cpp` 运行 forge autopilot，production 配置。」*

Agent 注册细节：[docs/REGISTER_AGENT.md](docs/REGISTER_AGENT.md)。

编排器自动调度：`forge-env` → `forge-scan` → `forge-scaffold` → 并行 `forge-enrich` → `forge-review` → `forge-build`。

Agent 提示词：[`.opencode/agents/forge.md`](.opencode/agents/forge.md) · Skill：[`.opencode/skills/sdk-forge/SKILL.md`](.opencode/skills/sdk-forge/SKILL.md)

## Autopilot 一键流程（v5.1）

只需提供 SDK 路径，编排器自动推进全流程，enrich 失败时由 orchestration **自动重试**：

```bash
forge autopilot ./examples/test_sdk_cpp --profile production
# 或 MCP：run_forge_autopilot(sdk_root=..., profile=production)
```

| 阶段 | 行为 |
|------|------|
| init / env / scan / scaffold | 程序化执行（无 LLM） |
| enrich | Agent 执行 `next_actions`；断言门禁未通过时自动 re-dispatch weak 文件（最多 `max_enrich_rounds` 轮） |
| review → build | `forge-review` 后 `forge-build --profile production` |
| 构建后 | 可选从 `EXPECT_EQ` 自动 `golden snapshot` |

```yaml
# .forge.yaml Autopilot 选项（v5.1）
max_enrich_rounds: 3          # 默认 1 = v5.0 单轮行为
autopilot_profile: production
auto_golden_snapshot: true
```

## 生产级工作流（v5.0+）

需要可 merge 的测试质量时，使用 **production 配置**：

```bash
forge golden init --project-dir ./my_tests    # 生成 .forge/golden.yaml 模板
# 编辑 golden.yaml，填写核心 API 的预期值
forge assert-quality --project-dir ./my_tests
forge build --project-dir ./my_tests --profile production
```

| 门禁 | 检查内容 |
|------|----------|
| Scaffold 质量 | 占位符 / `// AGENT:` 比例 |
| 断言质量 | 弱断言、自比、`// AGENT:` 残留 |
| Golden oracle | `.forge/golden.yaml` 中的预期值 |
| 覆盖率（production） | 行覆盖率 ≥ 80%（Linux gcov） |

检查清单：[docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md)

### 示例 `.forge.yaml`

```yaml
sdk_root: ../examples/test_sdk_cpp
tests_dir: tests
build_dir: build

sdk_include_dirs:
  - ../examples/test_sdk_cpp/include
sdk_lib_dirs:
  - ../examples/test_sdk_cpp/build
link_libraries:
  - my_sdk

gtest_source: auto
gtest_version: auto

# 多 Agent enrich 批大小（v4.6）
multi_agent_batch_size: 4

# 生产 merge 门禁（v5.0）— 或使用 CLI：forge build --profile production
# forge_profile: production
# min_assertion_score: 80
# block_weak_tests: true
# block_agent_markers: true
```

JSON 配置示例：[`examples/forge_test_sdk/.forge.json`](examples/forge_test_sdk/.forge.json)

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `forge doctor` | 检查 cmake、编译器、缓存、GTest |
| `forge setup-toolchain --confirm` | 自动安装 MSVC / MinGW / g++（Agent 用 MCP `ensure_forge_environment`） |
| `forge init <dir>` | 初始化 `tests/`、`build/`、`.forge.yaml`、golden 模板 |
| `forge plan <sdk>` | 扫描并生成结构化测试方案 |
| `forge scaffold <sdk>` | 生成测试文件（`--fidelity smart`） |
| `forge enrich` | Agent 补全 brief（`--test-files` 分批） |
| `forge quality` | 占位符比例分析 |
| `forge assert-quality` | 语义断言质量评分（v5.0） |
| `forge golden init\|verify\|snapshot` | Golden 模板 / 验证 / 从测试快照（v5.1） |
| `forge autopilot <sdk>` | 一键 Autopilot 入口（v5.1） |
| `forge build` | 探测 + 编译 + 运行 + HTML 报告（`--profile production`、`--retry 3`） |
| `forge bench` | plan→scaffold→quality→build 基准测试 |
| `forge gap` | 方案 vs 测试 / 覆盖率缺口 |
| `forge analyze` / `propose-fix` / `apply-fix` | 失败分析与修复 |
| `forge report` | Markdown / HTML / JSON 报告 |
| `forge session` | 会话与编排上下文 JSON |
| `forge scan` / `probe` / `compile` / `run` / `coverage` / `mocks` / `clean` | 底层分步命令 |

所有命令向 stdout 输出 JSON。退出码：`0` 成功，`1` 测试失败，`2` 错误。

## MCP 工具（OpenCode / Cursor）

| MCP 工具 | CLI 等价 |
|----------|----------|
| `ensure_forge_environment` | `forge setup-toolchain` + doctor |
| `scan_headers` | `forge scan` |
| `suggest_test_plan` | `forge plan` |
| `generate_test_skeleton` | `forge scaffold` |
| `enrich_test_cases` | `forge enrich` |
| `analyze_assertion_quality` | `forge assert-quality` |
| `load_golden_cases` / `verify_golden_coverage` / `snapshot_golden_cases` | `forge golden` |
| `run_forge_autopilot` | `forge autopilot` |
| `build_tests` | `forge build` |
| `get_session_context` | `forge session`（含 `orchestration`） |
| `record_agent_run` | 多 Agent 完成状态 |
| `forge_report` | `forge report` |

完整列表与注册步骤：[REGISTER_AGENT.md](docs/REGISTER_AGENT.md)

## 多 Agent 架构（v4.6+，v5.10 仅 task() 派发）

编排器 **forge**（primary）通过 OMO **`task()`**（`get_task_dispatch_plan`）派发子 Agent，对齐 OpenCode GUI Task 卡片；并行 enrich 使用 `run_in_background=true`。详见 [docs/DELEGATION.md](docs/DELEGATION.md)。

| Agent | 职责 |
|-------|------|
| `forge`（primary） | 编排器 — 通过 `task()` 调度子 Agent |
| `forge-env` | 工具链 + 环境检查 |
| `forge-scan` | 扫描 + 测试方案 |
| `forge-scaffold` | 智能骨架生成 |
| `forge-enrich` | 并行补全 `// AGENT:` 标记 |
| `forge-review` | 生产就绪审查清单（v5.0） |
| `forge-build` | 编译、运行、修复循环 |

子 Agent 定义见 [`.opencode/agents/`](.opencode/agents/)。

## 示例 SDK

| 目录 | 说明 |
|------|------|
| [`examples/test_sdk/`](examples/test_sdk/) | C 库（`calc`） |
| [`examples/test_sdk_cpp/`](examples/test_sdk_cpp/) | C++ 命名空间、虚函数 |
| [`examples/test_sdk_medium/`](examples/test_sdk_medium/) | 多模块、`#ifdef`、pkg-config |
| [`examples/yaml_cpp_bench/`](examples/yaml_cpp_bench/) | 基准测试 fixture |
| [`examples/forge_test_sdk/`](examples/forge_test_sdk/) | 示例 `.forge.json` |

构建 fixture SDK：见 [examples/README.md](examples/README.md)。

## 项目结构

```
sdk-forge/
├── sdk_forge/          # Python 包（CLI + 核心逻辑）
├── mcp_server.py       # OpenCode MCP 入口
├── tests/              # pytest 测试
├── examples/           # 示例 SDK
├── docs/               # Agent 文档、发布说明、检查清单
├── .opencode/          # Agent 提示词 + Skill
├── plugin.yaml         # OpenCode 插件清单
└── README.md / README.zh-CN.md
```

## 能力矩阵

| 功能 | MCP | CLI | 版本 |
|------|-----|-----|------|
| Production 配置 | `build_tests(profile=production)` | `forge build --profile production` | v5.0 |
| 断言质量门禁 | `analyze_assertion_quality` | `forge assert-quality` | v5.0 |
| Golden oracle | `load_golden_cases` | `forge golden` | v5.0 |
| 多 Agent 编排 | `get_session_context` | — | v4.6 |
| 并行 enrich | `enrich_test_cases(test_files=...)` | `forge enrich --test-files` | v4.6 |
| 自动工具链 | `ensure_forge_environment` | `forge setup-toolchain --confirm` | v4.5 |
| 质量门禁 | `build_tests` | `forge build --skip-quality-gate` | v4.1 |
| 智能生成 + enrich | `generate_test_skeleton` / `enrich_test_cases` | `forge scaffold` / `forge enrich` | v4.0 |
| 会话 / 缺口 / 修复 | `get_session_context` / `analyze_plan_gap` | `forge session` / `forge gap` | v3.4 |
| HTML 报告 | `forge_report` | `forge report --format html` | v3.6 |
| GTest 自动下载 | compile JSON `gtest_tag` | `--gtest-source auto` | v3.1 |

完整历史见 [CHANGELOG.md](CHANGELOG.md)。

## 约定

- **Agent 回复：** 默认中文；在聊天中说「请用英文」可切换。
- **代码注释：** 公共 API 中英双语 — [docs/CONVENTIONS.md](docs/CONVENTIONS.md)。

## 开发

```bash
# 单元测试（无需 cmake）
python -m pytest tests/ -v -k "not TestCompileAndRun and not TestCliIntegration"

# 完整测试（需 cmake + 编译器）
python -m pytest tests/ -v
```

## 常见问题

| 现象 | 处理 |
|------|------|
| `cmake not found` | 安装 CMake 并加入 `PATH` |
| `compiler_not_found` | 运行 `forge setup-toolchain --confirm` 或 MCP `ensure_forge_environment` |
| `assertion_quality_blocked` | 运行 `forge assert-quality`；修复弱断言 / AGENT 标记 |
| `undefined reference` | 配置 `link_libraries`；运行 `forge probe` |
| GTest 下载失败 | 安装 git；`forge doctor`；固定 `gtest_version: 1.14.0` |
| 覆盖率不可用 | gcov 仅支持 Linux |
| libclang 漏符号 | 设置 `LIBCLANG_PATH`；添加 `compile_args: ["-DFEATURE_X"]` |

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/INSTALL.zh-CN.md](docs/INSTALL.zh-CN.md) | **安装与更新** OpenCode 插件 + CLI |
| [docs/INSTALL.md](docs/INSTALL.md) | Install & update (English) |
| [docs/REGISTER_AGENT.md](docs/REGISTER_AGENT.md) | OpenCode / MCP 注册指南 |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent 提示词源文件 |
| [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) | Merge 前检查清单 |
| [docs/releases/](docs/releases/) | 各版本发布说明 |
| [CHANGELOG.md](CHANGELOG.md) | 完整变更日志 |

## 发布

- [全部 Release](https://github.com/weininghui/TestAgent/releases)
- 最新：[RELEASE_NOTES_v5.14.0.md](docs/releases/RELEASE_NOTES_v5.14.0.md)

## 许可证

MIT — 见 [LICENSE](LICENSE)。
