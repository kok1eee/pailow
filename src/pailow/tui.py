"""TUI editor (Step 4) for pailow specs.

矢印キーで選択中の box の x/y を ±10 移動、Tab で box 切替、s で保存、q で終了。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from pailow.box import Box, Canvas
from pailow.layout import load_spec_from_mapping
from pailow.render import render_from_mapping


class PailowTUI(App):
    """spec.json を矢印キーで編集する TUI。"""

    CSS = """
    Screen {
        layout: horizontal;
    }
    #left {
        width: 40%;
        border: solid green;
        padding: 1;
    }
    #right {
        width: 60%;
        border: solid blue;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("up", "move(0, -10)", "y -= 10"),
        Binding("down", "move(0, 10)", "y += 10"),
        Binding("left", "move(-10, 0)", "x -= 10"),
        Binding("right", "move(10, 0)", "x += 10"),
        Binding("tab", "next_box", "Next box"),
        Binding("shift+tab", "prev_box", "Prev box"),
        Binding("s", "save", "Save"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        spec_path: Path,
        image: Optional[Path] = None,
        output: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.spec_path = spec_path
        self.image = image
        self.output = output
        self.spec_data: dict = {}
        self.canvas: Optional[Canvas] = None
        self.boxes: list[Box] = []
        self.selected_idx = 0
        self.dirty = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            with Vertical(id="left"):
                yield Static("Loading...", id="info")
            with Vertical(id="right"):
                yield Static("Preview", id="preview")
        yield Footer()

    def on_mount(self) -> None:
        self.reload_spec()
        self.refresh_ui()

    def reload_spec(self) -> None:
        self.spec_data = json.loads(self.spec_path.read_text(encoding="utf-8"))
        self.canvas, self.boxes = load_spec_from_mapping(self.spec_data)

    def action_next_box(self) -> None:
        if self.boxes:
            self.selected_idx = (self.selected_idx + 1) % len(self.boxes)
            self.refresh_ui()

    def action_prev_box(self) -> None:
        if self.boxes:
            self.selected_idx = (self.selected_idx - 1) % len(self.boxes)
            self.refresh_ui()

    def action_move(self, dx: int, dy: int) -> None:
        if not self.boxes:
            return
        box_data = self.spec_data["boxes"][self.selected_idx]
        box_data["x"] = max(0, int(box_data.get("x", 0)) + dx)
        box_data["y"] = max(0, int(box_data.get("y", 0)) + dy)
        self.dirty = True
        self.reload_spec()
        self.refresh_ui()

    def action_save(self) -> None:
        self.spec_path.write_text(
            json.dumps(self.spec_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.dirty = False
        self.notify(f"Saved: {self.spec_path}")

    def refresh_ui(self) -> None:
        info = self.query_one("#info", Static)
        if self.boxes:
            b = self.boxes[self.selected_idx]
            text_preview = b.text[:40]
            if len(b.text) > 40:
                text_preview += "..."
            info.update(
                f"Box {self.selected_idx + 1}/{len(self.boxes)}  "
                f"{'*' if self.dirty else ''}\n"
                f"id:   {b.id}\n"
                f"x:    {b.x}\n"
                f"y:    {b.y}\n"
                f"w:    {b.w}\n"
                f"h:    {b.h}\n"
                f"size: {b.size}\n"
                f"fit:  {b.fit}\n"
                f"text: {text_preview!r}"
            )
        else:
            info.update("(no boxes)")

        if self.output is not None:
            try:
                background = PILImage.open(self.image) if self.image else None
                result = render_from_mapping(self.spec_data, background=background)
                result.save(self.output)
                preview = self.query_one("#preview", Static)
                preview.update(
                    f"preview saved: {self.output}\n"
                    f"size: {self.canvas.width}x{self.canvas.height}"
                )
            except Exception as e:
                self.notify(f"render error: {e}", severity="error")