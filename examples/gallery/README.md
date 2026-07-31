# pailow gallery

Curated, validated example specs. Each example pairs a natural-language
request with a working JSON spec, plus (for `06_repair`) a broken spec and
its fixed counterpart.

| file | intent | canvas | boxes | coverage |
|------|--------|--------|-------|----------|
| `01_poster.json`              | sale poster with eyebrow / title / body / CTA   | 1200×800 | 4 | shrink + wrap + truncate, multiple align/valign |
| `02_quote.json`               | centered quote card with attribution            | 1080×1080 | 3 | shrink, top valign, decorative glyph |
| `03_social_square.json`       | 1080² social post with multi-line headline      | 1080×1080 | 4 | shrink with embedded `\n`, multiple boxes |
| `04_banner.json`              | wide announcement banner, dual-column           | 1600×400 | 5 | right align, multi-region |
| `05_product_card.json`        | product info card with price / body / CTA       | 800×1000 | 5 | top valign, long body wrap, truncate |
| `06_repair_broken.json`       | intentionally broken spec for repair example    | 600×200 | 2 | css color names, duplicate id, bad enum |
| `06_repair_fixed.json`        | the same spec after the repair cycle            | 600×200 | 2 | shows the corrected form |
| `07_long_text_bottom.json`    | long disclaimer copy + bottom-anchored footer   | 1200×800 | 3 | wrap over many lines, **bottom valign**, **#RRGGBBAA** |

## Building

```bash
python scripts/build_gallery.py
```

The script:
1. Validates each spec with `pailow.validate` (schema + semantic).
2. Analyzes each spec for fit (`pailow.fit`).
3. Renders each spec onto a per-example background.
4. Composes a contact sheet at `examples/gallery/_contact_sheet.png`.

Exits non-zero if any example fails validation or fit. Run in CI to catch
regressions in the gallery (which also acts as an LLM few-shot
regression set).
