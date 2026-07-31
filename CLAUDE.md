# CLAUDE.md

Guidance for AI coding agents (and human contributors) working on **pailow** —
a container-based text overlay CLI. LLMs emit a structured JSON spec; pailow
renders it pixel-perfect with Pillow.

## Quick commands

```bash
uv sync                      # install deps (or: pip install -e ".[dev]")
uv run pytest                # run the test suite
uv run pailow --help         # run the CLI from source
uv run python -m pailow      # same
```

- Python 3.10+. Package is `src/`-layout, installed editable.
- Tests: `pytest` (config in `pyproject.toml`: `testpaths = ["tests"]`, `-q`).

## Architecture

```
src/pailow/
├── box.py        # Box / Canvas frozen dataclasses + parse_color. NO Pillow.
├── layout.py     # JSON spec → Box/Canvas (load_spec, load_spec_from_mapping)
├── render.py     # analyze() measures text fit; render() draws. Pillow lives here.
├── schema.py     # build_schema() → JSON Schema draft 2020-12 (LLM contract)
├── errors.py     # SpecError: {code, path, value, expected, fix}
├── cli.py        # Typer app — thin wrapper over the modules above
├── diff.py       # diff_specs (unified) / diff_images (pixel stats)
├── gallery.py    # GALLERY: curated few-shot specs (LLM few-shot set)
├── history.py    # .pailow/history — renders saved by `watch --history`
├── inherit.py    # spec inheritance / `parent` / extends resolution
├── nesting.py    # nested-box layout
├── presets.py    # typography presets
├── tui.py        # PailowTUI — Textual editor for box positioning
└── __main__.py   # python -m pailow
```

Key layering rules (do not break):

- **`box.py` must stay Pillow-free.** It is a pure data model with
  validation in `__post_init__`. Adding a Pillow import there is a regression.
- **`render.py` separates measurement from drawing**: `analyze(box, draw)`
  returns fit diagnostics; `render(canvas, boxes, ...)` draws. Keep it that way.
- **`cli.py` is thin**: commands parse args, call the library, format output.
  Business logic belongs in the modules, not in CLI handlers.
- **Public library API** is re-exported from `__init__.py` — check it before
  renaming/moving module-level functions.

## Code conventions

- Frozen `dataclasses` for the data model (`Box`, `Canvas`); input validation
  in `__post_init__` raising `ValueError` with actionable messages.
- Colors: `#RGB` / `#RRGGBB` / `#RRGGBBAA` only, parsed by `parse_color`.
- Fit strategies: `wrap` / `shrink` / `truncate` (see `box.py`), plus
  `min_size` (shrink floor) and `char_size_steps` (char-count sizing).
- `Optional[...]` typing style; `from __future__ import annotations`.
- Some module docstrings and CLI help text are in Japanese — leave existing
  ones as-is; new user-facing text can be English.
- CLI output: `rich` tables/console; errors to stderr via `err_console`,
  exit codes via `typer.Exit`.

## Public contract (do not break)

These outputs are part of the LLM-facing contract — tests depend on them:

- `pailow schema` — canonical JSON Schema (draft 2020-12). Tool definitions
  are generated from it; field names must stay exact.
- `pailow validate <spec>` — exit `0` valid / `1` invalid; `--json` emits
  `{valid, level, errors[]}` with `SpecError.to_dict()` items
  (`code`, `path`, `value`, `expected`, `fix`).
- `pailow fit --json` — per-box `{box_id, fits, lines, chars, used_w,
  used_h, capacity, font_size, strategy}`.
- `validate` collects ALL errors in one pass; don't stop at the first.

When behavior changes, update `docs/prompt.md` and `SKILL.md` (the LLM-facing
docs) in the same change.

## Testing

- One test file per module area: `test_box.py`, `test_layout.py`,
  `test_render.py`, `test_cli.py`, `test_step3.py`, `test_diff.py`,
  `test_history.py`, `test_inherit.py`, `test_nesting.py`.
- New features MUST ship with tests. `examples/gallery` doubles as a
  regression set — `scripts/build_gallery.py` validates + analyzes + renders
  every example and exits non-zero on any failure.
- The starter spec in `cli.py new_cmd` is referenced by tests; changing the
  default spec requires updating those tests.

## Do / Don't

- Do: keep `box.py` Pillow-free; keep `analyze`/`render` separate; make new
  errors go through `SpecError` with a stable `code` + `fix` hint.
- Don't: invent new spec fields without adding them to `box.py` +
  `schema.py` + docs; break the `validate`/`fit --json` output shapes;
  put logic in CLI handlers.
