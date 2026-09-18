# ============================================================
# 一键打包 rawtherapee-photo-skills 为豆包工作可上传的 zip
# 用法：双击「一键打包上传.bat」，或右键 → 使用 PowerShell 运行
# ============================================================

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 技能根目录（脚本所在目录）
$skillRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillName = Split-Path $skillRoot -Leaf

# 输出路径：技能根目录下
$zipPath = Join-Path $skillRoot "$skillName.zip"

Write-Host "==> Skill root: $skillRoot"
Write-Host "==> Output zip:  $zipPath"

# 临时目录
$tempDir = Join-Path $env:TEMP "skill_upload_$(Get-Random)"
if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

# 排除规则（和 .clawhubignore 保持一致）
$excludeDirs = @(".venv", "venv", "__pycache__", ".git", ".idea", ".vscode", ".DS_Store")
$excludeFiles = @("config.toml", "*.pyc", "*.pyo", "*.pyd")

# 用 robocopy 复制到临时目录，排除不需要的内容
$rcArgs = @($skillRoot, $tempDir, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
foreach ($d in $excludeDirs) { $rcArgs += "/XD"; $rcArgs += "$d" }
foreach ($f in $excludeFiles) { $rcArgs += "/XF"; $rcArgs += "$f" }

Write-Host "==> Copying and filtering files..."
& robocopy @rcArgs | Out-Null

# 删除旧 zip
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

# 打包
Write-Host "==> Compressing to zip..."
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath -CompressionLevel Optimal

# 统计
$fileCount = (Get-ChildItem -Path $tempDir -Recurse -File).Count
$sizeKB = [math]::Round((Get-Item $zipPath).Length / 1KB, 1)

# 清理临时目录
Remove-Item -Recurse -Force $tempDir

Write-Host ""
Write-Host "Done! Files: $fileCount, Size: $sizeKB KB"
Write-Host "Output: $zipPath"
Write-Host ""
