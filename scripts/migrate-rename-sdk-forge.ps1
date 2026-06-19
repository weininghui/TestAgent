# Migrate OpenCode plugin: sdk-test-forge -> sdk-forge (SDK Forge v5.4)
param(
    [string]$OldDir = "$env:APPDATA\OpenCode\plugins\sdk-test-forge",
    [string]$NewDir = "$env:APPDATA\OpenCode\plugins\sdk-forge",
    [string]$Ref = "v5.4.0"
)

$ErrorActionPreference = "Stop"
$Repo = "https://github.com/weininghui/TestAgent.git"
# After renaming the GitHub repo to sdk-forge, this URL redirects automatically.

Write-Host "==> SDK Forge rename migration"

if ((Test-Path $OldDir) -and -not (Test-Path $NewDir)) {
    Write-Host "Moving $OldDir -> $NewDir"
    Move-Item $OldDir $NewDir
} elseif (-not (Test-Path $NewDir)) {
    Write-Host "Cloning fresh to $NewDir"
    New-Item -ItemType Directory -Force -Path (Split-Path $NewDir) | Out-Null
    git clone --branch $Ref --depth 1 $Repo $NewDir
}

if (-not (Test-Path $NewDir)) {
    Write-Error "Plugin directory not found: $NewDir"
}

Push-Location $NewDir
git remote set-url origin $Repo
git fetch --tags origin 2>$null
git fetch origin 2>$null
if ($Ref -match "^v") {
    git checkout $Ref 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Tag $Ref not found yet — using main"
        git checkout main
        git pull origin main
    }
} else {
    git checkout $Ref
    git reset --hard "origin/$Ref"
}
Pop-Location

Write-Host "==> pip: uninstall legacy sdk-test-forge (if present)"
python -m pip uninstall sdk-test-forge -y 2>$null

Write-Host "==> pip: install sdk-forge"
python -m pip install -r "$NewDir\requirements.txt" -q
python -m pip install -e $NewDir --force-reinstall -q

$AgentsDir = "$env:APPDATA\OpenCode\agents"
New-Item -ItemType Directory -Force -Path $AgentsDir | Out-Null
Copy-Item -Force "$NewDir\.opencode\agents\forge*.md" $AgentsDir

foreach ($Name in @("SDKForge-PluginAutoUpdate", "SDKTestForge-PluginAutoUpdate")) {
    $Existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($Existing) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "Removed scheduled task: $Name"
    }
}

python -c "import sdk_forge; print('sdk_forge', sdk_forge.__version__)"
pip show sdk-forge | Select-String "Version|Name"

Write-Host ""
Write-Host "Done. Fully quit OpenCode and reopen."
Write-Host "MCP plugin ID should be: sdk-forge"
Write-Host "See docs/MIGRATION_v5.4.md if you use manual opencode.json MCP keys."
