from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from pailow.box import Box, Canvas
from pailow.errors import SpecError
from pailow.render import (
    analyze,
    fit_text,
    line_height,
    load_font,
    render,
    truncate_text,
    wrap_lines,
)


@pytest.fixture
def font_path() -> str:
    from pailow.render import find_default_font_path

    path = find_default_font_path()
    if not path:
        pytest.skip("no system font available")
    return path


@pytest.fixture
def font(font_path: str):
    return load_font(Box(id="x", x=0, y=0, w=10, h=10, font=font_path, size=24))


@pytest.fixture
def draw() -> ImageDraw.ImageDraw:
    img = Image.new("RGB", (500, 500))
    return ImageDraw.Draw(img)


class TestWrapLines:
    def test_empty(self, draw, font):
        assert wrap_lines(draw, "", font, 100) == [""]

    def test_single_word(self, draw, font):
        assert wrap_lines(draw, "hello", font, 100) == ["hello"]

    def test_short_text(self, draw, font):
        lines = wrap_lines(draw, "hi there", font, 1000)
        assert lines == ["hi there"]

    def test_breaks_at_word(self, draw, font):
        text = "one two three four five six seven"
        max_w = 100
        lines = wrap_lines(draw, text, font, max_w)
        assert len(lines) >= 2
        for line in lines:
            if " " in line:
                assert draw.textlength(line, font=font) <= max_w


class TestTruncate:
    def test_fits(self, draw, font):
        assert truncate_text(draw, "hi", font, 1000) == "hi"

    def test_truncates(self, draw, font):
        result = truncate_text(draw, "the quick brown fox", font, 50)
        assert result.endswith("…")
        assert draw.textlength(result, font=font) <= 50

    def test_empty(self, draw, font):
        assert truncate_text(draw, "", font, 100) == ""


class TestLineHeight:
    def test_basic(self, font):
        h = line_height(font, 1.0)
        assert h > 0
        h12 = line_height(font, 1.2)
        assert h12 > h


class TestFitText:
    def test_wrap(self, draw, font_path: str):
        box = Box(
            id="t", x=0, y=0, w=200, h=200, text="hello world", fit="wrap",
            font=font_path, size=20,
        )
        f, lines, size = fit_text(box, 200, 200, draw)
        assert size == 20
        assert lines == ["hello world"] or len(lines) >= 1

    def test_shrink(self, draw, font_path: str):
        box = Box(
            id="t", x=0, y=0, w=80, h=40, text="a very long text that won't fit",
            fit="shrink", font=font_path, size=200,
        )
        f, lines, size = fit_text(box, 80, 40, draw)
        assert size < 200
        assert len(lines) >= 1

    def test_shrink_with_min_size(self, draw, font_path: str):
        """shrink 戦略で min_size を指定すると、そのサイズ以下にはならない。"""
        box = Box(
            id="t", x=0, y=0, w=80, h=40, text="a very long text that won't fit",
            fit="shrink", font=font_path, size=200, min_size=18,
        )
        f, lines, size = fit_text(box, 80, 40, draw)
        assert size >= 18

    def test_shrink_min_size_overflow(self, draw, font_path: str):
        """min_size でも枠に収まらない場合はオーバーフローとなる (size >= min_size は保証)。"""
        box = Box(
            id="t", x=0, y=0, w=20, h=20, text="x" * 200,
            fit="shrink", font=font_path, size=120, min_size=24,
        )
        f, lines, size = fit_text(box, 20, 20, draw)
        # min_size 以上で止まる (24 以上)
        assert size >= 24

    def test_char_size_steps_short_text(self, draw, font_path: str):
        """短文は char_size_steps の最初のエントリの size で開始する。"""
        box = Box(
            id="t", x=0, y=0, w=600, h=80, text="短い",
            fit="shrink", font=font_path, size=24,
            char_size_steps=((15, 44), (50, 36)),
        )
        f, lines, size = fit_text(box, 600, 80, draw)
        assert size == 44

    def test_char_size_steps_medium_text(self, draw, font_path: str):
        """中文は2番目のエントリの size 以下に shrink される。"""
        box = Box(
            id="t", x=0, y=0, w=600, h=80, text="あ" * 30,
            fit="shrink", font=font_path, size=24,
            char_size_steps=((15, 44), (50, 36)),
        )
        f, lines, size = fit_text(box, 600, 80, draw)
        # 初期 36 から枠に収まるまで shrink (24 < size <= 36)
        assert 24 < size <= 36

    def test_char_size_steps_long_text(self, draw, font_path: str):
        """長文は box.size 以下に shrink される。"""
        box = Box(
            id="t", x=0, y=0, w=600, h=80, text="あ" * 80,
            fit="shrink", font=font_path, size=28,
            char_size_steps=((15, 44), (50, 36)),
        )
        f, lines, size = fit_text(box, 600, 80, draw)
        # 初期 28 から枠に収まるまで shrink (size <= 28)
        assert size <= 28

    def test_truncate(self, draw, font_path: str):
        box = Box(
            id="t", x=0, y=0, w=60, h=20, text="supercalifragilisticexpialidocious",
            fit="truncate", font=font_path, size=16,
        )
        f, lines, size = fit_text(box, 60, 20, draw)
        assert len(lines) == 1
        assert lines[0].endswith("…")

    def test_empty_text(self, draw):
        box = Box(id="t", x=0, y=0, w=100, h=100, text="")
        f, lines, size = fit_text(box, 100, 100, draw)
        assert lines == [""]


class TestAnalyze:
    def test_fits(self, draw, font_path: str):
        box = Box(
            id="t", x=0, y=0, w=400, h=100, text="hello",
            font=font_path, size=20, fit="wrap",
        )
        result = analyze(box, draw)
        assert result["box_id"] == "t"
        assert result["fits"] is True
        assert result["chars"] == 5
        assert result["lines"] == 1
        assert result["strategy"] == "wrap"
        assert result["font_size"] == 20

    def test_overflow(self, draw, font_path: str):
        box = Box(
            id="t", x=0, y=0, w=50, h=20, text="x" * 100,
            font=font_path, size=48, fit="wrap",
        )
        result = analyze(box, draw)
        assert result["fits"] is False
        assert result["chars"] == 100

    def test_shrink_strategy_fits(self, draw, font_path: str):
        box = Box(
            id="t", x=0, y=0, w=120, h=30, text="This is a long sentence that should shrink",
            font=font_path, size=64, fit="shrink",
        )
        result = analyze(box, draw)
        assert result["strategy"] == "shrink"
        assert result["font_size"] < 64
        assert result["fits"] is True

    def test_truncate_strategy(self, draw, font_path: str):
        box = Box(
            id="t", x=0, y=0, w=40, h=20, text="abcdefghijklmnop",
            font=font_path, size=16, fit="truncate",
        )
        result = analyze(box, draw)
        assert result["strategy"] == "truncate"
        assert result["lines"] == 1
        assert result["fits"] is True

    def test_empty_text(self, draw, font_path: str):
        box = Box(
            id="t", x=0, y=0, w=100, h=100, text="",
            font=font_path, size=20,
        )
        result = analyze(box, draw)
        assert result["fits"] is True
        assert result["lines"] == 0
        assert result["chars"] == 0


class TestRender:
    def test_render_solid_canvas(self, font_path: str):
        canvas = Canvas(width=200, height=100, background="#FF0000")
        boxes = [
            Box(
                id="a", x=10, y=10, w=180, h=80, text="hello",
                font=font_path, size=24, color="#FFFFFF", align="center", valign="middle",
            )
        ]
        img = render(canvas, boxes)
        assert img.size == (200, 100)
        assert img.mode == "RGBA"
        pixel = img.getpixel((0, 0))
        assert isinstance(pixel, tuple)
        assert pixel[:3] == (255, 0, 0)

    def test_render_with_background(self, font_path: str, tmp_path: Path):
        bg = Image.new("RGB", (200, 100), (0, 0, 255))
        canvas = Canvas(width=200, height=100)
        boxes = [
            Box(
                id="a", x=10, y=10, w=180, h=80, text="hi",
                font=font_path, size=24, color="#FFFFFF", align="left", valign="middle",
            )
        ]
        img = render(canvas, boxes, background=bg)
        pixel = img.getpixel((0, 0))
        assert isinstance(pixel, tuple)
        assert pixel[:3] == (0, 0, 255)

    def test_render_size_mismatch_raises(self, font_path: str):
        bg = Image.new("RGB", (100, 100))
        canvas = Canvas(width=200, height=100)
        with pytest.raises(SpecError) as exc_info:
            render(canvas, [], background=bg)
        assert exc_info.value.code == "background_size_mismatch"

    def test_render_with_debug_outline(self, font_path: str):
        canvas = Canvas(width=200, height=100)
        boxes = [
            Box(id="a", x=10, y=10, w=180, h=80, text="x", font=font_path, size=20)
        ]
        img = render(canvas, boxes, draw_boxes=True)
        pixel = img.getpixel((10, 10))
        assert isinstance(pixel, tuple)
        assert pixel[:3] == (255, 0, 0)

    def test_render_empty_text(self, font_path: str):
        canvas = Canvas(width=200, height=100, background="#112233")
        boxes = [Box(id="empty", x=10, y=10, w=100, h=50, text="")]
        img = render(canvas, boxes)
        pixel = img.getpixel((50, 50))
        assert isinstance(pixel, tuple)
        assert pixel[:3] == (17, 34, 51)

    def test_one_box_overflow_continues(self, font_path: str):
        canvas = Canvas(width=300, height=200)
        boxes = [
            Box(id="ok", x=10, y=10, w=100, h=50, text="ok", font=font_path, size=20),
            Box(
                id="bad", x=10, y=70, w=50, h=20, text="xxxxxxxxxxxxxxxxxxxxxxxxxx",
                font=font_path, size=48, fit="wrap",
            ),
            Box(id="ok2", x=10, y=100, w=100, h=50, text="ok2", font=font_path, size=20),
        ]
        img = render(canvas, boxes)
        assert img.size == (300, 200)
