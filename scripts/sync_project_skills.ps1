param(
    [string]$SourceRoot = ".\.codex\skills",
    [string]$DestinationRoot = "$env:USERPROFILE\.codex\skills",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$resolvedSource = (Resolve-Path -LiteralPath $SourceRoot).Path
if (-not (Test-Path -LiteralPath $DestinationRoot)) {
    if ($DryRun) {
        Write-Output "DRY-RUN create directory: $DestinationRoot"
    } else {
        New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    }
}

$skills = Get-ChildItem -LiteralPath $resolvedSource -Directory | Sort-Object Name
if (-not $skills) {
    throw "No project skills found under $resolvedSource"
}

foreach ($skill in $skills) {
    $skillFile = Join-Path $skill.FullName "SKILL.md"
    if (-not (Test-Path -LiteralPath $skillFile)) {
        throw "Missing SKILL.md: $skillFile"
    }

    $destination = Join-Path $DestinationRoot $skill.Name
    if ($DryRun) {
        Write-Output "DRY-RUN sync: $($skill.FullName) -> $destination"
        continue
    }

    if (Test-Path -LiteralPath $destination) {
        Remove-Item -LiteralPath $destination -Recurse -Force
    }
    Copy-Item -LiteralPath $skill.FullName -Destination $destination -Recurse -Force
    Write-Output "Synced: $destination"
}
