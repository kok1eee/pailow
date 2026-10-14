from __future__ import annotations

import base64
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from PIL import Image
from rich.console import Console
from rich.table import Table

from pailow import __version__, build_schema, schema_version, validate_spec
from pailow.diff import diff_images, diff_specs
from pailow.errors import SpecError
from pailow.gallery import GALLERY_IDS, get_gallery_item, render_gallery_example
from pailow.history import get_history_dir, get_history_entry, list_history, save_to_history
from pailow.layout import load_spec
from pailow.render import analyze, render
from pailow.tui import PailowTUI

app = typer.Typer(
    name="pailow",
    help="pailow — container-based text overlay CLI for images. Bridge between Pillow and LLMs.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


# Step 3 (LLM に優しく) — canonical prompt snippets
SHORT_PROMPT = """You are generating pailow JSON specs.

pailow renders text overlays on images using Pillow.

A spec is a JSON object:
{
  "canvas": {"width": 1200, "height": 800, "background": "#FFFFFF"},
  "boxes": [
    {
      "id": "title",
      "x": 40, "y": 40, "w": 1120, "h": 100,
      "text": "Hello world",
      "size": 64,
      "color": "#FFD86B",
      "align": "left",
      "valign": "middle",
      "fit": "shrink"
    }
  ]
}

fit: wrap | shrink | truncate
align: left | center | right
valign: top | middle | bottom
color: #RGB / #RRGGBB / #RRGGBBAA (no CSS names, hash prefix required)

Before returning: run `pailow validate spec.json --json` to check.
Use --json output to get parseable error messages.
"""


DETAILED_PROMPT = """You are generating pailow JSON specs — text overlays rendered on top of images.

# Schema

canvas (object):
  - width (int, > 0)
  - height (int, > 0)
  - background (#RGB / #RRGGBB / #RRGGBBAA, default "#FFFFFF")

boxes (array, at least 1):
  - id (string, unique, required)
  - x, y (int, >= 0, required)
  - w, h (int, > 0, required)
  - text (string, default "", empty = skip)
  - pad (int, >= 0, default 0)
  - font (string path or null, default = system sans)
  - size (int, > 0, default 24)
  - color (#RGB / #RRGGBB, default "#FFFFFF")
  - align: left | center | right (default left)
  - valign: top | middle | bottom (default middle)
  - fit: wrap | shrink | truncate (default wrap)
  - line_spacing (number > 0, default 1.2)
  - min_size (int >= 1, optional, only meaningful with fit=shrink)
  - char_size_steps (array of [max_chars, size] pairs, optional)

# Common mistakes

- color without # prefix (e.g. "FFFFFF" → must be "#FFFFFF")
- align="middle" → only valid for valign; align accepts left/center/right
- size: 0 or negative
- w or h: 0 or negative
- duplicate box id
- x/y/w/h exceeding canvas

# Validation

Run `pailow validate spec.json` before returning the spec.
Use `--json` for machine-readable output.

# Few-shot references

`pailow gallery --list` shows all verified examples.
`pailow gallery --show <id>` prints the spec for that id.
`pailow gallery --show <id> -o out.png` renders it as a PNG.
"""


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    pass


@app.command("new")
def new_cmd(
    output: Path = typer.Argument(..., help="Path to write starter spec"),
) -> None:
    """Generate a starter JSON spec."""
    starter = {
        "canvas": {"width": 1200, "height": 800, "background": "#1A1A1A"},
        "boxes": [
            {
                "id": "eyebrow",
                "x": 40,
                "y": 40,
                "w": 600,
                "h": 40,
                "pad": 0,
                "text": "LIMITED TIME",
                "size": 28,
                "color": "#FFD86B",
                "align": "left",
                "valign": "top",
                "fit": "wrap",
                "line_spacing": 1.2,
            },
            {
                "id": "title",
                "x": 40,
                "y": 90,
                "w": 1120,
                "h": 240,
                "pad": 8,
                "text": "50% OFF EVERYTHING",
                "size": 128,
                "color": "#FFFFFF",
                "align": "left",
                "valign": "middle",
                "fit": "shrink",
                "line_spacing": 1.0,
            },
            {
                "id": "body",
                "x": 40,
                "y": 360,
                "w": 800,
                "h": 240,
                "pad": 0,
                "text": "Shop our entire collection. Discount auto-applied at checkout. No code needed.",
                "size": 32,
                "color": "#E5E5E5",
                "align": "left",
                "valign": "top",
                "fit": "wrap",
                "line_spacing": 1.4,
            },
            {
                "id": "cta",
                "x": 40,
                "y": 680,
                "w": 360,
                "h": 80,
                "pad": 0,
                "text": "Shop now",
                "size": 48,
                "color": "#1A1A1A",
                "align": "center",
                "valign": "middle",
                "fit": "truncate",
                "line_spacing": 1.0,
            },
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(starter, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    typer.echo(f"wrote starter spec: {output}")


@app.command("fit")
def fit_cmd(
    spec: Path = typer.Argument(..., help="Path to JSON spec"),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """Analyze whether text fits each box (no rendering)."""
    from PIL import Image, ImageDraw

    try:
        canvas, boxes = load_spec(spec)
    except (FileNotFoundError, ValueError) as e:
        err_console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=1)

    dummy = Image.new("RGB", (canvas.width, canvas.height))
    draw = ImageDraw.Draw(dummy)
    results = [analyze(box, draw) for box in boxes]

    if json_output:
        out = {
            "canvas": {"width": canvas.width, "height": canvas.height},
            "boxes": results,
        }
        typer.echo(json.dumps(out, indent=2, ensure_ascii=False))
        return

    table = Table(title=f"fit: {spec}", show_lines=False)
    table.add_column("box", style="bold")
    table.add_column("fits", justify="center")
    table.add_column("lines", justify="right")
    table.add_column("chars", justify="right")
    table.add_column("used (w×h)", justify="right")
    table.add_column("capacity", justify="right")
    table.add_column("font", justify="right")
    table.add_column("strategy", justify="center")

    all_fit = True
    for r in results:
        fits_str = "[green]OK[/green]" if r["fits"] else "[red]OVER[/red]"
        used = f"{r['used_w']}x{r['used_h']}"
        table.add_row(
            r["box_id"],
            fits_str,
            str(r["lines"]),
            str(r["chars"]),
            used,
            str(r["capacity"]),
            str(r["font_size"]),
            r["strategy"],
        )
        if not r["fits"]:
            all_fit = False

    console.print(table)
    if not all_fit:
        raise typer.Exit(code=2)


@app.command("render")
def render_cmd(
    spec: Path = typer.Argument(..., help="Path to JSON spec"),
    image: Optional[Path] = typer.Option(
        None, "-i", "--image", help="Background image path."
    ),
    output: Path = typer.Option(..., "-o", "--out", help="Output image path."),
    draw_boxes_flag: bool = typer.Option(
        False, "--draw-boxes", help="Overlay box outlines for debugging."
    ),
    open_after: bool = typer.Option(
        False, "--open", help="Open the output image after rendering."
    ),
) -> None:
    """Render the spec onto an image."""
    from PIL import Image

    try:
        canvas, boxes = load_spec(spec)
    except (FileNotFoundError, ValueError) as e:
        err_console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=1)

    background: Optional[Image.Image] = None
    if image is not None:
        if not image.exists():
            err_console.print(f"[red]error:[/red] background image not found: {image}")
            raise typer.Exit(code=1)
        background = Image.open(image)

    try:
        result = render(canvas, boxes, background=background, draw_boxes=draw_boxes_flag)
    except (FileNotFoundError, ValueError) as e:
        err_console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=1)

    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    typer.echo(f"wrote: {output}")

    if open_after:
        _open_file(output)


@app.command("inspect")
def inspect_cmd(
    spec: Path = typer.Argument(..., help="Path to JSON spec"),
    image: Optional[Path] = typer.Option(
        None, "-i", "--image", help="Background image path."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
    annotate_out: Optional[Path] = typer.Option(
        None, "--annotate", help="Write an annotated PNG showing intended vs painted ink."
    ),
    fix: bool = typer.Option(
        False, "--fix", help="Apply auto-fixable suggestions and write a fixed spec."
    ),
    fix_out: Optional[Path] = typer.Option(
        None, "--fix-out", help="Where to write the fixed spec (default: <spec>.fixed.json)."
    ),
    loop: int = typer.Option(
        0, "--loop", help="Iterate measure -> fix up to N times (max 8)."
    ),
) -> None:
    """Measure the rendered pixels and report where the ink really is.

    Unlike 'fit' (which predicts from font metrics), this draws the image and
    measures the actual ink, so it can tell you how far a box is off.
    """
    from PIL import Image

    from pailow.annotate import annotate as annotate_report
    from pailow.inspect import inspect_canvas
    from pailow.layout import load_spec_from_mapping
    from pailow.suggest import apply_suggestions, collect_auto, spec_hash

    if loop < 0:
        err_console.print("[red]error:[/red] --loop must be >= 0")
        raise typer.Exit(code=1)
    max_loops = min(loop, 8)
    if loop > 8:
        err_console.print("[yellow]warning:[/yellow] --loop clamped to 8")

    try:
        raw = json.loads(spec.read_text(encoding="utf-8"))
    except FileNotFoundError:
        err_console.print(f"[red]error:[/red] spec not found: {spec}")
        raise typer.Exit(code=1)
    except json.JSONDecodeError as e:
        err_console.print(f"[red]error:[/red] invalid JSON: {e}")
        raise typer.Exit(code=1)

    background: Optional[Image.Image] = None
    if image is not None:
        if not image.exists():
            err_console.print(f"[red]error:[/red] background image not found: {image}")
            raise typer.Exit(code=1)
        background = Image.open(image)

    def run_once(current: dict) -> tuple[dict, Image.Image]:
        canvas, boxes = load_spec_from_mapping(current)
        return inspect_canvas(canvas, boxes, background)

    try:
        report, rendered = run_once(raw)
    except (FileNotFoundError, ValueError) as e:
        err_console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=1)

    passes = max_loops
    if fix and passes == 0:
        passes = 1

    data = raw
    iterations: list[dict] = []
    seen: dict[str, int] = {}

    for i in range(passes):
        auto = collect_auto(report)
        if not auto:
            break
        candidate = apply_suggestions(data, auto)
        digest = spec_hash(candidate)
        if digest in seen:
            iterations.append({"n": i + 1, "applied": 0, "stopped": "cycle"})
            break
        seen[digest] = i + 1
        iterations.append({"n": i + 1, "applied": len(auto)})
        data = candidate
        try:
            report, rendered = run_once(data)
        except (FileNotFoundError, ValueError) as e:
            err_console.print(f"[red]error:[/red] {e}")
            raise typer.Exit(code=1)

    report["iterations"] = iterations

    if annotate_out is not None:
        annotate_out.parent.mkdir(parents=True, exist_ok=True)
        annotate_report(rendered, report).save(annotate_out)
        # stderr so `--json` keeps stdout machine-readable
        err_console.print(f"wrote: {annotate_out}")

    remaining_auto = len(collect_auto(report))
    has_problem = any(
        finding["severity"] in ("error", "warning")
        for record in report["boxes"]
        for finding in record["findings"]
    )

    if fix:
        out_path = fix_out or spec.with_name(spec.stem + ".fixed.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        err_console.print(f"wrote: {out_path}")

    if json_output:
        typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_inspect_table(report, spec)

    if fix:
        raise typer.Exit(code=0 if not (has_problem or remaining_auto) else 2)
    raise typer.Exit(code=0 if not has_problem else 1)


def _print_inspect_table(report: dict, spec: Path) -> None:
    table = Table(title=f"inspect: {spec}")
    table.add_column("box", style="bold")
    table.add_column("ink", justify="center")
    table.add_column("overflow", justify="left")
    table.add_column("contrast", justify="right")
    table.add_column("findings", justify="left")
    for record in report.get("boxes", []):
        ink = "[green]ok[/green]" if record["visible"] else "[red]none[/red]"
        overflow = ", ".join(f"{k}+{v}" for k, v in (record.get("overflow") or {}).items())
        contrast = "-" if record.get("contrast") is None else f"{record['contrast']:.1f}"
        findings = ", ".join(
            f"{f['code']}" for f in record.get("findings", []) if f["severity"] != "info"
        )
        table.add_row(record["box_id"], ink, overflow or "-", contrast, findings or "-")
    console.print(table)
    summary = report.get("summary", {})
    console.print(
        f"errors={summary.get('errors', 0)} warnings={summary.get('warnings', 0)} "
        f"infos={summary.get('infos', 0)} converged={summary.get('converged', False)}"
    )
    for record in report.get("boxes", []):
        for item in record.get("suggestions", []):
            marker = "auto" if item.get("auto") else "manual"
            console.print(
                f"[yellow]{marker}[/yellow] {record['box_id']}: {item['action']} "
                f"{item.get('params') or ''} — {item['reason']}"
            )


@app.command("schema")
def schema_cmd(
    pretty: bool = typer.Option(
        False, "--pretty", help="Pretty-print the JSON Schema."
    ),
) -> None:
    """Emit the pailow JSON Schema (draft 2020-12) on stdout."""
    doc = build_schema()
    doc["x-pailow-version"] = schema_version()
    indent = 2 if pretty else None
    typer.echo(json.dumps(doc, indent=indent, ensure_ascii=False))


@app.command("validate")
def validate_cmd(
    spec: Path = typer.Argument(..., help="Path to JSON spec"),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
    preflight: bool = typer.Option(
        False,
        "--preflight",
        help="Also check environment-level constraints (font files exist, etc.).",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Reject spec with unknown fields (default: allow unknown fields).",
    ),
) -> None:
    """Validate a spec without rendering. Exits 0 if valid, 1 if invalid."""
    import json as _json

    level = "preflight" if preflight else "schema"

    if not spec.exists():
        err_obj = SpecError(
            code="spec_not_found",
            path="",
            value=str(spec),
            expected="existing file path",
            fix=f"spec file {spec!s} does not exist",
        )
        if json_output:
            typer.echo(
                _json.dumps(
                    {"valid": False, "level": level, "errors": [err_obj.to_dict()]},
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            err_console.print(f"[red]error:[/red] {err_obj.message}")
        raise typer.Exit(code=1)

    try:
        data = _json.loads(spec.read_text(encoding="utf-8"))
    except _json.JSONDecodeError as e:
        err_obj = SpecError(
            code="invalid_json",
            path="",
            value=str(e),
            expected="valid JSON",
            fix=f"file is not valid JSON: {e.msg} at line {e.lineno} column {e.colno}",
        )
        if json_output:
            typer.echo(_json.dumps({"valid": False, "errors": [err_obj.to_dict()]}, indent=2))
        else:
            err_console.print(f"[red]error:[/red] {err_obj.message}")
        raise typer.Exit(code=1)

    errors = validate_spec(data, level=level, strict=strict)

    if json_output:
        typer.echo(
            _json.dumps(
                {
                    "valid": not errors,
                    "level": level,
                    "errors": [e.to_dict() for e in errors],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if not errors:
            console.print(f"[green]OK[/green] {spec}")
            return
        for e in errors:
            loc = f"[bold]{e.path}[/bold] " if e.path else ""
            console.print(
                f"[red]{e.code}[/red] {loc}{e.fix}  "
                f"[dim](expected: {e.expected})[/dim]"
            )

    if errors:
        raise typer.Exit(code=1)


@app.command("prompt")
def prompt_cmd(
    detail: bool = typer.Option(
        False,
        "--detail",
        help="Include schema, common mistakes, and references to the few-shot gallery.",
    ),
) -> None:
    """LLM の system prompt に貼るための pailow ガイドを吐く。"""
    typer.echo(DETAILED_PROMPT if detail else SHORT_PROMPT)


@app.command("gallery")
def gallery_cmd(
    list_ids: bool = typer.Option(
        False, "--list", help="List available few-shot example IDs."
    ),
    show: Optional[str] = typer.Option(
        None,
        "--show",
        help="Print the JSON spec for the given gallery id (or render to -o).",
    ),
    image: Optional[Path] = typer.Option(
        None, "-i", "--image", help="Background image path (only with --show)."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--out", help="Render the example to this PNG (only with --show)."
    ),
) -> None:
    """Few-shot gallery: LLM に渡す検証済みサンプル集 (Step 3)。"""
    if list_ids:
        for item_id in GALLERY_IDS:
            typer.echo(item_id)
        return

    if show is None:
        err_console.print("[red]error:[/red] pass --list or --show <id>")
        raise typer.Exit(code=1)

    try:
        item = get_gallery_item(show)
    except KeyError as e:
        err_console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=1)

    if output is None:
        # デフォルトは spec を JSON で出力
        typer.echo(json.dumps(item["spec"], indent=2, ensure_ascii=False))
        return

    background = None
    if image is not None:
        if not image.exists():
            err_console.print(f"[red]error:[/red] background image not found: {image}")
            raise typer.Exit(code=1)
        background = Image.open(image)

    try:
        result = render_gallery_example(show, background=background)
    except Exception as e:
        err_console.print(f"[red]error:[/red] failed to render gallery example: {e}")
        raise typer.Exit(code=1)

    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    typer.echo(f"wrote: {output}")


def _render_one_to_output(
    spec: Path, image: Optional[Path], output: Path
) -> None:
    """watch 用ヘルパー: spec を読み込んで 1 枚レンダリングして保存する。"""
    from pailow.box import Canvas
    from pailow.layout import load_spec

    canvas, boxes = load_spec(spec)
    background: Optional[Image.Image] = None
    if image is not None:
        if not image.exists():
            raise FileNotFoundError(f"background image not found: {image}")
        background = Image.open(image)
    if isinstance(canvas, Canvas):
        result = render(canvas, boxes, background=background)
    else:  # pragma: no cover -- defensive
        result = render(canvas, boxes)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)


def _detect_inline_image_terminal() -> Optional[str]:
    """ターミナルがインライン画像表示に対応していれば識別子を返す。

    対応:
    - wezterm (env: WEZTERM_PANE)
    - kitty (env: TERM=xterm-kitty)
    - iTerm2 (env: TERM_PROGRAM=iTerm.app)
    """
    if os.environ.get("WEZTERM_PANE"):
        return "wezterm"
    if os.environ.get("TERM") == "xterm-kitty":
        return "kitty"
    if os.environ.get("TERM_PROGRAM") == "iTerm.app":
        return "iterm"
    return None


def _inline_preview(path: Path, terminal: str) -> None:
    """ターミナル種別に応じて画像を表示する。

    - kitty:  kitty +kitten icat サブプロセス
    - wezterm / iterm: OSC 1337 escape sequence でインライン表示
    - その他: パスのみ出力
    """
    if terminal == "kitty":
        kitty = shutil_which("kitty")
        if kitty:
            subprocess.run([kitty, "+kitten", "icat", str(path)])
        else:
            err_console.print(
                f"[yellow]warning:[/yellow] kitty binary not found; image at {path}"
            )
        return

    if terminal in ("iterm", "wezterm"):
        data = path.read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        sys.stdout.write(
            f"\033]1337;File=inline=1;preserveAspectRatio=1;size={len(data)}:"
            f"{encoded}\a"
        )
        sys.stdout.flush()
        return

    err_console.print(f"[dim](image: {path})[/dim]")


@app.command("watch")
def watch_cmd(
    spec: Path = typer.Argument(..., help="Path to JSON spec to watch."),
    image: Optional[Path] = typer.Option(
        None, "-i", "--image", help="Background image path."
    ),
    output: Path = typer.Option(..., "-o", "--out", help="Output image path."),
    debounce_ms: int = typer.Option(
        200, "--debounce", help="Debounce milliseconds (skip rapid duplicate events)."
    ),
    inline: bool = typer.Option(
        False, "--inline", help="Update inline image preview in supported terminals."
    ),
    history: bool = typer.Option(
        False, "--history", help="Save each render to history (.pailow/history)."
    ),
) -> None:
    """spec の変更を検知して自動で再レンダリングする。

    エディタで spec.json を保存するたびに <output> を上書きする。
    Ctrl+C で停止。
    """
    import time

    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    terminal = _detect_inline_image_terminal() if inline else None

    class _Handler(FileSystemEventHandler):
        def __init__(self) -> None:
            self._last_render = 0.0

        def on_modified(self, event) -> None:
            try:
                if Path(event.src_path).resolve() != spec.resolve():
                    return
            except OSError:
                return
            now = time.monotonic()
            if (now - self._last_render) * 1000 < debounce_ms:
                return
            self._last_render = now
            try:
                _render_one_to_output(spec, image, output)
                if terminal:
                    _inline_preview(output, terminal)
                if history:
                    save_to_history(output, spec_path=spec)
                console.print(f"[green]rendered[/green] {output}")
            except Exception as e:
                err_console.print(f"[red]error:[/red] {e}")

    if not spec.exists():
        err_console.print(f"[red]error:[/red] spec not found: {spec}")
        raise typer.Exit(code=1)

    # 初回レンダリング
    try:
        _render_one_to_output(spec, image, output)
        if terminal:
            _inline_preview(output, terminal)
        if history:
            save_to_history(output, spec_path=spec)
        console.print(f"[green]rendered[/green] {output}")
    except Exception as e:
        err_console.print(f"[red]error:[/red] initial render failed: {e}")
        raise typer.Exit(code=1)

    observer = Observer()
    observer.schedule(_Handler(), str(spec.parent.absolute()), recursive=False)
    observer.start()
    console.print(f"[cyan]watching[/cyan] {spec} → {output}")
    console.print("Press Ctrl+C to stop.")

    try:
        while observer.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[yellow]stopping[/yellow]")
        observer.stop()
    observer.join()


@app.command("tui")
def tui_cmd(
    spec: Path = typer.Argument(..., help="Path to JSON spec to edit."),
    image: Optional[Path] = typer.Option(
        None, "-i", "--image", help="Background image path."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--out", help="Save preview render to this path on each edit."
    ),
) -> None:
    """TUI エディタを起動して矢印キーで box 位置を調整する。"""
    if not spec.exists():
        err_console.print(f"[red]error:[/red] spec not found: {spec}")
        raise typer.Exit(code=1)

    app = PailowTUI(spec, image=image, output=output)
    app.run()


@app.command("diff")
def diff_cmd(
    left: Path = typer.Argument(..., help="Left spec or image path."),
    right: Path = typer.Argument(..., help="Right spec or image path."),
    json_output: bool = typer.Option(False, "--json", help="JSON output (image diff only)."),
) -> None:
    """2 つの spec / image の差分を表示する。

    - .json 同士 → unified diff
    - .png / .jpg 同士 → サイズ + pixel diff の統計
    - 混在 (.json と .png) → エラー
    """
    if not left.exists():
        err_console.print(f"[red]error:[/red] left not found: {left}")
        raise typer.Exit(code=1)
    if not right.exists():
        err_console.print(f"[red]error:[/red] right not found: {right}")
        raise typer.Exit(code=1)

    if left.suffix == ".json" and right.suffix == ".json":
        text = diff_specs(left, right)
        if text:
            typer.echo(text, nl=False)
        else:
            console.print("[green]specs are identical[/green]")
        return

    img_exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
    if left.suffix.lower() in img_exts and right.suffix.lower() in img_exts:
        result = diff_images(left, right)
        if json_output:
            typer.echo(json.dumps(result, indent=2))
        else:
            table = Table(title="image diff")
            table.add_column("field", style="bold")
            table.add_column("value")
            for k, v in result.items():
                table.add_row(k, str(v))
            console.print(table)
        return

    err_console.print(
        f"[red]error:[/red] cannot diff different file types: {left.suffix} vs {right.suffix}"
    )
    raise typer.Exit(code=1)


@app.command("history")
def history_cmd(
    list_all: bool = typer.Option(False, "--list", help="List history entries."),
    show: Optional[str] = typer.Option(None, "--show", help="Print path of entry id."),
    dir_: Optional[Path] = typer.Option(
        None, "--dir", help="History directory (default: .pailow/history)."
    ),
) -> None:
    """watch で保存したレンダリング履歴をリスト / 参照する。"""
    hdir = get_history_dir(dir_)

    if list_all:
        items = list_history(hdir)
        if not items:
            console.print(f"[dim](no history at {hdir})[/dim]")
            return
        table = Table(title=f"history: {hdir}")
        table.add_column("id", style="bold")
        table.add_column("size", justify="right")
        table.add_column("mtime", justify="right")
        table.add_column("has_spec", justify="center")
        from datetime import datetime as _dt

        for item in items:
            mtime = _dt.fromtimestamp(item["mtime"]).strftime("%m-%d %H:%M:%S")
            table.add_row(
                item["id"],
                f"{item['size'] // 1024}KB",
                mtime,
                "[green]yes[/green]" if item["spec"] else "[dim]no[/dim]",
            )
        console.print(table)
        return

    if show is not None:
        try:
            entry = get_history_entry(show, hdir)
        except KeyError as e:
            err_console.print(f"[red]error:[/red] {e}")
            raise typer.Exit(code=1)
        typer.echo(entry["png"])
        return

    err_console.print("[red]error:[/red] pass --list or --show <id>")
    raise typer.Exit(code=1)


@app.command("batch")
def batch_cmd(
    spec: Path = typer.Argument(..., help="Spec to apply."),
    pattern: str = typer.Option(
        ..., "--pattern", help="Glob pattern for image files (e.g. 'imgs/*.jpg')."
    ),
    output_dir: Path = typer.Option(
        ..., "-o", "--out", help="Output directory for rendered PNGs."
    ),
    prefix: str = typer.Option(
        "", "--prefix", help="Optional prefix for output filenames."
    ),
) -> None:
    """1 つの spec を複数画像に一気に適用する (Step 5: バッチ量産)。"""
    import glob as _glob

    from pailow.box import Canvas as _Canvas

    image_paths = sorted(Path(p) for p in _glob.glob(pattern))
    if not image_paths:
        err_console.print(f"[red]error:[/red] no images matched: {pattern}")
        raise typer.Exit(code=1)

    if not spec.exists():
        err_console.print(f"[red]error:[/red] spec not found: {spec}")
        raise typer.Exit(code=1)

    canvas, boxes = load_spec(spec)
    if not isinstance(canvas, _Canvas):  # pragma: no cover -- defensive
        err_console.print("[red]error:[/red] failed to load spec canvas")
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)

    for i, img_path in enumerate(image_paths, start=1):
        try:
            background = Image.open(img_path) if img_path.exists() else None
            result = render(canvas, boxes, background=background)
            out = output_dir / f"{prefix}{img_path.stem}.png"
            result.save(out)
            console.print(
                f"[green]{i}/{len(image_paths)}[/green] {img_path.name} \u2192 {out.name}"
            )
        except Exception as e:
            err_console.print(f"[red]error:[/red] {img_path}: {e}")


def _open_file(path: Path) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
        elif system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            opener = "xdg-open"
            if shutil_which(opener):
                subprocess.Popen([opener, str(path)])
            else:
                err_console.print(
                    f"[yellow]warning:[/yellow] no opener found; output at {path}"
                )
    except OSError as e:
        err_console.print(f"[yellow]warning:[/yellow] could not open image: {e}")


def shutil_which(name: str) -> Optional[str]:
    import shutil

    return shutil.which(name)


if __name__ == "__main__":
    app()
