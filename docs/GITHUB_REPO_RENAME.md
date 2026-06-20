# GitHub Repository Rename — TestAgent → sdk-forge

The canonical name per v5.4 migration is **`weininghui/sdk-forge`**. The live repo may still be **`weininghui/TestAgent`** until you rename it on GitHub.

## Manual rename (GitHub UI)

1. Open https://github.com/weininghui/TestAgent/settings
2. Under **General** → **Repository name**, change `TestAgent` to `sdk-forge`
3. Confirm — GitHub keeps redirects from old URLs

## After rename — local + repo URLs

```powershell
# Local clone remote
cd E:\vs_test\AINew\aiagent-main
git remote set-url origin https://github.com/weininghui/sdk-forge.git

# Replace TestAgent URLs in docs/scripts (run from repo root)
powershell -ExecutionPolicy Bypass -File scripts/apply-sdk-forge-urls.ps1
git add -A
git commit -m "docs: point GitHub URLs to sdk-forge after repo rename"
git push origin main
```

## OpenCode plugin directory

If your global plugin was cloned from TestAgent:

```powershell
cd $env:APPDATA\OpenCode\plugins\sdk-forge
git remote set-url origin https://github.com/weininghui/sdk-forge.git
```

## If rename is blocked (403 / permissions)

Keep using `weininghui/TestAgent` URLs (current default in this repo). Badges and clone commands work with TestAgent until rename succeeds.

Automated rename via `gh repo rename sdk-forge --repo weininghui/TestAgent` requires a token with `admin:repo` scope.
