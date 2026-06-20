# Merge SDK Forge forge-* agents into oh-my-openagent.json
# 将 forge 子 agent 模型配置合并到 oh-my-openagent.json

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$Example = Join-Path $RepoRoot "docs\examples\oh-my-openagent.multi-agent.json"

$OmoPath = Join-Path $env:USERPROFILE ".config\opencode\oh-my-openagent.json"
if (-not (Test-Path $OmoPath)) {
    Write-Error "oh-my-openagent.json not found at $OmoPath"
}

$example = Get-Content -Raw $Example | ConvertFrom-Json
$omo = Get-Content -Raw $OmoPath | ConvertFrom-Json

if (-not $omo.agents) {
    $omo | Add-Member -NotePropertyName agents -NotePropertyValue ([PSCustomObject]@{})
}

foreach ($prop in $example.agents.PSObject.Properties) {
    $name = $prop.Name
    $omo.agents | Add-Member -NotePropertyName $name -NotePropertyValue $prop.Value -Force
}

if ($example.background_task) {
    $omo | Add-Member -NotePropertyName background_task -NotePropertyValue $example.background_task -Force
}

$backup = "$OmoPath.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item $OmoPath $backup
$omo | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $OmoPath

Write-Host "Merged forge agents + permission (task:allow, call_omo_agent:deny) into $OmoPath"
Write-Host "Backup: $backup"
Write-Host "Restart OpenCode to reload oh-my-openagent config."
