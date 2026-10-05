# ============================================================
# 一键打包：产出多个平台的技能包
#
#   <skill>-豆包版.zip     豆包工作 — 条目平铺在压缩包根目录
#   <skill>-通用版.zip     Qoder / Marvis / WorkBuddy / Claude 等
#                          整套约定为 <工具>/skills/<技能名>/SKILL.md，
#                          此包把所有条目套在一层 <skill>/ 目录下，
#                          且包内不含中文文件名（部分导入器会直接拒收）
#
# 用法：双击 .bat
#
# 注意：本文件必须存成「UTF-8 with BOM」。PowerShell 5.1 读无 BOM 的
# UTF-8 时按 ANSI(cp936) 解码，下面的中文包名会变成乱码文件名。
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
$prefixLen = $skillRoot.Length + 1

Write-Host "Skill root: $skillRoot"

# --- Rules shared by every package ---
$excludeDirs = @(".venv", "venv", "__pycache__", ".git", ".idea", ".vscode", ".workbuddy")
# *.zip: a previous run's output sits in $skillRoot and is picked up by
# Get-ChildItem before New-Package deletes it, which would then throw on the
# missing file (and nest the other package into this one).
$excludeFiles = @("config.toml", "*.pyc", "*.pyo", "*.pyd", "*.zip")

# --- Rules only for the generic package ---
# Packaging tooling never ships; neither do non-ASCII names (some importers
# reject them outright) nor repo-local dotfiles.
$toolFiles = @("build_upload_zip.ps1")

function Test-AsciiOnly {
    param([string]$Text)
    foreach ($ch in $Text.ToCharArray()) {
        if ([int]$ch -gt 127) { return $false }
    }
    return $true
}

Write-Host "Collecting files..."
$allFiles = Get-ChildItem -Path $skillRoot -Recurse -File

$shared = $allFiles | Where-Object {
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

function Get-RelativePath {
    param([System.IO.FileInfo]$File)
    return $File.FullName.Substring($prefixLen).Replace('\', '/')
}

$generic = $shared | Where-Object {
    $rel = Get-RelativePath $_
    $keep = $true
    if (-not (Test-AsciiOnly $rel)) { $keep = $false }
    if ($toolFiles -contains $_.Name) { $keep = $false }
    if ($_.Name -like ".*") { $keep = $false }
    $keep
}

function New-Package {
    param(
        [string]$ZipPath,
        [object]$Items,
        [string]$EntryPrefix = ""
    )
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    $written = 0
    $zip = [System.IO.Compression.ZipFile]::Open($ZipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($file in $Items) {
            $rel = Get-RelativePath $file
            $entry = if ($EntryPrefix) { "$EntryPrefix/$rel" } else { $rel }
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $zip, $file.FullName, $entry,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
            $written++
        }
    } finally {
        $zip.Dispose()
    }
    return $written
}

function Show-Package {
    param(
        [string]$ZipPath,
        [int]$Written,
        [string]$SkillMdEntry
    )
    $sizeKB = [math]::Round((Get-Item $ZipPath).Length / 1KB, 1)
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $skillMdOk = (@($zip.Entries | Where-Object { $_.FullName -eq $SkillMdEntry }).Count -gt 0)
        $pyCount = @($zip.Entries | Where-Object { $_.FullName -like "*.py" }).Count
        $roots = @($zip.Entries | ForEach-Object { ($_.FullName -split '/')[0] } | Sort-Object -Unique)
    } finally {
        $zip.Dispose()
    }
    $leaf = Split-Path $ZipPath -Leaf
    Write-Host ""
    Write-Host "  $leaf"
    Write-Host "    $Written files, $sizeKB KB, $pyCount .py scripts"
    Write-Host "    SKILL.md at '$SkillMdEntry': $(if ($skillMdOk) { 'OK' } else { 'MISSING' })"
    Write-Host "    top-level entries: $($roots -join ', ')"
    if (-not $skillMdOk) { exit 1 }
}

$doubaoZip = Join-Path $skillRoot "$skillName-豆包版.zip"
$genericZip = Join-Path $skillRoot "$skillName-通用版.zip"

Write-Host "Compressing 豆包版 ($($shared.Count) candidates)..."
$n1 = New-Package -ZipPath $doubaoZip -Items $shared

Write-Host "Compressing 通用版 ($($generic.Count) candidates)..."
$n2 = New-Package -ZipPath $genericZip -Items $generic -EntryPrefix $skillName

Write-Host ""
Write-Host "Done. Packages written to $skillRoot"
Show-Package -ZipPath $doubaoZip -Written $n1 -SkillMdEntry "SKILL.md"
Show-Package -ZipPath $genericZip -Written $n2 -SkillMdEntry "$skillName/SKILL.md"
Write-Host ""
