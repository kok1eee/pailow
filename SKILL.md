# SKILL.md — pailow for LLMs

How to use **pailow** as a tool in an LLM tool-use loop. pailow is a CLI and
Python library that renders text onto images from a structured JSON spec.
You emit a **spec** (a JSON object describing a canvas and text boxes);
pailow renders a deterministic PNG.

For a condensed version to paste directly into a system prompt, see
[`docs/prompt.md`](docs/prompt.md). For humans, see [`README.md`](README.md).

## What pailow does

- Takes a JSON **spec**: `{canvas: {...}, boxes: [...]}` plus an optional
  background image.
- Produces pixel-exact text overlays: position, size, padding, alignment,
  color, and fit strategies are deterministic.
- Exposes a machine-readable contract: `schema`, `validate --json`,
  `fit --json`, `inspect --json` — designed for correction loops.
- `inspect` is the "eye": it renders the image and measures the actual ink, so
  you learn where a box really landed (overflow, collisions, contrast,
  invisible text) instead of trusting font metrics.

## When to use this tool

Emit a pailow spec when:

- The user wants text added to, changed, or laid out on an image.
- The user describes a layout in natural language and you can translate it
  to boxes (position, size, padding, alignment, fit strategy, color).
- The user asks to fix an existing spec (`pailow validate` tells you what's
  wrong — see "Correction loop" below).

Do **not** emit a pailow spec for:

- Image editing that is not text overlay (filtering, cropping, compositing
  without text). Use other tools.
- Hand-drawn or arbitrary-positioned glyphs. pailow is rectangle-based.

## Spec format

```json
{
  "canvas": {"width": 1200, "height": 800, "background": "#1A1A1A"},
  "boxes": [
    {
      "id": "title",
      "x": 40,
      "y": 40,
      "w": 1120,
      "h": 200,
      "text": "50% OFF EVERYTHING",
      "size": 128,
      "color": "#FFFFFF",
      "align": "left",
      "valign": "middle",
      "fit": "shrink"
    }
  ]
}
```

### Box fields

| Field             | Required | Default     | Description                                         |
|-------------------|----------|-------------|-----------------------------------------------------|
| `id`              | yes      | —           | Unique ID; referenced in diagnostics.               |
| `x`, `y`          | yes      | —           | Top-left origin, pixels. `x` right, `y` down.       |
| `w`, `h`          | yes      | —           | Box size, pixels.                                   |
| `text`            | no       | `""`        | Text to render. **Empty text skips the box.**       |
| `pad`             | no       | `0`         | Inner padding, pixels (CSS-style).                  |
| `font`            | no       | system      | TTF/OTF path on the rendering host. Omit = system sans. |
| `size`            | no       | `24`        | Font size, points.                                  |
| `color`           | no       | `#FFFFFF`   | `#RGB`, `#RRGGBB`, or `#RRGGBBAA`. Hex only.        |
| `align`           | no       | `left`      | `left` / `center` / `right`.                        |
| `valign`          | no       | `middle`    | `top` / `middle` / `bottom`.                        |
| `fit`             | no       | `wrap`      | `wrap` / `shrink` / `truncate`.                     |
| `line_spacing`    | no       | `1.2`       | Line height multiplier (> 0).                       |
| `min_size`        | no       | —           | Font-size floor when `fit: shrink`.                 |
| `char_size_steps` | no       | —           | `[[max_chars, size], ...]` — size by char count.    |
| `parent`          | no       | —           | Box id to inherit fields from (spec inheritance).   |

### fit strategies

- **`wrap`** (default): word-based wrapping into multiple lines. Vertical
  overflow is possible.
- **`shrink`**: decrement font size from `size` down to 1 until the text
  fits. Set `min_size` to stop early (e.g. keep a title legible).
- **`truncate`**: single line, appends `…` (U+2026) on overflow.
- **`char_size_steps`**: `[[6, 64], [12, 48]]` sizes text by character count —
  good for variable-length content.

### Defaults (use them; do not re-state)

| field          | default    |
|----------------|------------|
| `pad`          | `0`        |
| `font`         | system     |
| `size`         | `24`       |
| `color`        | `#FFFFFF`  |
| `align`        | `left`     |
| `valign`       | `middle`   |
| `fit`          | `wrap`     |
| `line_spacing` | `1.2`      |
| `background`   | `#FFFFFF`  |

## CLI usage in a tool loop

| Command | What to use it for |
|---------|--------------------|
| `pailow schema` | Build the tool's `input_schema` (draft 2020-12). Canonical — don't paraphrase field names. |
| `pailow validate <spec> --json` | Structured error list before returning a spec. |
| `pailow fit <spec> --json` | Fit diagnostics: `{fits, lines, chars, capacity, font_size, strategy}` per box. |
| `pailow render <spec> -i <bg> -o <out>` | Produce the final PNG. |
| `pailow prompt` | Emit the built-in LLM guide (condensed — this doc is the full reference, incl. `parent`). |
| `pailow gallery --list` / `--show <id>` | Verified few-shot specs to imitate. |
| `pailow diff <a> <b>` | Compare two specs (unified diff) or two images (pixel stats). |
| `pailow history --list` | Browse renders saved by `watch --history`. |

Exit codes: `validate` → `0` valid / `1` invalid; `fit` → `2` if any box
overflows.

## Correction loop

1. Emit a spec.
2. Run `pailow validate spec.json --json` (or `validate_spec` in Python).
3. Read the errors. Each has:
   - `code` — stable identifier (`invalid_color`, `invalid_enum`,
     `duplicate_id`, `out_of_range`, `out_of_bounds`, `unknown_field`, ...).
   - `path` — JSON Pointer to the failing field (`/boxes/0/align`).
   - `expected` — what the field should be.
   - `fix` — action-oriented hint.
4. Edit the spec, re-validate. The validator collects **all** errors in one
   pass — don't stop at the first.
5. Optional: `pailow fit spec.json --json` for the quality signal
   (text-fits vs doesn't). A `fits: false` box is not invalid — it just
   overflows. Switch strategy (e.g. `wrap` → `shrink`) or enlarge the box.

## Visual correction loop (`inspect`)

`fit` predicts; `inspect` measures. When the rendered result matters, add this
loop after validation:

1. Render and measure in one step:
   `pailow inspect spec.json -i bg.png --json`
2. Read each box's `painted` rect against its `inner` rect and the `findings`:
   - `overflow` — ink crosses the inner rect; `overflow` holds the px per side
     (differences within ±2px are normal and reported as `within_tolerance`).
   - `collision` — this box's ink intersects another box's ink.
   - `invisible` — text exists but no ink was painted (often color == background).
   - `contrast` — measured WCAG ratio against the real backdrop, below 4.5
     (3.0 for text ≥ 18px).
   - `min_size`, `line_density`, `box_too_small`, `outside_canvas`.
3. Apply only the `auto: true` suggestions, or let pailow do it:
   `pailow inspect spec.json --fix --loop 3`
   (`set_size` for `wrap`/`truncate`, `set_min_size` for `fit: shrink`,
   `set_color` for invisible/low-contrast text).
4. Look at the annotated image before and after:
   `pailow inspect spec.json --annotate debug.png`
   Dashed = intended rect, solid = measured ink, red fill = collision.
5. Manual findings (`collision`, `box_too_small`, `min_size`) are **not**
   auto-applied — they change design intent, so decide them yourself.

Exit codes: `0` clean, `1` findings remain, `2` auto-fixable findings remain
after `--fix`.

## Few-shot gallery

`pailow gallery --list` prints verified example IDs (poster, quote, social
square, banner, product card, repair cycle, long-text footer). To imitate a
style, `pailow gallery --show <id>` prints its spec. The `06_repair`
examples show a broken spec and its corrected form — a good demonstration
of the correction loop.

## Library mode (when you are in Python)

```python
from pailow import (
    Box, Canvas, build_schema, load_spec_from_mapping,
    render_from_mapping, validate_spec, SpecError,
)
from pathlib import Path

errors = validate_spec(spec_dict)          # 1. validate
if errors:
    for e in errors:
        print(e.code, e.path, e.fix)
    raise SystemExit(1)

img = render_from_mapping(spec_dict, background=Path("bg.png"))  # 2. render
img.save("out.png")
```

The full public API is re-exported from `pailow` — see `src/pailow/__init__.py`
for the authoritative list.

## Non-goals (do not invent these)

- No percent coords, anchor strings, or relative positioning (beyond `parent`
  inheritance).
- No CSS color names — hex only (`#RGB` / `#RRGGBB` / `#RRGGBBAA`).
- No invented fields. Unknown fields are ignored by default; pass
  `validate --strict` (or `validate_spec(..., strict=True)`) to reject them
  with an `unknown_field` error.
- Rectangle-based only. Not for free-form glyph placement.

## Reference

- Full schema: `pailow schema --pretty`
- All commands: `pailow --help`
- Example specs: `examples/gallery/`
- Drop-in prompt: `docs/prompt.md`
