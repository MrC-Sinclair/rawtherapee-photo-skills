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

# ── Native-command runner ────────────────────────────────────
# PowerShell 5.1 promotes a native command's redirected stderr to an ErrorRecord,
# which $ErrorActionPreference="Stop" then aborts the script on -- a failing
# `python -c "import x"` therefore killed the script before it could report or
# repair anything. Every probe below decides on $LASTEXITCODE, so stderr has to
# stay non-terminating for those calls.
function Invoke-Native {
    param(
        [string]$Exe,
        [string[]]$Arguments = @(),
        [switch]$Show
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Show) {
            & $Exe @Arguments 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    # pip flushes an empty stderr chunk; rendering one prints nothing but
                    # the exception type name, so skip it.
                    if ($_.Exception.Message) { Write-Host $_.Exception.Message }
                } else {
                    Write-Host $_
                }
            }
        } else {
            $null = & $Exe @Arguments 2>&1
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}

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
    if ((Invoke-Native $venvPy @("-c", "import sys; sys.exit(0)")) -eq 0) {
        $coreOk = (Invoke-Native $venvPy @("-c", "import rawpy, PIL.Image, numpy")) -eq 0
        $heifOk = (Invoke-Native $venvPy @("-c", "import pillow_heif")) -eq 0
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
    if ((Invoke-Native $py @("-m", "venv", (Join-Path $SkillRoot ".venv")) -Show) -ne 0 -or
        -not (Test-Path $venvPy)) {
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
        if ((Invoke-Native $venvPy @("-m", "pip", "install", "-r", $reqPath, "--quiet") -Show) -ne 0) {
            Write-Host "❌ pip install failed: $req" -ForegroundColor Red
            exit 1
        }
    }
}

# ── Verify ───────────────────────────────────────────────────
Write-Host ""
foreach ($check in @(
    @{ imp = "rawpy, numpy, PIL.Image"; ok = "core deps OK";                 miss = "rawpy/pillow/numpy MISSING" },
    @{ imp = "pillow_heif";            ok = "pillow-heif OK (HEIC input)";  miss = "pillow-heif MISSING (needed for .heic/.heif input)" },
    @{ imp = "tifffile";               ok = "tifffile OK (10/12-bit HEIC)"; miss = "tifffile MISSING (10/12-bit HEIC degrades to 8-bit)" }
)) {
    if ((Invoke-Native $venvPy @("-c", "import $($check.imp)")) -eq 0) {
        Write-Host "  ✓ $($check.ok)" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $($check.miss)" -ForegroundColor Red
    }
}

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
