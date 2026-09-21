# Changelog — rawtherapee-photo-skills

All notable changes to this merged skill are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This skill bundles two upstream ClawHub skills, `photo-toolkit` and `photo-grader`
(<https://github.com/konanok/photo-skills>) into a single installable package, because
ClawHub / Marvis treat one folder as one skill. The per-module history lives in
`photo-toolkit/CHANGELOG.md` and `photo-grader/CHANGELOG.md`.

## [Unreleased]

Review pass over the execution chain: three script-level defects and three documentation
mismatches. No CLI contract, `grading_params.json` field, or dependency change; the whole chain
stays parameter-only grading plus deterministic geometry — there is no generative/image-synthesis
step anywhere (no diffusion/img2img/inpainting, no model downloads, no remote inference; the only
external process is the RawTherapee CLI, the only network call is ffmpeg-free local assembly).

### Fixed

- **`photo-grader/scripts/grade.py`: RAW/HEIC "16-bit TIFF" export actually produced 8-bit JPEG
  content with a `.tif` extension.** RawTherapee CLI ignores the PP3 `[Output]` section, so the
  fixed `-j95` flag forced 8-bit JPEG regardless of `output_bpp=16`. The CLI now passes `-t`
  (16-bit integer TIFF) whenever `output_bpp == 16`; the 8-bit JPG path is unchanged. Verified on
  RT 5.13: DNG/HEIC outputs are real 16-bit TIFF (`II*\0`, `uint16`).
- **`photo-toolkit/scripts/find_by_date.py`: HEIC/HEIF shooting dates were never parsed.** EXIF
  lives inside ISO BMFF (`ftyp`) boxes, so the raw-header scan (TIFF `II/MM` / JPEG APP1) always
  missed it and every HEIC fell into `no_date`, contradicting the documented "searches HEIC by
  EXIF date". HEIC inputs are now routed through `pillow_heif.open_heif(...).info["exif"]`, the
  `Exif\0\0` prefix stripped, and the bytes run through the shared TIFF parser.
- **`photo-toolkit/scripts/convert.py`: `--from-stdin` blew up on empty/garbage stdin.**
  `json.load(sys.stdin)` had no error handling, so an empty pipe or non-JSON input dumped a
  `JSONDecodeError` traceback. Empty/invalid JSON and a non-object payload now print a clean
  message to stderr and exit 1.
- **User-facing errors went to stdout in four scripts.** `deflicker.py` / `assemble.py` /
  `layout_preview.py` / `grade.py` printed ❌ errors and ⚠️ warnings on stdout, polluting
  pipelines that consume stdout (e.g. `find_by_date.py --json | convert.py --from-stdin`) and
  defeating `2>/dev/null`. All error/warning prints now go to `sys.stderr`; informational output
  stays on stdout.
- **`photo-toolkit/scripts/convert.py`: copied EXIF never survived the re-encode.** The handwritten
  APP1 scan handed the *whole* segment (`\xff\xe1` + 2-byte length + payload) to
  `Image.save(exif=...)`, but Pillow expects the payload alone — it prepends its own `Exif\0\0`
  header, so the emitted segment was malformed and every tag was silently dropped
  (`getexif()` came back empty, verified by round-trip). `_extract_exif_payload()` now walks the
  JPEG header for the first *Exif* APP1 segment (skipping XMP ones) and returns the payload only.
- **`photo-toolkit/scripts/layout_preview.py`: the BEFORE side was a grey placeholder on every RAW
  session.** `grading_params.json` points at RAW originals, which Pillow cannot decode, so the
  comparison fell into a silent `except` branch every time. Originals are now ranked by
  decodability (`_pick_original`), `convert.py`'s `thumbnails/` directories act as a last-resort
  source (`_thumbnail_index`), and an undecodable original is reported on stdout instead of being
  papered over with a grey rectangle.
- **`photo-toolkit/scripts/layout_preview.py`: key derivation destroyed ordinary filenames.** The
  "strip the subdirectory prefix" step ran unconditionally, so `DSC_0001_warm.jpg` yielded `0001`
  and missed both the `grading_params.json` mapping and the thumbnail fallback. A leading segment
  is now stripped only when it is purely numeric (`001_DSC_0001` → `DSC_0001`), and all candidates
  are tried in order (`graded_stem_keys`).
- **`photo-previewer/scripts/preview.py`: every response was labelled `image/jpeg`.** RAW/HEIC
  sessions export `.tif`, so graded cells were served with a Content-Type that did not describe
  their bytes. `_content_type_for()` derives it from the file suffix (jpeg / png / tiff / webp /
  gif) with the previous value kept as the fallback.

### Fixed

- **`file_matcher.py`: stem matching was case-sensitive on Linux/macOS.** Glob patterns like
  `*.nef` never matched `.NEF`, and `rglob("<stem>*")` compared stems case-sensitively, so a
  reference written as `DSC_0001` could miss `dsc_0001.NEF` on a case-sensitive filesystem. Matching
  now walks the directory and compares `stem.lower()` / `suffix.lower()` in Python.
- **`grade.py --uniform-dir` could not recurse.** It always scanned the top level only. A
  `--recursive` / `-r` flag is now accepted (subdirectories are scanned; `thumbnails/graded/sessions`
  are still skipped).
- **`grade.py --pp3-only` and `--dry-run` required RawTherapee to be installed.** They never invoke
  the engine (PP3-only writes sidecar files; dry-run only lists files), so a missing engine is now a
  warning and the run continues. Normal grading still hard-fails when the CLI is missing or unusable.

### Added

- **`RAWTHERAPEE_CLI` environment variable** (grade.py): an explicit machine-local override for the
  CLI path, checked after `config.toml` and before `PATH`. It survives a `config.toml` copied from
  another machine, so a stale path in the file no longer needs to be hand-edited on every new box.
  When the CLI still isn't found, the error message now lists the three discovery options and a
  PowerShell one-liner an agent can run to locate an existing install.
- **`setup_deps.ps1`** (Windows): one command that creates or *repairs* the project `.venv`
  (a venv copied from another machine is detected as dead and rebuilt) and installs all three
  modules' requirements; SKILL.md's setup section is now Windows-aware with a venv self-check.

### Changed

- **`SKILL.md`: output depth and previewer limits now match the code.** The note claiming "every
  export is 8-bit JPG" contradicted `is_hires_input()` (RAW/HEIC → 16-bit TIFF, `--quality`
  inapplicable); the "avoid underscores in style names" trade-off predated `preview.py`'s
  suffix-based `_claim()` matching; and the fact that browsers cannot render the TIFF graded side
  (so RAW sessions need `layout_preview.py`, or a JPG `graded/`) is now stated.

## [1.0.7] - 2026-09-18

Marvis could not import the skill at all: the frontmatter files started with a UTF-8 BOM.

### Fixed

- **`SKILL.md`, `skill.yaml`, `VERSION`: a UTF-8 BOM (EF BB BF) broke frontmatter detection.**
  Marvis only treats the first line as frontmatter when it is exactly `---`; a BOM decodes to
  U+FEFF, so line 1 read as `\ufeff---` and the import aborted with "SKILL.md 解析失败" (1003),
  while `/` could not list the skill. All three files are now stored without a BOM; their
  contents are otherwise byte-identical to 1.0.6.

## [1.0.6] - 2026-09-18

HEIC depth is no longer thrown away, and the dependency notes now say what the code actually does.

### Fixed

- **`photo-grader/scripts/grade.py`: 10/12-bit HEIC was flattened to 8-bit.** `_prepare_rt_input()`
  transcoded every HEIC through Pillow's HEIF plugin, which only ever decodes 8 bits per channel,
  while its own docstring promised a "16-bit-capable TIFF". It now decodes through
  `pillow_heif.open_heif(convert_hdr_to_8bit=False)`; when that yields `uint16` (10/12-bit source) the
  pixels are written as 16-bit RGB TIFF with `tifffile`, and the embedded ICC profile is carried over
  into tag 34675. 8-bit sources keep the Pillow path unchanged, and a missing `tifffile` degrades to
  the previous 8-bit behaviour with a stderr notice instead of failing the run.
- **`photo-grader/requirements.txt`: `tifffile` was missing.** The 10/12-bit path had no declared
  dependency; it is now listed with the non-8-bit rationale.
- **`README.md`: `pillow-heif` was called optional and rawpy's path looked avoidable.** rawpy backs
  every RAW decode in `convert.py` — it is not an optional shortcut — and `pillow-heif` is required
  for any HEIC/HEIF input to `convert.py` / `grade.py`.

### Changed

- Documentation now states the HDR caveat plainly: an iPhone "HDR" gain map is never applied, so RT
  receives the base image. A 10/12-bit HEIC therefore keeps its per-channel depth but not its HDR
  highlights.

### Verified

- Synthetic 10-bit HEIC (with and without ICC): the transcode now reports
  `BitsPerSample=(16, 16, 16)` with a 588-byte ICC tag, where the old path produced 8-bit.
- RawTherapee 5.13 renders the 16-bit TIFF and the 8-bit TIFF both at rc=0; `grade.py` runs a 2-file
  10-bit HEIC batch end to end with 0 errors.
- Narrow-range 10-bit shadow data (8 distinct 10-bit levels): the old path collapsed it to 3 levels,
  the new path keeps 8. After RT's 8-bit JPEG export the visible difference is small on a
  normal-range image (MAE 0.67/255) and still modest under a strong shadow lift (MAE 1.15/255) —
  the depth is preserved through grading, not after the 8-bit export.

## [1.0.5] - 2026-09-18

The tonal section is honest now — every slider it advertises either reaches the engine or is
reported. White balance, tone curves and the auto-matched curve conflict had all been silently
swallowed by RawTherapee 5.13.

### Fixed

- **`photo-grader/scripts/grade.py`: white balance was a no-op.** `Temperature` / `Green` were
  written without enabling the tool and without `Setting=Custom`, so RT kept the camera white
  balance: the rendered file was byte-identical with and without `temperature_kelvin` (pixel diff
  0.00, 12.99 once both keys are set).
- **`photo-grader/scripts/grade.py`: tone curves were a no-op whenever auto-matched curve was on.**
  The 0-999 → FCT_CubicSpline change in 1.0.4 was necessary but not sufficient — `HistogramMatching=1`
  (the shipped default, `auto_matched_curve = true`) replaces `[Exposure] Curve` outright, so every
  `tone_curve` / `whites` / `blacks` adjustment still rendered as a 0.00 diff. `build_pp3()` now skips
  histogram matching for parameter sets that define those keys, prints one stderr notice, and keeps
  the mapped curve (28.59 diff). `highlights` / `shadows` deliberately keep histogram matching: they
  map to `HighlightCompr` / `ShadowCompr`, not to the curve (2.54 diff from the compression alone).
- **`whites` / `blacks` are no longer dropped.** RT has no dedicated keys for them; both are folded
  into the tone-curve endpoints instead (35.41 diff for `whites: 80, blacks: -60`).
- **HEIC input works.** The RawTherapee Windows build has no libheif support and exits rc=2 on
  `.heic`; files are now transcoded to TIFF with `pillow_heif` before grading.
- **Concurrent renders no longer collide.** Parallel jobs on the same source file overwrote each
  other's pp3 / TIFF / `-o` output paths and died with `Error saving to …`. Every job now renders into
  its own `__rt_tmp__/<stem>_<style>_<pid>_<ts>` scratch directory, is published with `os.replace()`
  and cleaned up on failure.
- **`AppVersion` in generated pp3 files is the real engine version** (parsed from
  `rawtherapee-cli -h`); it had been hard-coded to 5.11 while the engine was 5.13.
- **Invalid parameter JSON reports the problem and the offending line instead of a bare traceback.**
- **`--dry-run` / `--pp3-only` no longer demand `--output`.**
- **Wrong-shaped `hsl` / `color_grading` input was swallowed silently.** A nested `hsl` object
  (`{"blue": {"saturation": -40}}`) or a zone-nested `color_grading` (`{"shadow": {"hue": …}}`)
  produced a clean render with no adjustment and no message, because both mappings expect a list /
  flat keys. Wrong `hsl` containers, unknown `hsl` channel names and nested `color_grading` values are
  now announced on stderr with the expected shape.

### Changed

- `SKILL.md`: `pillow-heif` moved from optional to required, with the reason spelled out (RawTherapee
  — including the 5.13 Windows build — cannot read HEIC; both photo-toolkit and photo-grader need the
  library).
- `SKILL.md` and `photo-grader/templates/rt-mapping-reference.md`: new "grading_params.json input
  shape" section showing the correct `hsl` list and flat `color_grading` keys, i.e. the two forms that
  used to fail without a trace.

### Verified

- A/B CLI render regression on RT 5.13 (Canon EOS 2000D CR2 + HEIC): base vs `tone_curve` 27.77,
  base vs `whites`/`blacks` 35.41, base vs `highlights`/`shadows` 2.54, base vs white balance 41.24.
- Parallel batches (6 and 7 jobs over the same source file) finish rc=0 with no `Error saving`
  collisions and no `__rt_tmp__` leftovers.

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
