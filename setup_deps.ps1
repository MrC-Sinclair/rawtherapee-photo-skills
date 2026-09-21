# ============================================================
# photo-skills — Windows dependency setup (venv-aware, idempotent)
# Usage:  powershell -ExecutionPolicy Bypass -File setup_deps.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$SkillRoot = $PSScriptRoot
if (-not $SkillRoot) { $SkillRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$SkillRoot = $SkillRoot.TrimEnd('\')

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  photo-skills — Windows 依赖安装"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host ""

# ── Locate a Python ──────────────────────────────────────────
$py = $null
foreach ($cand in @("py -3", "python", "python3")) {
    try {
        $v = & { Invoke-Expression "$cand -c 'import sys; print(sys.executable)'" } 2>$null
        if ($v -and (Test-Path $v)) { $py = $v; break }
    } catch {}
}
if (-not $py) {
    Write-Host "❌ No Python found. Install Python 3.11+ from https://www.python.org/downloads/ and re-run." -ForegroundColor Red
    exit 1
}
Write-Host "  Python: $py"

# ── venv: create or repair ──────────────────────────────────
$venvPy = Join-Path $SkillRoot ".venv\Scripts\python.exe"
$needVenv = $true
if (Test-Path $venvPy) {
    # A venv copied from another machine points at a non-existent base
    # interpreter. Verify it actually runs before trusting it.
    & $venvPy -c "import sys; sys.exit(0)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $venvPy -c "import rawpy, PIL.Image, PIL.Image, numpy" 2>$null
        $coreOk = ($LASTEXITCODE -eq 0)
        & $venvPy -c "import pillow_heif" 2>$null
        $heifOk = ($LASTEXITCODE -eq 0)
        if ($coreOk -and $heifOk) {
            Write-Host "  ✓ Existing .venv is healthy" -ForegroundColor Green
            $needVenv = $false
        } else {
            Write-Host "  ⚠ Existing .venv is broken (missing deps or dead interpreter) — recreating." -ForegroundColor Yellow
            Remove-Item (Join-Path $SkillRoot ".venv") -Recurse -Force
        }
    } else {
        Write-Host "  ⚠ Existing .venv is dead (base interpreter gone) — recreating." -ForegroundColor Yellow
        Remove-Item (Join-Path $SkillRoot ".venv") -Recurse -Force
    }
}

if ($needVenv) {
    Write-Host "  Creating .venv ..."
    & $py -m venv (Join-Path $SkillRoot ".venv")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) {
        Write-Host "❌ venv creation failed" -ForegroundColor Red
        exit 1
    }
}

# ── Install requirements ────────────────────────────────────
Write-Host ""
Write-Host "  Installing Python packages ..."
foreach ($req in @(
    "photo-toolkit\requirements.txt",
    "photo-grader\requirements.txt",
    "photo-previewer\requirements.txt"
)) {
    $reqPath = Join-Path $SkillRoot $req
    if (Test-Path $reqPath) {
        Write-Host "    $req"
        & $venvPy -m pip install -r $reqPath --quiet
    }
}

# ── Verify ───────────────────────────────────────────────────
Write-Host ""
& $venvPy -c "import rawpy, numpy, PIL.Image; print('  ✓ core deps OK')" 2>$null
& $venvPy -c "import pillow_heif; print('  ✓ pillow-heif OK (HEIC input)')" 2>$null
& $venvPy -c "import tifffile; print('  ✓ tifffile OK (10/12-bit HEIC)')" 2>$null

# ── RawTherapee CLI (best-effort; external app, not pip) ────
Write-Host ""
$rtHint = "  RawTherapee CLI (grade.py only): not auto-detected. Install from https://rawtherapee.com/downloads, then set RAWTHERAPEE_CLI or rawtherapee_cli in config.toml."
$rt = $null
foreach ($cand in @("rawtherapee-cli")) {
    $found = Get-Command $cand -ErrorAction SilentlyContinue
    if ($found) { $rt = $found.Source; break }
}
if (-not $rt) {
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\RawTherapee",
        "$env:ProgramFiles\RawTherapee",
        "${env:ProgramFiles(x86)}\RawTherapee"
    )) {
        if (Test-Path $p) {
            $hit = Get-ChildItem $p -Filter rawtherapee-cli.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { $rt = $hit.FullName; break }
        }
    }
}
# Custom-install fallback: bounded scan of fixed drives' top-level folders
# (e.g. D:\workspace\RawTherapee\rawtherapee-cli.exe). Two levels deep only.
if (-not $rt) {
    foreach ($letter in "DEFGHIJKLMNOPQSTUVWXYZ".ToCharArray()) {
        $drive = "${letter}:\"
        if (-not (Test-Path $drive)) { continue }
        foreach ($top in Get-ChildItem $drive -Directory -ErrorAction SilentlyContinue) {
            foreach ($sub in Get-ChildItem $top.FullName -Directory -ErrorAction SilentlyContinue) {
                if ($sub.Name -match "rawtherapee") {
                    $hit = Join-Path $sub.FullName "rawtherapee-cli.exe"
                    if (Test-Path $hit) { $rt = $hit; break }
                }
            }
            if ($rt) { break }
        }
        if ($rt) { break }
    }
}
if ($rt) {
    Write-Host "  ✓ RawTherapee CLI: $rt" -ForegroundColor Green
} else {
    Write-Host $rtHint -ForegroundColor Yellow
}

# ffmpeg (best-effort; only needed by assemble.py)
$ff = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ff) {
    foreach ($letter in "DEFGHIJKLMNOPQSTUVWXYZ".ToCharArray()) {
        $drive = "${letter}:\"
        if (-not (Test-Path $drive)) { continue }
        foreach ($top in Get-ChildItem $drive -Directory -ErrorAction SilentlyContinue) {
            foreach ($sub in Get-ChildItem $top.FullName -Directory -ErrorAction SilentlyContinue) {
                if ($sub.Name -match "ffmpeg") {
                    $hit = Join-Path $sub.FullName "bin\ffmpeg.exe"
                    if (-not (Test-Path $hit)) { $hit = Join-Path $sub.FullName "ffmpeg.exe" }
                    if (Test-Path $hit) { $ff = $hit; break }
                }
            }
            if ($ff) { break }
        }
        if ($ff) { break }
    }
}
if ($ff) {
    Write-Host "  ✓ ffmpeg: $ff" -ForegroundColor Green
} else {
    Write-Host "  ffmpeg: not detected (only needed for assemble.py)." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Done. Activate before use:  .venv\Scripts\Activate.ps1"
