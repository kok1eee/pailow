from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "1.0"
PAILOW_VERSION = "0.1.0"


def build_schema() -> dict[str, Any]:
    """Return the JSON Schema (draft 2020-12) describing a pailow spec.

    Generated in code so it stays aligned with the Box / Canvas dataclasses.
    The schema covers field types, required fields, enums, and color format.
    Cross-field constraints (pad <= w/2, box within canvas) are checked at
    the semantic validation level, not in the schema.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://pailow.dev/schema/v{SCHEMA_VERSION}",
        "title": "pailow spec",
        "description": (
            "A pailow spec is a JSON object describing a canvas and a list of "
            "text overlay boxes. Each box is rendered in order onto a "
            "background image or solid color."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": ["canvas", "boxes"],
        "properties": {
            "canvas": _canvas_schema(),
            "boxes": _boxes_schema(),
        },
        "$defs": {
            "box": _box_schema(),
        },
    }


def _color_pattern() -> str:
    return r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"


def _canvas_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["width", "height"],
        "properties": {
            "width": {
                "type": "integer",
                "minimum": 1,
                "description": "Canvas width in pixels.",
                "examples": [1200],
            },
            "height": {
                "type": "integer",
                "minimum": 1,
                "description": "Canvas height in pixels.",
                "examples": [800],
            },
            "background": {
                "type": "string",
                "pattern": _color_pattern(),
                "default": "#FFFFFF",
                "description": (
                    "Solid background color when no image is provided. "
                    "Accepts #RGB, #RRGGBB, or #RRGGBBAA."
                ),
                "examples": ["#1A1A1A", "#FFFFFF"],
            },
        },
    }


def _boxes_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "minItems": 1,
        "items": {"$ref": "#/$defs/box"},
        "description": "Ordered list of text overlay boxes.",
    }


def _box_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "x", "y", "w", "h"],
        "properties": {
            "id": {
                "type": "string",
                "minLength": 1,
                "description": "Unique identifier for the box. Referenced in dry-run output.",
            },
            "x": {
                "type": "integer",
                "minimum": 0,
                "description": "Left edge in pixels from the canvas origin.",
            },
            "y": {
                "type": "integer",
                "minimum": 0,
                "description": "Top edge in pixels from the canvas origin.",
            },
            "w": {
                "type": "integer",
                "minimum": 1,
                "description": "Box width in pixels.",
            },
            "h": {
                "type": "integer",
                "minimum": 1,
                "description": "Box height in pixels.",
            },
            "text": {
                "type": "string",
                "default": "",
                "description": "Text to render. Empty string skips the box.",
            },
            "pad": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
                "description": "Inner padding in pixels. Text is flowed inside the padded area.",
            },
            "font": {
                "type": ["string", "null"],
                "default": None,
                "description": "Path to a TTF/OTF font file. null uses a discovered system sans font.",
            },
            "size": {
                "type": "integer",
                "minimum": 1,
                "default": 24,
                "description": "Font size in points.",
            },
            "color": {
                "type": "string",
                "pattern": _color_pattern(),
                "default": "#FFFFFF",
                "description": "Text color. Accepts #RGB, #RRGGBB, or #RRGGBBAA.",
            },
            "align": {
                "type": "string",
                "enum": ["left", "center", "right"],
                "default": "left",
                "description": "Horizontal alignment within the box.",
            },
            "valign": {
                "type": "string",
                "enum": ["top", "middle", "bottom"],
                "default": "middle",
                "description": "Vertical alignment within the box.",
            },
            "fit": {
                "type": "string",
                "enum": ["wrap", "shrink", "truncate"],
                "default": "wrap",
                "description": (
                    "Text fitting strategy. "
                    "'wrap' = word-wrap, may produce multiple lines. "
                    "'shrink' = decrement font size until it fits. "
                    "'truncate' = single line, appends U+2026 on overflow."
                ),
            },
            "line_spacing": {
                "type": "number",
                "exclusiveMinimum": 0,
                "default": 1.2,
                "description": "Line height multiplier. 1.0 = tight, 1.5 = loose.",
            },
            "min_size": {
                "type": ["integer", "null"],
                "minimum": 1,
                "default": None,
                "description": (
                    "Minimum font size for the shrink strategy. "
                    "If set, font size will not shrink below this value. "
                    "Useful to prevent text from becoming unreadable. "
                    "Must be <= size."
                ),
            },
            "char_size_steps": {
                "type": ["array", "null"],
                "default": None,
                "description": (
                    "Character-count-based initial font size selector. "
                    "Each entry is [max_chars, size]; the first entry where "
                    "len(text) <= max_chars determines the starting font size "
                    "for the shrink strategy. Entries must be sorted by max_chars "
                    "ascending. If unset or no entry matches, the box's `size` is used."
                ),
                "items": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": [
                        {"type": "integer", "minimum": 0},
                        {"type": "integer", "minimum": 1},
                    ],
                },
            },
            "parent": {
                "type": ["string", "null"],
                "default": None,
                "description": (
                    "Parent box id for nested layout. When set, the box's x/y are "
                    "relative to the parent box's padded inner area (CSS-like "
                    "position: relative). The box is rendered at the parent's "
                    "padding edge as origin."
                ),
            },
        },
    }


def schema_version() -> str:
    return f"{PAILOW_VERSION} (spec v{SCHEMA_VERSION})"
