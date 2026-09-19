#!/usr/bin/env python3
"""
Layout Preview Generator — Compare original vs graded photos side-by-side,
or compose graded photos into a grid preview.

Default mode: side-by-side comparison (left=original, right=graded)
Grid mode: use --grid flag for 4/9-grid layout (宫格)

Dependencies:
    Python: pip install pillow

    Check & install: bash scripts/setup_deps.sh

Usage:
    # Default: side-by-side comparison (left=original, right=graded)
    python layout_preview.py ~/data/output/{session-id}/graded \
        --originals ~/data/RAW \
        --params ~/data/output/{session-id}/grading_params.json

    # Grid mode (宫格): only graded photos
    python layout_preview.py ~/data/output/{session-id}/graded --grid \
        --params ~/data/output/{session-id}/grading_params.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from file_matcher import find_original_for_graded

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("❌ Missing dependency: pillow", file=sys.stderr)
    print("   Install with: pip3 install pillow", file=sys.stderr)
    _SKILL_DIR = Path(__file__).resolve().parent.parent
    print(f"   Or run: bash {_SKILL_DIR}/scripts/setup_deps.sh", file=sys.stderr)
    sys.exit(1)


# ── Image Helpers ───────────────────────────────────────────────


def center_crop_square(img):
    """Center-crop an image to a square (1:1 ratio)."""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def resize_to_fit(img, max_w, max_h):
    """Resize image to fit within max_w × max_h, preserving aspect ratio."""
    w, h = img.size
    ratio = min(max_w / w, max_h / h)
    if ratio >= 1.0:
        return img.copy()
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


# Extensions Pillow decodes directly. Camera RAW is deliberately absent:
# grading_params.json normally points at the RAW original, and a RAW file
# cannot be opened by Pillow, so it must lose to a convert.py thumbnail
# instead of silently rendering as a grey placeholder.
DIRECTLY_DECODABLE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp", ".gif"}


def _pick_original(candidates):
    """Return the best usable original out of ``candidates`` (first = highest priority).

    Pass 1 keeps the highest-priority file Pillow can actually decode; pass 2
    falls back to the highest-priority existing file, so a lone RAW path keeps
    the previous behaviour instead of returning None.
    """
    existing = []
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        if p.exists():
            existing.append(p)
    for p in existing:
        if p.suffix.lower() in DIRECTLY_DECODABLE_EXTENSIONS:
            return p
    return existing[0] if existing else None


def _thumbnail_index(graded_paths, params_mapping=None):
    """Map ``stem.lower() -> path`` for every ``thumbnails/`` dir in the session.

    Two locations are scanned: the session's own ``thumbnails/`` sibling of
    ``graded/``, and the ``thumbnails/`` directory next to the RAW originals
    (``convert.py``'s default ``{input}/thumbnails/`` output).
    """
    dirs = []
    if graded_paths:
        dirs.append(graded_paths[0].parent.parent / "thumbnails")
    for ref in (params_mapping or {}).values():
        dirs.append(Path(ref).parent / "thumbnails")

    index = {}
    for d in dict.fromkeys(dirs):
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg"):
                index.setdefault(p.stem.lower(), p)
    return index


def graded_stem_keys(graded_path):
    """Candidate original-stem keys to try for a graded filename, lowercase.

    ``DSC_0001_暖春丝滑`` → ``("dsc_0001_暖春丝滑", "dsc_0001")``;
    ``001_DSC_0001_暖春丝滑`` additionally yields ``"dsc_0001"`` with the numeric
    subdirectory prefix stripped (``grade.py::_compute_output_name`` prefixes the
    outputs of files that live in a subdirectory of the RAW root).
    """
    stem_lower = graded_path.stem.lower()
    keys = [stem_lower]
    parts = graded_path.stem.rsplit("_", 1)
    if len(parts) == 1:
        return tuple(keys)

    base_stem = parts[0].lower()
    if base_stem not in keys:
        keys.append(base_stem)

    # Strip a leading *numeric* prefix only ("001_DSC_0001" → "dsc_0001").
    # Stripping the first segment unconditionally would turn an ordinary
    # "DSC_0001" into "0001" and lose the original.
    first_seg, _, rest = base_stem.partition("_")
    if rest and first_seg.isdigit() and rest not in keys:
        keys.append(rest)
    return tuple(keys)


def _find_originals_from_params(params_json):
    """从 grading_params.json 获取 originals 绝对路径映射。"""
    if not params_json:
        return {}
    params_path = Path(params_json).expanduser().resolve()
    if not params_path.exists():
        return {}
    try:
        with open(params_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = [data]
        mapping = {}
        for item in data:
            file_ref = item.get("file", "")
            if file_ref:
                file_path = Path(file_ref)
                # 用 stem 做匹配 key（包括子目录前缀的也匹配）
                mapping[file_path.stem.lower()] = file_path
                mapping[file_path.name.lower()] = file_path
        return mapping
    except Exception:
        return {}


def find_graded_images(graded_dir, params_json=None):
    """
    Find graded JPG files, optionally ordered by grading_params.json.
    Returns list of (graded_path, original_filename_stem) tuples.
    """
    graded_dir = Path(graded_dir).expanduser().resolve()
    if not graded_dir.exists():
        return []

    all_jpgs = {}
    for p in graded_dir.iterdir():
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".tif", ".tiff"):
            all_jpgs[p.stem.lower()] = p
            # Also index by original stem (before style suffix)
            # e.g. "DSC_0001_暖春丝滑" → "DSC_0001"
            # Also handle subdirectory prefix: "001_DSC_0001_暖春丝滑" → "DSC_0001"
            parts = p.stem.rsplit("_", 1)
            if len(parts) > 1:
                all_jpgs[parts[0].lower()] = p
                # Try stripping subdirectory prefix too: "001_DSC_0001" → "DSC_0001"
                sub_parts = parts[0].rsplit("_", 1)
                if len(sub_parts) > 1:
                    all_jpgs[sub_parts[1].lower()] = p

    if not all_jpgs:
        return []

    if params_json:
        params_path = Path(params_json).expanduser().resolve()
        if params_path.exists():
            try:
                with open(params_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    data = [data]
                if isinstance(data, list):
                    ordered = []
                    seen = set()
                    for item in data:
                        file_name = item.get("file", "")
                        stem = Path(file_name).stem.lower()
                        if stem in all_jpgs:
                            p = all_jpgs[stem]
                            if p not in seen:
                                ordered.append(p)
                                seen.add(p)
                    if ordered:
                        return ordered
            except (json.JSONDecodeError, OSError):
                pass

    # Deduplicate: multiple keys may point to the same file path
    seen = set()
    unique = []
    for p in sorted(all_jpgs.values(), key=lambda p: p.name):
        if p not in seen:
            unique.append(p)
            seen.add(p)
    return unique


def _get_label_font(font_size):
    """Find and return a suitable font for labels."""
    for font_path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    ]:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, font_size)
            except Exception:
                pass
    return ImageFont.load_default()


def add_label(
    img, text, position="bottom-left", font_size=28, color=(255, 255, 255), bg_color=(0, 0, 0, 160), padding=8
):
    """Add a text label overlay to an image. Returns a new image."""
    img = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _get_label_font(font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    if position == "bottom-left":
        x = padding
        y = img.height - text_h - padding * 2
    elif position == "bottom-right":
        x = img.width - text_w - padding * 2
        y = img.height - text_h - padding * 2
    elif position == "top-left":
        x = padding
        y = padding
    elif position == "top-right":
        x = img.width - text_w - padding * 2
        y = padding
    else:
        x = padding
        y = img.height - text_h - padding * 2

    # Draw background rectangle
    draw.rectangle(
        [x - padding // 2, y - padding // 2, x + text_w + padding, y + text_h + padding],
        fill=bg_color,
    )
    draw.text((x, y), text, fill=color, font=font)

    return Image.alpha_composite(img, overlay).convert("RGB")


# ── Layout Generators ──────────────────────────────────────────


def generate_comparison(
    graded_paths,
    originals_dir,
    params_json=None,
    params_mapping=None,
    cell_height=800,
    gap=8,
    label_gap=4,
    bg_color=(245, 245, 245),
):
    """
    Generate side-by-side comparison images (original left, graded right).
    Multiple photos are stacked vertically, with a header bar and prominent labels.
    """
    thumbs = _thumbnail_index(graded_paths, params_mapping)

    pairs = []
    for gp in graded_paths:
        stem_keys = graded_stem_keys(gp)
        candidates = []

        # Priority 1: from params_mapping (absolute paths in grading_params.json)
        if params_mapping:
            for key in stem_keys:
                if key in params_mapping:
                    candidates.append(params_mapping[key])
                    break

        # Priority 2: from originals_dir
        if originals_dir:
            match = find_original_for_graded(gp, originals_dir, params_json)
            if match:
                candidates.append(match)

        # Priority 3: convert.py thumbnails. params normally points at the RAW
        # original, which Pillow cannot decode — without this fallback the
        # BEFORE side silently degenerates into a grey placeholder.
        if thumbs:
            for key in stem_keys:
                if key in thumbs:
                    candidates.append(thumbs[key])
                    break

        pairs.append((_pick_original(candidates), gp))

    if not pairs:
        return None

    # Label styling — scale font with cell_height
    label_font_size = max(24, cell_height // 16)
    header_height = label_font_size + 20  # Top header bar height
    divider_width = max(4, gap)  # Vertical divider between BEFORE/AFTER

    # Each row: [original | graded], both fit into cell_height
    row_images = []
    for orig_path, graded_path in pairs:
        try:
            graded_img = Image.open(graded_path).convert("RGB")
        except Exception as e:
            print(f"   ⚠️  Failed to load graded {graded_path.name}: {e}")
            continue

        # Scale graded to cell_height
        g_w, g_h = graded_img.size
        scale = cell_height / g_h
        target_w = int(g_w * scale)
        target_h = cell_height
        graded_resized = graded_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        orig_resized = None
        if orig_path and orig_path.exists():
            try:
                orig_img = Image.open(orig_path).convert("RGB")
                orig_resized = orig_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            except Exception as e:
                # Pillow cannot decode camera RAW — report it instead of
                # silently substituting the grey placeholder.
                print(f"   ⚠️  Original not decodable: {orig_path.name} ({e})")
                print("      Run convert.py to build thumbnails, or pass --originals <thumbnails_dir>.")
        if orig_resized is None:
            print(f"   ⚠️  No usable original for {graded_path.name} — BEFORE side left blank.")
            orig_resized = Image.new("RGB", (target_w, target_h), (200, 200, 200))

        # Add corner labels on images
        orig_labeled = add_label(
            orig_resized,
            "BEFORE",
            position="top-left",
            font_size=label_font_size,
            bg_color=(80, 80, 80, 200),
            padding=12,
        )
        graded_labeled = add_label(
            graded_resized,
            "AFTER",
            position="top-right",
            font_size=label_font_size,
            bg_color=(0, 120, 60, 200),
            padding=12,
        )

        row_images.append((orig_labeled, graded_labeled, target_w, target_h))

    if not row_images:
        return None

    # Calculate canvas size
    max_pair_width = max(tw for _, _, tw, _ in row_images)
    canvas_w = max_pair_width * 2 + divider_width
    total_image_h = sum(th for _, _, _, th in row_images) + label_gap * (len(row_images) - 1)
    canvas_h = total_image_h

    canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)

    y_offset = 0
    for orig_img, graded_img, tw, th in row_images:
        # Center each pair horizontally if narrower than max
        x_left = (max_pair_width - tw) // 2
        x_right = max_pair_width + divider_width + (max_pair_width - tw) // 2

        canvas.paste(orig_img, (x_left, y_offset))
        canvas.paste(graded_img, (x_right, y_offset))

        # Draw vertical divider line
        draw = ImageDraw.Draw(canvas)
        divider_x = max_pair_width
        draw.rectangle(
            [divider_x, y_offset, divider_x + divider_width - 1, y_offset + th - 1],
            fill=(220, 220, 220),
        )

        y_offset += th + label_gap

    return canvas


def generate_grid(images, cell_size=800, gap=6, bg_color=(255, 255, 255)):
    """
    Compose images into a grid layout.

    Grid dimensions:
      1 photo: 1×1, 2: 1×2, 3: 1×3, 4: 2×2, 5-6: 2×3, 7-9: 3×3
    """
    count = len(images)
    if count <= 1:
        rows, cols = 1, 1
    elif count == 2:
        rows, cols = 1, 2
    elif count == 3:
        rows, cols = 1, 3
    elif count == 4:
        rows, cols = 2, 2
    elif count <= 6:
        rows, cols = 2, 3
    else:
        rows, cols = 3, 3

    canvas_w = cols * cell_size + (cols - 1) * gap
    canvas_h = rows * cell_size + (rows - 1) * gap
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)

    for idx, img in enumerate(images[: rows * cols]):
        row = idx // cols
        col = idx % cols
        x = col * (cell_size + gap)
        y = row * (cell_size + gap)

        cropped = center_crop_square(img)
        resized = cropped.resize((cell_size, cell_size), Image.Resampling.LANCZOS)
        canvas.paste(resized, (x, y))

    return canvas


# ── Main ────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Generate layout preview: side-by-side comparison (default) or grid",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  Default (comparison): Shows original (left) vs graded (right) for each photo.
                        Requires --originals to specify the original photos directory.

  Grid (--grid):        Classic grid layout (4宫格 / 9宫格).
                        Only shows graded photos.

Examples:
  # Side-by-side comparison (default)
  %(prog)s ~/data/output/20260324-155000/graded \\
      --originals ~/data/RAW \\
      --params ~/data/output/20260324-155000/grading_params.json

  # Grid mode (宫格)
  %(prog)s ~/data/output/20260324-155000/graded --grid \\
      --params ~/data/output/20260324-155000/grading_params.json
        """,
    )
    parser.add_argument("graded_dir", help="Directory containing graded JPG files")
    parser.add_argument("--originals", type=str, default=None, help="Originals 目录（仅当 params 中无绝对路径时需要）")
    parser.add_argument("--params", type=str, default=None, help="grading_params.json for photo ordering")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output JPG path")
    parser.add_argument("--grid", action="store_true", help="Use grid layout (宫格) instead of side-by-side comparison")
    parser.add_argument(
        "--layout-config",
        type=str,
        default=None,
        help="layout_config.json for photo ordering and count (overrides --params ordering)",
    )
    parser.add_argument(
        "--cell-size", type=int, default=800, help="Grid cell size or comparison row height in pixels (default: 800)"
    )
    parser.add_argument("--gap", type=int, default=6, help="Gap between cells in pixels (default: 6)")
    parser.add_argument("--quality", type=int, default=92, help="JPEG quality for output (default: 92)")
    parser.add_argument(
        "--platform",
        type=str,
        default=None,
        choices=["wechat", "xiaohongshu"],
        help="Use platform-specific ordering from layout_config.json",
    )

    args = parser.parse_args()

    graded_dir = Path(args.graded_dir).expanduser().resolve()
    if not graded_dir.exists():
        print(f"❌ Graded directory not found: {graded_dir}", file=sys.stderr)
        sys.exit(1)

    # ── Load layout_config if provided ──────────────────────────
    layout_order = None
    layout_count = None
    if args.layout_config:
        lc_path = Path(args.layout_config).expanduser().resolve()
        if not lc_path.exists():
            print(f"   ⚠️  Layout config not found, ignored: {lc_path}", file=sys.stderr)
        if lc_path.exists():
            try:
                with open(lc_path, "r", encoding="utf-8") as f:
                    lc = json.load(f)
                platform = args.platform or "wechat"
                if platform in lc:
                    plat_cfg = lc[platform]
                    layout_order = plat_cfg.get("order", [])
                    layout_count = plat_cfg.get("count")
                    print(f"📋 Layout config: {platform} ({layout_count} photos)")
                elif "order" in lc:
                    layout_order = lc["order"]
                    layout_count = lc.get("count")
            except (json.JSONDecodeError, OSError) as e:
                print(f"   ⚠️  Failed to load layout config: {e}")

    image_paths = find_graded_images(graded_dir, args.params)

    # Apply layout_config ordering if available
    if layout_order and image_paths:
        stem_to_path = {}
        for p in image_paths:
            stem_to_path[p.stem.lower()] = p
            parts = p.stem.rsplit("_", 1)
            if len(parts) > 1:
                stem_to_path[parts[0].lower()] = p
        ordered = []
        seen = set()
        for fname in layout_order:
            stem = Path(fname).stem.lower()
            if stem in stem_to_path and stem_to_path[stem] not in seen:
                ordered.append(stem_to_path[stem])
                seen.add(stem_to_path[stem])
        if ordered:
            image_paths = ordered

    # Apply count limit
    if layout_count and layout_count < len(image_paths):
        image_paths = image_paths[:layout_count]
    if not image_paths:
        print("❌ No graded JPG files found.", file=sys.stderr)
        sys.exit(1)

    print(f"📸 Found {len(image_paths)} graded photo(s):")
    for i, p in enumerate(image_paths, 1):
        print(f"   {i}. {p.name}")

    if args.grid:
        # ── Grid mode (宫格) ──
        print(f"\n🎨 Generating {len(image_paths)}-photo grid preview...")
        images = []
        for p in image_paths:
            try:
                img = Image.open(p).convert("RGB")
                images.append(img)
            except Exception as e:
                print(f"   ⚠️  Failed to load {p.name}: {e}")

        if not images:
            print("❌ No images could be loaded.", file=sys.stderr)
            sys.exit(1)

        result = generate_grid(images, cell_size=args.cell_size, gap=args.gap)
        mode_label = "grid"
    else:
        # ── Comparison mode (default) ──
        # Get originals from grading_params.json if available
        params_mapping = _find_originals_from_params(args.params)

        originals_dir = args.originals
        if not originals_dir and not params_mapping:
            # Try to auto-detect: look in ~/data/RAW or thumbnails sibling dir
            candidates = [
                graded_dir.parent / "thumbnails",
                Path("~/data/RAW").expanduser().resolve(),
            ]
            for c in candidates:
                if c.exists() and any(c.iterdir()):
                    originals_dir = str(c)
                    print(f"   📂 Auto-detected originals: {c}")
                    break

        if not originals_dir and not params_mapping:
            print(
                "❌ No originals found. Use --originals or --params with absolute paths, or --grid for grid mode.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"\n🔄 Generating side-by-side comparison (BEFORE | AFTER)...")
        if originals_dir:
            print(f"   Originals: {originals_dir}")
        if params_mapping:
            print(f"   Originals from params: {len(params_mapping)} file(s)")
        result = generate_comparison(
            image_paths,
            originals_dir,
            params_json=args.params,
            params_mapping=params_mapping,
            cell_height=args.cell_size,
            gap=args.gap,
        )

        if result is None:
            print("❌ Failed to generate comparison.", file=sys.stderr)
            sys.exit(1)

        mode_label = "comparison"

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = graded_dir.parent / "layout_preview.jpg"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, "JPEG", quality=args.quality, optimize=True)

    size_kb = output_path.stat().st_size / 1024
    print(f"\n✅ Layout preview saved: {output_path}")
    print(f"   📐 {result.width}×{result.height}px, {size_kb:.0f}KB")
    print(f"   📸 {len(image_paths)} photos ({mode_label})")


if __name__ == "__main__":
    main()
