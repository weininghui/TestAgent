# Release Notes — v5.4.0

Rebrand to **SDK Forge** — unified professional naming.

## Highlights

| Item | Old | New |
|------|-----|-----|
| GitHub repo | `weininghui/TestAgent` | **`weininghui/sdk-forge`** |
| OpenCode plugin | `sdk-test-forge` | **`sdk-forge`** |
| pip package | `sdk-test-forge` | **`sdk-forge`** |
| Brand | SDK Test Forge | **SDK Forge** |

**Unchanged:** Python module `sdk_forge`, CLI `forge`, Agent `forge`.

## GitHub repository rename (manual)

The code and docs use **`weininghui/sdk-forge`**. Rename the repository on GitHub:

1. Open https://github.com/weininghui/TestAgent/settings
2. **Repository name** → `sdk-forge` → Rename

Old clone URLs (`TestAgent.git`) redirect automatically. Then run:

```bash
git remote set-url origin https://github.com/weininghui/sdk-forge.git
```

## Migration

See [MIGRATION_v5.4.md](../MIGRATION_v5.4.md) or run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/migrate-rename-sdk-forge.ps1
```

```powershell
cd $env:APPDATA\OpenCode\plugins\sdk-forge
git fetch --tags; git checkout v5.4.0
pip uninstall sdk-test-forge -y
pip install -e .
```

Restart OpenCode. MCP list should show **sdk-forge**.

## Upgrade from v5.3

No API changes to MCP tools or orchestration. Only names and paths change.
