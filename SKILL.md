---
name: rawtherapee-photo-skills
version: 1.0.3
description: |
  AI photography post-processing toolkit (photo-toolkit + photo-grader + photo-previewer
  merged into one skill):
  batch convert RAW/JPG/HEIC to JPG thumbnails, find photos by shooting date, detect timelapse
  sequences, deflicker frames, assemble frames into MP4 video, generate before/after or grid
  layout previews, serve an interactive browser preview of a graded session (graded↔original
  grid toggle, per-style tabs, mobile gestures), and apply professional Lightroom-style color
  grading driven by LLM-generated JSON parameters (RawTherapee CLI as the grading engine).

  Use when the user wants to:
    - Convert RAW/JPG/HEIC files to JPG format (single file or batch)
    - Generate thumbnails / previews from camera photos
    - Batch process camera photos in a directory (with optional recursive search)
    - Find / filter / list photos by shooting date
    - Detect timelapse sequences, deflicker frames, assemble frames into MP4 video
    - Apply color grading / post-processing to camera photos
    - Batch apply Lightroom-style adjustments (exposure, contrast, HSL, tone curve, etc.)
    - Process a set of photo files with AI-recommended color parameters
    - Export color-graded JPGs or RawTherapee PP3 sidecar files from RAW/JPG/HEIC files
    - Apply uniform grading to all files in a directory (timelapse / batch mode)
    - Generate before/after comparison or grid (宫格) preview images
    - Preview a graded session in the browser with an interactive graded↔original grid toggle
    - Browse the historical grading sessions of a project (laptop or phone)

  Triggers: User mentions converting RAW/NEF/CR2/CR3/ARW/RAF/ORF/RW2/DNG/JPG/HEIC to JPG,
  generating thumbnails, batch processing camera photos, finding photos by date, timelapse,
  deflicker, video assembly, color grading, applying Lightroom parameters, post-processing
  camera photos, uniform grading for timelapse sequences, browser preview of graded photos,
  interactive before/after preview, preview server, mobile preview.

  Supported camera brands: Nikon (NEF/NRW), Canon (CR2/CR3/CRW), Sony (ARW/SRF/SR2),
  Fujifilm (RAF), Olympus/OM (ORF), Panasonic (RW2), Pentax (PEF), Samsung (SRW),
  Leica (RWL/DNG), Adobe DNG, Hasselblad (3FR/FFF), Phase One (IIQ), Sigma (X3F),
  plus standard JPEG (.jpg/.jpeg) and Apple HEIC/HEIF (.heic/.heif).

  Dependencies:
    System: libraw (RedHat: dnf install LibRaw-devel / Debian: apt-get install libraw-dev),
            ffmpeg (only needed by assemble.py), RawTherapee CLI (only needed by photo-grader)
    Python: rawpy, pillow, numpy, pillow-heif (optional, for HEIC/HEIF), tomli (Python < 3.11)
metadata:
  openclaw:
    homepage: https://github.com/MrC-Sinclair/rawtherapee-photo-skills
    emoji: "📸"
    requires:
      bins:
        - python3
---

# rawtherapee-photo-skills — convert, screen, grade, and compose camera photos.
This single skill bundles three upstream modules, which share one root `config.toml`:

- **photo-toolkit** — convert / find_by_date / layout_preview / deflicker / assemble
- **photo-grader** — RawTherapee-based color grading
- **photo-previewer** — interactive browser preview server for graded sessions

## Pipeline

```
RAW / JPG / HEIC
    │
    ▼  photo-toolkit/scripts/convert.py
    │  Generate JPG thumbnails for preview
    │
    ▼  [LLM generates grading_params.json]
    │
    ▼  photo-grader/scripts/grade.py
    │  Batch color grading (RawTherapee)
    │
    ├──▶ photo-toolkit/scripts/layout_preview.py
    │    Before/After comparison or grid preview (static composite, fallback)
    │
    └──▶ photo-previewer/scripts/preview.py
         Interactive browser preview (per-style tabs, graded↔original toggle)
```

## Supported Formats

### Camera RAW

| Brand      | Extensions             |
| ---------- | ---------------------- |
| Nikon      | `.nef`, `.nrw`         |
| Canon      | `.cr2`, `.cr3`, `.crw` |
| Sony       | `.arw`, `.srf`, `.sr2` |
| Fujifilm   | `.raf`                 |
| Olympus/OM | `.orf`                 |
| Panasonic  | `.rw2`                 |
| Pentax     | `.pef`                 |
| Samsung    | `.srw`                 |
| Leica      | `.rwl`, `.dng`         |
| Adobe DNG  | `.dng`                 |
| Hasselblad | `.3fr`, `.fff`         |
| Phase One  | `.iiq`                 |
| Sigma      | `.x3f`                 |

### Standard Image / Apple

| Format    | Extensions       | Notes                                            |
| --------- | ---------------- | ------------------------------------------------ |
| JPEG      | `.jpg`, `.jpeg`  | Processed directly with Pillow                   |
| HEIC/HEIF | `.heic`, `.heif` | Requires `pip install pillow-heif` (optional)    |

> **Note**: RAW files provide full 16-bit editing latitude for maximum quality. JPG/HEIC are 8-bit —
> grading range is more limited, exposure adjustments should be more conservative.

## Dependencies & Setup

**Prefer venv**: Before running scripts, activate the project-root virtual environment (e.g. `.venv/`).
If it doesn't exist, create one first:

```bash
# Create venv and install dependencies (recommended)
python3 -m venv .venv
source .venv/bin/activate
pip install -r photo-toolkit/requirements.txt -r photo-grader/requirements.txt

# Or run each module's setup script
bash photo-toolkit/scripts/setup_deps.sh
bash photo-grader/scripts/setup_deps.sh

# Before each session, activate venv
source .venv/bin/activate
```

### System requirements

- **libraw** — `brew install libraw` (macOS) / `apt-get install libraw-dev` (Debian) / `dnf install LibRaw-devel` (RedHat)
- **FFmpeg** — `brew install ffmpeg` / `apt-get install ffmpeg` — only needed by `assemble.py`
- **RawTherapee CLI** — required by `photo-grader` only (`apt install rawtherapee-cli` on Debian,
  `dnf install RawTherapee` on Fedora; on Windows the CLI is located automatically, see Windows Notes)

**Verify:**

```bash
python3 -c "import rawpy; from PIL import Image; import numpy; print('✓ Core dependencies installed')"
python3 -c "from pillow_heif import register_heif_opener; print('✓ HEIC/HEIF support available')" 2>/dev/null || echo "ℹ HEIC/HEIF support not installed (optional: pip install pillow-heif)"
```

## Config Files

Copy `config.example.toml` to `config.toml` (in this folder, next to `SKILL.md`) and edit to set your
directories. Every module falls back to the shared root `config.toml` when it has no own copy.
CLI arguments always override config values.

| Module        | Key config fields                                                        |
| ------------- | ------------------------------------------------------------------------ |
| photo-toolkit | `raw_dir`, `output_dir`, `jpeg_quality` (85), `max_size` (1200)          |
| photo-grader  | `raw_dir`, `output_dir`, `jpeg_quality` (95), `rawtherapee_cli`, `lens_correction`, `auto_matched_curve` |

## photo-toolkit

### 1. `convert.py` — Photo → JPG Thumbnails

Supports RAW, JPG, and HEIC/HEIF input. By default, thumbnails are output to `{input}/thumbnails/`.

```bash
# Convert all photo files (thumbnails output to ~/data/RAW/thumbnails/)
python3 photo-toolkit/scripts/convert.py ~/data/RAW

# Custom settings
python3 photo-toolkit/scripts/convert.py ~/data/RAW ~/data/output/thumbnails --size 2048 --quality 95

# Read file list from stdin (pipe from find_by_date.py)
python3 photo-toolkit/scripts/find_by_date.py --date today ~/data/RAW | \
    python3 photo-toolkit/scripts/convert.py --from-stdin

# With report output
python3 photo-toolkit/scripts/convert.py ~/data/RAW --report /tmp/convert_report.json

# Dry run
python3 photo-toolkit/scripts/convert.py ~/data/RAW --dry-run
```

| Option         | Description                        | Default               |
| -------------- | ---------------------------------- | --------------------- |
| `input`        | Photo file or directory            | from config           |
| `output_dir`   | Output directory                   | `{input}/thumbnails/` |
| `--size`       | Max thumbnail dimension (px)       | 1200                  |
| `--quality`    | JPEG quality (1-100)               | 85                    |
| `--workers`    | Parallel workers                   | auto (max 8)          |
| `--recursive`  | Search subdirectories              | off                   |
| `--overwrite`  | Overwrite existing files           | off                   |
| `--dry-run`    | Preview only                       | off                   |
| `--no-exif`    | Skip EXIF copy                     | off                   |
| `--report`     | Output processing report JSON path | none                  |
| `--from-stdin` | Read file paths from stdin (JSON)  | off                   |

### 2. `find_by_date.py` — Find Photo Files by Date / Detect Timelapse

Searches for RAW, JPG, and HEIC/HEIF files by EXIF shooting date. Outputs JSON path list to stdout.
Also detects timelapse sequences by identifying runs of photos with regular shooting intervals.

```bash
# Find by exact date (outputs JSON to stdout)
python3 photo-toolkit/scripts/find_by_date.py --date 3月15日
python3 photo-toolkit/scripts/find_by_date.py --date 2026-03-15

# Date range
python3 photo-toolkit/scripts/find_by_date.py --from 2026-03-10 --to 2026-03-15

# Save output to file
python3 photo-toolkit/scripts/find_by_date.py --date 3月15日 --output ~/data/found_files.json

# List all dates
python3 photo-toolkit/scripts/find_by_date.py --list-dates

# Timelapse: detect sequences with regular intervals, exclude casual shots
python3 photo-toolkit/scripts/find_by_date.py ~/data/RAW --timelapse
python3 photo-toolkit/scripts/find_by_date.py ~/data/RAW --timelapse --copy-to ~/output/frames
python3 photo-toolkit/scripts/find_by_date.py ~/data/RAW --timelapse --min-sequence 50
```

| Option                 | Description                                    | Default |
| ---------------------- | ---------------------------------------------- | ------- |
| `--output`, `-o`       | Save JSON output to file                       | stdout  |
| `--timelapse`          | Detect timelapse sequences (regular intervals) | off     |
| `--min-sequence`       | Minimum frames to qualify as timelapse         | 30      |
| `--interval-tolerance` | Interval deviation tolerance (0.5 = ±50%)      | 0.5     |
| `--mtime-fallback`     | Use filesystem mtime when EXIF is unreadable   | off     |
| `--progress-interval`  | Print scan progress every N files (0 = off)    | 100     |

Supported date formats: `2026-03-15`, `03-15`, `3月15日`, `today`, `yesterday`, `3 days ago`

### 3. `layout_preview.py` — Layout Preview (Comparison / Grid)

**Default: side-by-side comparison** (left=original, right=graded)

When `--params` is provided and contains absolute paths, originals are resolved automatically
without `--originals`.

```bash
# Comparison mode with absolute paths in params (--originals not needed)
python3 photo-toolkit/scripts/layout_preview.py ~/data/output/graded --params grading_params.json

# Comparison mode with explicit originals directory
python3 photo-toolkit/scripts/layout_preview.py ~/data/output/graded \
    --originals ~/data/RAW --params grading_params.json

# Grid mode (宫格) — only graded photos
python3 photo-toolkit/scripts/layout_preview.py ~/data/output/graded --grid \
    --params grading_params.json
```

| Option        | Description                     | Default                 |
| ------------- | ------------------------------- | ----------------------- |
| `graded_dir`  | Graded JPG directory (required) | —                       |
| `--originals` | Original photos directory       | auto-detect from params |
| `--params`    | grading_params.json path        | none                    |
| `--grid`      | Use grid layout instead         | off (comparison)        |
| `--cell-size` | Row height / grid cell px       | 800                     |
| `--gap`       | Gap between images px           | 6                       |
| `--quality`   | JPEG output quality             | 92                      |
| `-o/--output` | Output path                     | `../layout_preview.jpg` |

> **Note**: Without `--grid`, the script generates side-by-side BEFORE|AFTER comparisons.
> Use `--grid` only when the user explicitly requests 四宫格 or 九宫格.

### 4. `deflicker.py` — Timelapse Deflicker (in-place)

Smooths luminance fluctuations across a timelapse JPG frame sequence using a sliding window.

```bash
python3 photo-toolkit/scripts/deflicker.py ~/output/graded
python3 photo-toolkit/scripts/deflicker.py ~/output/graded --window 11 --quality 95
python3 photo-toolkit/scripts/deflicker.py ~/output/graded --dry-run
```

| Option      | Description                                    | Default           |
| ----------- | ---------------------------------------------- | ----------------- |
| `input`     | Directory containing JPG frames                | required          |
| `--window`  | Sliding window size, odd number                | 11                |
| `--quality` | Output JPEG quality                            | 95                |
| `--backup`  | Create backup copies before modifying (.bak)   | off               |
| `--dry-run` | Analyze without modifying files                | off               |
| `--config`  | Path to config.toml                            | auto              |

### 5. `assemble.py` — Frames → MP4 Video

Encodes a sequence of sequentially-named JPG frames into an H.264 MP4 via FFmpeg.

```bash
python3 photo-toolkit/scripts/assemble.py ~/Photos/graded --output timelapse.mp4
python3 photo-toolkit/scripts/assemble.py ~/Photos/graded --output timelapse.mp4 --fps 30 --crf 15
python3 photo-toolkit/scripts/assemble.py ~/Photos/graded --dry-run
```

| Option         | Description                                        | Default                    |
| -------------- | -------------------------------------------------- | -------------------------- |
| `input`        | Directory containing JPG frames                    | required                   |
| `--output/-o`  | Output video path                                  | `<input>/../timelapse.mp4` |
| `--fps`        | Video frame rate                                   | 25                         |
| `--crf`        | H.264 CRF quality: 0=lossless, 18=high, 23=default | 18                         |
| `--dry-run`    | Preview without encoding                           | off                        |
| `--config`     | Path to config.toml                                | auto                       |

## photo-grader

### Engine

**RawTherapee CLI** is the sole processing engine, providing:

| Feature          | RawTherapee                          |
| ---------------- | ------------------------------------ |
| Demosaicing      | Multi-algorithm (AMAZE, IGT, etc.)   |
| Sharpening       | RL Deconvolution (Richardson-Lucy)   |
| Noise Reduction  | IWT / astronomy denoise              |
| Lens Correction  | **lensfun auto**                     |
| Color Management | ProPhoto internal pipeline           |
| Camera Matching  | **Auto-Matched Curve (~50 cameras)** |
| Output Quality   | **Professional**                     |

### Usage

```bash
# With absolute paths in grading_params.json (--raw-dir not needed)
python3 photo-grader/scripts/grade.py grading_params.json --output ~/Photos/graded

# With relative filenames in params (needs --raw-dir)
python3 photo-grader/scripts/grade.py grading_params.json \
    --raw-dir ~/Photos/RAW --output ~/Photos/graded

# Full resolution
python3 photo-grader/scripts/grade.py grading_params.json --no-resize

# Uniform mode: apply one parameter set to ALL files in a directory
# (useful for timelapse or batch-processing with identical settings)
python3 photo-grader/scripts/grade.py grading_params.json \
    --uniform-dir ~/data/timelapse --output ~/data/output/graded

# Preview
python3 photo-grader/scripts/grade.py grading_params.json --dry-run

# Export PP3 only (for manual inspection or external use)
python3 photo-grader/scripts/grade.py grading_params.json --pp3-only --pp3-output ./pp3_files/

# Fast export mode (skip heavy modules for speed)
python3 photo-grader/scripts/grade.py grading_params.json --fast-export

# Control lens correction and camera matching
python3 photo-grader/scripts/grade.py grading_params.json --lens-corr
python3 photo-grader/scripts/grade.py grading_params.json --no-lens-corr
python3 photo-grader/scripts/grade.py grading_params.json --auto-match
python3 photo-grader/scripts/grade.py grading_params.json --no-auto-match
```

| Option          | Description                                          | Default      |
| --------------- | ---------------------------------------------------- | ------------ |
| `params_json`   | Grading parameters JSON                              | required     |
| `--raw-dir`     | RAW files directory (only needed for relative paths) | from config  |
| `--uniform-dir` | Apply first param set to ALL files in directory      | —            |
| `--output`      | Output directory                                     | from config  |
| `--quality`     | JPEG quality (1-100)                                 | 95           |
| `--workers`     | Parallel workers                                     | auto (max 8) |
| `--overwrite`   | Overwrite existing files                             | off          |
| `--dry-run`     | Preview only                                         | off          |
| `--pp3-only`    | Only generate PP3 files, don't render                | off          |
| `--pp3-output`  | Directory for PP3-only output                        | `./pp3/`     |
| `--fast-export` | Use RT fast export mode (skip heavy modules)         | off          |
| `--lens-corr`   | Enable/disable lens correction                       | from config  |
| `--auto-match`  | Enable/disable Auto-Matched Camera Curve             | from config  |

> **Note**: `--uniform-dir` ignores the `file` field in the JSON and applies the first parameter set
> to every supported photo in the directory. Useful for timelapse sequences where all frames share
> one grading preset.

### Color Grading Features

All standard Lightroom parameters are supported with intelligent mapping:

**Fully Supported**

- ✅ Exposure (stop-based)
- ✅ Contrast
- ✅ Highlights / Shadows / Whites / Blacks
- ✅ White Balance (temperature/tint)
- ✅ Vibrance & Saturation
- ✅ Parametric Tone Curve
- ✅ HSL Per-channel Adjustments (8 channels)
- ✅ Three-Way Color Grading
- ✅ Sharpening (RL Deconvolution)
- ✅ Noise Reduction (IWT/astronomy)
- ✅ Vignette
- ✅ Film Grain

**RawTherapee-Specific Features**

- **Auto-Matched Tone Curve** (RT `[Exposure] HistogramMatching`): Matches in-camera JPEG tone for ~50 camera models
- **Lens Correction**: Automatic via lensfun database
- **Fast Export Mode**: Skip heavy modules for speed
- **16-bit Output**: TIFF/PNG at 16-bit depth

Grading parameters JSON top-level fields: `file` / `style` / `basic` / `tone_curve` / `hsl` /
`color_grading` / `detail` / `effects` / `raw` — see the `rt_map_*()` functions in
`photo-grader/scripts/grade.py` for the authoritative field list.

### Cross-Format Support

The `find_raw_file()` function intelligently matches filenames across camera brands and formats:

- **Absolute path mode**: If `grading_params.json` has `"file": "/path/to/DSC_0001.NEF"` and the file
  exists, it's used directly
- **Absolute path fallback**: If the absolute path doesn't exist, tries different extensions in the
  same directory
- **Relative path mode**: If `"file": "DSC_0001.NEF"`, searches under `--raw-dir` by stem name
- **Subdirectory prefix**: If a RAW file is in a subdirectory under `--raw-dir`, the output filename
  gets a prefix: `001_DSC_0001_暖春丝滑.jpg`

Stem-based matching works across formats:

- If `grading_params.json` says `DSC_0001.NEF` but the actual file is `DSC_0001.CR2`, it will still be found
- Also matches JPG and HEIC files: `IMG_0001.HEIC` or `DSC_0001.JPG`

## photo-previewer

Local HTTP server that renders a graded session in the browser — the interactive counterpart of
`layout_preview.py`'s static composite. The mode is auto-detected from the input path depth:

- **Session mode** — the path directly contains `grading_params.json` → straight into the 9-cell
  grid view (use at the end of the pipeline, instead of the static `layout_preview.py --grid`):

  ```bash
  python3 photo-previewer/scripts/preview.py <session_dir> [--port N] [--external-url URL] [--config PATH]
  ```

- **Browse mode** — the path has no `grading_params.json` but its child directories do → lists every
  session of that project (newest first), click one to open it:

  ```bash
  python3 photo-previewer/scripts/preview.py <project_dir> [--port N] [--external-url URL] [--config PATH]
  ```

`--port` reads `port` from `config.toml`, then falls back to an OS-assigned free port.
`--external-url` is the URL the user finally sees (reverse-proxy scenario); when unset, the internal
`http://127.0.0.1:<port>/` is printed. Precedence: CLI > config > built-in default.

### Deployment shape

The server **always binds `127.0.0.1`** and never exposes itself to the public internet.

- **Local debugging** — open `http://127.0.0.1:<port>/` directly (or via SSH port-forward).
- **Behind a reverse proxy** (nginx / OpenClaw gateway / k8s ingress) — map e.g. `/preview/...` →
  `http://127.0.0.1:<port>/` and put the public URL into `config.toml`'s `external_url`.
- **Agent passthrough** — the server prints `Preview ready: <url>` as its first stdout line; forward
  that `<url>` to the user as-is. The agent needs no knowledge of the reverse-proxy details.

### Core interactions

- Click anywhere on the grid → all 9 cells flip to the original thumbnails; click again → graded.
- Style tabs at the top switch between the per-style grids.
- Double-click a cell → fullscreen single photo (pinch to zoom; double-click / ESC / backdrop exits).
- Mobile: horizontal swipe switches style; vertical swipe lets the page scroll normally.
- Keyboard: `Space` = graded↔original, `←/→` = style tabs, `1-9` = jump to a style.

### Requirements

- Python 3.8+ — **stdlib only** (`tomllib` on 3.11+, optional `tomli` on 3.8-3.10; no pip deps).
- One free TCP port on `127.0.0.1` (OS-assigned by default, or pin it with `--port` / `config.toml`).
- Consumes the other two modules' outputs: `convert.py` thumbnails are shown as the "original" side,
  `grade.py`'s `graded/` + `grading_params.json` as the graded side.

### Known trade-offs

- Thumbnails (`convert.py`, ≤2048px / quality 80-85) are lower-resolution than the full-resolution RT
  renders, so the "original" side looks softer. Use RawTherapee's own viewer for pixel-level checks.
- Mobile single-click has a ~250ms delay to disambiguate click vs. double-click (desktop unaffected).
- Avoid underscores in style names: `rpartition('_')` can mis-split a style name containing an
  underscore when the file stem does not, and the cell is then reported as `graded missing`.

## Agent Integration

1. Run each module's `scripts/setup_deps.sh` to verify and install dependencies
2. Use `--dry-run` on any script to preview before executing
3. All scripts output structured progress to stdout, errors to stderr
4. Scripts exit with code 0 on success, 1 on error

### Typical agent workflow

```bash
# Step 1: Convert
python3 photo-toolkit/scripts/convert.py ~/Photos/RAW ~/output/thumbnails

# Step 2: [Agent reads thumbnails → generates grading_params.json]

# Step 3: Grade
python3 photo-grader/scripts/grade.py ~/output/grading_params.json \
    --raw-dir ~/Photos/RAW --output ~/output/graded

# Step 4a: Interactive browser preview (preferred; prints "Preview ready: <url>")
python3 photo-previewer/scripts/preview.py <session_dir> --port 8765

# Step 4b: Static composite fallback (no browser / SSH / remote container)
python3 photo-toolkit/scripts/layout_preview.py ~/output/graded \
    --originals ~/Photos/RAW --params ~/output/grading_params.json
```

### Timelapse workflow

```bash
# Step 1: Detect & extract timelapse frames (exclude casual shots)
python3 photo-toolkit/scripts/find_by_date.py ~/Photos/RAW \
    --timelapse --copy-to ~/output/timelapse_frames

# Step 2: Uniform grade — one parameter set for all frames
python3 photo-grader/scripts/grade.py ~/output/grading_params.json \
    --uniform-dir ~/output/timelapse_frames --output ~/output/graded

# Step 3: Deflicker — smooth luminance fluctuations
python3 photo-toolkit/scripts/deflicker.py ~/output/graded

# Step 4: Assemble — frames → MP4 video
python3 photo-toolkit/scripts/assemble.py ~/output/graded \
    --output ~/output/timelapse.mp4 --fps 25
```

## Windows Notes

No path is hard-coded anywhere in this skill — it runs on any Windows machine
that has RawTherapee installed.

- **No bash needed.** Skip every `setup_deps.sh`. The Python deps are tiny: only
  `tomli` is needed below Python 3.11; on 3.11+ `tomllib` is stdlib, so nothing
  has to be installed for `convert.py` / `grade.py`.
- **The RawTherapee CLI is located automatically**, in this order:
  `rawtherapee_cli` in `config.toml` → `PATH` (`rawtherapee-cli`) → the folder of
  the `rawtherapee` GUI binary → the usual install locations
  (`%ProgramFiles%\RawTherapee\<version>\rawtherapee-cli.exe`, plus the
  `ProgramW6432` / `ProgramFiles(x86)` / `LocalAppData\Programs` variants;
  version folders are tried newest-first). Windows installers never add the CLI
  to `PATH`, so the install-folder scan is what makes it work out of the box.
  If RawTherapee lives somewhere unusual, set `rawtherapee_cli` in `config.toml`.
- **`config.toml` is optional and private.** Copy `config.example.toml` to
  `config.toml` **in this folder** (next to `SKILL.md`) and fill in only what you
  need — every module falls back to the shared root `config.toml` when it has no
  own copy. `config.toml` is listed in `.clawhubignore` and must never be part of
  a published bundle.
- **Run command (PowerShell):**
  ```powershell
  python "<skill_dir>\photo-grader\scripts\grade.py" <grading_params.json> --output <out_dir>
  ```
  Set `$env:PYTHONUTF8="1"` (or use `python -X utf8`) so emoji/Chinese log lines
  do not hit cp936 encoding errors.
- **Browser preview (`photo-previewer`):** Python stdlib only — nothing to install, no bash.
  ```powershell
  $env:PYTHONUTF8="1"
  python "<skill_dir>\photo-previewer\scripts\preview.py" <session_dir> --port 8765
  ```
  It binds `127.0.0.1` and prints `Preview ready: http://127.0.0.1:8765/` as its first stdout
  line — open that URL in a local browser. `PYTHONUTF8=1` matters here too (the config loader
  logs `⚠️` / `📄` lines, which break cp936). If there is no browser at all, fall back to
  `layout_preview.py`, which writes a static composite JPG.
- **JSON paths:** use Windows absolute paths with escaped backslashes
  (`"C:\\Photos\\a.jpg"`).
- **Keep the folder together.** `photo-grader\scripts\grade.py` loads
  `file_matcher.py` from the sibling module `photo-toolkit\scripts\` via
  `sys.path`, so the two module folders must stay in the same parent directory.
  They ship inside this single skill, so this is already satisfied.

## Local Layout

```
rawtherapee-photo-skills\
├── SKILL.md
├── CHANGELOG.md             ← changelog for the merged skill
├── config.example.toml      ← shared template (copy to config.toml)
├── photo-toolkit\
│   ├── CHANGELOG.md
│   ├── config.example.toml
│   ├── requirements.txt
│   └── scripts\             convert.py / find_by_date.py / layout_preview.py /
│                            deflicker.py / assemble.py / file_matcher.py
├── photo-grader\
│   ├── CHANGELOG.md
│   ├── config.example.toml
│   ├── requirements.txt
│   ├── templates\           photo-curator-user-prompt-grading.md (JSON schema
│   │                        reference that grade.py points users to) /
│   │                        rt-mapping-reference.md (LR→RT mapping tables)
│   └── scripts\             grade.py  (imports file_matcher.py from the sibling
│                            photo-toolkit\scripts\ via sys.path)
└── photo-previewer\
    ├── config.example.toml
    ├── requirements.txt
    └── scripts\             preview.py (interactive browser preview server,
                             stdlib only) / setup_deps.sh
```
