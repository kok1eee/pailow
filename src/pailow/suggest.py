"""Suggestions for `pailow inspect`.

Turns measured findings into concrete, verifiable edits. Nothing here mutates a
Box; callers apply suggestions and re-measure.

Design notes (see .graphhopper/plans/g-mw34eb32.md, 判断4):
- `fit: "shrink"` already shrinks automatically, so `size` is a no-op there;
  the lever is `min_size`.
- A linear size estimate is only a starting point: every candidate is verified
  with the real layout code before it is suggested.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any, Optional

from PIL import Image, ImageDraw

from pailow.box import Box
from pailow.render import fit_text, line_height

# WCAG しきい値
CONTRAST_NORMAL = 4.5
CONTRAST_LARGE = 3.0
LARGE_FONT_PX = 18.0

_DRAW = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def _measure(box: Box) -> tuple[bool, float, float]:
    """Return (fits, max_line_width, total_height) from font metrics only."""
    inner_w = box.w - 2 * box.pad
    inner_h = box.h - 2 * box.pad
    if inner_w <= 0 or inner_h <= 0 or not box.text:
        return False, 0.0, 0.0
    font, lines, _ = fit_text(box, inner_w, inner_h, _DRAW)
    max_w = max((_DRAW.textlength(line, font=font) for line in lines), default=0.0)
    total_h = len(lines) * line_height(font, box.line_spacing)
    return (max_w <= inner_w and total_h <= inner_h), float(max_w), float(total_h)


def _find_fitting_size(box: Box, overflow_px: int = 0) -> Optional[int]:
    """Largest size below the current one that fits.

    The starting point uses the linear estimate from the *measured* overflow
    (`size * inner_w / (inner_w + overflow)`), then walks down verifying each
    candidate with the real layout code. Metrics alone can call a text "fitting"
    while its ink still overshoots, so the estimate matters.
    """
    current = int(round(box.size))
    inner_w = box.w - 2 * box.pad
    start = current - 1
    if overflow_px > 0 and inner_w > 0:
        estimate = int(current * inner_w / (inner_w + overflow_px))
        start = min(start, max(1, estimate))
    for size in range(start, 0, -1):
        if _measure(replace(box, size=size))[0]:
            return size
    return None


def _find_fitting_min_size(box: Box, overflow_px: int = 0) -> Optional[int]:
    """Largest min_size below the current one that lets shrink fit. None if none."""
    current = int(box.min_size) if box.min_size is not None else 1
    start = current - 1
    if overflow_px > 0:
        ratio = box.size / max(1, box.size)
        start = min(start, max(1, current - max(1, int(overflow_px * ratio))))
    for ms in range(start, 0, -1):
        if _measure(replace(box, min_size=ms))[0]:
            return ms
    return None


def _suggestion(box: Box, action: str, params: dict, reason: str, auto: bool) -> dict:
    return {
        "box_id": box.id,
        "action": action,
        "params": params,
        "reason": reason,
        "auto": auto,
        "confidence": "high" if auto else "low",
    }


def suggest_for_box(
    box: Box,
    findings: list[dict],
    *,
    bg_rgb: tuple[int, int, int],
    current_contrast: Optional[float],
    font_size: float,
    overflow_px: int = 0,
) -> list[dict]:
    """Build suggestions for one box from its findings."""
    out: list[dict] = []
    codes = {f["code"] for f in findings}

    if "overflow" in codes:
        if box.fit == "shrink":
            new_min = _find_fitting_min_size(box, overflow_px)
            if new_min is not None:
                out.append(
                    _suggestion(
                        box,
                        "set_min_size",
                        {"from": box.min_size, "to": new_min},
                        "ink overflows the inner rect and fit=shrink is already at min_size",
                        True,
                    )
                )
            else:
                out.append(
                    _suggestion(
                        box,
                        "resize_box",
                        {},
                        "text cannot fit even at size 1; the box needs to grow",
                        False,
                    )
                )
        elif box.char_size_steps:
            out.append(
                _suggestion(
                    box,
                    "resize_box",
                    {},
                    "char_size_steps controls the font size, so editing size has no effect",
                    False,
                )
            )
        else:
            new_size = _find_fitting_size(box, overflow_px)
            if new_size is not None:
                out.append(
                    _suggestion(
                        box,
                        "set_size",
                        {"from": int(round(box.size)), "to": new_size},
                        "ink overflows the inner rect",
                        True,
                    )
                )
            else:
                out.append(
                    _suggestion(
                        box,
                        "resize_box",
                        {},
                        "text cannot fit at any size; the box needs to grow",
                        False,
                    )
                )

    if "box_too_small" in codes:
        out.append(
            _suggestion(
                box,
                "resize_box",
                {"pad": box.pad, "w": box.w, "h": box.h},
                "inner area is non-positive, so nothing is drawn",
                False,
            )
        )

    if "invisible" in codes or "contrast" in codes:
        want = _pick_contrast_color(bg_rgb)
        if want.lower() != str(box.color).lower():
            reason = (
                "text is invisible against the measured background"
                if "invisible" in codes
                else "contrast against the measured background is below WCAG AA"
            )
            # 改善しないなら提案しない（適用後の再測定で必ず改善するものだけ出す）
            gain = contrast_ratio(_hex_to_rgb(want), bg_rgb) - (current_contrast or 0.0)
            if gain > 0.1:
                out.append(
                    _suggestion(box, "set_color", {"from": box.color, "to": want}, reason, True)
                )

    if "collision" in codes:
        out.append(
            _suggestion(
                box,
                "move",
                {},
                "measured ink intersects another box; moving changes the composition intent",
                False,
            )
        )

    if "min_size" in codes:
        out.append(
            _suggestion(
                box,
                "raise_min_size",
                {"from": font_size, "to": 11},
                "effective font size is below 11px",
                False,
            )
        )

    return out


# ── color helpers (shared with inspect) ─────────────────────────────────────


def _srgb_to_linear(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (_srgb_to_linear(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) < 6:
        return (0, 0, 0)
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def _pick_contrast_color(bg_rgb: tuple[int, int, int]) -> str:
    """Pick the hex color (black or white) with the better WCAG contrast."""
    return (
        "#000000"
        if contrast_ratio((0, 0, 0), bg_rgb) >= contrast_ratio((255, 255, 255), bg_rgb)
        else "#FFFFFF"
    )


def apply_suggestions(data: dict[str, Any], suggestions: list[dict]) -> dict[str, Any]:
    """Return a deep copy of the spec with `auto` suggestions applied.

    Only fields that actually control the outcome are touched (see 判断4):
    `set_size`, `set_min_size`, `set_color`.
    """
    out = copy.deepcopy(data)
    by_id = {box.get("id"): box for box in out.get("boxes", []) if isinstance(box, dict)}
    for item in suggestions:
        if not item.get("auto"):
            continue
        box = by_id.get(item.get("box_id"))
        if box is None:
            continue
        action = item.get("action")
        params = item.get("params") or {}
        if action == "set_size" and "to" in params:
            box["size"] = params["to"]
        elif action == "set_min_size" and "to" in params:
            box["min_size"] = params["to"]
        elif action == "set_color" and "to" in params:
            box["color"] = params["to"]
    return out


def collect_auto(report: dict[str, Any]) -> list[dict]:
    """Flatten the auto-applicable suggestions from an inspect report."""
    out: list[dict] = []
    for record in report.get("boxes", []):
        for item in record.get("suggestions", []):
            if item.get("auto"):
                out.append(item)
    return out


def spec_hash(data: dict[str, Any]) -> str:
    """Stable hash of a spec for loop convergence detection."""
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
