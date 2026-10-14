"""Annotated PNG for `pailow inspect --annotate`.

One image should be enough to see what is wrong: intended rects (dashed),
measured ink (solid), collisions (translucent fill), and short labels.

Design notes (see .graphhopper/plans/g-mw34eb32.md, 判断6):
- Labels are ASCII only. `find_default_font_path()` returns Latin fonts, so a
  Japanese box id would render as tofu; non-ASCII characters become `?`.
- Translucent fills go through a separate layer and `Image.alpha_composite`,
  because drawing straight onto RGBA overwrites instead of blending.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

_PALETTE = [
    (255, 0, 0, 255),
    (0, 128, 255, 255),
    (0, 176, 80, 255),
    (255, 140, 0, 255),
    (160, 0, 255, 255),
    (0, 176, 176, 255),
]


def _load_font(size: int, path: Optional[str]) -> ImageFont.ImageFont:
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _clamp(value: float, lo: float, hi: float) -> float:
    if hi < lo:
        return lo
    return max(lo, min(hi, value))


def _dash_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int, int],
    dash: float,
    gap: float,
) -> None:
    ax, ay = start
    bx, by = end
    length = math.hypot(bx - ax, by - ay)
    if length <= 0:
        return
    ux, uy = (bx - ax) / length, (by - ay) / length
    position = 0.0
    while position < length:
        stop = min(position + dash, length)
        draw.line(
            [(ax + ux * position, ay + uy * position), (ax + ux * stop, ay + uy * stop)],
            fill=color,
            width=1,
        )
        position = stop + gap


def _dash_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float, float, float],
    color: tuple[int, int, int, int],
) -> None:
    x0, y0, x1, y1 = xy
    _dash_line(draw, (x0, y0), (x1, y0), color, 6, 4)
    _dash_line(draw, (x1, y0), (x1, y1), color, 6, 4)
    _dash_line(draw, (x1, y1), (x0, y1), color, 6, 4)
    _dash_line(draw, (x0, y1), (x0, y0), color, 6, 4)


def _ascii(text: str) -> str:
    return "".join(ch if ord(ch) < 128 else "?" for ch in text)


def _label(record: dict[str, Any], index: int) -> str:
    parts = [f"#{index}", _ascii(str(record.get("box_id", "")))]
    overflow = record.get("overflow") or {}
    if overflow:
        parts.append(" ".join(f"+{v}{k[0]}" for k, v in sorted(overflow.items())))
    if not record.get("visible", True):
        parts.append("INVISIBLE")
    return " ".join(parts)[:48]


def annotate(
    img: Image.Image,
    report: dict[str, Any],
    *,
    label_font: Optional[str] = None,
    label_size: int = 12,
) -> Image.Image:
    """Return a new image with inspection annotations drawn on top."""
    base = img.convert("RGBA")
    width, height = base.size
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _load_font(label_size, label_font)

    for index, record in enumerate(report.get("boxes", [])):
        color = _PALETTE[index % len(_PALETTE)]

        inner = record.get("inner")
        if inner:
            x0 = _clamp(inner["x"], 0, width)
            y0 = _clamp(inner["y"], 0, height)
            x1 = _clamp(inner["x"] + inner["w"], 0, width)
            y1 = _clamp(inner["y"] + inner["h"], 0, height)
            if x1 > x0 and y1 > y0:
                _dash_rect(draw, (x0, y0, x1, y1), color)

        painted = record.get("painted")
        if painted:
            x0 = _clamp(painted["x"], 0, width)
            y0 = _clamp(painted["y"], 0, height)
            x1 = _clamp(painted["x"] + painted["w"], 0, width)
            y1 = _clamp(painted["y"] + painted["h"], 0, height)
            if x1 > x0 and y1 > y0:
                draw.rectangle([x0, y0, x1, y1], outline=color, width=1)

        for collision in record.get("collisions", []):
            rect = collision.get("rect")
            if not rect:
                continue
            x0 = _clamp(rect[0], 0, width)
            y0 = _clamp(rect[1], 0, height)
            x1 = _clamp(rect[2], 0, width)
            y1 = _clamp(rect[3], 0, height)
            if x1 > x0 and y1 > y0:
                draw.rectangle([x0, y0, x1, y1], fill=(255, 0, 0, 80))

        if painted:
            lx = _clamp(painted["x"], 0, max(0, width - 8))
            ly = _clamp(painted["y"] - label_size - 2, 0, max(0, height - label_size - 1))
            draw.text((lx, ly), _label(record, index), font=font, fill=color)

    summary = report.get("summary", {})
    legend = (
        f"errors {summary.get('errors', 0)} "
        f"warnings {summary.get('warnings', 0)} "
        f"infos {summary.get('infos', 0)}"
    )
    draw.text((4, 4), legend, font=font, fill=(0, 0, 0, 200))

    return Image.alpha_composite(base, overlay)
