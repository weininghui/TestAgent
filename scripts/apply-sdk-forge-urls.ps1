# Apply sdk-forge GitHub URLs after repository rename
# Run AFTER renaming TestAgent -> sdk-forge on GitHub
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

$patterns = @(
    @{ From = 'weininghui/TestAgent'; To = 'weininghui/sdk-forge' }
    @{ From = 'github.com/weininghui/TestAgent'; To = 'github.com/weininghui/sdk-forge' }
)

$extensions = @('*.md', '*.mdc', '*.ps1', '*.sh', '*.toml', '*.yml', '*.yaml')

$files = Get-ChildItem -Path $Root -Recurse -Include $extensions -File |
    Where-Object {
        $_.FullName -notmatch '\\\.git\\' -and
        $_.FullName -notmatch '\\\.opencode\\node_modules\\' -and
        $_.FullName -notmatch '\\build\\' -and
        $_.FullName -notmatch '\\\.pytest_cache\\'
    }

$changed = 0
foreach ($file in $files) {
    $text = Get-Content -Raw -Encoding UTF8 $file.FullName
    $newText = $text
    foreach ($p in $patterns) {
        $newText = $newText -replace [regex]::Escape($p.From), $p.To
    }
    if ($newText -ne $text) {
        $changed++
        if ($DryRun) {
            Write-Host "Would update: $($file.FullName)"
        } else {
            Set-Content -Path $file.FullName -Value $newText -Encoding UTF8 -NoNewline
            Write-Host "Updated: $($file.FullName)"
        }
    }
}

Write-Host ""
if ($DryRun) {
    Write-Host "Dry run: $changed file(s) would change."
} else {
    Write-Host "Updated $changed file(s)."
    Write-Host "Also run: git remote set-url origin https://github.com/weininghui/sdk-forge.git"
}
