# Release Notes — v3.6.2 (Chinese-First & Bilingual Comments)

Project conventions for testers and contributors in China.

## Highlights

### Agent 默认中文
- Forge Agent **默认用中文**回复用户（步骤、结论、排错说明）
- 用户仅在聊天中说「请用英文」「reply in English」时才切换英文
- 已写入 `forge.md`、`SKILL.md`、`docs/AGENTS.md`

### 代码中英文注释
- 新增 [docs/CONVENTIONS.md](docs/CONVENTIONS.md)
- 模块 docstring：英文一行 + 中文一行
- 核心模块已更新：`report`、`pipeline`、`session`、`workflow` 等

### 测试人员工作流（延续 v3.6.1）
- `build_tests` 仍自动生成 `.forge/cache/report.html`
- 返回 `html_path`，无需手动 `forge_report`

---

Release title: **v3.6.2 — Chinese-First & Conventions**
