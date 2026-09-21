# ============================================================
# Build uploadable zip for Doubao Work
# Usage: double-click the .bat file
# ============================================================

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

# --- Locate skill root ---
$skillRoot = $PSScriptRoot
if (-not $skillRoot) {
    $skillRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $skillRoot) {
    $skillRoot = (Get-Location).Path
}
$skillRoot = $skillRoot.TrimEnd('\')
$skillName = Split-Path $skillRoot -Leaf
$zipPath = Join-Path $skillRoot "$skillName.zip"

Write-Host "Skill root: $skillRoot"
Write-Host "Output zip: $zipPath"

# --- Exclusion rules ---
$excludeDirs = @(".venv", "venv", "__pycache__", ".git", ".idea", ".vscode", ".workbuddy")
$excludeFiles = @("config.toml", "*.pyc", "*.pyo", "*.pyd")

# --- Delete old zip ---
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

# --- Create standard zip with .NET (forward slashes) ---
# Get all files, filter out excluded dirs/files
Write-Host "Collecting files..."
$allFiles = Get-ChildItem -Path $skillRoot -Recurse -File

# Filter out excluded directories
$filtered = $allFiles | Where-Object {
    $path = $_.FullName
    $skip = $false
    foreach ($d in $excludeDirs) {
        if ($path -like "*\$d\*" -or $path -like "*\$d") { $skip = $true; break }
    }
    if (-not $skip) {
        foreach ($f in $excludeFiles) {
            if ($_.Name -like $f) { $skip = $true; break }
        }
    }
    -not $skip
}

Write-Host "Compressing $($filtered.Count) files..."
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)

$prefixLen = $skillRoot.TrimEnd('\').Length + 1

foreach ($file in $filtered) {
    $relativePath = $file.FullName.Substring($prefixLen).Replace('\', '/')
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $zip, $file.FullName, $relativePath,
        [System.IO.Compression.CompressionLevel]::Optimal
    ) | Out-Null
}
$zip.Dispose()

# --- Stats & verify ---
$fileCount = $filtered.Count
$sizeKB = [math]::Round((Get-Item $zipPath).Length / 1KB, 1)

$verifyZip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
$hasSkillMd = $false
foreach ($entry in $verifyZip.Entries) {
    if ($entry.FullName -eq "SKILL.md") { $hasSkillMd = $true; break }
}
$verifyZip.Dispose()

Write-Host ""
Write-Host "Done! $fileCount files, $sizeKB KB"
if ($hasSkillMd) {
    Write-Host "SKILL.md at root: OK"
} else {
    Write-Host "WARNING: SKILL.md missing at root!"
}
Write-Host ""
