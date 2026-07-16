$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackupRoot = Join-Path $ProjectRoot "backups"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$StageRoot = Join-Path $env:TEMP "engineering-files-source-$Timestamp"
$ArchivePath = Join-Path $BackupRoot "engineering-files-source-$Timestamp.zip"

$ExcludedNames = @(
    ".git",
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "backups",
    "data",
    "dist",
    "node_modules"
)

$ExcludedFiles = @(
    ".env"
)

function Test-IsExcludedPath {
    param([System.IO.FileSystemInfo]$Item)

    $relativePath = Resolve-Path -LiteralPath $Item.FullName -Relative
    $parts = $relativePath -split "[\\/]" | Where-Object { $_ -and $_ -ne "." }
    foreach ($part in $parts) {
        if ($ExcludedNames -contains $part) {
            return $true
        }
    }
    if (-not $Item.PSIsContainer -and $ExcludedFiles -contains $Item.Name) {
        return $true
    }
    return $false
}

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
if (Test-Path $StageRoot) {
    $resolvedStage = Resolve-Path $StageRoot
    if (-not $resolvedStage.Path.StartsWith((Resolve-Path $env:TEMP).Path)) {
        throw "Refusing to clean a staging path outside TEMP: $resolvedStage"
    }
    Remove-Item -LiteralPath $resolvedStage.Path -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null

Push-Location $ProjectRoot
try {
    Get-ChildItem -LiteralPath $ProjectRoot -Force -Recurse -File | ForEach-Object {
        if (Test-IsExcludedPath $_) {
            return
        }
        $relativePath = Resolve-Path -LiteralPath $_.FullName -Relative
        $targetPath = Join-Path $StageRoot $relativePath
        $targetDir = Split-Path -Parent $targetPath
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $targetPath -Force
    }
} finally {
    Pop-Location
}

Compress-Archive -Path (Join-Path $StageRoot "*") -DestinationPath $ArchivePath -Force
Remove-Item -LiteralPath $StageRoot -Recurse -Force

Write-Host "Source backup created: $ArchivePath"
