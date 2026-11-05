"""`pailow inspect` — measure the rendered pixels, not the font metrics.

`analyze()` predicts whether text fits. `inspect` draws the image and measures
what actually landed on the canvas, then reports where the real ink sits
relative to the box that asked for it.

Design notes (see .graphhopper/plans/g-mw34eb32.md):
- Layout is resolved by `render.layout_box()` — the same function `render()`
  uses — so inspection can never disagree with the renderer.
- `auto` colors are resolved against the accumulated image (render parity),
  while the ink mask is measured from "background only + this box".
"""

from __future__ import annotations

from typing import Any, Optional

from PIL import Image, ImageChops, ImageDraw

from pailow.box import Box, Canvas
from pailow.render import BoxLayout, layout_box, line_height, render
from pailow.suggest import contrast_ratio, suggest_for_box

INK_THRESHOLD = 8
TOLERANCE_PX = 2
MIN_FONT_PX = 11.0
CONTRAST_NORMAL = 4.5
CONTRAST_LARGE = 3.0
LARGE_FONT_PX = 18.0


def _ink_mask(with_text: Image.Image, bg_only: Image.Image) -> Image.Image:
    """Binary mask (mode L) of pixels that differ from the background."""
    diff = ImageChops.difference(with_text.convert("RGBA"), bg_only.convert("RGBA"))
    r, g, b, a = diff.split()
    widest = ImageChops.lighter(ImageChops.lighter(r, g), ImageChops.lighter(b, a))
    return widest.point(lambda v: 255 if v > INK_THRESHOLD else 0)


def _bg_rgb(bg_only: Image.Image, box: Box) -> tuple[int, int, int]:
    """Median background color under the box (robust for photo backgrounds)."""
    left = max(0, box.x)
    top = max(0, box.y)
    right = min(bg_only.width, box.x + box.w)
    bottom = min(bg_only.height, box.y + box.h)
    if right <= left or bottom <= top:
        return (0, 0, 0)
    region = bg_only.crop((left, top, right, bottom)).convert("RGB")
    pixels = list(region.getdata())
    if not pixels:
        return (0, 0, 0)
    chans = list(zip(*pixels))
    median = tuple(sorted(c)[len(c) // 2] for c in chans)
    return (int(median[0]), int(median[1]), int(median[2]))


def _composite(fg: tuple[int, int, int, int], bg: tuple[int, int, int]) -> tuple[int, int, int]:
    alpha = fg[3] / 255.0 if len(fg) > 3 else 1.0
    return tuple(round(fg[i] * alpha + bg[i] * (1.0 - alpha)) for i in range(3))  # type: ignore[return-value]


def _intersection(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> Optional[tuple[int, int, int, int]]:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _outside_canvas(
    layout: BoxLayout,
    bbox: Optional[tuple[int, int, int, int]],
    canvas: Canvas,
) -> bool:
    """True only when ink is actually clipped by the canvas edge.

    Font metrics alone are too eager: a descender line can cross the edge
    without losing a single pixel. So the metric estimate must agree with the
    measured ink touching that edge.
    """
    if bbox is None:
        return False
    ascent, descent = layout.font.getmetrics()
    for (x, y), width in zip(layout.positions, layout.line_widths):
        if x < 0 and bbox[0] <= 1:
            return True
        if y < 0 and bbox[1] <= 1:
            return True
        if x + width > canvas.width and bbox[2] >= canvas.width - 1:
            return True
        if y + ascent + descent > canvas.height and bbox[3] >= canvas.height - 1:
            return True
    return False


def inspect_canvas(
    canvas: Canvas,
    boxes: list[Box],
    background: Optional[Image.Image] = None,
) -> tuple[dict[str, Any], Image.Image]:
    """Measure every box. Returns (report, rendered image)."""
    bg_only = render(canvas, [], background=background)
    rendered = bg_only.copy()
    render_draw = ImageDraw.Draw(rendered)

    records: list[dict[str, Any]] = []

    for box in boxes:
        if not box.text:
            continue

        # Color/positions come from the accumulated image: exactly what render() sees.
        layout = layout_box(box, rendered, render_draw)

        if layout is None:
            findings = [
                {
                    "code": "box_too_small",
                    "severity": "error",
                    "detail": f"inner area is {box.w - 2 * box.pad}x{box.h - 2 * box.pad}; nothing is drawn",
                }
            ]
            records.append(
                _record(box, None, None, [], findings, None, None, 0.0)
            )
            continue

        # Draw into the accumulated image so later `auto` boxes see this ink (render parity).
        backdrop = rendered.copy()
        for line, (x, y) in zip(layout.lines, layout.positions):
            render_draw.text((x, y), line, font=layout.font, fill=layout.color)

        # Measure in isolation: background + this box only.
        solo = bg_only.copy()
        solo_draw = ImageDraw.Draw(solo)
        for line, (x, y) in zip(layout.lines, layout.positions):
            solo_draw.text((x, y), line, font=layout.font, fill=layout.color)
        mask = _ink_mask(solo, bg_only)
        bbox = mask.getbbox()

        findings: list[dict] = []
        overflow: dict[str, int] = {}
        within_tolerance = True

        inner = (layout.inner_x, layout.inner_y, layout.inner_x + layout.inner_w, layout.inner_y + layout.inner_h)

        if bbox is None:
            findings.append(
                {
                    "code": "invisible",
                    "severity": "error",
                    "detail": "text is set but no ink was painted (same color as the background?)",
                }
            )
        else:
            left_over = inner[0] - bbox[0]
            top_over = inner[1] - bbox[1]
            right_over = bbox[2] - inner[2]
            bottom_over = bbox[3] - inner[3]
            for name, amount in (
                ("left", left_over),
                ("top", top_over),
                ("right", right_over),
                ("bottom", bottom_over),
            ):
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

        if _outside_canvas(layout, bbox, canvas):
            findings.append(
                {
                    "code": "outside_canvas",
                    "severity": "error",
                    "detail": "some text falls outside the canvas",
                }
            )

        # Alignment drift (informational: ink has bearings/leading that make
        # perfect symmetry impossible, so this is reported but never fails).
        if bbox is not None and box.align == "center":
            left_gap = bbox[0] - inner[0]
            right_gap = inner[2] - bbox[2]
            if abs(left_gap - right_gap) > TOLERANCE_PX:
                findings.append(
                    {
                        "code": "align_drift",
                        "severity": "info",
                        "detail": f"center ink is off by {abs(left_gap - right_gap)}px",
                    }
                )

        if box.valign == "middle":
            lh = line_height(layout.font, box.line_spacing)
            total_h = len(layout.lines) * lh
            top_gap = layout.positions[0][1] - inner[1]
            bottom_gap = inner[3] - (layout.positions[0][1] + total_h)
            if abs(top_gap - bottom_gap) > TOLERANCE_PX:
                findings.append(
                    {
                        "code": "valign_drift",
                        "severity": "info",
                        "detail": f"middle block is off by {abs(int(top_gap - bottom_gap))}px",
                    }
                )

        bg_rgb = _bg_rgb(backdrop, box)
        text_rgb = _composite(layout.color, bg_rgb)
        ratio = contrast_ratio(text_rgb, bg_rgb)
        required = CONTRAST_LARGE if layout.font_size >= LARGE_FONT_PX else CONTRAST_NORMAL
        if ratio < required:
            findings.append(
                {
                    "code": "contrast",
                    "severity": "warning",
                    "detail": f"{ratio:.2f}:1 < {required}:1",
                }
            )

        if layout.font_size < MIN_FONT_PX:
            findings.append(
                {
                    "code": "min_size",
                    "severity": "warning",
                    "detail": f"effective font size {layout.font_size:.0f}px < {MIN_FONT_PX:.0f}px",
                }
            )

        if layout.color[3] < 255:
            findings.append(
                {
                    "code": "alpha_not_blended",
                    "severity": "info",
                    "detail": f"color alpha {layout.color[3]} is written raw; render() does not composite",
                }
            )

        suggestions = suggest_for_box(
            box,
            findings,
            bg_rgb=bg_rgb,
            current_contrast=ratio,
            font_size=layout.font_size,
            overflow=overflow,
        )

        records.append(
            _record(
                box,
                layout,
                bbox,
                [],
                findings,
                ratio,
                bg_rgb,
                layout.font_size,
                overflow=overflow,
                within_tolerance=within_tolerance,
                suggestions=suggestions,
            )
        )

    # Collisions are pairwise, so they are attached after every box is measured.
    for i, record in enumerate(records):
        mine = record.get("_bbox")
        if mine is None:
            continue
        for j, other in enumerate(records):
            if i == j:
                continue
            theirs = other.get("_bbox")
            if theirs is None:
                continue
            hit = _intersection(mine, theirs)
            if hit is not None:
                area = (hit[2] - hit[0]) * (hit[3] - hit[1])
                record["collisions"].append(
                    {"box_id": other["box_id"], "area": area, "rect": list(hit)}
                )
        if record["collisions"]:
            record["findings"].append(
                {
                    "code": "collision",
                    "severity": "error",
                    "detail": "ink intersects " + ", ".join(c["box_id"] for c in record["collisions"]),
                }
            )
            record["suggestions"].extend(
                suggest_for_box(
                    _boxes_by_id(boxes)[record["box_id"]],
                    [{"code": "collision"}],
                    bg_rgb=record["background"] or (0, 0, 0),
                    current_contrast=record["contrast"],
                    font_size=record["font_size"],
                )
            )

    for record in records:
        record.pop("_bbox", None)

    summary = {
        "errors": sum(1 for r in records for f in r["findings"] if f["severity"] == "error"),
        "warnings": sum(1 for r in records for f in r["findings"] if f["severity"] == "warning"),
        "infos": sum(1 for r in records for f in r["findings"] if f["severity"] == "info"),
        "converged": not any(s["auto"] for r in records for s in r["suggestions"]),
    }
    report = {
        "canvas": {"width": canvas.width, "height": canvas.height},
        "threshold": INK_THRESHOLD,
        "boxes": records,
        "summary": summary,
        "iterations": [],
    }
    return report, rendered


def _boxes_by_id(boxes: list[Box]) -> dict[str, Box]:
    return {box.id: box for box in boxes}


def _record(
    box: Box,
    layout: Optional[BoxLayout],
    bbox: Optional[tuple[int, int, int, int]],
    collisions: list[dict],
    findings: list[dict],
    contrast: Optional[float],
    bg_rgb: Optional[tuple[int, int, int]],
    font_size: float,
    *,
    overflow: Optional[dict] = None,
    within_tolerance: bool = True,
    suggestions: Optional[list[dict]] = None,
) -> dict[str, Any]:
    inner = None
    if layout is not None:
        inner = {
            "x": layout.inner_x,
            "y": layout.inner_y,
            "w": layout.inner_w,
            "h": layout.inner_h,
        }
    painted = None
    if bbox is not None:
        painted = {"x": bbox[0], "y": bbox[1], "w": bbox[2] - bbox[0], "h": bbox[3] - bbox[1]}
    return {
        "box_id": box.id,
        "inner": inner,
        "painted": painted,
        "overflow": overflow or {},
        "within_tolerance": within_tolerance,
        "collisions": collisions,
        "visible": bbox is not None,
        "contrast": None if contrast is None else round(contrast, 2),
        "background": bg_rgb,
        "font_size": round(float(font_size), 1),
        "findings": findings,
        "suggestions": suggestions or [],
        "_bbox": bbox,
    }


def inspect_from_mapping(
    spec: Any,
    *,
    background: Optional[Image.Image] = None,
    level: str = "preflight",
) -> dict[str, Any]:
    """Inspect a spec mapping (or path string) and return the report."""
    from pathlib import Path

    from pailow.layout import load_spec, load_spec_from_mapping

    if isinstance(spec, (str, Path)):
        canvas, boxes = load_spec(spec, level=level)
    else:
        canvas, boxes = load_spec_from_mapping(spec, level=level)
    report, _ = inspect_canvas(canvas, boxes, background)
    return report


def inspect_spec(
    spec: Any,
    *,
    background: Optional[Image.Image] = None,
    level: str = "preflight",
) -> dict[str, Any]:
    """Inspect a spec path. Alias kept for symmetry with render_spec callers."""
    return inspect_from_mapping(spec, background=background, level=level)
