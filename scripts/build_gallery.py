"""Build the pailow gallery: validate, analyze, render, and compose a contact sheet."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from pailow import (
    analyze_from_mapping,
    load_spec_from_mapping,
    render_from_mapping,
    validate_spec,
)


HERE = Path(__file__).parent
GALLERY = HERE.parent / "examples" / "gallery"
OUT_DIR = GALLERY / "_build"
CONTACT_SHEET = GALLERY / "_contact_sheet.png"


def _generate_bg(canvas_w: int, canvas_h: int, out: Path) -> None:
    img = Image.new("RGB", (canvas_w, canvas_h), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    for y in range(canvas_h):
        t = y / max(1, canvas_h - 1)
        r = int(245 - 10 * t)
        g = int(245 - 10 * t)
        b = int(250 - 5 * t)
        draw.line([(0, y), (canvas_w, y)], fill=(r, g, b))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def _thumbnail(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    w, h = img.size
    scale = min(max_w / w, max_h / h, 1.0)
    new_w = int(w * scale)
    new_h = int(h * scale)
    resampling = getattr(Image, "Resampling", Image)
    lanczos = getattr(resampling, "LANCZOS", getattr(Image, "LANCZOS", 1))
    return img.resize((new_w, new_h), lanczos)


def _process_spec(spec_path: Path) -> tuple[Path, dict, list[dict], dict]:
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    is_broken = spec_path.name.endswith("_broken.json")

    if is_broken:
        errors = validate_spec(data, level="schema")
        return spec_path, {"valid": False, "errors": [e.to_dict() for e in errors], "expected": True}, [], {"skipped": True}

    errors = validate_spec(data, level="schema")
    if errors:
        return spec_path, {"valid": False, "errors": [e.to_dict() for e in errors]}, [], {}

    canvas, _boxes = load_spec_from_mapping(data)
    fit = analyze_from_mapping(data)
    fits_all = all(r["fits"] for r in fit)

    bg_path = OUT_DIR / f"{spec_path.stem}_bg.png"
    out_path = OUT_DIR / f"{spec_path.stem}.png"

    _generate_bg(canvas.width, canvas.height, bg_path)
    img = render_from_mapping(data, background=bg_path)
    img.save(out_path)
    return spec_path, {"valid": True, "errors": []}, fit, {
        "rendered": out_path,
        "fits": fits_all,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    spec_files = sorted(GALLERY.glob("*.json"))

    rendered: list[tuple[Path, Image.Image, list[dict]]] = []
    failures: list[tuple[Path, list[dict]]] = []
    expected_invalid: list[tuple[Path, list[dict]]] = []

    for spec_path in spec_files:
        _path, validation, fit, meta = _process_spec(spec_path)
        if not validation["valid"]:
            if validation.get("expected"):
                expected_invalid.append((spec_path, validation["errors"]))
            else:
                failures.append((spec_path, validation["errors"]))
            continue
        if "rendered" in meta and not meta.get("fits", True):
            failures.append((spec_path, [{"reason": "text does not fit", "fit": fit}]))
            continue
        if "rendered" in meta:
            img = Image.open(meta["rendered"])
            rendered.append((spec_path, img, fit))

    sheet_w = 1200
    thumb_w = 380
    thumb_h = 380
    cols = max(1, sheet_w // (thumb_w + 20))
    rows = (len(rendered) + cols - 1) // cols
    sheet_h = rows * (thumb_h + 60) + 40

    sheet = Image.new("RGB", (sheet_w, sheet_h), (250, 250, 250))
    draw = ImageDraw.Draw(sheet)

    for i, (spec_path, img, fit) in enumerate(rendered):
        col = i % cols
        row = i // cols
        x = col * (thumb_w + 20) + 20
        y = row * (thumb_h + 60) + 20

        thumb = _thumbnail(img, thumb_w, thumb_h)
        sheet.paste(thumb, (x, y))
        label = spec_path.stem
        fits_marker = "OK" if all(r["fits"] for r in fit) else "OVER"
        draw.text((x, y + thumb_h + 5), f"{label}  [{fits_marker}]", fill=(20, 20, 20))

    sheet.save(CONTACT_SHEET)
    print(f"wrote contact sheet: {CONTACT_SHEET}")

    if expected_invalid:
        print(
            f"info: {len(expected_invalid)} example(s) intentionally invalid "
            f"(used to demonstrate the repair cycle):"
        )
        for spec_path, errs in expected_invalid:
            print(f"  {spec_path.name}: {len(errs)} expected error(s)")

    if failures:
        print("FAIL: gallery has invalid or unfit examples:", file=sys.stderr)
        for spec_path, errs in failures:
            print(f"  {spec_path.name}:", file=sys.stderr)
            for e in errs:
                if "code" in e:
                    print(f"    {e['code']} {e['path']}: {e['fix']}", file=sys.stderr)
                else:
                    print(f"    {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
