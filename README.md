---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 40c8af801da8629c99b9e5611c578fea_5abc62f8b1e111f197a3525400248c00
    ReservedCode1: MqbrTkswHOsSw6AYZtdjSJ0Nq8/6S4wWSmB038905J0k5oTE/bN7L69ZtbRlT6IDbI09n6VxmB2Ls3KgemixPNKYvBCU7BLxWA1EMwrAqbUDCwCVGhcf0JQzjtkv3XW9Z4c/1b3slJhwT5JQziUNVGbLPGUo81MmpYeImnsh+fbDtKHriPfRzj6UvSk=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 40c8af801da8629c99b9e5611c578fea_5abc62f8b1e111f197a3525400248c00
    ReservedCode2: MqbrTkswHOsSw6AYZtdjSJ0Nq8/6S4wWSmB038905J0k5oTE/bN7L69ZtbRlT6IDbI09n6VxmB2Ls3KgemixPNKYvBCU7BLxWA1EMwrAqbUDCwCVGhcf0JQzjtkv3XW9Z4c/1b3slJhwT5JQziUNVGbLPGUo81MmpYeImnsh+fbDtKHriPfRzj6UvSk=
---

# rawtherapee-photo-skills

AI photography post-processing toolkit packaged as a single installable skill (for Marvis / Claw-style
skill runtimes). It bundles three modules that share one root `config.toml`, using the
**RawTherapee CLI** as the color-grading engine.

| Module | Entry scripts | What it does |
| --- | --- | --- |
| **photo-toolkit** | `convert.py`, `find_by_date.py`, `layout_preview.py`, `deflicker.py`, `assemble.py`, `file_matcher.py` | Batch convert RAW/JPG/HEIC to JPG thumbnails, find/filter photos by shooting date, detect timelapse sequences, deflicker frames, assemble frames into MP4, generate before/after or grid (宫格) previews |
| **photo-grader** | `grade.py` | Professional Lightroom-style batch color grading driven by LLM-generated JSON parameters (exposure, contrast, HSL, tone curve, ...), exports graded JPG or RawTherapee `.pp3` sidecars |
| **photo-previewer** | `preview.py` | Interactive browser preview of a graded session: graded↔original grid toggle, per-style tabs, mobile gestures, zero extra dependencies |

## Pipeline

```
RAW / JPG / HEIC
    │
    ▼  photo-toolkit/scripts/convert.py        → JPG thumbnails
    ▼  [LLM generates grading_params.json]
    ▼  photo-grader/scripts/grade.py           → graded JPG / PP3 (RawTherapee)
    ├──▶ photo-toolkit/scripts/layout_preview.py  → static before/after or grid
    └──▶ photo-previewer/scripts/preview.py      → interactive browser preview
```

## Requirements

- **RawTherapee CLI** — required by `grade.py` (color grading). Not required for the other modules.
- **FFmpeg** — only needed by `assemble.py` (video assembly).
- **libraw** — system package (RedHat: `dnf install LibRaw-devel` / Debian: `apt-get install libraw-dev`).
- **Python** — `rawpy`, `pillow`, `numpy` (required by `convert.py`, which uses rawpy for every RAW
  decode — not an optional path); `pillow-heif` (required for HEIC/HEIF input to
  `convert.py` / `grade.py` — RawTherapee 5.13 cannot decode HEIC itself); `tifffile` (only for
  10/12-bit HEIC — keeps that depth in the TIFF handed to RawTherapee instead of falling back to
  8-bit); `tomli` (Python < 3.11). Per-module dependency lists are in each module's `requirements.txt`.

On Windows, external CLIs are usually not on `PATH` — put their absolute paths into `config.toml`.

## Install

1. Copy this folder into your skills directory, e.g. `skills/custom/rawtherapee-photo-skills/`.
2. Copy `config.example.toml` to `config.toml` at the package root and fill in the RawTherapee CLI
   absolute path (plus FFmpeg path if you use `assemble.py`). `config.toml` is machine-local and is
   git-ignored.
3. Restart your skill host so the new skill gets indexed.

## Layout

```
rawtherapee-photo-skills/
├── SKILL.md                  ← skill contract (name / version / description / usage)
├── skill.yaml                ← host metadata
├── VERSION
├── CHANGELOG.md
├── config.example.toml       ← shared template, copy to config.toml
├── photo-toolkit/            ← convert / find_by_date / layout_preview / deflicker / assemble
├── photo-grader/             ← grade.py + Prompt/RT mapping templates
└── photo-previewer/          ← preview.py (interactive browser preview server)
```

Keep the three module folders together: `photo-grader/scripts/grade.py` resolves `file_matcher.py`
from the sibling `photo-toolkit/scripts/` directory via `sys.path`.

## Supported formats

Nikon (NEF/NRW), Canon (CR2/CR3/CRW), Sony (ARW/SRF/SR2), Fujifilm (RAF), Olympus/OM (ORF),
Panasonic (RW2), Pentax (PEF), Samsung (SRW), Leica (RWL/DNG), Adobe DNG, Hasselblad (3FR/FFF),
Phase One (IIQ), Sigma (X3F), plus JPEG (.jpg/.jpeg) and Apple HEIC/HEIF (.heic/.heif).

## Credits & License

Merged and repackaged from [konanok/photo-skills](https://github.com/konanok/photo-skills)
(photo-toolkit + photo-grader + photo-previewer), which is distributed under **MIT-0**.
This repackaging keeps the same license terms; RawTherapee itself is a separate project and is
only invoked as an external CLI.
*（内容由AI生成，仅供参考）*
