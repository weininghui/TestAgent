# Install & Update — OpenCode Plugin & CLI

**English** | [简体中文](INSTALL.zh-CN.md)

This guide separates three topics:

| Section | When to use |
|---------|-------------|
| [1. CLI only](#1-cli-only-no-opencode-plugin) | Scripts, CI, terminal — no OpenCode |
| [2. OpenCode plugin — first install](#2-opencode-plugin-first-install) | First-time MCP + Agent setup |
| [3. Update to the latest release](#3-update-to-the-latest-release) | Already installed but version is old |

**Current release:** [v5.1.0](releases/RELEASE_NOTES_v5.1.0.md) — check [GitHub Releases](https://github.com/weininghui/TestAgent/releases) for the latest tag.

## Easiest workflows (recommended)

| Use case | Approach | When you update |
|----------|----------|-----------------|
| **One SDK / dev in this repo** | Open **TestAgent** in OpenCode (Option A) | `git pull` + **restart OpenCode** (`run_mcp.py` auto-pips) |
| **forge in every project** | Global plugin dir + one script | Run `scripts/update-opencode-plugin.ps1` + **restart OpenCode** |

`plugin.yaml` uses `python run_mcp.py`: on MCP start it **auto-checks** `mcp`/`pydantic` and `sdk_forge` version, and runs a silent `pip install -e .` if needed.  
You still must **restart OpenCode** (MCP does not hot-reload), but you usually **do not need manual pip**.

**Windows one-liner (global plugin dir):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/update-opencode-plugin.ps1
```

---

## Version numbers — read the right file

| Source | What it shows | Trust for features? |
|--------|---------------|---------------------|
| `python -c "import sdk_forge; print(sdk_forge.__version__)"` | **Runtime code version** | **Yes** |
| `plugin.yaml` → `version:` | OpenCode plugin manifest | Yes |
| `pip show sdk-test-forge` → `Version` | `pyproject.toml` package metadata | Only if `pyproject.toml` was updated with the release |
| GitHub Release tag | Official release | Yes |

If `pip show` says `4.0.0` but `sdk_forge.__version__` says `5.1.0`, your **code is new** but **package metadata is stale** — run `pip install -e .` again after updating files.

**v5.1+ smoke check:** these should exist after a correct install:

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"   # expect 5.1.0
forge autopilot --help                                         # subcommand must appear
python -c "import sdk_forge.autopilot"                           # module must import
```

In OpenCode MCP tool list, look for **`run_forge_autopilot`** and **`snapshot_golden_cases`**.

---

## 1. CLI only (no OpenCode plugin)

Use this when you only need the `forge` command in a terminal or CI job.

### Requirements

- Python 3.10+
- CMake 3.14+
- C++ compiler (g++/clang++/MSVC)
- `git` recommended (GTest prefetch)

### Install

```bash
git clone https://github.com/weininghui/TestAgent.git
cd TestAgent
pip install -r requirements.txt
pip install -e .

# Optional
pip install "sdk-test-forge[clang]"   # libclang header parsing
pip install "sdk-test-forge[yaml]"    # .forge.yaml support
```

### Verify

```bash
forge doctor
forge --help
```

---

## 2. OpenCode plugin — first install

OpenCode loads this project as a **Python MCP plugin** (`sdk-test-forge`). It does **not** appear in OpenCode’s npm plugin marketplace.

Choose **one** of the following:

### Option A — Open this repo as the project (simplest)

1. Clone the repo:

   ```bash
   git clone https://github.com/weininghui/TestAgent.git
   cd TestAgent
   ```

2. Install Python package (editable):

   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

3. Open the **TestAgent folder** in OpenCode.

4. OpenCode auto-loads root `plugin.yaml` → MCP server `python mcp_server.py`.

5. Copy or symlink agents (if not already in repo):

   - Agents live in `.opencode/agents/forge.md` and `forge-*.md` inside this repo.
   - For **global** use across all projects, also copy them to:

     ```
     %APPDATA%\OpenCode\agents\          # Windows
     ~/.config/opencode/agents/          # Linux / macOS
     ```

6. In OpenCode: select Agent **`forge`** in the chat dropdown; confirm MCP **`sdk-test-forge`** is enabled.

### Option B — Global plugin directory (use forge in any project)

Standard location on Windows:

```
%APPDATA%\OpenCode\plugins\sdk-test-forge
```

Full path example:

```
C:\Users\<YOU>\AppData\Roaming\OpenCode\plugins\sdk-test-forge
```

**Steps (Windows PowerShell):**

```powershell
$PluginDir = "$env:APPDATA\OpenCode\plugins\sdk-test-forge"
New-Item -ItemType Directory -Force -Path (Split-Path $PluginDir) | Out-Null

# First install: clone release tag
git clone --branch v5.1.0 --depth 1 https://github.com/weininghui/TestAgent.git $PluginDir

cd $PluginDir
pip install -r requirements.txt
pip install -e .

# Agent prompts (global)
$AgentsDir = "$env:APPDATA\OpenCode\agents"
New-Item -ItemType Directory -Force -Path $AgentsDir | Out-Null
Copy-Item -Force ".opencode\agents\forge*.md" $AgentsDir
```

**Linux / macOS:**

```bash
PLUGIN_DIR="$HOME/.config/opencode/plugins/sdk-test-forge"
mkdir -p "$(dirname "$PLUGIN_DIR")"
git clone --branch v5.1.0 --depth 1 https://github.com/weininghui/TestAgent.git "$PLUGIN_DIR"
cd "$PLUGIN_DIR"
pip install -r requirements.txt
pip install -e .
mkdir -p "$HOME/.config/opencode/agents"
cp .opencode/agents/forge*.md "$HOME/.config/opencode/agents/"
```

**Optional — register MCP in `opencode.json`** (if not using project-level `plugin.yaml`):

```json
{
  "mcp": {
    "sdk-test-forge": {
      "command": ["python", "C:/Users/YOU/AppData/Roaming/OpenCode/plugins/sdk-test-forge/mcp_server.py"],
      "enabled": true,
      "type": "local"
    }
  }
}
```

7. **Restart OpenCode completely** (quit app, not just close chat).

8. Verify (see [Version numbers](#version-numbers--read-the-right-file) above).

---

## 3. Update to the latest release

Use this when OpenCode still shows old tools (no `run_forge_autopilot`) or `sdk_forge.__version__` is below the [latest release](https://github.com/weininghui/TestAgent/releases).

> **Important:** Updating files alone is not enough. You must **`pip install -e .`** again and **restart OpenCode** so the MCP subprocess reloads.

### Path A — You installed via global plugin directory

Replace `v5.1.0` with the latest tag from GitHub Releases.

**Windows PowerShell:**

```powershell
$PluginDir = "$env:APPDATA\OpenCode\plugins\sdk-test-forge"
cd $PluginDir

# If directory is a git repo
git fetch --tags
git checkout v5.1.0

# If not using git: delete folder and re-clone (see Option B first install)

pip install -r requirements.txt
pip install -e . --force-reinstall

# Refresh agent prompts
Copy-Item -Force ".opencode\agents\forge*.md" "$env:APPDATA\OpenCode\agents\"

# Restart OpenCode completely
```

**Linux / macOS:**

```bash
PLUGIN_DIR="$HOME/.config/opencode/plugins/sdk-test-forge"
cd "$PLUGIN_DIR"
git fetch --tags
git checkout v5.1.0
pip install -r requirements.txt
pip install -e . --force-reinstall
cp .opencode/agents/forge*.md "$HOME/.config/opencode/agents/"
# Restart OpenCode
```

### Path B — You open the TestAgent repo as the project

```bash
cd /path/to/TestAgent
git fetch --tags
git checkout v5.1.0
pip install -r requirements.txt
pip install -e . --force-reinstall
# Restart OpenCode (or reopen the project)
```

### Path C — Sync from a local dev clone

If you develop in `E:\vs_test\AINew\aiagent-main` (or similar) and want OpenCode to use that copy:

**Windows:**

```powershell
$Src = "E:\vs_test\AINew\aiagent-main"
$Dst = "$env:APPDATA\OpenCode\plugins\sdk-test-forge"
robocopy $Src $Dst /MIR /XD .git build .forge __pycache__ .pytest_cache
cd $Dst
pip install -e . --force-reinstall
Copy-Item -Force ".opencode\agents\forge*.md" "$env:APPDATA\OpenCode\agents\"
```

### After every update — verify

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"
forge autopilot --help
pip show sdk-test-forge
```

| Check | Expected (v5.1.0) |
|-------|-------------------|
| `sdk_forge.__version__` | `5.1.0` |
| `forge autopilot --help` | Shows `autopilot` subcommand |
| MCP tools | `run_forge_autopilot`, `snapshot_golden_cases` |
| `pip show` Version | `5.1.0` (after `pip install -e .`) |

If version is still wrong:

1. Confirm `Editable project location` in `pip show` points to the directory you updated.
2. Run `pip install -e . --force-reinstall` in that directory.
3. Restart OpenCode (MCP runs as a child process; it does not hot-reload).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| AI says forge is `4.0.0` | Stale `pyproject.toml` or old editable install | Update repo + `pip install -e . --force-reinstall` |
| No `run_forge_autopilot` in MCP | Plugin directory not updated | Section 3 above |
| `forge` has no `autopilot` | CLI not reinstalled from new code | `pip install -e .` in plugin dir |
| MCP works in one project only | Project-level `plugin.yaml` only | Use Option B global plugin dir |
| Changes not visible after git pull | OpenCode MCP not restarted | Quit OpenCode completely and reopen |

---

## Related docs

- [REGISTER_AGENT.md](REGISTER_AGENT.md) — Agent dropdown, `opencode.json`, skills
- [README.md](../README.md) — Features and CLI reference
- [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) — Production workflow
