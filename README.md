# pailow

Container-based text overlay CLI for images. The bridge between Pillow and LLMs —
AI emits structured intent, pailow renders it pixel-perfect.

> Why? When an AI is told "put 'SALE' in the top-left, white, bold," it roughly
> places text. When pailow does it, the pixels are exact. Let AI handle
> *what* and *why*; let pailow handle *where* and *how*.

## Install

```bash
pip install -e .
# or, with uv:
uv sync
```

Dependencies: Python 3.10+, Pillow, Typer, Rich, Watchdog, Textual. A system
font is auto-discovered (sans via `fc-match`, then common paths) when
`Box.font` is omitted.

## Quickstart

```bash
# 1. Generate a starter spec
pailow new layout.json

# 2. Check whether text fits each box (no rendering)
pailow fit layout.json

# 3. Render onto an image
pailow render layout.json -i bg.png -o out.png

# 4. Debug layout: overlay box outlines
pailow render layout.json -i bg.png -o out_debug.png --draw-boxes

# 5. Open in your system viewer after rendering
pailow render layout.json -i bg.png -o out.png --open
```

## Concept: Box

A *box* is a rectangular container with position, size, and optional padding.
Text is flowed into the inner area (size minus `pad * 2`).

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
      "pad": 8,
      "text": "50% OFF EVERYTHING",
      "size": 128,
      "color": "#FFFFFF",
      "align": "left",
      "valign": "middle",
      "fit": "shrink",
      "line_spacing": 1.0
    }
  ]
}
```

### Box fields

| Field            | Required | Default     | Description                                          |
|------------------|----------|-------------|------------------------------------------------------|
| `id`             | yes      | —           | Unique ID; referenced in dry-run output.             |
| `x`, `y`         | yes      | —           | Top-left origin, in pixels.                          |
| `w`, `h`         | yes      | —           | Box size, in pixels.                                 |
| `text`           | no       | `""`        | Text to render. Empty text skips the box.            |
| `pad`            | no       | `0`         | Inner padding in pixels (CSS-style).                 |
| `font`           | no       | system     | Path to TTF/OTF. Omit = system sans if available.    |
| `size`           | no       | `24`        | Font size in points.                                 |
| `color`          | no       | `#FFFFFF`   | `#RGB`, `#RRGGBB`, or `#RRGGBBAA`.                   |
| `align`          | no       | `left`      | `left` / `center` / `right`.                         |
| `valign`         | no       | `middle`    | `top` / `middle` / `bottom`.                         |
| `fit`            | no       | `wrap`      | `wrap` / `shrink` / `truncate`.                      |
| `line_spacing`   | no       | `1.2`       | Line height multiplier.                              |
| `min_size`       | no       | `None`      | Floor for font size when `fit: shrink`.              |
| `char_size_steps`| no       | `None`      | `[[max_chars, size], ...]` — char-count-based sizing.|
| `parent`         | no       | `None`      | Box id to inherit fields from (spec inheritance).    |

### fit strategies

- **`wrap`** (default): word-based wrapping. Multiple lines allowed.
- **`shrink`**: decrement font size by 1pt until the wrapped text fits.
  Combine with `min_size` to stop shrinking early.
- **`truncate`**: single line, appends `…` if overflow.
- **`char_size_steps`**: pick font size by character count
  (e.g. `[[6, 64], [12, 48], [20, 32]]`) — good for variable-length content.

## CLI commands

| Command | Purpose | Key options |
|---------|---------|-------------|
| `new <out>`            | Generate a starter JSON spec | — |
| `fit <spec>`           | Fit analysis without rendering (exit 2 on overflow) | `--json` machine-readable diagnostics |
| `render <spec>`        | Render the spec onto an image | `-i/--image`, `-o/--out`, `--draw-boxes`, `--open` |
| `schema`               | Emit the JSON Schema (draft 2020-12) | `--pretty` |
| `validate <spec>`      | Validate a spec (exit 0 valid / 1 invalid) | `--json`, `--preflight`, `--strict` |
| `prompt`               | Emit an LLM system-prompt guide for pailow | `--detail` |
| `gallery`              | Few-shot example specs for LLM prompting | `--list`, `--show <id>`, `-o` |
| `watch <spec>`         | Auto re-render when the spec changes | `-o`, `--debounce`, `--inline`, `--history` |
| `tui <spec>`           | Arrow-key TUI editor for box positions | `-i`, `-o` |
| `diff <a> <b>`         | Unified spec diff or image pixel diff | `--json` |
| `history`              | List / view renders saved by `watch --history` | `--list`, `--show <id>` |
| `batch <spec>`         | Apply one spec to many images | `--pattern <glob>`, `-o`, `--prefix` |

See `pailow --help` for per-command details.

## Workflow

```bash
# 1. Draft the spec (or ask an LLM to draft it)
$EDITOR layout.json

# 2. Check fit before rendering
pailow fit layout.json
# OK / OVER with line count, used size, capacity per box

# 3. Render
pailow render layout.json -i bg.png -o v1.png

# 4. Inspect layout structure
pailow render layout.json -i bg.png -o v1_debug.png --draw-boxes

# 5. Iterate on the spec; goto 2
```

Interactive iteration: `pailow watch layout.json -i bg.png -o out.png --inline`
re-renders on every save and can preview inline in kitty / iTerm2 / WezTerm.
`pailow tui layout.json` lets you drag boxes with arrow keys.

## AI integration

pailow is built for LLM tool-use loops. The pipeline:

```bash
pailow schema              # 1. canonical JSON Schema → tool definition
pailow validate s.json --json  # 2. structured errors {code, path, fix}
pailow fit s.json --json   # 3. fit diagnostics {fits, lines, capacity, ...}
pailow prompt --detail     # 4. drop-in system prompt guide
pailow gallery --list      # 5. few-shot examples for in-context learning
```

- `validate --json` returns `{valid, level, errors[]}` where each error carries
  a stable `code`, a JSON Pointer `path`, and an action-oriented `fix`.
- `fit --json` returns per-box diagnostics — the quality signal an LLM needs
  to know *why* a layout overflowed.
- `schema` is the canonical spec contract; runtime validation depends on
  field names being exact, so generate tool schemas from it.
- `gallery` ships curated, validated few-shot specs (poster, quote, banner,
  product card, repair cycle, ...) that LLMs can imitate.

For LLM-facing guidance see **[SKILL.md](SKILL.md)** (full reference) and
**[docs/prompt.md](docs/prompt.md)** (condensed drop-in prompt).

### Example prompt

> You are a layout assistant. Given this `pailow` spec (JSON) and the fit
> diagnostics (JSON), edit the spec so that every box has `fits: true`.
> Keep `fit: shrink` for the title, change its `text` to "70% OFF", and
> pick a warm color (`#FFD86B`-ish) for the body text that matches a dark
> background. Return only the updated spec JSON.

## Examples

`examples/sale.json` + `examples/bg.png` produce a 4-box poster
(eyebrow / title / body / CTA) with different fit strategies:

```bash
python scripts/generate_bg.py
pailow render examples/sale.json -i examples/bg.png -o out.png
```

`examples/gallery/` contains curated few-shot specs with per-example
backgrounds and a contact sheet — see
[examples/gallery/README.md](examples/gallery/README.md). Regenerate the
background with `scripts/generate_bg.py`; rebuild the gallery with
`scripts/build_gallery.py` (validates + analyzes + renders every example,
exits non-zero on any regression).

## Development

```bash
uv run pytest          # test suite (tests/test_*.py)
uv run pailow --help   # run from source
```

## Architecture

```
src/pailow/
├── box.py        # Box / Canvas dataclasses, color parsing (no Pillow)
├── layout.py     # JSON spec → Box/Canvas, spec inheritance
├── render.py     # Pillow renderer: analyze() (measure) + render() (draw)
├── schema.py     # JSON Schema (draft 2020-12) generation
├── errors.py     # SpecError: {code, path, value, expected, fix}
├── cli.py        # Typer commands (thin wrapper)
├── diff.py       # spec / image diffing
├── gallery.py    # curated few-shot specs for LLM prompting
├── history.py    # watch render history (.pailow/history)
├── inherit.py    # spec inheritance / extends resolution
├── nesting.py    # nested-box layout
├── presets.py    # typography presets (shadow, outline, ...)
├── tui.py        # Textual TUI editor
└── __main__.py   # python -m pailow
```

- `box.py` has no Pillow dependency; pure data model, easy to test.
- `render.py` separates measurement (`analyze`) from drawing (`render`).
- `cli.py` is a thin wrapper that wires the modules together.
- `errors.py` + `schema.py` are the LLM-facing contract: stable error codes,
  JSON Pointers, and an exact machine-readable schema.

## License

MIT
