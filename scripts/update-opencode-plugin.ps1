# One-shot update: OpenCode global plugin dir + agents + pip
# 一键更新 OpenCode 全局插件目录
param(
    [string]$Ref = "main",
    [string]$PluginDir = "$env:APPDATA\OpenCode\plugins\sdk-forge"
)

$ErrorActionPreference = "Stop"
$AgentsDir = "$env:APPDATA\OpenCode\agents"

if (-not (Test-Path $PluginDir)) {
    Write-Host "Plugin dir not found: $PluginDir"
    Write-Host "First install: git clone --branch $Ref https://github.com/weininghui/sdk-forge.git `"$PluginDir`""
    exit 1
}

Push-Location $PluginDir
git fetch origin
if ($Ref -eq "main") {
    git checkout main
    git reset --hard origin/main
} else {
    git fetch --tags
    git checkout $Ref
}
Pop-Location

python -m pip install -r "$PluginDir\requirements.txt" -q
python -m pip install -e $PluginDir --force-reinstall -q

New-Item -ItemType Directory -Force -Path $AgentsDir | Out-Null
Copy-Item -Force "$PluginDir\.opencode\agents\forge*.md" $AgentsDir

python -c "import sdk_forge; print('sdk_forge', sdk_forge.__version__)"

Write-Host ""
Write-Host "Done. Fully quit OpenCode and reopen (MCP does not hot-reload)."
