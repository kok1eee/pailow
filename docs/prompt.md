# pailow — drop-in prompt for LLM tool use

Copy this into your LLM's system prompt when wiring pailow into a tool-use loop.
The matching tool definition should be generated from `pailow schema` (see
"Tool definition" below).

> **Full reference**: [`SKILL.md`](../SKILL.md) is the canonical, comprehensive
> LLM guide (all fields, fit strategies, correction loop, gallery, library
> mode). This document is the condensed drop-in version — when in doubt, read
> SKILL.md.

## What pailow does

pailow is a CLI and Python library that renders text onto images. You give it
a **spec** (a JSON object describing a canvas and a list of text boxes) and
an optional background image. It produces a deterministic PNG.

The bridge use case: an LLM that needs to produce or modify a text-overlay
image emits a pailow spec instead of free-form prose. pailow turns that spec
into pixel-perfect output.

## When to use this tool

Emit a pailow spec when:

- The user wants text added to, changed, or laid out on an image.
- The user describes a layout in natural language and you can translate it to
  boxes (position, size, padding, alignment, fit strategy, color).
- The user asks to fix an existing spec (`pailow validate` will tell you
  what's wrong — see "Correction loop" below).

Do **not** emit a pailow spec for:

- Image editing that is not text overlay (filtering, cropping, compositing
  without text). Use other tools.
- Hand-drawn or arbitrary-positioned glyphs. pailow is rectangle-based.

## Tool definition

Build the tool's `input_schema` from `pailow schema` (draft 2020-12).
That output is the canonical contract — do not paraphrase the schema; the
runtime validation depends on field names being exact.

If your tool platform does not accept draft 2020-12 directly, the minimum
required shape is:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["canvas", "boxes"],
  "properties": {
    "canvas": {
      "type": "object",
      "additionalProperties": false,
      "required": ["width", "height"],
      "properties": {
        "width":  {"type": "integer", "minimum": 1},
        "height": {"type": "integer", "minimum": 1},
        "background": {"type": "string", "pattern": "^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"}
      }
    },
    "boxes": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "x", "y", "w", "h"],
        "properties": {
          "id":    {"type": "string", "minLength": 1},
          "x":     {"type": "integer", "minimum": 0},
          "y":     {"type": "integer", "minimum": 0},
          "w":     {"type": "integer", "minimum": 1},
          "h":     {"type": "integer", "minimum": 1},
          "text":  {"type": "string"},
          "pad":   {"type": "integer", "minimum": 0},
          "font":  {"type": ["string", "null"]},
          "size":  {"type": "integer", "minimum": 1},
          "color": {"type": "string", "pattern": "^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"},
          "align":    {"type": "string", "enum": ["left", "center", "right"]},
          "valign":   {"type": "string", "enum": ["top", "middle", "bottom"]},
          "fit":      {"type": "string", "enum": ["wrap", "shrink", "truncate"]},
          "line_spacing": {"type": "number", "exclusiveMinimum": 0},
          "min_size": {"type": "integer", "minimum": 1},
          "char_size_steps": {
            "type": "array",
            "items": {
              "type": "array",
              "prefixItems": [
                {"type": "integer", "minimum": 1},
                {"type": "integer", "minimum": 1}
              ],
              "minItems": 2,
              "maxItems": 2
            }
          },
          "parent": {"type": "string"}
        }
      }
    }
  }
}
```

## Semantics

- **Coordinate origin**: top-left, in pixels. `x` increases right, `y` down.
- **Boxes** are rectangular containers. `pad` is inner padding in pixels
  (CSS-style); text is flowed inside `box.w - 2*pad` by `box.h - 2*pad`.
- **`fit` strategy**:
  - `wrap` — word-wrap into multiple lines. Vertical overflow is possible.
  - `shrink` — decrement font size from `box.size` down to 1 until text fits.
    `min_size` sets a floor to stop early.
  - `truncate` — single line, appends `…` (U+2026) on overflow.
  - `char_size_steps` — `[[max_chars, size], ...]`: font size picked by
    character count (variable-length content).
- **Color**: `#RGB`, `#RRGGBB`, or `#RRGGBBAA` only. No CSS color names.
- **Font**: omit `font` to use the system default sans. To use a specific
  font, set `font` to a TTF/OTF file path that exists on the rendering host.
- **`text` empty**: the box is skipped (no rendering). Useful for layouts
  that share a base spec and toggle boxes on/off.

## Defaults (use them; do not re-state)

| field         | default    |
|---------------|------------|
| `pad`         | `0`        |
| `font`        | system     |
| `size`        | `24`       |
| `color`       | `#FFFFFF`  |
| `align`       | `left`     |
| `valign`      | `middle`   |
| `fit`         | `wrap`     |
| `line_spacing`| `1.2`      |
| `background`  | `#FFFFFF`  |

## Correction loop

pailow emits structured errors. After producing a spec, you can run
`pailow validate spec.json --json` (or call the library function) to get a
list of errors. Each error has:

- `code` — stable identifier (e.g. `invalid_enum`, `out_of_bounds`).
- `path` — JSON Pointer to the field that failed (e.g. `/boxes/0/align`).
- `expected` — what the field should be.
- `fix` — human-readable, action-oriented hint.

Read the errors, edit the spec, re-validate. The validator collects all
errors in one pass — do not stop at the first one.

The four `fit` strategies produce a different *diagnostic* layer (text-fits
vs text-doesn't-fit) exposed by `pailow fit spec.json --json`. That
diagnostic does **not** make a spec invalid; it is a quality signal.
If `fits: false`, switch the strategy (e.g. from `wrap` to `shrink`) or
enlarge the box.

## Non-goals (do not invent these)

- No percent coords or anchor strings. Relative positioning is available only
  via `parent` (spec inheritance).
- No multi-line text flow beyond whitespace-based `wrap` (CJK / RTL
  word-breaking is not yet supported).
- No CSS color names. Only hex.
- No invented fields. Unknown fields are ignored by default; pass
  `validate --strict` to reject them with an `unknown_field` error. (The
  tool-definition schema above uses `additionalProperties: false` because a
  generated tool should not emit extras.)

## Good example — a sale poster

Request: *"Make a 1200x800 sale poster with a yellow eyebrow, a big white
title, a body description, and a small CTA button at the bottom."*

```json
{
  "canvas": {"width": 1200, "height": 800, "background": "#1A1A1A"},
  "boxes": [
    {"id": "eyebrow", "x": 40, "y": 40, "w": 600, "h": 40, "text": "LIMITED TIME", "size": 28, "color": "#FFD86B", "valign": "top"},
    {"id": "title",   "x": 40, "y": 90, "w": 1120, "h": 240, "pad": 8, "text": "50% OFF EVERYTHING", "size": 128, "color": "#FFFFFF", "fit": "shrink"},
    {"id": "body",    "x": 40, "y": 360, "w": 800, "h": 240, "text": "Shop our entire collection. Discount auto-applied at checkout.", "size": 32, "color": "#E5E5E5", "valign": "top", "line_spacing": 1.4},
    {"id": "cta",     "x": 40, "y": 680, "w": 360, "h": 80, "text": "Shop now", "size": 48, "color": "#1A1A1A", "align": "center"}
  ]
}
```

## Repair cycle — error → fix

Bad spec (invalid `align` and `color`, duplicate id, box out of canvas):

```json
{
  "canvas": {"width": 100, "height": 100, "background": "blue"},
  "boxes": [
    {"id": "a", "x": -5, "y": 0, "w": 50, "h": 20, "align": "middle", "color": "red"},
    {"id": "a", "x": 80, "y": 0, "w": 50, "h": 20}
  ]
}
```

`pailow validate --json` returns (abbreviated):

```json
{
  "valid": false,
  "errors": [
    {"code": "invalid_color", "path": "/canvas/background", "fix": "canvas.background 'blue' is not a valid color; use '#RGB', '#RRGGBB', or '#RRGGBBAA'"},
    {"code": "out_of_range", "path": "/boxes/0/x", "fix": "/boxes/0.x must be non-negative (got -5)"},
    {"code": "invalid_enum", "path": "/boxes/0/align", "fix": "change /boxes/0.align from 'middle' to one of: left, center, right"},
    {"code": "invalid_color", "path": "/boxes/0/color", "fix": "/boxes/0.color 'red' is not a valid color"},
    {"code": "duplicate_id", "path": "/boxes/1/id", "fix": "id 'a' is duplicated; each box needs a unique id"},
    {"code": "out_of_bounds", "path": "/boxes/1", "fix": "box 'a': x (80) + w (50) = 130 exceeds canvas width 100"}
  ]
}
```

Fixed spec:

```json
{
  "canvas": {"width": 100, "height": 100, "background": "#0000FF"},
  "boxes": [
    {"id": "a", "x": 0, "y": 0, "w": 50, "h": 20, "align": "center", "color": "#FF0000"},
    {"id": "b", "x": 0, "y": 30, "w": 50, "h": 20}
  ]
}
```

## Library mode (when the LLM is in Python)

```python
from pailow import (
    Box, Canvas,
    build_schema,
    load_spec_from_mapping,
    render_from_mapping,
    validate_spec,
    SpecError,
)
from pathlib import Path

# Validate first
errors = validate_spec(spec_dict)
if errors:
    for e in errors:
        print(e.code, e.path, e.fix)
    raise SystemExit(1)

# Render
img = render_from_mapping(spec_dict, background=Path("bg.png"))
img.save("out.png")
```

## Reference

- Full LLM guide: `SKILL.md` (repo root)
- Full schema: `pailow schema --pretty`
- All commands: `pailow --help`
- Example specs: `examples/gallery/`
