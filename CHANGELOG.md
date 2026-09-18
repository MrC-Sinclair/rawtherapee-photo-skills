# Changelog — rawtherapee-photo-skills

All notable changes to this merged skill are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This skill bundles two upstream ClawHub skills, `photo-toolkit` and `photo-grader`
(<https://github.com/konanok/photo-skills>) into a single installable package, because
ClawHub / Marvis treat one folder as one skill. The per-module history lives in
`photo-toolkit/CHANGELOG.md` and `photo-grader/CHANGELOG.md`.

## [1.0.4] - 2026-09-17

The `hsl` / `color_grading` mapping actually works now — it had been silently ignored by the engine.

### Fixed

- **`photo-grader/scripts/grade.py`: HSL and three-way color grading were no-ops.** The emitted pp3
  used `[Color Toning]`, `HueCurve/SatCurve/ValCurve` and `Shadows_Hue`/`Highlights_Hue`, none of
  which exist in RawTherapee 5.13; RT drops unknown sections and keys without any warning, so an
  A/B CLI render of the same image differed by exactly 0.00. Corrected to the real names verified
  against `rtengine/procparams.cc` (5.13) and re-measured by pixel diff.
  - `rt_map_hsl()` → `[HSV Equalizer]` `HCurve` / `SCurve` / `VCurve`, values as FlatCurve strings
    (`type;x;y;lt;rt;…`, type 1) with the eight LR hue positions as control points, a closing point
    at x=1.0 and split tangents at 0.35. Identity curves no longer emit the section, and the
    "changed" test uses `abs(y-0.5) > 1e-6` instead of a float `!= 0.5` comparison.
  - `rt_map_color_grading()` → `[ColorToning]` with `Enabled=1`, `Method=Splitco` and the per-zone
    `Redlow/Greenlow/Bluelow` … `Redhigh/Greenhigh/Bluehigh` sliders converted from hue+saturation
    (`hsv_to_rgb(hue,1,1) × sat`). `Strength=100` is written because RT scales tint by
    `pow(Strength/100, 0.4)` and the default 50 would cap it at 0.758. `Balance` is not written for
    Splitco, and the LR per-zone luminance that Splitco cannot express is reported on **stderr**
    rather than dropped silently.
  - `SECTION_ORDER`: `"Color Toning"` → `"ColorToning"`.

### Added

- `photo-grader/templates/rt-mapping-reference.md`: real section/key names for HSV Equalizer and
  ColorToning, FlatCurve encoding rules, worked hue+saturation→slider examples, and a new
  **engine fidelity differences** table (vCurve saturation damping, half-range luminance, linear
  working-space hue amplification, sparse-anchor bandwidth, Strength scaling, unequal zone weights,
  additive per-channel tinting).
- `SKILL.md`: HSL/Color Grading mapping targets and the same fidelity notes, plus the reminder that
  any pp3 field edit must be re-verified with an A/B CLI render.

### Verified

- A/B pixel-diff regression (RawTherapee CLI 5.13, synthetic 3000×2000 grey ramp + 6-hue × 3-luminance
  band chart, `np.abs(case - baseline).mean()`, determinism floor 0.00):
  - `ct_shadow` / `ct_midtone` / `ct_highlight` / `ct_all` — gradient 7.83 / 10.10 / 8.98 / 11.85,
    bands 19.63 / 18.46 / 30.37 / 37.98 (were 0.00).
  - `hsl_hue_sat_lum` / `hsl_desat_red` / `hsl_hue_only` — bands 7.30 / 14.76 / 3.41 (were 0.00);
    gradient diff is 0.00 by design, since neutral grey has no hue and the vCurve is saturation-damped.
  - Zone deltas match intent (shadow hue 220 → ΔR −14.5/ΔB +13.9; midtone hue 40 → ΔR +14.2/ΔB −23.3;
    highlight hue 300 → ΔR +22.6/ΔB +15.6).
  - `Strength`: 100 vs 50 vs key-absent → diff ×1.22~1.32, with 50 and absent byte-identical
    (confirming RT's default is 50).

## [1.0.3] - 2026-09-16

Third module merged in, plus the dangling Curator-prompt reference is fixed.

### Added

- **`photo-previewer` is now part of the bundle** (`photo-previewer/scripts/preview.py`,
  `config.example.toml`, `requirements.txt`, `setup_deps.sh`). Interactive browser preview server
  for graded sessions: session mode (path contains `grading_params.json`) and browse mode (project
  root listing all sessions), per-style tabs, whole-grid graded↔original toggle, fullscreen viewer,
  mobile swipe gestures, keyboard shortcuts. Stdlib only — no pip dependencies. It follows the same
  config fallback chain as the other modules (`photo-previewer/config.toml` → root `config.toml`),
  so no code change was needed for the merged layout.
- `SKILL.md`: new **photo-previewer** section (modes, CLI, deployment shape, core interactions,
  requirements, known trade-offs); Pipeline diagram and the typical agent workflow now show
  `preview.py` as the primary preview step (4a) with `layout_preview.py` as the static fallback (4b).
- `SKILL.md`: **Windows Notes** — how to run the preview server (`PYTHONUTF8=1`, binds
  `127.0.0.1`, prints `Preview ready: <url>`).
- `photo-grader/templates/` — `photo-curator-user-prompt-grading.md` and
  `rt-mapping-reference.md`, extracted from `openclaw-photo-agents-creator` so the schema reference
  lives inside the bundle (the `{{RT_MAPPING_REFERENCE}}` placeholder is filled by the latter).
- Root `config.example.toml`: `photo-previewer` section (`port`, `external_url`).

### Fixed

- `photo-grader/scripts/grade.py`: the invalid-parameter hint no longer points at the
  non-bundled `openclaw-photo-agents-creator/templates/photo-curator-user-prompt-grading.md`
  (dangling reference) — it now points at `photo-grader/templates/photo-curator-user-prompt-grading.md`
  and mentions `rt-mapping-reference.md`.

### Notes

- `photo-screener` (MobileCLIP + torch) stays **out** of this bundle: it needs a multi-GB model
  download and a separate runtime. Install it standalone from the upstream repo if you need
  pre-selection before grading. `openclaw-photo-agents-creator` itself is still not required — only
  its two prompt/mapping templates were pulled in, as text files.
- Version bumped to 1.0.3 (`SKILL.md` frontmatter, `skill.yaml`, `VERSION`).

## [1.0.2] - 2026-09-16

Documentation parity release: the merged skill now documents every capability of both
bundled modules.

### Added

- `SKILL.md`: full **Supported Formats** matrix (all camera brands + JPEG + HEIC/HEIF)
  and the RAW 16-bit vs JPG/HEIC 8-bit grading note, carried over from `photo-toolkit`.
- `SKILL.md`: complete per-script option tables (`convert.py`, `find_by_date.py`,
  `layout_preview.py`, `deflicker.py`, `assemble.py`) — previously only example
  commands were listed, so every flag lived only in the deleted module docs.
- `SKILL.md`: `photo-grader` **Engine** capability table, the full **Color Grading
  Features** list (12 Lightroom-style groups + 4 RawTherapee-specific features) and the
  **Cross-Format Support** matching rules (absolute / relative / stem / subdirectory
  prefix), carried over from `photo-grader`.
- `SKILL.md`: shared venv setup, system dependency list (libraw, ffmpeg, RawTherapee CLI)
  and verification commands.
- `SKILL.md`: `find_by_date.py --mtime-fallback` / `--progress-interval` options and
  `layout_preview.py` comparison-vs-grid guidance.
- This root `CHANGELOG.md`.

### Changed

- Version bumped to 1.0.2 (`SKILL.md` frontmatter, `skill.yaml`, `VERSION`).
- `description` in the frontmatter now enumerates both modules' task triggers, the
  supported formats and the dependencies, so the skill is retrievable by the full
  upstream trigger set.

## [1.0.1] - 2026-09-16

Initial merged package: `photo-skills` = `photo-toolkit` + `photo-grader` in one skill folder.

### Added

- Merged layout with a shared root `config.toml` / `config.example.toml`
  (one file serves both modules; each module falls back to the root config).
- `.clawhubignore` covering `config.toml`, `__pycache__/`, `*.pyc`, `.venv/`, editor cruft.

### Changed (portability / Windows)

- `photo-grader`: `find_rawtherapee_cli()` now finds the RawTherapee CLI without any
  configured path — `config.toml` → `PATH` → GUI install folder → usual install
  locations (`%ProgramFiles%\RawTherapee\<version>\`, `ProgramW6432`,
  `ProgramFiles(x86)`, `LocalAppData\Programs`, macOS/Linux equivalents), version
  folders newest-first. No release number is hard-coded.
- `photo-grader`: machine-specific paths removed from shipped files; `config.example.toml`
  is a blank template.
- `SKILL.md`: new Windows Notes section (no bash, UTF-8 mode, escaped JSON paths,
  keeping both module folders together for the `file_matcher.py` `sys.path` import).

### Fixed

- `photo-grader`: grading no longer moves the source photo out of the input folder —
  the render is claimed from the output directory first and leftover files are handled
  explicitly.
