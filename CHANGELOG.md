# Changelog — rawtherapee-photo-skills

All notable changes to this merged skill are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This skill bundles two upstream ClawHub skills, `photo-toolkit` and `photo-grader`
(<https://github.com/konanok/photo-skills>) into a single installable package, because
ClawHub / Marvis treat one folder as one skill. The per-module history lives in
`photo-toolkit/CHANGELOG.md` and `photo-grader/CHANGELOG.md`.

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
