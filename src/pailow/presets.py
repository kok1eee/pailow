"""Typography presets (Step 5).

spec の box に `"preset": "headline"` のように書くと、
その box に事前定義されたスタイルが適用される (box の個別フィールドが優先)。
"""

from __future__ import annotations

from typing import Any


PRESETS: dict[str, dict[str, Any]] = {
    "headline": {
        "size": 64,
        "color": "#FFFFFF",
        "align": "center",
        "valign": "middle",
        "fit": "shrink",
        "line_spacing": 1.0,
        "min_size": 32,
    },
    "subtitle": {
        "size": 28,
        "color": "#FFD86B",
        "align": "left",
        "valign": "middle",
        "fit": "shrink",
    },
    "body": {
        "size": 18,
        "color": "#333333",
        "align": "left",
        "valign": "top",
        "fit": "wrap",
        "line_spacing": 1.4,
    },
    "caption": {
        "size": 12,
        "color": "#666666",
        "align": "center",
        "valign": "middle",
    },
    "cta": {
        "size": 28,
        "color": "#FFFFFF",
        "align": "center",
        "valign": "middle",
        "fit": "shrink",
    },
}


def apply_preset(box_data: dict[str, Any], preset_name: str) -> dict[str, Any]:
    """box dict に preset を適用する。box の個別フィールドが preset より優先。

    box_data から `"preset"` キーは取り除かれる。
    """
    if preset_name not in PRESETS:
        raise KeyError(
            f"unknown preset: {preset_name!r}. "
            f"Available: {', '.join(PRESETS)}"
        )
    preset = PRESETS[preset_name]
    result = dict(preset)
    box_data = dict(box_data)
    box_data.pop("preset", None)
    result.update(box_data)
    return result


def resolve_presets(spec: dict[str, Any]) -> dict[str, Any]:
    """spec 内の全 box の `preset` フィールドを展開する。"""
    if "boxes" not in spec:
        return spec
    new_boxes = []
    for box in spec["boxes"]:
        if "preset" in box:
            new_boxes.append(apply_preset(box, box["preset"]))
        else:
            new_boxes.append(box)
    return {**spec, "boxes": new_boxes}