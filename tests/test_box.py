from __future__ import annotations

import pytest

from pailow.box import Box, Canvas, parse_color


class TestParseColor:
    def test_rgb(self):
        assert parse_color("#FFF") == (255, 255, 255, 255)
        assert parse_color("#000") == (0, 0, 0, 255)
        assert parse_color("#F00") == (255, 0, 0, 255)

    def test_rrggbb(self):
        assert parse_color("#FFFFFF") == (255, 255, 255, 255)
        assert parse_color("#1A1A1A") == (26, 26, 26, 255)
        assert parse_color("#FFD86B") == (255, 216, 107, 255)

    def test_rrggbbaa(self):
        assert parse_color("#FFFFFFFF") == (255, 255, 255, 255)
        assert parse_color("#00000000") == (0, 0, 0, 0)
        assert parse_color("#FF0000FF") == (255, 0, 0, 255)

    def test_strip_whitespace(self):
        assert parse_color("  #FFF  ") == (255, 255, 255, 255)

    def test_invalid_no_hash(self):
        with pytest.raises(ValueError, match="must start with '#'"):
            parse_color("FFF")

    def test_invalid_length(self):
        with pytest.raises(ValueError, match="invalid color"):
            parse_color("#FFFF")

    def test_invalid_chars(self):
        with pytest.raises(ValueError, match="invalid color"):
            parse_color("#GGGGGG")


class TestBox:
    def test_minimal(self):
        b = Box(id="a", x=0, y=0, w=100, h=100)
        assert b.text == ""
        assert b.pad == 0
        assert b.size == 24
        assert b.color == "#FFFFFF"
        assert b.align == "left"
        assert b.valign == "middle"
        assert b.fit == "wrap"
        assert b.line_spacing == 1.2
        assert b.min_size is None

    def test_min_size_set(self):
        b = Box(id="a", x=0, y=0, w=100, h=100, size=24, min_size=12)
        assert b.min_size == 12

    def test_min_size_invalid_zero(self):
        with pytest.raises(ValueError, match="min_size"):
            Box(id="a", x=0, y=0, w=100, h=100, min_size=0)

    def test_min_size_invalid_negative(self):
        with pytest.raises(ValueError, match="min_size"):
            Box(id="a", x=0, y=0, w=100, h=100, min_size=-5)

    def test_min_size_invalid_exceeds_size(self):
        with pytest.raises(ValueError, match="min_size"):
            Box(id="a", x=0, y=0, w=100, h=100, size=20, min_size=30)

    def test_char_size_steps_set(self):
        b = Box(
            id="a", x=0, y=0, w=100, h=100,
            char_size_steps=((15, 44), (50, 36)),
        )
        assert b.char_size_steps == ((15, 44), (50, 36))

    def test_char_size_steps_default(self):
        b = Box(id="a", x=0, y=0, w=100, h=100)
        assert b.char_size_steps is None

    def test_char_size_steps_invalid_unsorted(self):
        with pytest.raises(ValueError, match="strictly increasing"):
            Box(
                id="a", x=0, y=0, w=100, h=100,
                char_size_steps=((50, 36), (15, 44)),
            )

    def test_char_size_steps_invalid_format(self):
        with pytest.raises(ValueError, match="2-tuple"):
            Box(
                id="a", x=0, y=0, w=100, h=100,
                char_size_steps=((15, 44, 99),),
            )

    def test_invalid_align(self):
        with pytest.raises(ValueError, match="align"):
            Box(id="a", x=0, y=0, w=10, h=10, align="middle")  # type: ignore[arg-type]

    def test_invalid_valign(self):
        with pytest.raises(ValueError, match="valign"):
            Box(id="a", x=0, y=0, w=10, h=10, valign="center")  # type: ignore[arg-type]

    def test_invalid_fit(self):
        with pytest.raises(ValueError, match="fit"):
            Box(id="a", x=0, y=0, w=10, h=10, fit="scale")  # type: ignore[arg-type]

    def test_negative_size(self):
        with pytest.raises(ValueError, match="size"):
            Box(id="a", x=0, y=0, w=10, h=10, size=0)

    def test_pad_larger_than_box(self):
        with pytest.raises(ValueError, match="pad"):
            Box(id="a", x=0, y=0, w=10, h=10, pad=6)

    def test_negative_pad(self):
        with pytest.raises(ValueError, match="pad"):
            Box(id="a", x=0, y=0, w=10, h=10, pad=-1)

    def test_line_spacing_zero(self):
        with pytest.raises(ValueError, match="line_spacing"):
            Box(id="a", x=0, y=0, w=10, h=10, line_spacing=0)


class TestCanvas:
    def test_minimal(self):
        c = Canvas(width=800, height=600)
        assert c.background == "#FFFFFF"

    def test_zero_size(self):
        with pytest.raises(ValueError):
            Canvas(width=0, height=600)
        with pytest.raises(ValueError):
            Canvas(width=800, height=0)
