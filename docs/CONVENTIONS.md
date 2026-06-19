# 项目约定 / Project Conventions

## 交流语言 / Communication Language

| 场景 | 语言 |
|------|------|
| Agent 对用户回复（说明、步骤、结论、排错） | **中文（默认）** |
| 用户明确要求英文时 | 英文（仅在聊天中说「请用英文」「reply in English」等） |
| 代码标识符、CLI、JSON 字段、路径、日志 | 英文 |
| 自动测试报告摘要（`build_auto_summary`） | 中文 |
| API / 发布说明 / README 技术段落 | 中英均可，面向开发者以英文为主 |

**Agent 规则：**

1. 默认用中文与用户交流。
2. 不要主动切换英文，除非用户在本轮对话中明确要求。
3. 引用命令、工具名、文件路径时保持原文，周围用中文解释。

---

## 代码注释 / Code Comments

新增或修改代码时，**优先写中英双语注释**：

```python
def build_pipeline_impl(...) -> dict:
    """Probe, compile, run; auto-write HTML report after build.
    探测、编译、运行；构建结束后自动写入 HTML 报告。
    """
```

| 位置 | 约定 |
|------|------|
| 模块顶部 docstring | 英文一行 + 中文一行 |
| 公共函数 / 类 | 双语简要说明 |
| 非显而易见的业务逻辑 | `# EN: ... / CN: ...` 或两行注释 |
| MCP 工具 `description` | 英文（OpenCode 工具列表） |
| MCP 参数 `Annotated` 说明 | 英文为主，可加中文括号补充 |

不必给每一行加注释；自解释代码保持简洁即可。

---

## 文档同步 / Doc Sync

修改 Agent 行为或工作流时，同步更新：

- `.opencode/agents/forge.md`
- `.opencode/skills/test-forge/SKILL.md`
- `docs/AGENTS.md`（提示词源文件）

OpenCode 全局 Agent：复制 `forge.md` 到 `~/.config/opencode/agents/forge.md` 后重启 OpenCode。
