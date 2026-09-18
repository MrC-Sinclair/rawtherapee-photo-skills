# Changelog — photo-grader

All notable changes to this skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This skill carries its own version per [strategy C in RELEASING.md](../RELEASING.md).

## [1.0.6] - 2026-09-18

### Fixed

- **`scripts/grade.py`: 10/12-bit HEIC lost its depth in the transcode.** `_prepare_rt_input()`
  decoded through Pillow's HEIF plugin, which always flattens to 8 bits per channel, despite a
  docstring advertising a "16-bit-capable TIFF". It now uses
  `pillow_heif.open_heif(convert_hdr_to_8bit=False)`; `uint16` results are written as 16-bit RGB TIFF
  with `tifffile`, ICC profile preserved in tag 34675. 8-bit HEIC keeps the Pillow path, and without
  `tifffile` the old 8-bit behaviour is used with a stderr notice rather than an error.
- **`requirements.txt`: `tifffile` was missing**, so the 10/12-bit path had no declared dependency.

## [1.0.5] - 2026-09-18

### Fixed

- **`scripts/grade.py`: white balance never reached the engine.** `rt_map_whitebalance()` wrote
  `[White Balance] Temperature` / `Green` but never enabled the tool or set `Setting=Custom`, so RT
  fell back to the camera white balance. A CR2 rendered with and without `temperature_kelvin: 3000`
  was byte-identical (MAE 0.000); with `Enabled=1` + `Setting=Custom` the same pair differs by 12.99.
- **`scripts/grade.py`: the tone curve was overridden by auto-matched curve.** The FlatCurve /
  FCT_CubicSpline encoding added in 1.0.4 is correct, but `HistogramMatching=1` — written whenever
  `config.auto_matched_curve = true`, which is the shipped default — makes RT replace
  `[Exposure] Curve` with its histogram-matched curve, so `tone_curve` (and `whites` / `blacks`,
  which are folded into that curve) still produced a 0.00 diff. `build_pp3()` now skips
  `HistogramMatching` when the parameter set defines `tone_curve`, `whites` or `blacks`, and prints
  one stderr notice through `_warn_auto_matched_override()`. `highlights` / `shadows` are excluded
  from that test on purpose: they map to `HighlightCompr` / `ShadowCompr` (`[Exposure]`, plus
  `[HLRecovery]` / `[Shadows & Highlights]` for negative values), which coexists with histogram
  matching, so those parameter sets keep the matched base tone.
- **`scripts/grade.py`: `whites` / `blacks` had no consumer.** RT exposes no keys for them; they are
  now folded into the tone-curve endpoints in `rt_map_tone_curve()` (`±0.0002` at x=0, `±0.0006` at
  x=0.25, `±0.0006` at x=0.75, `±0.0003` at x=1.0 per slider unit, curve kept monotonic) instead of
  being dropped silently.
- **`scripts/grade.py`: HEIC input failed outright.** The RawTherapee 5.13 Windows build has no
  libheif and returns rc=2 on `.heic`, while the docs advertised HEIC support. Inputs are now
  transcoded to TIFF with `pillow_heif` (`_prepare_rt_input()`) before the CLI runs; the requirement
  is declared in `requirements.txt` and documented as mandatory in `SKILL.md`.
- **`scripts/grade.py`: parallel jobs on one source file clobbered each other.** The temp pp3, the
  HEIC→TIFF intermediate and the `-o` output all used one shared name, so concurrent styles for the
  same file failed with `Error saving to …` (or produced the wrong image). Each job now renders in
  its own `output_dir/__rt_tmp__/<stem>_<style>_<pid>_<ts>/` scratch directory, publishes results
  with `os.replace()` (with the `alt_jpg` retry), and `rmtree`s the scratch dir on failure.
- **`scripts/grade.py`: `AppVersion` was hard-coded to 5.11** (`build_pp3()`), which is wrong on any
  other engine version. It is now parsed from `rawtherapee-cli -h` (`_parse_rt_version()`,
  `_RT_VERSION`) and written only when known.
- **`scripts/grade.py`: malformed parameter JSON crashed with a bare traceback.** It now reports the
  file, the reason and the offending line, and exits with a non-zero status.
- **`scripts/grade.py`: `--dry-run` and `--pp3-only` still required `--output`,** even though no
  image is written. `--output` is only mandatory for real renders now.
- **`scripts/grade.py`: wrong-shaped `hsl` / `color_grading` input was accepted silently.** `hsl` must
  be a *list* of `{"channel": "blue", "saturation": -40}` objects (channel ∈ red/orange/yellow/green/
  aqua/blue/purple/magenta) and `color_grading` uses *flat* keys (`shadow_hue`, `shadow_saturation`,
  `midtone_*`, `highlight_*`). Both `{"hsl": {"blue": {"saturation": -80}}}` and
  `{"color_grading": {"shadow": {"hue": 220, "saturation": 30}}}` rendered without error and without
  any visible change. A non-list `hsl`, an unknown `hsl` channel and a nested `color_grading` value are
  now each reported on stderr together with the expected schema, and ignored.

### Verified

- A/B CLI render regression on RT 5.13, Canon EOS 2000D CR2 (same source, one parameter set each):
  baseline vs `tone_curve` 27.77, vs `whites: 80 / blacks: -60` 35.41, vs
  `highlights: 60 / shadows: 60` 2.54, vs `temperature_kelvin: 3000` 41.24 — all non-zero, i.e. all
  of them now reach the engine. HEIC pair (`heic1` vs `heic2`) 39.90.
- pp3 inspection: `AppVersion=5.13`, curve-bearing styles carry `Curve=3;…` + `CurveMode=Standard`
  and no `HistogramMatching`, compression-only styles carry `HistogramMatching=1` plus
  `HighlightCompr` / `ShadowCompr`.
- Parallel batches (6 and 7 jobs, one source file, mixed styles) finish rc=0 with no collisions and no
  `__rt_tmp__` leftovers.
- Schema guards (Canon 2000D CR2): `hsl` as a dict → 1 warning, MAE 0.00; `hsl` channel `blu` → 1
  warning listing the valid channels; nested `color_grading` → 1 warning; the correct list/flat form →
  no warning, MAE 10.49 (hsl blue −80 / green +60 + shadow & highlight colour grading).

## [1.0.4] - 2026-09-17

### Fixed

- **`scripts/grade.py`: `hsl` and `color_grading` never reached the engine.** The pp3 carried
  `[Color Toning]`, `HueCurve`/`SatCurve`/`ValCurve` and `Shadows_Hue`/`Highlights_Hue` — none of
  which exist in RawTherapee 5.13. RT silently ignores unknown sections and keys, so the image came
  out identical to the baseline (pixel diff 0.00) with no error anywhere.
  - `rt_map_hsl()`: rewritten to emit `[HSV Equalizer]` `HCurve` / `SCurve` / `VCurve` as FlatCurve
    strings (`type;x;y;lt;rt;…`, type 1 = FCT_MinMaxCPoints), with control points at the eight LR hue
    positions (red 0 / orange 30 / yellow 60 / green 120 / aqua 180 / blue 240 / purple 270 /
    magenta 300), a closing point at x=1.0 reusing the red value, split tangent 0.35. Slider→y:
    hue `0.5 + (v/100*30)/720`; saturation and luminance `0.5 + 0.15*v/100` for v>0 and
    `0.5 + 0.5*v/100` for v<0 (v=−100 ⇒ fully desaturated). Values below |0.5| stay at identity, the
    change test is `abs(y-0.5) > 1e-6`, and an all-identity set no longer emits the section.
  - `rt_map_color_grading()`: rewritten to emit `[ColorToning]` (no space), `Enabled=1`,
    `Method=Splitco`, per-zone `Redlow/Greenlow/Bluelow`, `Redmed/Greenmed/Bluemed`,
    `Redhigh/Greenhigh/Bluehigh` built as `hsv_to_rgb(hue/360, 1, 1) × saturation`, plus
    `Strength=100` (RT scales tinting by `pow(Strength/100, 0.4)`; the default 50 caps it at 0.758).
    A zone is only written when |sat| ≥ 0.5; `Balance` is Splitlr-only and is not written, and the
    per-zone luminance with no Splitco counterpart is announced on stderr instead of being dropped.
  - `SECTION_ORDER`: `"Color Toning"` → `"ColorToning"`.

### Added

- `templates/rt-mapping-reference.md`: corrected rows for `hsl` and `color_grading`, a new
  "curve encoding" table (FlatCurve format, `ColorToning` slider semantics) and a new
  "engine fidelity differences" table (vCurve saturation damping and missing ×2 factor,
  linear working-space hue amplification, sparse-anchor bandwidth, Strength scaling, unequal
  zone weights, additive per-channel tinting).

### Verified

- A/B CLI render regression (RT 5.13, synthetic grey ramp and 6-hue × 3-luminance band chart,
  `np.abs(case - baseline).mean()`, determinism floor 0.00; was 0.00 before the fix):
  `ct_shadow` 7.83 / 19.63, `ct_midtone` 10.10 / 18.46, `ct_highlight` 8.98 / 30.37,
  `ct_all` 11.85 / 37.98 (gradient / bands); `hsl_hue_sat_lum` 7.30, `hsl_desat_red` 14.76,
  `hsl_hue_only` 3.41 on the band chart. Zone-averaged deltas point the intended way
  (shadow hue 220 → blue gain / red loss; midtone hue 40 → red gain / blue loss;
  highlight hue 300 → red and blue gain).

## [1.0.3] - 2026-09-16

### Added

- `templates/photo-curator-user-prompt-grading.md` and `templates/rt-mapping-reference.md`:
  the Curator's grading prompt (authoritative JSON schema reference) and the LR→RT mapping tables
  now ship inside the skill. Both were extracted from `openclaw-photo-agents-creator`, which is no
  longer referenced by this module; the `{{RT_MAPPING_REFERENCE}}` placeholder in the prompt is
  filled by `rt-mapping-reference.md`.

### Fixed

- The invalid-parameter hint printed by `_check_known_aliases()` no longer points at the
  non-bundled `openclaw-photo-agents-creator/templates/photo-curator-user-prompt-grading.md`
  (dangling path); it now points at `photo-grader/templates/photo-curator-user-prompt-grading.md`
  and additionally prints the `rt-mapping-reference.md` path.

## [1.0.2] - 2026-09-16

### Added (portability)

- `find_rawtherapee_cli()` falls back to scanning the usual install locations
  when neither `config.toml` nor `PATH` yields the CLI — Windows:
  `%ProgramFiles%\RawTherapee\<version>\`, `%ProgramW6432%`, `%ProgramFiles(x86)%`,
  `%LocalAppData%\Programs`; macOS: `/Applications/RawTherapee.app/Contents/MacOS/`,
  `/opt/homebrew/bin`; Linux: `/usr/bin`, `/usr/local/bin`, `/snap/bin`. Version
  folders are discovered and sorted newest-first, so **no release number is
  hard-coded** and GUI installers that never touch `PATH` work out of the box.
- `skill.yaml` / `VERSION` metadata files.

### Changed (Windows compatibility)

- `SKILL.md`: new "Windows Notes" section — no bash, UTF-8 mode, absolute JSON
  paths, `--output` is required, `photo-toolkit` must stay next to `photo-grader`.
- Machine-specific paths are gone from the shipped files: `config.example.toml`
  stays a blank template and `config.toml` is user-private (covered by
  `.clawhubignore`).

### Fixed (local Windows adaptation)

- **Source files were moved out of the input folder.** For JPG input, RT writes
  its render into the `--output` directory under the *original* stem
  (`<stem>.jpg`), not `<stem>_<style>.jpg`. The old lookup then fell through to
  the input directory, found the source file and `shutil.move`d it to the output
  path — silently deleting the original from the input folder. The render is now
  claimed from the output directory first, the source file is never moved, and
  leftover `<stem>.jpg` files are cleaned up (replaced when `--overwrite`, dropped
  otherwise).

## [1.0.1] - 2026-06-02

Fixes the "dark output" bug where graded JPGs came out about 1 stop darker
than expected. Root cause was two latent bugs in the RT engine integration
that masked each other:

### Fixed

- **`--auto-match` was a no-op** — `build_pp3` wrote `[Color Management] ToneCurve=false`
  when `auto_matched_curve=true`, but that PP3 key controls the DCP profile's
  embedded tone curve, not RawTherapee's Auto-Matched Camera Curve. The real
  field lives under `[Exposure]`. Now writes `[Exposure] HistogramMatching=true` +
  `CurveFromHistogramMatching=false` (the latter is required — see Ingo Weyrich's
  explanation on discuss.pixls.us, otherwise RT skips the matching step).
  Empirically verified on Nikon NEF (RT 5.10 + RT 5.12): mean luma 32.65 → 82.68
  (2.5× brighter), stddev 54.6 → 77.7 (matches in-camera JPG contrast).

- **`raw.auto_bright` was silently dropped** — `build_pp3` consumed `basic`,
  `tone_curve`, `hsl`, `color_grading`, `detail`, `effects` but never
  `params["raw"]`. Curator agents writing `"raw": {"auto_bright": true}` for
  dark scenes saw the request thrown away. Added `rt_map_raw()` which maps
  `auto_bright: true` → `[Exposure] Auto=true + Clip=0.02` (RT's auto-exposure
  algorithm) and `bright: float` → `[Exposure] Compensation` when user didn't
  already set it via `basic.exposure`.

- **Bad-schema JSON silently dropped fields** — When LLM agents wrote the
  Lightroom-shorthand `temperature: 6500` instead of `temperature_kelvin: 6500`
  (or `tint` instead of `tint_offset`), `rt_map_whitebalance` silently
  ignored the unknown key and the entire `[White Balance]` section was
  missing from the generated PP3. Now `_check_known_aliases()` hard-fails
  with `sys.exit(2)` and prints the correct field name + reason. Top-level
  legacy `{params: {...}}` still works (deprecation warn + migrate) for
  backward compatibility, but its inner fields are still checked for the
  known bad aliases. The `BASIC_KEYS` whitelist now includes
  `temperature_kelvin`, `green`, and `tint_offset` (previously missing,
  which is why these silently dropped through the migration path).

### Changed

- `SKILL.md` workflow step 2 no longer references the non-existent file
  `photo_curator_prompt.md V3`. Replaced with a self-describing pointer
  to the "Color Grading Features" section and the `rt_map_*()` functions
  in `grade.py`. The actual Curator prompt template lives in the
  `openclaw-photo-agents-creator` skill — see its `templates/`.

## [1.0.0] - 2026-05-20

Initial public release on [ClawHub](https://clawhub.ai).

### Added

- Apply Lightroom-style color grading to RAW / JPG / HEIC photos via RawTherapee CLI.
- 13 LR→RT auto-mappers covering exposure, contrast, HSL, tone curve, and effects.
- Multi-format JSON input (nested array, single object, `{files: [...]}` wrapper, flat params).
- Uniform mode (`--uniform-dir`) for timelapse / batch grading.
- Cross-format file matching by stem name (`DSC_0001.NEF` matches `DSC_0001.CR2`).
