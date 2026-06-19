# Plan: Register Forge Agent (Correct YAML Frontmatter Format)

## TL;DR

> Fix the agent registration after discovering OhMyOpenCode only loads `.md` files with YAML frontmatter from the `agents/` directory — not `.toml` files.
>
> **Deliverables**:
> - Create `.opencode/agents/forge.md` with correct format
> - Update `REGISTER_AGENT.md` to reflect correct approach
>
> **Estimated Effort**: Short
> **Parallel Execution**: None (sequential)
> **Critical Path**: Task 1 → Task 2

---

## Context

### Problem
OhMyOpenCode plugin reads agent definitions from:
- Global: `~/.config/opencode/agents/*.md`
- Project: `<project>/.opencode/agents/*.md`

It filters ONLY `.md` files via `isMarkdownFile()`, then parses YAML frontmatter + body (body becomes `developer_instructions`/prompt).

The `.toml` file we created earlier was completely ignored. The correct format is a `.md` file with YAML frontmatter.

### What's Already Done
- `forge.toml` deleted from `~/.config/opencode/agents/`
- `.opencode/agents/` directory created

### What Remains
1. Create `.opencode/agents/forge.md` with YAML frontmatter
2. Update `REGISTER_AGENT.md` to fix TOML → Markdown documentation

---

## Verification Strategy

> **Zero human intervention** — all verification agent-executed.

### QA Policy
- **File existence**: Verify `.opencode/agents/forge.md` exists and has valid YAML frontmatter
- **REGISTER_AGENT.md**: Verify TOML references are corrected to Markdown+YAML

---

## TODOs

- [ ] 1. Create `.opencode/agents/forge.md`

  **What to do**:
  - Create file at `E:\vs_test\AINew\aiagent-main\.opencode\agents\forge.md`
  - Use this exact content:

  ```markdown
  ---
  name: forge
  description: SDK 接口测试助手 — 自动生成 GTest 测试用例，编译并运行
  mode: edit
  color: "#4CAF50"
  ---

  # Test Forge Agent

  你是 SDK 接口测试助手。扫描 SDK 头文件，自动生成 GTest 测试用例，编译并运行。

  ## 工作流

  1. 用 Glob + Read 扫描目标 SDK 的 .h 文件，识别公开 API（函数、类、枚举）
  2. 为每个 API 设计测试用例（正常输入、边界值、异常输入、类型组合）
  3. 检查目标项目是否存在旧测试文件（GTest），如存在先删除
  4. 用 Write 生成新的 GTest .cpp 测试文件
  5. 用 Bash 编译测试文件（g++/cmake + -lgtest）
  6. 用 Bash 运行生成的可执行文件
  7. 输出测试报告

  ## MCP 工具（如可用）

  - `scan_headers(sdk_root)` → 读取 .h 文件内容
  - `delete_tests(test_dir)` → 删除测试文件
  - `compile_tests(source_dir)` → 编译 GTest
  - `run_tests(test_binary)` → 运行并解析输出

  ## 规则

  - 只测试公开 API（非 static/noncopyable）
  - 不修改任何 SDK 源文件
  - 测试文件输出到独立目录
  ```

  **Must NOT do**:
  - Do NOT create `.toml` files — OhMyOpenCode ignores them
  - Do NOT modify `oh-my-openagent.json`
  - Do NOT modify `opencode.json`

  **Recommended Agent Profile**: `quick` — single file creation

  **Parallelization**:
  - Can Run In Parallel: NO
  - Blocks: Task 2
  - Blocked By: None

  **Acceptance Criteria**:
  - [ ] File exists at `.opencode/agents/forge.md`
  - [ ] YAML frontmatter is valid (`---` delimiters present, `name: forge` present)
  - [ ] Body contains AGENTS.md content

  **QA Scenarios**:
  ```
  Scenario: Verify file exists and has correct format
    Tool: Bash (Read file)
    Steps:
      1. Read `.opencode/agents/forge.md`
      2. Check first 4 lines contain valid YAML frontmatter
      3. Verify `name: forge` present in frontmatter
    Expected Result: File exists, YAML frontmatter valid, name field is "forge"
    Evidence: .omo/evidence/task-1-verify-forge-md.txt
  ```

- [ ] 2. Update `REGISTER_AGENT.md` to correct format

  **What to do**:
  - Read `REGISTER_AGENT.md` at project root
  - Find all references to `agents/*.toml` and replace with `agents/*.md` (YAML frontmatter)
  - Update the "方式二" section to describe the correct `.md` + YAML frontmatter format
  - Update the FAQ section
  - Remove any incorrect TOML examples

  **Specific changes needed**:
  1. In the overview table: change `agents/*.toml` → `agents/*.md`
  2. In section 3 title: change `agents/*.toml` → `agents/*.md`
  3. Replace the TOML example with YAML frontmatter example
  4. Update the file location path from `~/.config/opencode/agents/*.toml` → 
     - Global: `~/.config/opencode/agents/*.md`
     - Project: `<project>/.opencode/agents/*.md`
  5. Remove "TOML 格式" section, replace with "Markdown + YAML Frontmatter 格式"
  6. Update the JSON example if needed
  7. FAQ: update any references to `.toml`

  **Must NOT do**:
  - Do not change the structure/section numbering
  - Do not rewrite unrelated sections
  - Keep all working content about plugin.yaml, opencode.json, command

  **Recommended Agent Profile**: `quick` — single file edit

  **Parallelization**:
  - Can Run In Parallel: NO
  - Blocks: None
  - Blocked By: Task 1

  **Acceptance Criteria**:
  - [ ] No `.toml` references remain in the TOML-based sections
  - [ ] YAML frontmatter example shown for `.md` files
  - [ ] File location paths mention both global and project scope

  **QA Scenarios**:
  ```
  Scenario: Verify REGISTER_AGENT.md has correct format
    Tool: Bash (grep)
    Steps:
      1. grep for `.toml` in REGISTER_AGENT.md — should have zero results in agent format sections
      2. grep for `.md` in REGISTER_AGENT.md — should show agent format references
    Expected Result: No artifact .toml references in agent registration sections
    Evidence: .omo/evidence/task-2-verify-register-md.txt
  ```

---

## Success Criteria

### Final Checklist
- [ ] `.opencode/agents/forge.md` exists with valid YAML frontmatter
- [ ] `REGISTER_AGENT.md` correctly describes `.md` + YAML frontmatter format
- [ ] OhMyOpenCode will load forge as available agent on next restart
