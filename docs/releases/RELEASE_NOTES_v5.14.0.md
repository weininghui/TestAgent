# Release Notes — v5.14.0

**Production reliability** — structured logging, audit trail, sub-agent auto-recovery, error codes.

## Added

| Feature | Description |
|---------|-------------|
| **`logging_config` / `trace` / `audit` / `response`** | Central logging, `run_id`, JSONL audit, MCP `forge_json()` |
| CLI **`--verbose`**, **`--log-file`**, **`forge health`** | Observability + cron-friendly health check |
| **`delegation/recovery.py`** | Auto-recovery with backoff + circuit breaker |
| MCP **`get_forge_audit_log`** | Read `audit.jsonl` |
| **`ForgeError`** + **`error_code`** | Structured build/delegation errors |
| **[docs/RELIABILITY.md](../RELIABILITY.md)** | Runbook |
| **`tests/test_reliability.py`** | Logging, auto-recovery, error tests |
| CI | pytest-cov 50% gate, Ruff blocking, macOS smoke |

## Changed

- **`poll_forge_delegations`** returns **`auto_recovered`** when `delegation_auto_recovery` is enabled
- Production profile: **`delegation_auto_recovery: true`**
- **`run_mcp.py`**: skill sync `test-forge` → **`sdk-forge`**
- MCP/CLI JSON includes **`run_id`**

## Config

```yaml
delegation_auto_recovery: true
delegation_auto_recovery_max: 2
delegation_retry_backoff_sec: 30
```

## Upgrade

```powershell
pip install -e .
python -c "import sdk_forge; print(sdk_forge.__version__)"   # 5.14.0
forge health --help
```

Fully restart OpenCode after plugin update.

## Tests

183+ passed (fast suite), 72% Python coverage on `sdk_forge`.
