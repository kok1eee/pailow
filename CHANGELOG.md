# Changelog

## 0.3.0

### Added

- **`pailow.measure_image`** — measure an image produced by someone else,
  without drawing anything. Intended for test scripts: an external pipeline
  renders a PNG, the test asks pailow where the ink actually landed.
  - Returns the same per-box shape as `inspect` (`inner`, `painted`, `overflow`,
    `collisions`, `contrast`, `findings`) plus `suggested_adjust`
    (`dx` / `dy` / `resize_required`) for writing corrections back.
  - `background` is a text-free image of the same size; omit it to assume a
    solid `bg_color`.
  - Text color and background color are both measured from the pixels, so no
    spec colour information is required.

## 0.2.0

### Added

- **`pailow inspect`** — measures the rendered pixels instead of trusting font
  metrics. Reports, per box:
  - `overflow` — how far the actual ink crosses the inner rect, with direction
    (±2px tolerance; shorter text than the box is never an error)
  - `collision` — ink intersecting another box's ink
  - `invisible` — text set but no ink painted (usually color == background)
  - `contrast` — WCAG ratio against the measured backdrop (median of the real
    pixels, alpha composited)
  - `min_size`, `box_too_small`, `outside_canvas`, `alpha_not_blended`
- `--json` for machine consumption, `--annotate <png>` to write a debug image
  (dashed intended rect, solid measured ink, red collision fill).
- `--fix` / `--fix-out` / `--loop <n>`: applies the safe suggestions
  (`set_size`, `set_min_size`, `set_color`) and re-measures until it converges.
  Collisions and box-size problems are reported but never auto-applied.
- Python API: `inspect_spec`, `inspect_from_mapping`, `inspect_canvas`,
  `layout_box`.

### Changed

- `render()` now draws through the new `layout_box()` / `draw_layout()` pair.
  Behaviour is unchanged; the extraction makes the single layout
  implementation shareable with `inspect`, so measurement can never drift from
  rendering.

### Notes

- `fit` is unchanged. It still predicts from font metrics (no image is drawn);
  use `inspect` when you need to know what the viewer actually sees.
