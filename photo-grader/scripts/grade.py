#!/usr/bin/env python3
"""
Photo Grader — Apply Lightroom-style color grading via RawTherapee CLI.

Reads a JSON parameter file (from LLM output or manual creation) and applies
professional color grading to each specified photo file, exporting high-quality JPGs.

Uses RawTherapee CLI (rawtherapee-cli) as the sole processing engine.
LR parameters are automatically mapped to PP3 sidecar files for rendering.

Supported Camera RAW Formats:
    Nikon (.nef .nrw), Canon (.cr2 .cr3 .crw), Sony (.arw .srf .sr2),
    Fujifilm (.raf), Olympus (.orf), Panasonic (.rw2), Pentax (.pef),
    Samsung (.srw), Leica (.rwl .dng), Adobe (.dng), Hasselblad (.3fr .fff),
    Phase One (.iiq), Sigma (.x3f)

Also supports: JPEG (.jpg/.jpeg), Apple HEIC/HEIF (.heic/.heif)

HEIC/HEIF note:
    RawTherapee builds compiled without libheif (the 5.13 Windows build is one
    of them) cannot decode HEIC at all — they report "is not one of the selected
    parsed extensions". grade.py therefore transcodes HEIC/HEIF to TIFF before
    handing the file to RawTherapee. Sources carrying more than 8 bits per
    channel (iPhone 10/12-bit HEIC) are written losslessly as 16-bit RGB TIFF
    with tifffile, ICC profile carried over; 8-bit sources take the plain Pillow
    path. RawTherapee always receives the base image: an iPhone "HDR" gain map
    is never applied, so a 10/12-bit file keeps its per-channel depth but not its
    HDR highlights.

Dependencies:
    RawTherapee CLI (rawtherapee-cli)
    pillow-heif (only for HEIC/HEIF input)
    tifffile (only for 10/12-bit HEIC/HEIF; without it those fall back to 8-bit)
    tomllib (stdlib 3.11+) / tomli (<3.11)

    Check & install: bash scripts/setup_deps.sh

Usage:
    python grade.py grading_params.json
    python grade.py grading_params.json --raw-dir ~/Photos/RAW --output ~/Photos/Graded
    python grade.py grading_params.json --dry-run
    python grade.py grading_params.json --pp3-only --pp3-output ./pp3/
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add photo-toolkit to path for shared utilities
_TOOLKIT_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "photo-toolkit" / "scripts"
sys.path.insert(0, str(_TOOLKIT_SCRIPTS))
try:
    from file_matcher import find_file_by_stem, find_raw_file, SUPPORTED_EXTENSIONS
except ImportError:
    # photo-toolkit is published as its own skill; it must sit next to this folder.
    sys.stderr.write(
        "[ERROR] photo-toolkit skill not found.\n"
        f"        expected at: {_TOOLKIT_SCRIPTS}\n"
        "        photo-grader depends on photo-toolkit; install both skills into the "
        "same parent folder.\n"
    )
    sys.exit(1)

# ── Configuration ───────────────────────────────────────────────

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

_SKILL_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _SKILL_DIR.parent
_DEFAULT_CONFIG_PATH = (
    _SKILL_DIR / "config.toml" if (_SKILL_DIR / "config.toml").exists() else _ROOT_DIR / "config.toml"
)


def load_config(config_path=None):
    """Load configuration from config.toml."""
    path = Path(config_path or _DEFAULT_CONFIG_PATH).expanduser().resolve()
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
        if not isinstance(cfg, dict):
            print(f"⚠️  Config is not a valid mapping, ignoring: {path}", file=sys.stderr)
            return {}
        print(f"📄 Loaded config: {path}")
        return cfg
    except Exception as e:
        print(f"⚠️  Failed to read config ({path}): {e}", file=sys.stderr)
        return {}


# ── RawTherapee CLI Detection ──────────────────────────────────

_RT_CLI = None


def _version_key(name):
    """Sort key for version-like folder names ('5.13' sorts above '5.9')."""
    parts = []
    for token in name.replace("_", ".").replace("-", ".").split("."):
        parts.append((1, int(token)) if token.isdigit() else (0, 0))
    return parts


def _common_rt_cli_locations():
    """Yield plausible rawtherapee-cli paths for the current OS.

    GUI installers never put the CLI on PATH. No RawTherapee release number is
    hard-coded: versioned folders are discovered and sorted newest-first.
    """
    if sys.platform == "win32":
        roots = []
        for env in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                roots.append(Path(base) / "RawTherapee")
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            roots.append(Path(local_appdata) / "Programs" / "RawTherapee")
        for root in roots:
            yield root / "rawtherapee-cli.exe"
            if root.is_dir():
                try:
                    subdirs = sorted(
                        (p for p in root.iterdir() if p.is_dir()),
                        key=lambda p: _version_key(p.name),
                        reverse=True,
                    )
                except OSError:
                    subdirs = []
                for sub in subdirs:
                    yield sub / "rawtherapee-cli.exe"
    elif sys.platform == "darwin":
        yield Path("/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli")
        yield Path("/opt/homebrew/bin/rawtherapee-cli")
        yield Path("/usr/local/bin/rawtherapee-cli")
    else:
        for candidate in (
            "/usr/bin/rawtherapee-cli",
            "/usr/local/bin/rawtherapee-cli",
            "/snap/bin/rawtherapee-cli",
        ):
            yield Path(candidate)


def find_rawtherapee_cli(cli_path=None):
    """Find rawtherapee-cli executable."""
    global _RT_CLI
    if _RT_CLI is not None:
        return _RT_CLI

    if cli_path and Path(cli_path).exists():
        _RT_CLI = str(Path(cli_path).resolve())
        return _RT_CLI

    # Search PATH
    rt = shutil.which("rawtherapee-cli")
    if rt:
        _RT_CLI = rt
        return rt

    # Try 'rawtherapee' (some distros only install GUI binary)
    rt_gui = shutil.which("rawtherapee")
    if rt_gui:
        gui_dir = Path(rt_gui).parent
        cli_candidate = gui_dir / "rawtherapee-cli"
        if cli_candidate.exists():
            _RT_CLI = str(cli_candidate.resolve())
            return _RT_CLI
        _RT_CLI = rt_gui  # Fallback: use GUI binary (works but slower)
        return _RT_CLI

    # Last resort: scan the usual install locations (GUI installers keep the
    # binary out of PATH). Version-independent, nothing machine-specific.
    for candidate in _common_rt_cli_locations():
        if candidate.is_file():
            _RT_CLI = str(candidate.resolve())
            return _RT_CLI

    return None


def _rt_cli_install_hint():
    if sys.platform == "win32":
        return (
            "Install RawTherapee from https://rawtherapee.com/downloads, then either add its "
            "folder to PATH or set rawtherapee_cli in config.toml to the full path of "
            "rawtherapee-cli.exe"
        )
    if sys.platform == "darwin":
        # Always verify the CLI on macOS. If an agent installed RawTherapee via
        # Homebrew and the user has not explicitly opened/authorized it yet,
        # macOS may block startup with 133 / SIGTRAP. A user-authorized
        # Homebrew CLI can work; otherwise use the official standalone CLI.
        return (
            "Verify with rawtherapee-cli -h. If macOS blocks a Homebrew-installed CLI, "
            "open/authorize it manually or use the official standalone rawtherapee-cli in PATH"
        )
    return "Install: apt install rawtherapee-cli (Debian/Ubuntu) / dnf install RawTherapee (Fedora/RHEL)"


# Engine version reported by `rawtherapee-cli -h`, e.g. "5.13". Written into the
# [Version] AppVersion of generated PP3s instead of a hard-coded value.
_RT_VERSION = None


def _parse_rt_version(text):
    """Extract the engine version from `rawtherapee-cli -h` output."""
    match = re.search(r"rawtherapee,\s*version\s+([0-9][\w.]*)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _validate_rt_cli_executable(rt):
    """Run a lightweight smoke test to ensure rawtherapee-cli can actually start."""
    try:
        result = subprocess.run([rt, "-h"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"failed to start: {e}"

    output = f"{result.stdout}\n{result.stderr}"
    output_lower = output.lower()
    if "rawtherapee, version" in output_lower and "command line" in output_lower:
        global _RT_VERSION
        _RT_VERSION = _parse_rt_version(output)
        return True, output.splitlines()[0] if output.splitlines() else "RawTherapee CLI"

    if result.returncode == 133 or "sigtrap" in output_lower or "trace trap" in output_lower:
        return False, "exited with 133 (SIGTRAP / trace trap), often macOS blocking an unapproved CLI before startup"
    if result.returncode == 132 or "sigill" in output_lower or "illegal instruction" in output_lower:
        return False, "exited with 132 (SIGILL / illegal instruction), usually an incompatible macOS CLI build"

    if result.returncode != 0:
        tail = output.strip().splitlines()[-1] if output.strip() else f"exit code {result.returncode}"
        return False, tail

    return (
        False,
        "executable did not print RawTherapee command-line help; make sure this is rawtherapee-cli, not the GUI binary",
    )


def check_rt_cli(config=None):
    """Check that rawtherapee-cli is available and can start successfully."""
    cfg = config or {}
    rt = find_rawtherapee_cli(cfg.get("rawtherapee_cli", ""))
    if not rt:
        print("❌ RawTherapee CLI not found.", file=sys.stderr)
        print(f"   {_rt_cli_install_hint()}", file=sys.stderr)
        sys.exit(1)

    ok, message = _validate_rt_cli_executable(rt)
    if not ok:
        print(f"❌ RawTherapee CLI is not usable: {rt}", file=sys.stderr)
        print(f"   Reason: {message}", file=sys.stderr)
        print(f"   Verify manually with: {rt} -h", file=sys.stderr)
        print(f"   {_rt_cli_install_hint()}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Engine: RawTherapee ({rt}) — {message}")
    return rt


# ═══════════════════════════════════════════════════════════════
# RawTherapee: LR → PP3 Parameter Mapping
# ═══════════════════════════════════════════════════════════════


def rt_clamp(v, lo=0, hi=999):
    """Clamp value to range [lo, hi] for RT PP3."""
    return max(lo, min(hi, v))


def rt_clamp_f(v, lo=0.0, hi=999.0):
    """Clamp float value to range [lo, hi] for RT PP3."""
    return max(lo, min(hi, v))


def rt_map_exposure(pp3, basic):
    """Map LR exposure ±2.0 → RT Exposure.Comensation + Black."""
    val = basic.get("exposure", 0)
    if abs(val) < 0.001:
        return
    pp3[("Exposure", "Compensation")] = round(val * 2.0, 3)
    if val < -0.3:
        pp3[("Exposure", "Black")] = int(round(-val * 500))


def rt_map_contrast(pp3, basic):
    """Map LR contrast ±100 → RT Exposure.Contrast."""
    val = basic.get("contrast", 0)
    if abs(val) < 0.5:
        return
    pp3[("Exposure", "Contrast")] = round(val * 0.8)


def rt_map_tone_compression(pp3, basic):
    """Map LR highlights/shadows/whites/blacks → RT HighlightCompr/ShadowCompr."""
    hl = basic.get("highlights", 0)
    sh = basic.get("shadows", 0)

    if abs(hl) >= 0.5:
        if hl > 0:
            pp3[("Exposure", "HighlightCompr")] = round(rt_clamp(hl, 0, 100))
        else:
            pp3[("HLRecovery", "Enabled")] = True
            pp3[("HLRecovery", "Method")] = "Coloropp"
            pp3[("HLRecovery", "Hlbl")] = round(rt_clamp(-hl, 0, 100))

    if abs(sh) >= 0.5:
        if sh > 0:
            pp3[("Exposure", "ShadowCompr")] = round(rt_clamp(sh, 0, 100))
        else:
            # RT Shadow recovery via Shadows & Highlights
            pp3[("Shadows & Highlights", "Enabled")] = True
            pp3[("Shadows & Highlights", "Shadows")] = round(rt_clamp(-sh, 0, 100))

    # Whites/Blacks have no dedicated RT keys; rt_map_tone_curve folds them into
    # the [Exposure] Curve endpoints (build_pp3 passes `basic` through).


def rt_map_whitebalance(pp3, basic):
    """Map explicit RawTherapee white balance values.

    Lightroom-style temp_offset is intentionally not mapped to RT Temperature:
    RawTherapee expects an absolute Kelvin value, not a relative offset.
    Use temperature_kelvin for absolute WB, and green for RT's green multiplier.
    """
    temp_kelvin = basic.get("temperature_kelvin")
    green = basic.get("green")
    tint = basic.get("tint_offset", 0)

    if temp_kelvin is not None:
        try:
            temp_kelvin = float(temp_kelvin)
        except (TypeError, ValueError) as e:
            raise ValueError("temperature_kelvin must be a number") from e
        if not 2000 <= temp_kelvin <= 25000:
            raise ValueError("temperature_kelvin must be between 2000 and 25000")
        pp3[("White Balance", "Temperature")] = int(round(temp_kelvin))

    if green is not None:
        try:
            green = float(green)
        except (TypeError, ValueError) as e:
            raise ValueError("green must be a number") from e
        if not 0.5 <= green <= 2.0:
            raise ValueError("green must be between 0.5 and 2.0")
        pp3[("White Balance", "Green")] = round(green, 3)
    elif abs(tint) >= 0.5:
        pp3[("White Balance", "Green")] = round(rt_clamp_f(1.0 + tint * 0.005, 0.5, 2.0), 3)

    # RT only honours explicit Temperature/Green when the WB tool is enabled and
    # its setting is Custom; otherwise the keys below are silently ignored and
    # the camera/auto white balance is used (verified on RT 5.13: a CR2 rendered
    # byte-identical with and without Temperature=3000 until both keys were set).
    if ("White Balance", "Temperature") in pp3 or ("White Balance", "Green") in pp3:
        pp3[("White Balance", "Enabled")] = True
        pp3[("White Balance", "Setting")] = "Custom"


def rt_map_vibrance_saturation(pp3, basic):
    """Map LR vibrance/saturation → RT Vibrance.Pastels/Saturated."""
    vib = basic.get("vibrance", 0)
    sat = basic.get("saturation", 0)
    if abs(vib) >= 0.5:
        pp3[("Vibrance", "Enabled")] = True
        pp3[("Vibrance", "Pastels")] = round(vib * 0.9)
    if abs(sat) >= 0.5:
        pp3[("Vibrance", "Enabled")] = True
        pp3[("Vibrance", "Saturated")] = round(sat * 0.7)


def rt_map_tone_curve(pp3, tc_params, basic=None):
    """Map LR tonal controls → RT [Exposure] Curve (FCT_CubicSpline, 0-1 coords).

    RT parses Exposure.Curve as "type;x1;y1;x2;y2;...;" — type 3 is
    FCT_CubicSpline and every coordinate is normalised to 0..1, which is the
    format RT's own bundled profiles use. The previous 0..999 integer list was
    silently discarded by RT 5.13, making the whole tonal section a no-op.

    ``basic`` optionally supplies Lightroom's whites/blacks: RT has no dedicated
    keys for them, so they are folded into the curve endpoints here instead of
    being dropped on the floor.
    """
    tc = tc_params or {}
    bs = basic or {}
    hl = tc.get("highlights", 0)
    lt = tc.get("lights", 0)
    dk = tc.get("darks", 0)
    sh = tc.get("shadows", 0)
    whites = bs.get("whites", 0)
    blacks = bs.get("blacks", 0)
    if all(abs(v) < 0.5 for v in [hl, lt, dk, sh, whites, blacks]):
        return

    xs = (0.0, 0.25, 0.5, 0.75, 1.0)
    ys = [0.0, 0.25, 0.5, 0.75, 1.0]
    # Shadows raise the toe and highlights lift the shoulder; darks/lights act
    # on the mid-quarter points. Slider range ±100 → up to ±0.10 curve units.
    ys[0] += (sh * 0.0002) + (blacks * 0.0002)
    ys[1] += (sh * 0.0010) + (dk * 0.0005) + (blacks * 0.0006)
    ys[2] += (dk * 0.0005) + (lt * 0.0005)
    ys[3] += (lt * 0.0008) + (hl * 0.0008) + (whites * 0.0006)
    ys[4] += (hl * 0.0002) + (whites * 0.0003)

    ys = [rt_clamp_f(v, 0.0, 1.0) for v in ys]
    for i in range(1, len(ys)):  # keep the curve monotonic
        ys[i] = max(ys[i], ys[i - 1])

    curve = "3;" + "".join(f"{x:.5f};{y:.5f};" for x, y in zip(xs, ys))
    pp3[("Exposure", "Curve")] = curve
    pp3[("Exposure", "CurveMode")] = "Standard"


# LR's 8 HSL channels → positions on the 0-360° hue wheel (degrees).
# RT's HSV Equalizer is a continuous curve over hue, so each LR channel
# becomes a single control point at its characteristic hue.
_HSL_CHANNEL_HUE = {
    "red": 0,
    "orange": 30,
    "yellow": 60,
    "green": 120,
    "aqua": 180,
    "blue": 240,
    "purple": 270,
    "magenta": 300,
}

# RT FlatCurve encoding used by [HSV Equalizer] HCurve/SCurve/VCurve:
#   "1;x1;y1;lt1;rt1;x2;y2;lt2;rt2;..."
#   type 1 = FCT_MinMaxCPoints; x / y / tangents are 0..1 floats; the string
#   ends with a trailing ';'. Identity is the line y = 0.5 — a curve whose
#   points are all y = 0.5 is classified FCT_Empty by RT (i.e. no-op), which
#   is why identity curves must never be written.
_FLATCURVE_TYPE = "1"
_FLATCURVE_IDENTITY = 0.5
_FLATCURVE_TANGENT = 0.35  # same tangent RT uses for its own generated curves


def _hsl_slider_to_y(kind, value):
    """LR per-channel slider (-100..100) → FlatCurve y (identity = 0.5).

    Semantics mirror RT's improcfun.cc HSV Equalizer formulas:
      hue : h = (y - 0.5) * 2 + h   (h is a 0..1 hue fraction, 1.0 = 360°)
      sat : y > 0.5 → blend toward full saturation;
            y < 0.5 → s *= 1 + 2 * (y - 0.5)
      lum : same shape as saturation, but additionally damped by saturation,
            so near-grey pixels are unaffected — an inherent RT/LR difference.
    """
    v = max(-100.0, min(100.0, float(value)))
    if kind == "hue":
        # ±100 LR ⇒ ±30° hue rotation
        return _FLATCURVE_IDENTITY + (v / 100.0 * 30.0) / 720.0
    if v > 0:
        return _FLATCURVE_IDENTITY + 0.15 * v / 100.0
    # Negative side is an exact multiplicative cut: v = -100 ⇒ y = 0 ⇒ s *= 0
    return _FLATCURVE_IDENTITY + 0.5 * v / 100.0


def _hsl_flatcurve(kind, adj_by_channel):
    """Build one FlatCurve string from {channel: LR slider value}.

    Returns None when every channel is (near-)identity, so callers can skip
    writing a curve that RT would treat as empty anyway.
    """
    points = []
    for channel, hue_deg in _HSL_CHANNEL_HUE.items():
        raw = adj_by_channel.get(channel, 0.0)
        y = _hsl_slider_to_y(kind, raw) if abs(raw) >= 0.5 else _FLATCURVE_IDENTITY
        points.append([hue_deg / 360.0, y])

    # Float-safe identity test: never compare to 0.5 with '!='.
    if all(abs(y - _FLATCURVE_IDENTITY) <= 1e-6 for _, y in points):
        return None

    # Close the curve: x = 1.0 repeats the red point (red sits at 0°/360°).
    points.append([1.0, points[0][1]])

    parts = [_FLATCURVE_TYPE]
    for x, y in points:
        parts.append(f"{x:.6f}")
        parts.append(f"{y:.6f}")
        parts.append(f"{_FLATCURVE_TANGENT}")
        parts.append(f"{_FLATCURVE_TANGENT}")
    return ";".join(parts) + ";"


def rt_map_hsl(pp3, hsl_list):
    """Map LR 8-channel HSL adjustments → RT HSV Equalizer FlatCurves.

    The real RT keys are HCurve / SCurve / VCurve — HueCurve/SatCurve/ValCurve
    do not exist and are silently ignored by the engine (diff = 0.00).
    """
    if not hsl_list:
        return

    if not isinstance(hsl_list, list):
        print(
            "  ⚠️  hsl must be a LIST of objects, e.g. "
            '[{"channel": "blue", "saturation": -40}] — got '
            f"{type(hsl_list).__name__}; the value is ignored.",
            file=sys.stderr,
        )
        return

    collected = {"hue": {}, "saturation": {}, "luminance": {}}
    unknown_channels = set()
    for item in hsl_list:
        if not isinstance(item, dict):
            continue
        channel = str(item.get("channel", "")).lower()
        if channel not in _HSL_CHANNEL_HUE:
            unknown_channels.add(channel or "(missing 'channel' key)")
            continue
        for kind in collected:
            try:
                value = float(item.get(kind, 0) or 0)
            except (TypeError, ValueError):
                continue
            if abs(value) >= 0.5:
                collected[kind][channel] = value

    curves = {
        "HCurve": _hsl_flatcurve("hue", collected["hue"]),
        "SCurve": _hsl_flatcurve("saturation", collected["saturation"]),
        "VCurve": _hsl_flatcurve("luminance", collected["luminance"]),
    }
    if unknown_channels:
        print(
            "  ⚠️  hsl: unknown channel(s) "
            + ", ".join(sorted(unknown_channels))
            + " — valid: " + ", ".join(sorted(_HSL_CHANNEL_HUE))
            + "; those entries are ignored.",
            file=sys.stderr,
        )

    if not any(curves.values()):
        return

    pp3[("HSV Equalizer", "Enabled")] = True
    for key, curve in curves.items():
        if curve:
            pp3[("HSV Equalizer", key)] = curve


# LR 3-way color grading zone → RT [ColorToning] Splitco channel sliders.
# (Splitco == "Color Balance Shadows/Midtones/Highlights"; the engine's
#  mixerToCurve() turns each RGB triple into hue + strength.)
_CG_ZONE_KEYS = {
    "shadow": ("Redlow", "Greenlow", "Bluelow"),
    "midtone": ("Redmed", "Greenmed", "Bluemed"),
    "highlight": ("Redhigh", "Greenhigh", "Bluehigh"),
}


def _cg_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _hue_to_rgb_sliders(hue_deg, saturation):
    """(hue°, LR saturation 0..100) → RT Splitco RGB slider triple.

    mixerToCurve() normalises the triple to derive the hue and takes
    sat = (max - min) / 2 as the toning strength. Feeding it the pure hue
    chroma scaled by `saturation` therefore yields strength = saturation / 2
    (LR 100 → 0.5), with the hue preserved exactly.
    """
    h = (float(hue_deg) % 360.0) / 60.0
    index = int(h) % 6
    f = h - int(h)
    table = [
        (1.0, f, 0.0),
        (1.0 - f, 1.0, 0.0),
        (0.0, 1.0, f),
        (0.0, 1.0 - f, 1.0),
        (f, 0.0, 1.0),
        (1.0, 0.0, 1.0 - f),
    ]
    r, g, b = table[index]
    return tuple(int(round(c * saturation)) for c in (r, g, b))


def _warn_cg_ignored(cg_params):
    """Report LR color-grading fields that Splitco cannot express.

    RT's Splitco method has no Balance field (only Splitlr uses it) and no
    per-zone luminance controls, so those LR params are dropped — loudly,
    never silently.
    """
    dropped = []
    for key, value in sorted(cg_params.items()):
        if key.startswith("_"):
            continue
        lowered = key.lower()
        if not any(token in lowered for token in ("balance", "luminance", "blending")):
            continue
        if abs(_cg_float(value)) < 1e-6:
            continue
        dropped.append(f"{key}={value}")
    if dropped:
        print(
            "⚠️  color_grading: RT Splitco has no equivalent for "
            + ", ".join(dropped)
            + " — ignored (Balance / per-zone luminance only exist for "
            "Splitlr, which cannot express shadows+midtones+highlights at once).",
            file=sys.stderr,
        )


def rt_map_color_grading(pp3, cg_params):
    """Map LR 3-way color grading → RT [ColorToning] with Method=Splitco.

    The real RT section name is [ColorToning] (no space) — "[Color Toning]"
    is silently ignored by the engine (diff = 0.00).
    """
    if not cg_params:
        return

    nested = sorted(
        key for key, value in cg_params.items()
        if not str(key).startswith("_") and isinstance(value, (dict, list))
    )
    if nested:
        print(
            "  ⚠️  color_grading: nested value(s) "
            + ", ".join(nested)
            + ' — expected FLAT keys, e.g. {"shadow_hue": 220, "shadow_saturation": 30, '
              '"highlight_hue": 40, "highlight_saturation": 25}; ignored.',
            file=sys.stderr,
        )

    zones = {
        "shadow": (_cg_float(cg_params.get("shadow_hue")), _cg_float(cg_params.get("shadow_saturation"))),
        "midtone": (_cg_float(cg_params.get("midtone_hue")), _cg_float(cg_params.get("midtone_saturation"))),
        "highlight": (_cg_float(cg_params.get("highlight_hue")), _cg_float(cg_params.get("highlight_saturation"))),
    }
    active = {zone: values for zone, values in zones.items() if abs(values[1]) >= 0.5}
    if not active:
        return

    pp3[("ColorToning", "Enabled")] = True
    pp3[("ColorToning", "Method")] = "Splitco"
    # Strength drives strProtect = pow(strength/100, 0.4) in toningsmh()
    # (rtengine/improcfun.cc, RT 5.13). RT's default is 50 ⇒ 0.758, i.e. the
    # tint lands ~24% weaker than the saturation/200 model assumes; writing 100
    # makes the documented mapping exact.
    pp3[("ColorToning", "Strength")] = 100
    for zone, (hue, saturation) in active.items():
        r, g, b = _hue_to_rgb_sliders(hue, saturation)
        red_key, green_key, blue_key = _CG_ZONE_KEYS[zone]
        pp3[("ColorToning", red_key)] = r
        pp3[("ColorToning", green_key)] = g
        pp3[("ColorToning", blue_key)] = b

    _warn_cg_ignored(cg_params)


def rt_map_sharpening(pp3, detail):
    """Map LR sharpening → RT Sharpening (RL Deconvolution)."""
    if not detail:
        return
    amount = detail.get("sharpen_amount", 0)
    radius = detail.get("sharpen_radius", 1.0)
    if amount < 1:
        return
    pp3[("Sharpening", "Enabled")] = True
    pp3[("Sharpening", "Method")] = "rl"
    pp3[("Sharpening", "DeconvRadius")] = round(rt_clamp_f(radius * 0.75, 0.5, 2.0), 2)
    pp3[("Sharpening", "DeconvAmount")] = round(rt_clamp(amount * 1.5, 0, 250))
    pp3[("Sharpening", "DeconvIterations")] = 30


def rt_map_noise_reduction(pp3, detail):
    """Map LR noise reduction → RT Directional Pyramid Denoising."""
    if not detail:
        return
    nr = detail.get("noise_reduction", 0)
    nd = detail.get("noise_detail", 50)
    if nr < 1:
        return
    pp3[("Directional Pyramid Denoising", "Enabled")] = True
    pp3[("Directional Pyramid Denoising", "Luma")] = round(rt_clamp(nr * 0.8, 0, 100))
    pp3[("Directional Pyramid Denoising", "Ldetail")] = round(rt_clamp(100 - nd, 0, 100))
    pp3[("Directional Pyramid Denoising", "Chroma")] = round(rt_clamp(nr * 0.5 + 15, 0, 100))
    pp3[("Directional Pyramid Denoising", "Gamma")] = 1.4
    pp3[("Directional Pyramid Denoising", "Method")] = "Lab"


def rt_map_vignette(pp3, effects):
    """Map LR vignette → RT Vignetting Correction."""
    if not effects:
        return
    vig = effects.get("vignette_amount", 0)
    if abs(vig) < 0.5:
        return
    pp3[("Vignetting Correction", "Amount")] = round(abs(vig) * 1.5)
    pp3[("Vignetting Correction", "Radius")] = 50
    pp3[("Vignetting Correction", "Strength")] = 1
    pp3[("Vignetting Correction", "CenterX")] = 0
    pp3[("Vignetting Correction", "CenterY")] = 0


def rt_map_grain(pp3, effects):
    """LR grain is not mappable: RT 5.13 has no film-grain module.

    [FilmSimulation] would need a CLUT file this skill does not ship, so a
    non-zero grain_amount is reported on stderr and dropped instead of being
    written as a "_Comment" entry that never reaches the generated PP3.
    """
    if not effects:
        return
    grain = effects.get("grain_amount", 0)
    if grain < 1:
        return
    print(
        f"  ⚠️  grain_amount={grain} (size={effects.get('grain_size', 0)}) is not supported: "
        "RawTherapee 5.13 has no film-grain module — the value is ignored.",
        file=sys.stderr,
    )


def rt_map_raw(pp3, raw_params):
    """Map LR-style raw preprocessing flags → RT PP3.

    Currently handled:
      - auto_bright (bool): Lightroom's "Auto" exposure toggle. Maps to
        RT `[Exposure] Auto=true` + `Clip=0.02`. RT analyzes the histogram
        and adjusts Compensation to lift dark scenes automatically.

        Empirically verified on Nikon NEF (RT 5.12): turning this on
        alone lifts mean_luma from 32.65 (empty PP3) to 70.98 (+117%).
        Combined with `[Exposure] HistogramMatching=true` reaches
        mean_luma 83.05 with stddev 77.78 (high contrast + bright).

      - bright (float, optional): direct exposure compensation in stops,
        added on top of any user exposure value. Range ±2.0.

    Note: `params["raw"]` was historically silently dropped — agents writing
    `"raw": {"auto_bright": true}` saw their brighten request thrown away
    because `build_pp3` never consumed this section. This function fixes
    that omission.
    """
    if not raw_params:
        return
    auto_bright = raw_params.get("auto_bright")
    if auto_bright:
        pp3[("Exposure", "Auto")] = True
        # Clip 0.02 = 2% highlight clip tolerance, RT default for auto exposure
        pp3[("Exposure", "Clip")] = 0.02

    bright = raw_params.get("bright")
    if bright is not None:
        try:
            bright_val = float(bright)
        except (TypeError, ValueError):
            return
        if abs(bright_val) >= 0.01:
            # Only set if user didn't already set Compensation via basic.exposure
            if ("Exposure", "Compensation") not in pp3:
                pp3[("Exposure", "Compensation")] = round(rt_clamp_f(bright_val, -5.0, 5.0), 3)


_AUTO_MATCHED_WARNED = False


def _warn_auto_matched_override():
    """Tell the user once that a custom curve disabled Auto-Matched Curve."""
    global _AUTO_MATCHED_WARNED
    if _AUTO_MATCHED_WARNED:
        return
    _AUTO_MATCHED_WARNED = True
    print(
        "ℹ️  Auto-Matched Curve (histogram matching) is skipped for parameter sets "
        "that define tone_curve / whites / blacks — otherwise RawTherapee would "
        "replace the custom tone curve with the matched one and the adjustment "
        "would be silently lost.",
        file=sys.stderr,
    )


def build_pp3(params, style="graded", config=None, engine_version=None):
    """Convert a single LR parameter set to a RawTherapee PP3 file content string.

    All rt_map_* functions populate pp3 with (section, key) → value entries,
    which are then serialized to INI format with correct RT section names.

    ``engine_version`` is the version reported by rawtherapee-cli, written into
    [Version] AppVersion; when unknown the section is omitted (RT then applies
    its own defaults, exactly like the profiles shipped with RawTherapee).
    """
    cfg = config or {}
    pp3 = {}

    basic = params.get("basic", {})
    tc = params.get("tone_curve", {})
    hsl = params.get("hsl", [])
    cg = params.get("color_grading", {})
    detail = params.get("detail", {})
    effects = params.get("effects", {})
    raw = params.get("raw", {})

    rt_map_exposure(pp3, basic)
    rt_map_contrast(pp3, basic)
    rt_map_tone_compression(pp3, basic)
    rt_map_whitebalance(pp3, basic)
    rt_map_vibrance_saturation(pp3, basic)
    rt_map_tone_curve(pp3, tc, basic)
    rt_map_hsl(pp3, hsl)
    rt_map_color_grading(pp3, cg)
    rt_map_sharpening(pp3, detail)
    rt_map_noise_reduction(pp3, detail)
    rt_map_vignette(pp3, effects)
    rt_map_grain(pp3, effects)
    rt_map_raw(pp3, raw)  # NEW: consume params["raw"] (auto_bright / bright)

    # RAW preprocessing defaults
    pp3[("RAW", "CA_AutoCorrect")] = False
    pp3[("RAW", "DenoiseBlack")] = False
    pp3[("RAW", "HotPixelFilter")] = False
    pp3[("RAW", "DeadPixelFilter")] = False
    pp3[("RAW", "FF_AutoClipControl")] = False

    # Output settings
    bpp = cfg.get("output_bpp", 16)
    pp3[("Color Management", "OutputBPC")] = True
    if bpp == 16:
        pp3[("Output", "Format")] = "TIFF"
        pp3[("Output", "BitDepth")] = 16
    else:
        pp3[("Output", "Format")] = "JPEG"
        pp3[("Output", "Quality")] = cfg.get("output_quality", 95)

    # Lens correction
    if cfg.get("lens_correction", True):
        pp3[("LensProfile", "LcMode")] = "lensfun"
        pp3[("LensProfile", "UseDistortion")] = True
        pp3[("LensProfile", "UseVignette")] = True
        pp3[("LensProfile", "UseCA")] = True

    # Auto-Matched Camera Curve (Auto-Matched Tone Curve)
    #
    # Historical bug: this used to write `[Color Management] ToneCurve = False`,
    # which is actually a DCP (DNG Camera Profile) toggle and has nothing to do
    # with Auto-Matched Camera Curve. The correct PP3 fields live under
    # `[Exposure]`. Empirically verified on RT 5.10 / 5.12 (Nikon NEF):
    #   - `[CM] ToneCurve=true/false` and an empty PP3 produce byte-identical
    #     pixel data on a NEF without a DCP profile (0-op).
    #   - `[Exposure] HistogramMatching=true` is what actually generates the
    #     in-camera-JPEG-matched tone curve, lifting mean luma by ~+45 / +59%.
    #
    # `CurveFromHistogramMatching=false` is required: if true, RT assumes the
    # curve has already been computed and skips the expensive matching step.
    # See pixls.us discussion w/ Ingo Weyrich (RT dev) for the authoritative
    # explanation.
    # A user-supplied curve always wins. RT's HistogramMatching *replaces*
    # `[Exposure] Curve` with the in-camera-JPEG-matched curve, so leaving it on
    # while also writing a custom Curve silently discards the entire tone_curve /
    # highlights / shadows / whites / blacks request (verified on RT 5.13:
    # MAE 0.000 with HistogramMatching=1, 6.32 with HistogramMatching=0).
    _tone_curve = params.get("tone_curve") or {}
    _basic = params.get("basic") or {}
    # highlights/shadows are excluded on purpose: they map to HighlightCompr /
    # ShadowCompr (their own PP3 keys), so they coexist fine with histogram
    # matching. Only the parameters that actually write [Exposure] Curve — the
    # tone_curve knobs plus whites/blacks, which rt_map_tone_curve folds into
    # that curve — conflict with it.
    _has_custom_curve = any(v for v in _tone_curve.values()) or any(
        _basic.get(k) for k in ("whites", "blacks")
    )
    if _has_custom_curve:
        _warn_auto_matched_override()
    elif cfg.get("auto_matched_curve", True):
        pp3[("Exposure", "HistogramMatching")] = True
        pp3[("Exposure", "CurveFromHistogramMatching")] = False

    # ── Section order for PP3 output ──
    # Defines the order sections appear in the PP3 file.
    # Sections not in this list but present in pp3 will be appended at the end.
    SECTION_ORDER = [
        "Version",
        "Exposure",
        "HLRecovery",
        "White Balance",
        "Vibrance",
        "Color Management",
        "HSV Equalizer",
        "ColorToning",
        "Sharpening",
        "Directional Pyramid Denoising",
        "Vignetting Correction",
        "LensProfile",
        "Shadows & Highlights",
        "RAW",
        "Output",
    ]

    # Group pp3 entries by section
    sections = {}
    for (sec, key), val in pp3.items():
        sections.setdefault(sec, {})[key] = val

    # Build INI content
    lines = []
    written_sections = set()

    # Version header: written only when the engine version is known. RT's own
    # bundled profiles omit [Version] entirely, and the old hard-coded
    # "AppVersion=5.11 / Version=333" made every sidecar claim the wrong engine.
    if engine_version:
        lines.append("[Version]")
        lines.append(f"AppVersion={engine_version}")
        lines.append("")

    def _fmt_val(val):
        # RawTherapee expects 1/0 for booleans, not Python True/False
        if isinstance(val, bool):
            return 1 if val else 0
        return val

    for sec_name in SECTION_ORDER:
        if sec_name == "Version":
            written_sections.add(sec_name)
            continue
        if sec_name in sections:
            lines.append(f"[{sec_name}]")
            for key, val in sections[sec_name].items():
                lines.append(f"{key}={_fmt_val(val)}")
            lines.append("")
            written_sections.add(sec_name)

    # Append any remaining sections not in SECTION_ORDER (except _Comment)
    for sec_name in sorted(sections.keys()):
        if sec_name in written_sections or sec_name.startswith("_"):
            continue
        lines.append(f"[{sec_name}]")
        for key, val in sections[sec_name].items():
            lines.append(f"{key}={_fmt_val(val)}")
        lines.append("")

    style_tag = params.get("style", style)
    safe_style = "".join(c if c.isalnum() or c in "-_" else "_" for c in style_tag)[:20]

    return "\n".join(lines), safe_style


# Formats the RawTherapee build itself cannot decode. The 5.13 Windows build
# ships without libheif, so HEIC/HEIF inputs are rejected outright:
#   "[...] is not one of the selected parsed extensions. Image skipped."
# They are transcoded through pillow-heif (the decoder photo-toolkit already
# uses for these files) so the documented HEIC support actually works; sources
# with more than 8 bits per channel keep their depth via tifffile.
_RT_UNREADABLE_EXTENSIONS = {".heic", ".heif"}


def _prepare_rt_input(raw_path, work_dir):
    """Return (path RawTherapee can read, temp file to clean up or None).

    HEIC/HEIF is transcoded under ``work_dir`` keeping the original stem, so RT's
    "<stem>.jpg" output naming — and the rename step that follows it — keeps
    working unchanged.

    Depth is preserved where the source has it: HEIC may carry 10/12-bit samples
    and pillow-heif decodes those as 16-bit arrays, so they are written as 16-bit
    RGB TIFF (tifffile, embedded ICC profile carried over in tag 34675) instead of
    being flattened to 8-bit. 8-bit sources keep taking the plain Pillow path.
    RawTherapee always receives the base image only — an iPhone "HDR" gain map is
    never applied.
    """
    if raw_path.suffix.lower() not in _RT_UNREADABLE_EXTENSIONS:
        return raw_path, None

    try:
        import numpy as np
        import pillow_heif
    except ImportError as e:
        raise RuntimeError(
            f"{raw_path.name}: HEIC/HEIF inputs need pillow-heif (with numpy), which is not "
            f"available ({e}). Install it (pip install pillow-heif) or convert the file first "
            "with photo-toolkit/convert.py."
        ) from e

    work_dir.mkdir(parents=True, exist_ok=True)
    tiff_path = work_dir / f"{raw_path.stem}.tif"

    # Pillow's HEIF plugin always flattens to 8-bit, so read the pixels through
    # pillow-heif's own API instead; 10/12-bit sources come back as uint16.
    pixels = None
    icc = b""
    try:
        heif = pillow_heif.open_heif(str(raw_path), convert_hdr_to_8bit=False)
        pixels = np.asarray(heif[0])
        icc = bytes(heif.info.get("icc_profile") or b"")
    except Exception as e:
        print(
            f"{raw_path.name}: native HEIC decode failed ({e}); falling back to 8-bit.",
            file=sys.stderr,
        )

    if pixels is not None and pixels.dtype == np.uint16:
        try:
            import tifffile
        except ImportError:
            print(
                f"{raw_path.name}: this HEIC carries more than 8-bit samples; writing it "
                "losslessly needs tifffile (pip install tifffile). Falling back to 8-bit.",
                file=sys.stderr,
            )
        else:
            if pixels.ndim == 3 and pixels.shape[2] >= 3:
                pixels, photometric = pixels[:, :, :3], "rgb"
            elif pixels.ndim == 3:
                pixels, photometric = pixels[:, :, 0], "minisblack"
            else:
                photometric = "minisblack"
            extra = {"extratags": [(34675, 7, len(icc), icc, True)]} if icc else {}
            tifffile.imwrite(
                tiff_path, pixels, photometric=photometric, compression="deflate", **extra
            )
            return tiff_path, tiff_path

    pillow_heif.register_heif_opener()
    from PIL import Image

    with Image.open(raw_path) as im:
        im.convert("RGB").save(tiff_path, format="TIFF", compression="tiff_deflate")
    return tiff_path, tiff_path


# Input format classification for smart output routing
_RAW_EXTS = {".nef", ".nrw", ".cr2", ".cr3", ".crw", ".arw", ".srf", ".sr2",
             ".raf", ".orf", ".rw2", ".pef", ".srw", ".rwl", ".dng",
             ".3fr", ".fff", ".iiq", ".x3f"}
_HEIC_EXTS = {".heic", ".heif"}
_JPG_EXTS = {".jpg", ".jpeg"}


def is_hires_input(raw_path):
    """Return True if input is RAW or high-bit-depth HEIC (worth 16-bit TIFF)."""
    ext = raw_path.suffix.lower()
    return ext in _RAW_EXTS or ext in _HEIC_EXTS


def _compute_output_name(raw_path, safe_style, raw_root=None, output_ext=".jpg"):
    """Compute output filename with subdirectory prefix if needed.

    If raw_path is under a subdirectory of raw_root, prefix the output name
    with the subdirectory path: e.g., 001_DSC_0001_暖春丝滑.jpg
    """
    stem = raw_path.stem
    if raw_root:
        try:
            rel = raw_path.relative_to(raw_root)
            if rel.parent != Path("."):
                prefix = str(rel.parent).replace("/", "_").replace("\\", "_")
                return f"{prefix}_{stem}_{safe_style}{output_ext}"
        except ValueError:
            pass
    return f"{stem}_{safe_style}{output_ext}"


def grade_single_file(
    raw_path,
    output_dir,
    params,
    config,
    quality=95,
    overwrite=False,
    dry_run=False,
    pp3_only=False,
    pp3_output_dir=None,
    fast_export=False,
    raw_root=None,
):
    """Grade a single photo using RawTherapee CLI: LR params → PP3 → render."""
    start = time.monotonic()
    raw_name = raw_path.name

    try:
        style = params.get("style", "graded")
        safe_style = "".join(c if c.isalnum() or c in "_-" else "_" for c in style)[:20]

        # Smart output routing: RAW/HEIC -> 16-bit TIFF (无损存档); JPG -> JPG (按 quality 重编码，默认 95)
        import copy
        effective_config = copy.deepcopy(config)
        if is_hires_input(raw_path):
            effective_config["output_bpp"] = 16
            output_ext = ".tif"
        else:
            effective_config["output_bpp"] = 8
            effective_config["output_quality"] = quality
            output_ext = ".jpg"

        pp3_content, safe_style = build_pp3(
            params, style=safe_style, config=effective_config, engine_version=_RT_VERSION
        )

        # PP3-only mode
        if pp3_only and pp3_output_dir:
            pp3_dir = Path(pp3_output_dir).expanduser().resolve()
            pp3_path = pp3_dir / f"{raw_path.stem}_{safe_style}.pp3"
            pp3_dir.mkdir(parents=True, exist_ok=True)
            with open(pp3_path, "w", encoding="utf-8") as f:
                f.write(pp3_content)
            elapsed = time.monotonic() - start
            return (raw_name, True, f"✓ PP3 generated: {pp3_path.name} ({len(pp3_content)} bytes)", elapsed)

        jpg_name = _compute_output_name(raw_path, safe_style, raw_root, output_ext)
        jpg_path = output_dir / jpg_name

        if jpg_path.exists() and not overwrite:
            elapsed = time.monotonic() - start
            return (raw_name, True, f"⏭ Skipped (exists): {jpg_name}", elapsed)

        if dry_run:
            tmp_pp3 = output_dir / f"{raw_path.stem}_{safe_style}.pp3"
            with open(tmp_pp3, "w", encoding="utf-8") as f:
                f.write(pp3_content)
            elapsed = time.monotonic() - start
            return (raw_name, True, f"🔍 Dry-run: PP3 written to {tmp_pp3.name} ({len(pp3_content)} bytes)", elapsed)

        # Per-task scratch directory. RawTherapee always names its render after
        # the input stem, and the temp PP3/TIFF files are stem-based too, so two
        # styles of the same source file running concurrently (16 workers by
        # default) would otherwise overwrite each other's PP3/TIFF and race on
        # the same render path — one job dies with "Error saving to ...".
        task_tmp = output_dir / "__rt_tmp__" / f"{raw_path.stem}_{safe_style}_{os.getpid()}_{int(time.monotonic() * 1e6)}"
        task_tmp.mkdir(parents=True, exist_ok=True)
        tmp_pp3 = task_tmp / f"{raw_path.stem}.pp3"
        with open(tmp_pp3, "w", encoding="utf-8") as f:
            f.write(pp3_content)

        # Build rawtherapee-cli command (RT 5.10: -c must be last)
        cli = [_RT_CLI]
        if fast_export:
            cli += ["-f"]
        cli += ["-o", str(task_tmp)]
        cli += [f"-j{quality}"]  # RT 5.10: -j95 not -j 95
        cli += ["-p", str(tmp_pp3)]
        if overwrite:
            cli += ["-Y"]
        # RT builds without libheif cannot read HEIC/HEIF at all, so those
        # inputs are transcoded to TIFF first (see _prepare_rt_input). Both the
        # temp PP3 and this TIFF live in the per-task scratch dir above.
        rt_input, tmp_input = _prepare_rt_input(raw_path, task_tmp)
        cli += ["-c", str(rt_input)]  # Must be last

        result = subprocess.run(cli, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            shutil.rmtree(task_tmp, ignore_errors=True)
            stderr_tail = result.stderr[-500:] if len(result.stderr) > 500 else result.stderr
            elapsed = time.monotonic() - start
            return (raw_name, False, f"✗ {raw_name}: RT error (code {result.returncode})\n{stderr_tail}", elapsed)

        # RT writes the render into its scratch dir under the ORIGINAL stem
        # (e.g. "<stem>.tif" for 16-bit TIFF, "<stem>.jpg" for JPEG).
        # The styled output name is applied by this script afterwards.
        # The source file must never be moved.
        produced = task_tmp / f"{raw_path.stem}{output_ext}"
        if produced.exists():
            os.replace(str(produced), str(jpg_path))
        else:
            # Try any image extension in scratch dir (TIFF/JPG variants)
            leftovers = sorted(task_tmp.glob(f"*{output_ext}"))
            if not leftovers:
                leftovers = sorted(task_tmp.glob("*.tif")) + sorted(task_tmp.glob("*.tiff")) + sorted(task_tmp.glob("*.jpg"))
            if leftovers:
                os.replace(str(leftovers[0]), str(jpg_path))
            else:
                # RT occasionally outputs into the input directory (rare);
                # move only if that file is NOT the source file itself.
                alt_img = raw_path.parent / f"{raw_path.stem}{output_ext}"
                if alt_img.exists() and alt_img.resolve() != raw_path.resolve():
                    shutil.move(str(alt_img), str(jpg_path))
        shutil.rmtree(task_tmp, ignore_errors=True)
        try:
            task_tmp.parent.rmdir()  # drop __rt_tmp__ once the last job is done
        except OSError:
            pass
        output_jpg = jpg_path

        elapsed = time.monotonic() - start
        if output_jpg.exists():
            file_size_kb = output_jpg.stat().st_size / 1024
            return (raw_name, True, f"✓ {output_jpg.name} ({file_size_kb:.0f}KB)", elapsed)
        else:
            alt_img = raw_path.parent / f"{raw_path.stem}_{safe_style}{output_ext}"
            if alt_img.exists():
                return (raw_name, True, f"✓ {alt_img.name} (RT side-by-side)", elapsed)
            return (raw_name, True, f"✓ {raw_name} (RT completed)", elapsed)

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return (raw_name, False, f"✗ {raw_name}: Timeout after {elapsed:.1f}s", elapsed)
    except Exception as e:
        elapsed = time.monotonic() - start
        return (raw_name, False, f"✗ {raw_name}: {e}", elapsed)


# ═══════════════════════════════════════════════════════════════
# Shared file helpers
# ═══════════════════════════════════════════════════════════════


# ── grading_params.json schema constants ───────────────────────
#
# Authoritative field names that build_pp3 / rt_map_* functions consume.
# Update both BASIC_KEYS and the rt_map_*() implementations together —
# adding a key here without a mapper, or vice versa, creates silent
# "param accepted but does nothing" bugs.

_BASIC_KEYS = {
    # Tone / exposure
    "exposure",
    "contrast",
    "highlights",
    "shadows",
    "whites",
    "blacks",
    # White balance — note: Lightroom's relative temp_offset/tint are
    # intentionally NOT mapped (RT requires absolute Kelvin). Use the
    # *_kelvin / *_offset / green forms.
    "temperature_kelvin",
    "green",
    "tint_offset",
    "temp_offset",  # accepted but ignored by rt_map_whitebalance (deliberate)
    # Vibrance / saturation
    "vibrance",
    "saturation",
}
_DETAIL_KEYS = {"sharpen_amount", "sharpen_radius", "noise_reduction", "noise_detail"}
_EFFECTS_KEYS = {"vignette_amount", "grain_amount", "grain_size"}
_RAW_KEYS = {"auto_bright", "bright"}
_NESTED_GROUPS = ("basic", "tone_curve", "hsl", "color_grading", "detail", "effects", "raw")

# Known unrecoverable LLM-mistake field names. These are values that look
# plausible to an LLM but where silently accepting them would *lose data*
# (e.g. temperature=6500 silently dropped means user's WB was not applied).
# Hard-fail with a precise correction hint.
#
# NOTE: top-level `params` is intentionally NOT here — it's a recognized
# legacy schema that _normalize_flat_params() migrates with a warning.
# Only fields that have no safe migration go in this dict.
#
# Each entry: bad_key → (correct_field_path, explanation)
_KNOWN_BAD_ALIASES = {
    "temperature": (
        "basic.temperature_kelvin",
        "RT needs an absolute Kelvin value (2000-25000), not a relative offset",
    ),
    "tint": (
        "basic.tint_offset (or basic.green for direct RT multiplier)",
        "RT's Green channel is a multiplier (0.5-2.0); tint_offset is a ±100 LR-style shift",
    ),
}


def _scan_for_bad_aliases(field_dict, prefix=""):
    """Walk a dict looking for unrecoverable known-bad field names.

    Returns list of (qualified_path, (correct_field, reason)) tuples.
    Skip keys that match a valid _BASIC_KEYS entry — so `temperature_kelvin`
    doesn't false-positive on the `temperature` matcher.
    """
    if not isinstance(field_dict, dict):
        return []
    bad = []
    for key in field_dict:
        if key in _KNOWN_BAD_ALIASES and key not in _BASIC_KEYS:
            qualified = f"{prefix}{key}" if prefix else key
            bad.append((qualified, _KNOWN_BAD_ALIASES[key]))
    return bad


def _check_known_aliases(entry, file_label):
    """Scan an entry for hard-fail bad field names.

    Locations checked (in order):
      1. Top level — covers `{file, temperature: 6500}` style mistakes
      2. entry["basic"] — covers `{basic: {temperature: 6500}}`
      3. entry["params"] — covers the legacy flat-schema case
         `{params: {temperature: 6500}}` (still hard-fails on the inner
         temperature even though `params` itself is just deprecated).

    Hard-failure exits with code 2 and a precise hint. Recoverable
    mistakes (top-level `params`) are handled by _normalize_flat_params
    via a deprecation warning instead.
    """
    bad = []
    bad.extend(_scan_for_bad_aliases(entry))
    bad.extend(_scan_for_bad_aliases(entry.get("basic"), prefix="basic."))
    bad.extend(_scan_for_bad_aliases(entry.get("params"), prefix="params."))

    if not bad:
        return

    print(f"\n❌ Invalid grading_params.json entry for {file_label}:", file=sys.stderr)
    for key, (correct, reason) in bad:
        print(f"   ✗ Field '{key}' is not recognized.", file=sys.stderr)
        print(f"     → Use '{correct}' instead.", file=sys.stderr)
        print(f"     → Why: {reason}", file=sys.stderr)
    print(
        "\n   Authoritative schema reference: see rt_map_*() functions in "
        "photo-grader/scripts/grade.py,",
        file=sys.stderr,
    )
    print(
        "   or the bundled Curator prompt at "
        "photo-grader/templates/photo-curator-user-prompt-grading.md",
        file=sys.stderr,
    )
    print(
        "   (LR→RT mapping reference: "
        "photo-grader/templates/rt-mapping-reference.md)",
        file=sys.stderr,
    )
    sys.exit(2)


def _normalize_flat_params(entry):
    """Convert legacy flat {params: {...}} dict to nested structure.

    Accepts (and migrates with a deprecation warning) the old flat format
    that puts every field under top-level `params`. The canonical format
    uses nested groups: {file, style, basic: {...}, tone_curve: {...}, ...}.

    Hard-fails on known LLM-mistake aliases (params/temperature/tint at the
    top level or under basic) via _check_known_aliases().
    """
    # First: hard-fail on truly bad aliases (caught here regardless of nesting).
    # This intentionally runs BEFORE the flat→nested migration so users see
    # "use temperature_kelvin" before any silent normalization.
    _check_known_aliases(entry, file_label=entry.get("file", "<unknown>"))

    flat = entry.get("params", {})
    if not flat:
        return entry
    if any(k in entry for k in _NESTED_GROUPS):
        # Mixed schema: both nested groups (basic/tone_curve/...) AND legacy
        # top-level `params` are present. We can't safely merge them without
        # guessing the user's intent (which one wins on collision?), so
        # the nested groups take precedence and `params` is dropped.
        # Warn loudly so the user can move keys to the right nested group —
        # silent drop here is exactly the kind of failure mode this commit
        # set out to eliminate (see CHANGELOG 1.0.1 "P1-1 schema hard-fail").
        print(
            f"⚠️  Mixed schema in entry for '{entry.get('file', '?')}': "
            f"both nested groups (basic/tone_curve/...) AND legacy top-level "
            f"'params' are present. The 'params' block will be IGNORED — "
            f"move its keys into the appropriate nested group "
            f"(basic / tone_curve / hsl / color_grading / detail / effects / raw).",
            file=sys.stderr,
        )
        return entry

    print(
        f"⚠️  DEPRECATED schema in entry for '{entry.get('file', '?')}': "
        f"top-level 'params' is legacy. Use nested groups: "
        f"{{file, basic: {{...}}, tone_curve: {{...}}, raw: {{...}}, ...}}.",
        file=sys.stderr,
    )

    result = {"file": entry.get("file", ""), "style": entry.get("style", "graded")}
    basic, detail, effects, raw_params = {}, {}, {}, {}
    unrecognized = []
    for k, v in flat.items():
        if k in _BASIC_KEYS:
            basic[k] = v
        elif k in _DETAIL_KEYS:
            detail[k] = v
        elif k in _EFFECTS_KEYS:
            effects[k] = v
        elif k in _RAW_KEYS:
            raw_params[k] = v
        else:
            unrecognized.append(k)
    if unrecognized:
        print(
            f"   ⚠️  Ignored unrecognized field(s) inside flat params: "
            f"{', '.join(unrecognized)}",
            file=sys.stderr,
        )
    if basic:
        result["basic"] = basic
    if detail:
        result["detail"] = detail
    if effects:
        result["effects"] = effects
    if raw_params:
        result["raw"] = raw_params
    return result


def load_grading_params(json_path):
    """Load grading parameters from JSON file. Supports multiple formats."""
    path = Path(json_path).expanduser().resolve()
    if not path.exists():
        print(f"❌ Parameter file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in parameter file: {path}", file=sys.stderr)
        print(f"   Line {e.lineno}, column {e.colno}: {e.msg}", file=sys.stderr)
        sys.exit(1)

    entries = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        if "files" in data and isinstance(data["files"], list):
            entries = data["files"]
        else:
            entries = [data]
    else:
        print("❌ Invalid JSON format: expected object or array", file=sys.stderr)
        sys.exit(1)

    return [_normalize_flat_params(e) for e in entries]


def find_supported_files(input_dir, recursive=False):
    """Find all supported photo files in directory, sorted by name.

    Skips special directories (thumbnails, graded, sessions) to avoid
    processing already-converted or already-graded files.
    """
    SKIP_DIRS = {"thumbnails", "graded", "sessions", ".ds_store"}
    input_dir = Path(input_dir)
    results = []
    if recursive:
        for p in sorted(input_dir.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                if any(part in SKIP_DIRS for part in p.parts):
                    continue
                results.append(p)
    else:
        for p in sorted(input_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                results.append(p)
    return results


def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds) // 60
    secs = seconds - minutes * 60
    return f"{minutes}m {secs:.0f}s"


def get_cpu_count():
    """Get a reasonable default worker count (cpu_count * 2, max 16)."""
    try:
        return min((os.cpu_count() or 4) * 2, 16)
    except Exception:
        return 4


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Apply Lightroom-style color grading to camera photos via RawTherapee",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported formats: RAW (NEF, CR2, CR3, ARW, RAF, ORF, RW2, DNG, PEF, SRW, etc.), JPG, HEIC/HEIF

Engine: RawTherapee CLI (rawtherapee-cli) — professional-grade output
  AMAZE demosaicing, RL Deconvolution sharpening, IWT denoise,
  lensfun correction, Auto-Matched Tone Curve (~50 camera models).

Examples:
  %(prog)s grading_params.json
  %(prog)s grading_params.json --raw-dir ~/Photos/RAW --output ~/Photos/Graded
  %(prog)s grading_params.json --quality 98
  %(prog)s grading_params.json --dry-run
  %(prog)s grading_params.json --pp3-only --pp3-output ./pp3_files/

  # Uniform mode: apply one parameter set to all files in a directory
  %(prog)s grading_params.json --uniform-dir ~/Photos/timelapse --output ~/Photos/graded
        """,
    )
    parser.add_argument("params_json", help="JSON file with grading parameters")
    parser.add_argument("--raw-dir", type=str, default=None, help="RAW 文件目录（仅当 file 字段为相对路径时需要）")
    parser.add_argument(
        "--uniform-dir", type=str, default=None, help="Apply first parameter set to ALL files in this directory"
    )
    parser.add_argument("--output", type=str, default=None, help="Output directory for graded JPGs")
    parser.add_argument("--config", type=str, default=None, help="Path to config.toml")
    parser.add_argument("--quality", type=int, default=None, help="JPEG quality 1-100 (default: 95)")
    parser.add_argument("--overwrite", action="store_true", default=None, help="Overwrite existing output files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without processing")
    # RT-specific options
    parser.add_argument("--pp3-only", action="store_true", help="Only generate PP3 files, don't render")
    parser.add_argument(
        "--pp3-output", type=str, default="./pp3/", help="Directory for PP3-only output (default: ./pp3/)"
    )
    parser.add_argument("--fast-export", action="store_true", help="Use fast export mode (skip heavy modules)")
    parser.add_argument(
        "--lens-corr", action="store_true", default=None, help="Enable lens correction (default: from config)"
    )
    parser.add_argument("--no-lens-corr", dest="lens_corr", action="store_false", help="Disable lens correction")
    parser.add_argument(
        "--auto-match",
        action="store_true",
        default=None,
        help="Enable Auto-Matched Tone Curve (RT HistogramMatching — matches in-camera JPG tone)",
    )
    parser.add_argument(
        "--no-auto-match",
        dest="auto_match",
        action="store_false",
        help="Disable Auto-Matched Tone Curve",
    )
    parser.add_argument("--workers", type=int, default=None, help="Parallel workers")

    args = parser.parse_args()

    cfg = load_config(args.config)

    # Check RT CLI
    check_rt_cli(cfg)

    # Merge CLI flags into config
    if args.lens_corr is not None:
        cfg["lens_correction"] = args.lens_corr
    if args.auto_match is not None:
        cfg["auto_matched_curve"] = args.auto_match

    raw_dir_raw = args.raw_dir or cfg.get("raw_dir") or cfg.get("nef_dir")
    output_raw = args.output or cfg.get("output_dir")
    quality = args.quality if args.quality is not None else cfg.get("jpeg_quality", 95)
    workers = args.workers if args.workers is not None else cfg.get("workers") or get_cpu_count()
    overwrite = args.overwrite if args.overwrite is not None else cfg.get("overwrite", False)
    fast_export = args.fast_export or cfg.get("fast_export", False)

    if not args.uniform_dir and not raw_dir_raw:
        # raw_dir is optional when params use absolute paths
        raw_dir = None
    else:
        raw_dir = Path(raw_dir_raw).expanduser().resolve() if raw_dir_raw else None

    # --dry-run / --pp3-only never write a rendered JPG, so demanding --output
    # from them was needless friction.
    if not output_raw and not (args.dry_run or args.pp3_only):
        parser.error("--output is required. Provide it as an argument or set 'output_dir' in config.toml")
    if not 1 <= quality <= 100:
        print("Error: --quality must be between 1 and 100", file=sys.stderr)
        sys.exit(1)
    output_dir = Path(output_raw).expanduser().resolve() if output_raw else None

    all_params = load_grading_params(args.params_json)
    print(f"📋 Loaded {len(all_params)} grading parameter set(s)")

    # Uniform mode
    uniform_dir = args.uniform_dir
    if uniform_dir:
        uniform_path = Path(uniform_dir).expanduser().resolve()
        if not uniform_path.exists():
            print(f"❌ Uniform directory not found: {uniform_path}", file=sys.stderr)
            sys.exit(1)
        base_params = all_params[0]
        base_params.pop("file", None)
        all_files = find_supported_files(uniform_path)
        if not all_files:
            print(f"❌ No supported photo files found in: {uniform_path}")
            sys.exit(1)

        ext_counts = {}
        for f in all_files:
            ext = f.suffix.upper()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
        ext_summary = ", ".join(f"{ext}: {cnt}" for ext, cnt in sorted(ext_counts.items()))
        print(f"📷 Uniform mode: applying 1 parameter set to {len(all_files)} file(s) ({ext_summary})")

        tasks = [(f, base_params) for f in all_files]
    else:
        tasks = []
        for p in all_params:
            filename = p.get("file", "")
            if not filename:
                print(f"  ⚠️  Skipping entry with no 'file' field: {p.get('style', '?')}")
                continue
            raw_path = find_raw_file(filename, raw_dir)
            if raw_path is None:
                print(f"  ⚠️  RAW file not found: {filename}")
                continue
            tasks.append((raw_path, p))

    if not tasks:
        print("❌ No matching RAW files found for any parameter set.")
        sys.exit(1)

    print(f"\n📷 Will process {len(tasks)} file(s) via RawTherapee")

    if args.dry_run:
        print(f"\n🔍 Dry run — files that would be graded:")
        for raw_path, p in tasks:
            print(f"  📸 {raw_path.name} [{raw_path.suffix.upper().lstrip('.')}] → style: {p.get('style', '?')}")
        sys.exit(0)

    if args.pp3_only:
        pp3_dir = Path(args.pp3_output).expanduser().resolve()
        print(f"\n📝 PP3-only mode: generating PP3 files to {pp3_dir}")
    else:
        print(f"\n⚙️  Grading: quality={quality}, workers={workers}")
        if uniform_dir:
            print(f"   Source: {Path(uniform_dir).expanduser().resolve()} (uniform)")
        elif raw_dir:
            print(f"   RAW dir: {raw_dir}")
        else:
            print(f"   RAW files: from absolute paths in params")
        print(f"   Output:  {output_dir}\n")

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    total_start = time.monotonic()
    success_count = 0
    skip_count = 0
    error_count = 0
    total = len(tasks)

    # RT is I/O-bound (external CLI), use ThreadPoolExecutor
    max_workers = min(workers, total) if workers > 0 else min(total, get_cpu_count())

    if max_workers <= 1 or total == 1:
        for i, (raw_path, p) in enumerate(tasks, 1):
            raw_name, success, message, elapsed = grade_single_file(
                raw_path,
                output_dir,
                p,
                cfg,
                quality,
                overwrite,
                args.dry_run,
                args.pp3_only,
                args.pp3_output if args.pp3_only else None,
                fast_export,
                raw_root=raw_dir,
            )
            print(f"  [{i}/{total}] {message} ({format_time(elapsed)})")
            if success:
                skip_count += 1 if "Skipped" in message else 0
                success_count += 0 if "Skipped" in message else 1
            else:
                error_count += 1
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    grade_single_file,
                    raw_path,
                    output_dir,
                    p,
                    cfg,
                    quality,
                    overwrite,
                    args.dry_run,
                    args.pp3_only,
                    args.pp3_output if args.pp3_only else None,
                    fast_export,
                    raw_root=raw_dir,
                ): raw_path
                for raw_path, p in tasks
            }
            done = 0
            for future in as_completed(futures):
                done += 1
                raw_name, success, message, elapsed = future.result()
                print(f"  [{done}/{total}] {message} ({format_time(elapsed)})")
                if success:
                    skip_count += 1 if "Skipped" in message else 0
                    success_count += 0 if "Skipped" in message else 1
                else:
                    error_count += 1

    total_elapsed = time.monotonic() - total_start
    print(f"\n{'─' * 55}")
    print(f"✅ Done in {format_time(total_elapsed)}")
    if args.pp3_only:
        print(f"   PP3 files generated: {success_count} in {Path(args.pp3_output).resolve()}")
    else:
        print(f"   Graded: {success_count}  |  Skipped: {skip_count}  |  Errors: {error_count}")
        print(f"   Output: {output_dir}")

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
