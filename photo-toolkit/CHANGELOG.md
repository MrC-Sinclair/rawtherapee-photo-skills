# Changelog — photo-toolkit

All notable changes to this skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This skill carries its own version per [strategy C in RELEASING.md](../RELEASING.md).

## [Unreleased]

### Fixed

- **`convert.py`: copied EXIF never survived the re-encode.** The APP1 scan passed the whole
  segment (`\xff\xe1` + 2-byte length + payload) to `Image.save(exif=...)`, while Pillow expects
  the payload alone and adds its own `Exif\0\0` header — so the tag block was malformed and every
  tag was dropped (`getexif()` round-tripped empty). `_extract_exif_payload()` now returns the
  first *Exif* APP1 payload, skipping XMP segments.
- **`layout_preview.py`: the BEFORE side was a grey placeholder whenever `grading_params.json`
  pointed at RAW originals** (Pillow cannot decode RAW, and the failure was swallowed). Candidates
  are now ranked by decodability (`_pick_original`), `convert.py`'s `thumbnails/` serve as a
  fallback source (`_thumbnail_index`), and an unusable original is reported on stdout.
- **`layout_preview.py`: `graded_stem_keys()` destroyed ordinary filenames.** The subdirectory
  prefix was stripped unconditionally, so `DSC_0001_warm.jpg` resolved to key `0001` and matched
  neither the params mapping nor the thumbnails. Only a purely numeric leading segment is stripped
  now (`001_DSC_0001` → `DSC_0001`).

## [1.0.1] - 2026-06-02

### Added

- `find_by_date.py --mtime-fallback`: when a file's EXIF `DateTimeOriginal`
  can't be read (e.g. partial read on fuse / COS-mounted volumes), fall back
  to filesystem `mtime` instead of returning `None`. Avoids silent empty
  results on slow remote storage that previously made agents abandon
  `find_by_date.py` and reimplement date filtering by hand.
- `find_by_date.py --progress-interval N`: print "N/total processed (failures
  so far: X)" to stderr every N files during EXIF scan (default 100, set 0
  to disable). Useful when scanning thousands of files over slow storage.
- `find_by_date.py` now prints a summary at end of scan:
  `⚠ Skipped X/N file(s) (EXIF unreadable). Add --mtime-fallback to use
  filesystem mtime instead.` (or recovery stats when `--mtime-fallback` is on)

## [1.0.0] - 2026-05-20

Initial public release on [ClawHub](https://clawhub.ai).

### Added

- Convert RAW / JPG / HEIC to JPG thumbnails (`convert.py`).
- Find photos by EXIF shooting date (`find_by_date.py`), supports timelapse sequence detection.
- Generate before/after layout previews (`layout_preview.py`).
- Deflicker timelapse frames (`deflicker.py`).
- Assemble JPG frames into MP4 (`assemble.py`).
- Supports Nikon (NEF), Canon (CR2/CR3), Sony (ARW), Fujifilm (RAF), Olympus (ORF), Panasonic (RW2), Pentax (PEF), Samsung (SRW), Leica (DNG), Hasselblad (3FR), Phase One (IIQ), Sigma (X3F), plus standard JPEG and Apple HEIC/HEIF.
