"""Measure an already-rendered image: `measure_image`.

`inspect` renders the spec itself and measures what it drew. `measure_image` is
the read-only counterpart: it takes an image produced by *someone else* (another
pipeline, a designer, a CI artifact) plus the box rects that were intended, and
reports where the ink actually landed.

Use it from test scripts when you want to assert placement without making the
production code depend on pailow:

    from pailow import measure_image

    report = measure_image(
        "out/01_poster.png",
        [{"id": "title", "x": 40, "y": 90, "w": 1120, "h": 240, "pad": 8}],
        background="out/01_poster_bg.png",
    )
    report["boxes"][0]["painted"]          # measured ink rect
    report["boxes"][0]["suggested_adjust"] # {"dx": 0, "dy": -13, "resize_required": False}

Requirements / limits:
- The window searched for each box is its *rect* (x .. x+w, y .. y+h), optionally
  expanded by `margin`. Ink outside that window belongs to nobody: widen the box
  or pass `margin` if you expect it to spill further.
- `background` must be the same size and must NOT contain the text (a text-free
  render). When omitted, a solid `bg_color` canvas is assumed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from PIL import Image

from pailow.box import Box, parse_color
from pailow.errors import SpecError
from pailow.inspect import INK_THRESHOLD, TOLERANCE_PX, _ink_mask
from pailow.suggest import contrast_ratio

ImgLike = Union[Image.Image, str, Path]


def _load_rgba(value: ImgLike) -> Image.Image:
    if isinstance(value, Image.Image):
        return value.convert("RGBA")
    return Image.open(value).convert("RGBA")


def _normalize_boxes(boxes: list[Any]) -> list[dict[str, int | str]]:
    out: list[dict[str, int | str]] = []
    for raw in boxes:
        if isinstance(raw, Box):
            out.append(
                {
                    "id": raw.id,
                    "x": raw.x,
                    "y": raw.y,
                    "w": raw.w,
                    "h": raw.h,
                    "pad": raw.pad,
                }
            )
            continue
        if not isinstance(raw, dict):
            raise SpecError(
                code="invalid_box",
                path="",
                value=raw,
                expected="object with id/x/y/w/h",
                fix="Pass boxes as dicts: {id, x, y, w, h, pad?}.",
            )
        out.append(
            {
                "id": str(raw["id"]),
                "x": int(raw["x"]),
                "y": int(raw["y"]),
                "w": int(raw["w"]),
                "h": int(raw["h"]),
                "pad": int(raw.get("pad", 0)),
            }
        )
    return out


def _median_rgb(pixels: list[tuple[int, int, int]]) -> Optional[tuple[int, int, int]]:
    if not pixels:
        return None
    chans = list(zip(*pixels))
    median = tuple(sorted(channel)[len(channel) // 2] for channel in chans)
    return (int(median[0]), int(median[1]), int(median[2]))


def _masked_pixels(image: Image.Image, mask: Image.Image, window: tuple[int, int, int, int]):
    region = image.crop(window).convert("RGB")
    flags = mask.crop(window)
    return [
        (r, g, b)
        for (r, g, b), flag in zip(list(region.getdata()), list(flags.getdata()))
        if flag
    ]


def measure_image(
    rendered: ImgLike,
    boxes: list[Any],
    *,
    background: Optional[ImgLike] = None,
    bg_color: str = "#FFFFFF",
    threshold: int = INK_THRESHOLD,
    margin: int = 0,
) -> dict[str, Any]:
    """Measure where the ink actually is in an already-rendered image.

    Read-only: nothing is drawn. Returns the same per-box shape as
    `inspect --json`, plus `suggested_adjust` for writing corrections back to
    the caller's own layout parameters.
    """
    img = _load_rgba(rendered)

    if background is not None:
        bg = _load_rgba(background)
        if bg.size != img.size:
            raise SpecError(
                code="background_size_mismatch",
                path="/background",
                value=str(bg.size),
                expected=str(img.size),
                fix="The background image must have the same size as the rendered image.",
            )
    else:
        bg = Image.new("RGBA", img.size, parse_color(bg_color))

    mask = _ink_mask(img, bg, threshold)
    normalized = _normalize_boxes(boxes)
    width, height = img.size

    records: list[dict[str, Any]] = []
    for box in normalized:
        bx, by = int(box["x"]), int(box["y"])
        bw, bh = int(box["w"]), int(box["h"])
        pad = int(box["pad"])
        inner = (bx + pad, by + pad, bx + bw - pad, by + bh - pad)

        window = (
            max(0, bx - margin),
            max(0, by - margin),
            min(width, bx + bw + margin),
            min(height, by + bh + margin),
        )
        painted: Optional[tuple[int, int, int, int]] = None
        if window[2] > window[0] and window[3] > window[1]:
            local = mask.crop(window).getbbox()
            if local is not None:
                painted = (
                    window[0] + local[0],
                    window[1] + local[1],
                    window[0] + local[2],
                    window[1] + local[3],
                )

        findings: list[dict] = []
        overflow: dict[str, int] = {}
        within_tolerance = True
        text_rgb: Optional[tuple[int, int, int]] = None

        if painted is None:
            findings.append(
                {
                    "code": "invisible",
                    "severity": "error",
                    "detail": "no ink found inside the box window",
                }
            )
        else:
            over = {
                "left": inner[0] - painted[0],
                "top": inner[1] - painted[1],
                "right": painted[2] - inner[2],
                "bottom": painted[3] - inner[3],
            }
            for name, amount in over.items():
                if amount > 0:
                    overflow[name] = int(amount)
                    if amount > TOLERANCE_PX:
                        within_tolerance = False
            if overflow and not within_tolerance:
                findings.append(
                    {
                        "code": "overflow",
                        "severity": "error",
                        "detail": ", ".join(f"{k} +{v}px" for k, v in overflow.items()),
                    }
                )
            text_rgb = _median_rgb(_masked_pixels(img, mask, window))

        bg_rgb = _median_rgb(list(bg.crop(window).convert("RGB").getdata()))

        contrast = None
        if text_rgb is not None and bg_rgb is not None:
            contrast = round(contrast_ratio(text_rgb, bg_rgb), 2)

        if painted is not None:
            if painted[0] <= 0 and inner[0] < 0:
                findings.append(
                    {"code": "outside_canvas", "severity": "error", "detail": "ink clipped at left"}
                )
            if painted[1] <= 0 and inner[1] < 0:
                findings.append(
                    {"code": "outside_canvas", "severity": "error", "detail": "ink clipped at top"}
                )
            if painted[2] >= width and inner[2] > width:
                findings.append(
                    {"code": "outside_canvas", "severity": "error", "detail": "ink clipped at right"}
                )
            if painted[3] >= height and inner[3] > height:
                findings.append(
                    {
                        "code": "outside_canvas",
                        "severity": "error",
                        "detail": "ink clipped at bottom",
                    }
                )

        records.append(
            {
                "box_id": box["id"],
                "inner": {
                    "x": inner[0],
                    "y": inner[1],
                    "w": inner[2] - inner[0],
                    "h": inner[3] - inner[1],
                },
                "painted": None
                if painted is None
                else {
                    "x": painted[0],
                    "y": painted[1],
                    "w": painted[2] - painted[0],
                    "h": painted[3] - painted[1],
                },
                "overflow": overflow,
                "within_tolerance": within_tolerance,
                "collisions": [],
                "visible": painted is not None,
                "contrast": contrast,
                "text_color": list(text_rgb) if text_rgb else None,
                "background": list(bg_rgb) if bg_rgb else None,
                "suggested_adjust": _suggested_adjust(overflow),
                "findings": findings,
                "_bbox": painted,
            }
        )

    for i, record in enumerate(records):
        mine = record["_bbox"]
        if mine is None:
            continue
        for j, other in enumerate(records):
            if i == j or other["_bbox"] is None:
                continue
            hit = _intersect(mine, other["_bbox"])
            if hit is not None:
                record["collisions"].append(
                    {
                        "box_id": other["box_id"],
                        "area": (hit[2] - hit[0]) * (hit[3] - hit[1]),
                        "rect": list(hit),
                    }
                )
        if record["collisions"]:
            record["findings"].append(
                {
                    "code": "collision",
                    "severity": "error",
                    "detail": "ink intersects "
                    + ", ".join(c["box_id"] for c in record["collisions"]),
                }
            )

    for record in records:
        record.pop("_bbox", None)

    summary = {
        "errors": sum(1 for r in records for f in r["findings"] if f["severity"] == "error"),
        "warnings": sum(1 for r in records for f in r["findings"] if f["severity"] == "warning"),
        "infos": sum(1 for r in records for f in r["findings"] if f["severity"] == "info"),
        "converged": not any(
            f["severity"] in ("error", "warning") for r in records for f in r["findings"]
        ),
    }
    return {
        "canvas": {"width": width, "height": height},
        "threshold": threshold,
        "boxes": records,
        "summary": summary,
    }


def _intersect(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> Optional[tuple[int, int, int, int]]:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _suggested_adjust(overflow: dict[str, int]) -> dict[str, Any]:
    """Turn measured overflow into the smallest dx/dy that fixes it.

    Only one-sided overflow can be fixed by moving. When ink spills out on both
    sides of an axis, the text itself is too large and must be resized.
    """
    dx = 0
    dy = 0
    if "left" in overflow and "right" not in overflow:
        dx = int(overflow["left"])
    elif "right" in overflow and "left" not in overflow:
        dx = -int(overflow["right"])
    if "top" in overflow and "bottom" not in overflow:
        dy = int(overflow["top"])
    elif "bottom" in overflow and "top" not in overflow:
        dy = -int(overflow["bottom"])

    resize = ("left" in overflow and "right" in overflow) or (
        "top" in overflow and "bottom" in overflow
    )
    return {"dx": dx, "dy": dy, "resize_required": bool(resize)}
