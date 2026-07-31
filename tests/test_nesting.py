"""Step 5: box nesting (parent) のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from pailow.layout import load_spec


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestBoxNesting:
    def test_no_parent_passthrough(self, tmp_path):
        spec_path = _write(
            tmp_path / "spec.json",
            {
                "canvas": {"width": 200, "height": 100},
                "boxes": [
                    {"id": "a", "x": 10, "y": 10, "w": 100, "h": 50, "text": "A"},
                    {"id": "b", "x": 10, "y": 60, "w": 100, "h": 30, "text": "B"},
                ],
            },
        )
        canvas, boxes = load_spec(spec_path)
        assert [b.id for b in boxes] == ["a", "b"]
        assert boxes[0].x == 10
        assert boxes[1].y == 60

    def test_parent_offset_basic(self, tmp_path):
        spec_path = _write(
            tmp_path / "spec.json",
            {
                "canvas": {"width": 400, "height": 300},
                "boxes": [
                    {"id": "card", "x": 100, "y": 100, "w": 200, "h": 100, "pad": 20},
                    {"id": "title", "parent": "card", "x": 0, "y": 0, "w": 100, "h": 50, "text": "T"},
                ],
            },
        )
        canvas, boxes = load_spec(spec_path)
        title = next(b for b in boxes if b.id == "title")
        # card の pad 20px 内側 (120, 120) を起点とする
        assert title.x == 120
        assert title.y == 120
        # 解決後は parent は None
        assert title.parent is None

    def test_parent_missing_errors(self, tmp_path):
        spec_path = _write(
            tmp_path / "spec.json",
            {
                "canvas": {"width": 400, "height": 300},
                "boxes": [
                    {"id": "title", "parent": "missing", "x": 0, "y": 0, "w": 50, "h": 50, "text": "T"},
                ],
            },
        )
        with pytest.raises(Exception) as exc_info:
            load_spec(spec_path)
        # SpecError.code == "invalid_parent" を含むことを確認
        assert "invalid_parent" in str(exc_info.value) or "parent" in str(exc_info.value).lower()

    def test_parent_pad_too_large_box_validation(self, tmp_path):
        """親の pad が大きすぎる場合、Box 構築時に ValueError。"""
        spec_path = _write(
            tmp_path / "spec.json",
            {
                "canvas": {"width": 200, "height": 200},
                "boxes": [
                    {"id": "card", "x": 0, "y": 0, "w": 30, "h": 30, "pad": 20},  # pad > w/2
                    {"id": "child", "parent": "card", "x": 0, "y": 0, "w": 10, "h": 10},
                ],
            },
        )
        with pytest.raises(Exception) as exc_info:
            load_spec(spec_path)
        # pad エラーが優先で発生する (Box の __post_init__ で弾かれる)
        msg = str(exc_info.value).lower()
        assert "pad" in msg or "larger" in msg


class TestSmartColor:
    """Step 5: color: auto が背景の輝度に応じて 白/黒 を選ぶ。"""

    def test_dark_background_white_text(self):
        from pailow.render import _auto_text_color

        from pailow.box import Box, Canvas
        img = Image.new("RGB", (200, 200), (0, 0, 0))  # 真っ黒
        box = Box(id="t", x=0, y=0, w=200, h=200)
        color = _auto_text_color(img, box)
        # 暗背景 → 白文字
        assert color == (255, 255, 255, 255)

    def test_bright_background_black_text(self):
        from pailow.render import _auto_text_color

        from pailow.box import Box
        img = Image.new("RGB", (200, 200), (255, 255, 255))  # 真っ白
        box = Box(id="t", x=0, y=0, w=200, h=200)
        color = _auto_text_color(img, box)
        # 明背景 → 黒文字
        assert color == (0, 0, 0, 255)

    def test_mid_background(self):
        from pailow.render import _auto_text_color

        from pailow.box import Box
        img = Image.new("RGB", (200, 200), (130, 130, 130))  # グレー
        box = Box(id="t", x=0, y=0, w=200, h=200)
        color = _auto_text_color(img, box)
        # 輝度 130 > 128 → 黒文字
        assert color == (0, 0, 0, 255)

    def test_render_with_auto_color(self):
        """color: auto がレンダリング時にエラーなく動作する。"""
        from pailow.box import Box, Canvas
        from pailow.render import render

        canvas = Canvas(width=200, height=100, background="#000000")
        boxes = [
            Box(id="t", x=10, y=10, w=180, h=80, text="hi", size=24, color="auto"),
        ]
        img = render(canvas, boxes)
        assert img.size == (200, 100)
        assert img.mode == "RGBA"