# Reliability Runbook / 可靠性运维手册

**English** | [中文](#中文)

## English

### Logging

- **CLI:** `forge --verbose build --project-dir ./my_tests` (DEBUG to stderr)
- **Log file:** `forge --log-file .forge/cache/forge.log build ...` or env `FORGE_LOG_FILE`
- **Level:** env `FORGE_LOG_LEVEL=DEBUG|INFO|WARNING`
- **Format:** `timestamp [logger] [run_id=forge_xxxxxxxx] LEVEL message`

### Correlation ID (`run_id`)

Every CLI command and MCP tool response includes `run_id` in JSON output. Use it to grep logs and audit events for one invocation.

### Audit trail

Events append to `{project_dir}/.forge/cache/audit.jsonl`:

| Event | Meaning |
|-------|---------|
| `stage_start` / `stage_end` | Pipeline stage boundaries |
| `delegation_register` | Sub-agent task registered |
| `health_issue` | Unhealthy pending delegation detected |
| `recovery` | Manual or auto recovery attempted |
| `error` | Recorded failure |

**Read audit:**

```bash
forge session --project-dir ./my_tests   # includes recent_audit
# MCP: get_forge_audit_log(project_dir, last_n=50)
```

### Sub-agent timeout playbook

**Automatic (production profile):**

1. `poll_forge_delegations` — if `auto_recovered` is non-empty, call `get_task_dispatch_plan` and re-dispatch `task()`
2. Or cron: `forge health --project-dir ./my_tests --auto-recover`

**Manual fallback:**

1. `check_subagent_health(include_preview=true)`
2. `recover_stalled_subagent(task_id=..., action=retry)`
3. `get_task_dispatch_plan` → tool-call `task` for retry
4. Or: `opencode run --session ses_xxx --continue`

**Config (`.forge.yaml` / `.forge.json`):**

```yaml
delegation_auto_recovery: true
delegation_auto_recovery_max: 2
delegation_retry_backoff_sec: 30
delegation_stale_sec: 900
```

Production profile sets `delegation_auto_recovery: true` by default.

### Common error codes

| Code | Stage | Action |
|------|-------|--------|
| `BUILD_LINK_ERROR` | build | Fix `--link` / include dirs; see `hints` |
| `SCAN_CLANG_FAILED` | scan | Retry with `--no-clang` or install libclang |
| `DELEGATION_RECOVERY_FAILED` | delegation | No pending task; check `poll_forge_delegations` |

### Cron example (health poll)

```bash
*/5 * * * * forge health --project-dir /path/to/tests --auto-recover --quiet
```

---

## 中文

### 日志

- **CLI：** `forge --verbose build --project-dir ./my_tests`
- **日志文件：** `--log-file` 或环境变量 `FORGE_LOG_FILE`
- **级别：** `FORGE_LOG_LEVEL=DEBUG|INFO|WARNING`

### 关联 ID（`run_id`）

CLI 与 MCP 的 JSON 响应均含 `run_id`，可用于关联日志与 audit 事件。

### 审计流

写入 `{project_dir}/.forge/cache/audit.jsonl`。通过 `forge session` 或 MCP `get_forge_audit_log` 查看最近事件。

### 子 Agent 超时

**自动（production）：** 轮询 `poll_forge_delegations`，若 `auto_recovered` 非空则 `get_task_dispatch_plan` 重派；或 `forge health --auto-recover`。

**手动：** `check_subagent_health` → `recover_stalled_subagent(action=retry)` → 重派 `task()`。

### 限制

无 OpenCode 时 CLI fallback 仅支持到 scaffold；完整多 Agent 编排需 OpenCode + MCP。
