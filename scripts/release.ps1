# SDK Forge release helper — bump version files and scaffold release notes
# Usage: .\release.ps1 -Version 5.12.0
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [switch]$SkipNotes
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Tag = "v$Version"

function Read-VersionFromFile {
    param([string]$Path, [string]$Pattern)
    $text = Get-Content -Raw -Encoding UTF8 $Path
    if ($text -match $Pattern) { return $Matches[1] }
    throw "Could not parse version from $Path"
}

$initPath = Join-Path $Root "sdk_forge\__init__.py"
$pyprojectPath = Join-Path $Root "pyproject.toml"
$pluginPath = Join-Path $Root "plugin.yaml"
$notesPath = Join-Path $Root "docs\releases\RELEASE_NOTES_$Tag.md"

$current = Read-VersionFromFile $initPath '__version__\s*=\s*"([^"]+)"'
Write-Host "Current version: $current"
Write-Host "Target version:  $Version"

if ($current -eq $Version) {
    Write-Host "Version already $Version in sdk_forge/__init__.py — updating other files only."
}

# sdk_forge/__init__.py
$initText = Get-Content -Raw -Encoding UTF8 $initPath
$initText = $initText -replace '__version__\s*=\s*"[^"]+"', "__version__ = `"$Version`""
Set-Content -Path $initPath -Value $initText -Encoding UTF8 -NoNewline

# pyproject.toml
$pyText = Get-Content -Raw -Encoding UTF8 $pyprojectPath
$pyText = $pyText -replace '(?m)^version\s*=\s*"[^"]+"', "version = `"$Version`""
Set-Content -Path $pyprojectPath -Value $pyText -Encoding UTF8 -NoNewline

# plugin.yaml
$pluginText = Get-Content -Raw -Encoding UTF8 $pluginPath
$pluginText = $pluginText -replace '(?m)^version:\s*[^\r\n]+', "version: $Version"
Set-Content -Path $pluginPath -Value $pluginText -Encoding UTF8 -NoNewline

# Verify consistency
$vInit = Read-VersionFromFile $initPath '__version__\s*=\s*"([^"]+)"'
$vPy = Read-VersionFromFile $pyprojectPath '(?m)^version\s*=\s*"([^"]+)"'
$pluginRaw = Get-Content -Raw -Encoding UTF8 $pluginPath
if ($pluginRaw -notmatch '(?m)^version:\s*([^\r\n]+)') {
    Write-Error "Could not parse version from plugin.yaml"
}
$vPlugin = $Matches[1].Trim()

if ($vInit -ne $Version -or $vPy -ne $Version -or $vPlugin -ne $Version) {
    Write-Error "Version mismatch after bump: init=$vInit pyproject=$vPy plugin=$vPlugin"
}

Write-Host "Bumped version files to $Version"

if (-not $SkipNotes -and -not (Test-Path $notesPath)) {
    $template = @'
# Release Notes — v{VERSION}

**Summary** — (one-line description)

## Added

| Feature | Description |
|---------|-------------|
| | |

## Changed

| Item | Description |
|------|-------------|
| | |

## Upgrade

```powershell
cd $env:APPDATA\OpenCode\plugins\sdk-forge
git fetch --tags
git checkout v{VERSION}
pip install -e . -q
# Fully restart OpenCode
python -c "import sdk_forge; print(sdk_forge.__version__)"   # {VERSION}
```

Or:

```powershell
cd E:\vs_test\AINew\aiagent-main\scripts
.\update-opencode-plugin.ps1 -Ref v{VERSION}
```

## Tests

(passed / skipped counts)
'@ -replace '\{VERSION\}', $Version
    Set-Content -Path $notesPath -Value $template -Encoding UTF8
    Write-Host "Created $notesPath"
} elseif (Test-Path $notesPath) {
    Write-Host "Release notes already exist: $notesPath"
}

Write-Host ""
Write-Host "Manual steps remaining:"
Write-Host "  1. Edit CHANGELOG.md (add [$Version] section)"
Write-Host "  2. Fill docs/releases/RELEASE_NOTES_$Tag.md"
Write-Host "  3. Update README.md / README.zh-CN.md current release links"
Write-Host "  4. Update docs/INSTALL.md / INSTALL.zh-CN.md version examples"
Write-Host "  5. Run tests:"
Write-Host "     python -m pytest tests/ -v -k `"not TestCompileAndRun and not TestCoveragePipeline and not TestCliIntegration`""
Write-Host "  6. git add -A && git commit -m `"feat: $Tag ...`""
Write-Host "  7. git tag $Tag"
Write-Host "  8. git push origin main --tags"
Write-Host "  9. scripts\update-opencode-plugin.ps1 -Ref $Tag"
