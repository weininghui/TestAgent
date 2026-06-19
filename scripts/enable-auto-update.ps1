# Enable GitHub auto-update fallback for SDK Forge OpenCode plugin
# 启用 GitHub 自动更新兜底（环境变量 + 可选每日计划任务）
param(
    [string]$PluginDir = "$env:APPDATA\OpenCode\plugins\sdk-forge",
    [bool]$DailyTask = $true,
    [string]$DailyAt = "03:00"
)

$ErrorActionPreference = "Stop"
$Repo = "https://github.com/weininghui/sdk-forge.git"

Write-Host "==> Setting FORGE_AUTO_UPDATE=1 (User environment)"
[System.Environment]::SetEnvironmentVariable("FORGE_AUTO_UPDATE", "1", "User")
$env:FORGE_AUTO_UPDATE = "1"

if (-not (Test-Path $PluginDir)) {
    Write-Host "==> Cloning plugin to $PluginDir"
    New-Item -ItemType Directory -Force -Path (Split-Path $PluginDir) | Out-Null
    git clone --branch main --depth 1 $Repo $PluginDir
}

$UpdateScript = Join-Path $PluginDir "scripts\update-opencode-plugin.ps1"
if (-not (Test-Path $UpdateScript)) {
    Write-Host "Update script missing — pulling latest main first..."
    Push-Location $PluginDir
    git fetch origin
    git checkout main
    git reset --hard origin/main
    Pop-Location
}

Write-Host "==> Running initial update"
powershell -NoProfile -ExecutionPolicy Bypass -File $UpdateScript

if ($DailyTask) {
    $TaskName = "SDKForge-PluginAutoUpdate"
    $LegacyTask = "SDKTestForge-PluginAutoUpdate"
    foreach ($Name in @($TaskName, $LegacyTask)) {
        $Existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        if ($Existing) {
            Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        }
    }
    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$UpdateScript`""
    $Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
        -Description "Auto-update SDK Forge OpenCode plugin from GitHub main" | Out-Null
    Write-Host "==> Scheduled task registered: $TaskName (daily at $DailyAt)"
}

Write-Host ""
Write-Host "Done. Auto-update fallback enabled:"
Write-Host "  - MCP start (run_mcp.py): git pull if behind (max once per 6h) + pip"
Write-Host "  - Daily task: update-opencode-plugin.ps1 (if enabled)"
Write-Host "  - After updates: fully quit and reopen OpenCode"
Write-Host ""
python -c "import sdk_forge; print('sdk_forge', sdk_forge.__version__)"
