# OpenCode Agent / Plugin 注册指南

> 以本仓库 (SDK Test Forge) 为例，详细说明如何在 OpenCode 中注册一个自定义 Agent。

---

## 目录

1. [概述：四种注册方式](#1-概述四种注册方式)
2. [方式一：plugin.yaml（项目级自动注册）](#2-方式一pluginyaml项目级自动注册)
3. [方式二：agents/*.md（YAML frontmatter 格式）](#3-方式二agentsmdyaml-frontmatter-格式)
4. [方式三：opencode.json agent 字段（用户级注册）](#4-方式三opencodejson-agent-字段用户级注册)
5. [方式四：opencode.json command 字段（斜杠命令）](#5-方式四opencodejson-command-字段斜杠命令)
6. [辅助文件说明](#6-辅助文件说明)
7. [FAQ](#7-faq)
8. [MCP 工具参数（v2.5）](#8-mcp-工具参数v25)

---

## 1. 概述：四种注册方式

| 方式 | 文件 | 作用范围 | 用途 |
|------|------|----------|------|
| **plugin.yaml** | 项目根目录 | 项目级（自动） | 注册 MCP 服务器 + Skill，项目打开时自动生效 |
| **agents/*.md** | `~/.config/opencode/agents/` 或 `<project>/.opencode/agents/` | 用户级 / 项目级 | 在 TUI 聊天窗口下拉框中出现可选 Agent |
| **opencode.json agent** | `~/.config/opencode/opencode.json` | 用户级（全局） | 注册 Agent 配置（提示词、工具权限等） |
| **opencode.json command** | `~/.config/opencode/opencode.json` | 用户级（全局） | 注册斜杠命令（`/xxx`）快捷入口 |

**推荐组合（本项目的做法）：**

```
plugin.yaml 或 opencode.json MCP  → 注册 sdk-test-forge MCP 工具
oh-my-openagent.json              → 配置 forge 模型（model、fallback）
.opencode/agents/forge.md         → Agent 出现在下拉选择框（mode: all）
docs/AGENTS.md                      → Agent 系统提示词源文件
```

> **注意**：TestAgent 是 Python MCP 插件，**不会**出现在 OpenCode 的 npm「插件」列表中。请在 MCP 列表中查找 `sdk-test-forge`，在 Agent 下拉框中查找 `forge`。

---

## 1.1 全局 MCP 注册（跨项目使用）

在 `~/.config/opencode/opencode.json` 中添加：

```json
{
  "mcp": {
    "sdk-test-forge": {
      "command": ["python", "C:/path/to/TestAgent/mcp_server.py"],
      "enabled": true,
      "type": "local"
    }
  }
}
```

Windows 示例：

```json
"command": ["python", "C:\\Users\\YOU\\AppData\\Roaming\\OpenCode\\plugins\\sdk-test-forge\\mcp_server.py"]
```

复制 `.opencode/agents/forge.md` 到 `~/.config/opencode/agents/forge.md`。

---

## 2. 方式一：plugin.yaml（项目级自动注册）

OpenCode 打开项目时，会自动检测根目录下的 `plugin.yaml` 并加载。

### 文件位置

```
<project-root>/plugin.yaml
```

### 格式

```yaml
# plugin.yaml
name: sdk-test-forge                          # 插件名称（唯一）
description: SDK Test Forge — auto-generate... # 插件描述
version: 2.5.0                                 # 版本号

# MCP 服务器配置（可选）
mcp:
  server: python mcp_server.py                 # 启动命令
  transport: stdio                             # 传输方式（stdio / sse）

# Skills（可选）
skills:
  - name: test-forge                           # Skill 名称
    description: |
      Scan C/C++ SDK headers, design test cases,
      generate GTest code, compile, run...
```

### 本项目的实际文件

```yaml
# plugin.yaml
name: sdk-test-forge
description: SDK Test Forge — auto-generate GTest test suites from C/C++ SDK headers
version: 2.5.0

mcp:
  server: python mcp_server.py
  transport: stdio

skills:
  - name: test-forge
    description: |
      Scan C/C++ SDK headers, design test cases, generate GTest code,
      compile, run, and report results — all using OpenCode's built-in
      model. No external API keys required.
```

### 效果

- 项目在 OpenCode 中打开时**自动注册** MCP 服务器和 Skill
- 用户可在对话中通过 `task(load_skills=["test-forge"], ...)` 使用
- 无需手动配置任何全局文件

### Skill 文件配置

Skill 的详细工作流定义在：

```
.opencode/skills/<skill-name>/SKILL.md
```

本项目：

```
.opencode/skills/test-forge/SKILL.md
```

Skill 文件包含：触发条件、详细工作流（分步骤）、规则约束。

---

## 3. 方式二：agents/*.md（YAML frontmatter 格式）

> **前置条件**：已安装 `oh-my-openagent` 插件（在 `opencode.json` 的 `plugin` 列表中）。

### 文件位置

```
项目级：<project-root>/.opencode/agents/*.md
用户级：C:\Users\<用户名>\.config\opencode\agents\*.md
```

每个 `.md` 文件定义一个 Agent。OpenCode 启动时，OhMyOpenCode 插件会扫描这些目录，将所有 Agent 添加到 TUI 聊天窗口的 Agent 下拉选择框中。

> 项目级优先于用户级。两者同时存在时，项目级会覆盖用户级同名 Agent。

### YAML frontmatter 格式

```markdown
---
name: forge                                   # Agent 名称（出现在下拉框）
description: SDK 接口测试助手 - 自动生成...    # 简短描述
mode: all                                     # primary | subagent | all
color: "#4CAF50"                              # 标识颜色（十六进制）
---

（文件正文 = 系统提示词 / developer_instructions）

你是 SDK 接口测试助手。扫描 SDK 头文件，自动生成 GTest 测试用例...

## 工作流
1. 用 Glob + Read 扫描目标 SDK 的 .h 文件...
2. ...
```

### 命名规则

- 文件名 `forge.md` → Agent 名称为 `forge`
- 文件名 `my-agent.md` → Agent 名称为 `my-agent`

### 与本项目配合

本项目的 `.opencode/agents/forge.md` 文件内容：

```markdown
---
name: forge
description: SDK 接口测试助手 — 自动生成 GTest 测试用例，编译并运行
mode: all
color: "#4CAF50"
---

# Test Forge Agent
你是 SDK 接口测试助手。扫描 SDK 头文件，自动生成 GTest 测试用例，编译并运行。
...
```

> **注意**：`.md` 文件中不设 `model` 字段，模型配置由 `oh-my-openagent.json` 统一管理（见下文）。

### OhMyOpenCode JSON 模型配置

文件位置：

```
C:\Users\<用户名>\.config\opencode\oh-my-openagent.json
```

此文件为 OhMyOpenCode 插件的**模型配置中心**，可以为每个 Agent 指定使用的模型和 fallback 策略：

```json
{
  "agents": {
    "forge": {
      "model": "opencode/deepseek-v4-flash-free",
      "fallback_models": [
        "opencode/nemotron-3-ultra-free",
        "opencode/mimo-v2.5-free",
        "opencode/north-mini-code-free"
      ]
    }
  }
}
```

### 工作原理

```
.opencode/agents/forge.md    oh-my-openagent.json
      │                           │
      │  name / description        │  model / fallback
      │  prompt                    │
      │                           │
      └──────────┬────────────────┘
                 │
                 ▼
         OpenCode Agent "forge"
     (显示在下拉框中，使用指定模型)
```

**YAML frontmatter + JSON 互不冲突，各司其职：**

| 文件 | 负责 |
|------|------|
| `.opencode/agents/forge.md` | 身份定义（名称、描述、提示词） |
| `oh-my-openagent.json` | 模型选择（model + fallback） |

---

## 4. 方式三：opencode.json agent 字段（用户级注册）

不需要 OhMyOpenCode 插件，直接在 `opencode.json` 中定义 Agent。

### 文件位置

```
C:\Users\<用户名>\.config\opencode\opencode.json
```

### 格式

```json
{
  "agent": {
    "test-forge": {
      "prompt": "你是 SDK 接口测试助手...",
      "description": "SDK 接口测试助手",
      "mode": "all",
      "color": "#4CAF50",
      "model": "opencode/deepseek-v4-flash-free",
      "tools": {
        "read": true,
        "write": true,
        "edit": true,
        "glob": true,
        "bash": true,
        "grep": true,
        "task": true
      }
    }
  }
}
```

### AgentConfig 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `prompt` | string | **系统提示词**（Agent 行为定义） |
| `description` | string | 简短描述，显示在 UI 中 |
| `mode` | `"primary"` / `"subagent"` / `"all"` | Agent 可见性与调用方式 |
| `color` | string | 十六进制颜色，用于标识 |
| `temperature` | number | 模型温度参数 |
| `model` | string | 指定模型（格式：`provider/model`） |
| `tools` | `{ [key]: boolean }` | 工具权限映射 |
| `permission` | object | 工具权限策略 |
| `maxSteps` | number | 最大推理步骤 |

### 效果

- 重启 OpenCode 后，Agent 会出现在可用 Agent 列表中
- Agent 名称 = 配置键名（如上例为 `test-forge`）

---

## 5. 方式四：opencode.json command 字段（斜杠命令）

在 `opencode.json` 中注册斜杠命令，快速切换 Agent。

### 格式

```json
{
  "command": {
    "forge": {
      "template": "帮我测试 {sdk_path} 的接口",
      "description": "SDK Test Forge — 生成 GTest 测试",
      "agent": "forge"
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `template` | string | 命令模板（`{param}` 为参数占位符） |
| `description` | string | 命令描述 |
| `agent` | string | 指向已注册的 Agent |
| `model` | string | 可选，指定模型 |
| `subtask` | boolean | 是否作为子任务执行 |

### 效果

- 输入 `/forge /path/to/sdk` 快速调用 Agent
- 适合常用操作的快捷入口

---

## 6. 辅助文件说明

### AGENTS.md（Agent 提示词源文件）

```
<project-root>/docs/AGENTS.md
```

**此文件不是 OpenCode 直接加载的配置文件**，而是 Agent 系统提示词（`developer_instructions`）的源材料。

当你需要注册 Agent 时，将 `AGENTS.md` 的内容复制到：
- `.md` 文件的文件正文（YAML frontmatter 下方，方式二）
- `opencode.json` 的 `prompt` 字段（方式三）

**语言约定：** Agent 默认中文回复；用户仅在聊天中明确要求时才用英文。详见 [CONVENTIONS.md](CONVENTIONS.md)。

### .opencode/skills/<name>/SKILL.md（Skill 定义）

```
<project-root>/.opencode/skills/test-forge/SKILL.md
```

Skill 是 OpenCode 的**任务级复用单元**，通过 `plugin.yaml` 的 `skills` 字段注册后，可在对话中使用：

```
task(load_skills=["test-forge"], prompt="generate tests for /path/to/sdk")
```

Skill 文件一般包含：
- 触发条件（When to Use）
- 详细工作流（Workflow，分步骤）
- 规则约束（Rules）

---

## 7. FAQ

### Q: 这四种方式需要全用吗？

**不需要**。按需组合：

| 目标 | 必须 |
|------|------|
| 项目自动注册 MCP + Skill | `plugin.yaml` |
| Agent 出现在下拉选择框 | `.opencode/agents/*.md` + `oh-my-openagent.json` |
| 仅通过 `task()` 使用 | `plugin.yaml` 的 skill 注册即可 |
| 斜杠命令快捷入口 | `opencode.json` 的 `command` 字段 |

### Q: 重启后看不到 Agent？

排查步骤：
1. 确认 `oh-my-openagent` 在 `opencode.json` 的 `plugin` 列表中
2. 确认 `.opencode/agents/forge.md` 语法正确（YAML frontmatter 格式）
3. 确认 `oh-my-openagent.json` 中 agent 名称与 `.md` 文件中的 `name` 一致
4. 确认文件位置正确：项目级在 `.opencode/agents/`，用户级在 `~/.config/opencode/agents/`
5. **完全重启 OpenCode**（不是关闭窗口，而是退出进程重开）

### Q: 模型配置冲突了怎么办？

**优先级**（从高到低）：
1. `oh-my-openagent.json`（OhMyOpenCode 插件）
2. `opencode.json` 的 `agent` 字段
3. `.md` 文件中的 `model` 字段（YAML frontmatter）

建议：**只在 `oh-my-openagent.json` 中配置模型**，`.md` 文件中不设 `model` 字段。

### Q: 如何在对话中切换到这个 Agent？

在 OpenCode TUI 界面中：
- 点击输入框上方的 Agent 选择器下拉框
- 或者直接输入 `/forge`（如果配置了 command）
- 或者通过 `task()` 使用 skill

---

## 8. MCP 工具参数（v3.0）

| 工具 | 关键参数 | 说明 |
|------|----------|------|
| `scan_headers` | `use_cache` | 默认 true；`FORGE_SCAN_CACHE` 覆盖目录 |
| `compile_tests` | `coverage`, `hints` | 失败时 JSON 含 `hints` 建议数组 |
| `generate_mocks` | `scan_json`, `class_name` | 输出 `mock_<Class>.hpp` |
| `collect_coverage` | `build_dir`, `source_dir` | Linux gcov/lcov |

CLI：`forge compile --from-probe <sdk_root>` 自动填充 probe 参数。

环境变量：`FORGE_GTEST_CACHE`、`FORGE_SCAN_CACHE`、`LIBCLANG_PATH`（Windows libclang）。
