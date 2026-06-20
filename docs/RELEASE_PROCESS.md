# Release Process

**English** | [简体中文](#简体中文)

## English

### Prerequisites

- Clean `main` branch synced with `origin/main`
- [GitHub Actions CI](https://github.com/weininghui/TestAgent/actions) green on `main`
- Write access to `weininghui/TestAgent`

### Version bump

```powershell
cd E:\vs_test\AINew\aiagent-main\scripts
.\release.ps1 -Version 5.12.0
```

This updates:

- `sdk_forge/__init__.py`
- `pyproject.toml`
- `plugin.yaml`
- `docs/releases/RELEASE_NOTES_v5.12.0.md` (template if missing)

### Manual edits

1. **CHANGELOG.md** — add `[5.12.0]` section at top
2. **RELEASE_NOTES** — fill `docs/releases/RELEASE_NOTES_v5.12.0.md`
3. **README.md / README.zh-CN.md** — update “Current release” link
4. **docs/INSTALL.md / INSTALL.zh-CN.md** — update current release + `sdk_forge.__version__` example

### Test before tag

```bash
# Fast
python -m pytest tests/ -v -k "not TestCompileAndRun and not TestCoveragePipeline and not TestCliIntegration"

# Windows integration (recommended before release)
python -m pytest tests/ -v -k "TestCompileAndRun and not pkg_config and not test_medium"
python -m pytest tests/ -v -k TestCliIntegration
```

### Publish

```bash
git add -A
git commit -m "feat: v5.12.0 ..."
git tag v5.12.0
git push origin main --tags
```

GitHub Actions [release.yml](../.github/workflows/release.yml) runs tests and creates the GitHub Release from `docs/releases/RELEASE_NOTES_v5.12.0.md`.

### After release

```powershell
scripts\update-opencode-plugin.ps1 -Ref v5.12.0
```

Fully quit and restart OpenCode.

Verify:

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"
forge autopilot --help
```

### Checklist

| Step | Done |
|------|------|
| `release.ps1` bumped version files | |
| CHANGELOG + RELEASE_NOTES written | |
| README / INSTALL version links updated | |
| Tests passed locally | |
| Commit on `main` | |
| Tag `vX.Y.Z` pushed | |
| GitHub Release created (Actions) | |
| OpenCode plugin updated locally | |

### PyPI (optional)

Workflow: [.github/workflows/pypi.yml](../.github/workflows/pypi.yml) publishes when a GitHub Release is **published**.

Setup (one-time on PyPI):

1. Create project `sdk-forge` on https://pypi.org (or claim if exists)
2. Configure **Trusted Publisher** for `weininghui/TestAgent` (or `sdk-forge` after rename) → workflow `pypi.yml`
3. Add GitHub environment `pypi` if using environment protection

Until PyPI is configured, installs remain: `git clone` + `pip install -e .`

---

## 简体中文

### 前置条件

- `main` 分支干净且与 `origin/main` 同步
- [GitHub Actions CI](https://github.com/weininghui/TestAgent/actions) 在 `main` 上通过
- 拥有 `weininghui/TestAgent` 写权限

### 版本号 bump

```powershell
cd E:\vs_test\AINew\aiagent-main\scripts
.\release.ps1 -Version 5.12.0
```

自动更新：

- `sdk_forge/__init__.py`
- `pyproject.toml`
- `plugin.yaml`
- `docs/releases/RELEASE_NOTES_v5.12.0.md`（不存在时生成模板）

### 需手动编辑

1. **CHANGELOG.md** — 顶部添加 `[5.12.0]` 条目
2. **RELEASE_NOTES** — 填写 `docs/releases/RELEASE_NOTES_v5.12.0.md`
3. **README.md / README.zh-CN.md** — 更新「当前版本」链接
4. **docs/INSTALL.md / INSTALL.zh-CN.md** — 更新当前 Release 与版本验证示例

### 打 tag 前测试

```bash
# 快速
python -m pytest tests/ -v -k "not TestCompileAndRun and not TestCoveragePipeline and not TestCliIntegration"

# Windows 集成（发版前建议）
python -m pytest tests/ -v -k "TestCompileAndRun and not pkg_config and not test_medium"
python -m pytest tests/ -v -k TestCliIntegration
```

### 发布

```bash
git add -A
git commit -m "feat: v5.12.0 ..."
git tag v5.12.0
git push origin main --tags
```

GitHub Actions [release.yml](../.github/workflows/release.yml) 会跑测试并从 `docs/releases/RELEASE_NOTES_v5.12.0.md` 创建 GitHub Release。

### 发布后

```powershell
scripts\update-opencode-plugin.ps1 -Ref v5.12.0
```

完全退出并重启 OpenCode。

验证：

```bash
python -c "import sdk_forge; print(sdk_forge.__version__)"
forge autopilot --help
```

### Checklist

| 步骤 | 完成 |
|------|------|
| `release.ps1` 已 bump 版本文件 | |
| CHANGELOG + RELEASE_NOTES 已写 | |
| README / INSTALL 版本链接已更新 | |
| 本地测试通过 | |
| 已 commit 到 `main` | |
| 已 push tag `vX.Y.Z` | |
| GitHub Release 已创建（Actions） | |
| 本地 OpenCode 插件已更新 | |
