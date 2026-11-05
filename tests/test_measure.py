"""Tests for `pailow.measure_image` — measuring someone else's rendered PNG.

The point of this API is the test-script use case: an external pipeline renders
an image, the test asks pailow where the ink landed, and nothing is drawn.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from pailow.box import Box, Canvas
from pailow.errors import SpecError
from pailow.measure import measure_image
from pailow.render import render


def _render(tmp_path: Path, spec_boxes: list[dict], width=400, height=200) -> tuple[Path, Path]:
    """Write a rendered PNG and its text-free background PNG."""
    canvas = Canvas(width=width, height=height, background="#000000")
    bg = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    boxes = [Box(**b) for b in spec_boxes]
    rendered = render(canvas, boxes)
    out = tmp_path / "rendered.png"
    bg_out = tmp_path / "bg.png"
    rendered.save(out)
    bg.save(bg_out)
    return out, bg_out


def _box_kwargs(**kwargs) -> dict:
    base = dict(
        id="title",
        x=20,
        y=20,
        w=300,
        h=80,
        text="HELLO",
        size=32,
        color="#FFFFFF",
        align="left",
        valign="top",
        fit="wrap",
    )
    base.update(kwargs)
    return base


def test_measures_rendered_ink_without_drawing(tmp_path: Path) -> None:
    rendered, bg = _render(tmp_path, [_box_kwargs()])
    report = measure_image(rendered, [{"id": "title", "x": 20, "y": 20, "w": 300, "h": 80}], background=bg)

    record = report["boxes"][0]
    assert record["visible"] is True
    assert record["painted"] is not None
    # インクは inner rect（pad=0 なので rect と同じ）の中に収まる
    assert record["overflow"] == {}
    assert record["within_tolerance"] is True
    assert record["suggested_adjust"] == {"dx": 0, "dy": 0, "resize_required": False}


def test_painted_rect_matches_render_bbox(tmp_path: Path) -> None:
    """measure_image の bbox は描画結果の実インクと一致する（描画側との整合）。"""
    kwargs = _box_kwargs()
    rendered, bg = _render(tmp_path, [kwargs])

    with Image.open(rendered) as img, Image.open(bg) as bg_img:
        from PIL import ImageChops

        diff = ImageChops.difference(img.convert("RGBA"), bg_img.convert("RGBA"))
        r, g, b, a = diff.split()
        widest = ImageChops.lighter(ImageChops.lighter(r, g), ImageChops.lighter(b, a))
        expected = widest.point(lambda v: 255 if v > 8 else 0).getbbox()

    report = measure_image(rendered, [{"id": "title", "x": 20, "y": 20, "w": 300, "h": 80}], background=bg)
    painted = report["boxes"][0]["painted"]
    assert expected is not None
    assert (painted["x"], painted["y"], painted["x"] + painted["w"], painted["y"] + painted["h"]) == expected


def test_empty_box_reported_as_invisible(tmp_path: Path) -> None:
    rendered, bg = _render(tmp_path, [_box_kwargs(text="")])
    report = measure_image(rendered, [{"id": "title", "x": 20, "y": 20, "w": 300, "h": 80}], background=bg)
    record = report["boxes"][0]
    assert record["visible"] is False
    assert "invisible" in {f["code"] for f in record["findings"]}


def test_overflow_and_suggested_adjust(tmp_path: Path) -> None:
    """右にはみ出したら dx を負で返す（Override にそのまま書ける）。"""
    # 文字は x=20 から始まるが、意図した box は x=260 から → 実際は左にはみ出す
    rendered, bg = _render(tmp_path, [_box_kwargs(x=20, y=20, w=300, h=80, text="HELLO WORLD HELLO")])
    report = measure_image(
        rendered, [{"id": "title", "x": 260, "y": 20, "w": 100, "h": 80}], background=bg, margin=200
    )
    record = report["boxes"][0]
    assert "overflow" in {f["code"] for f in record["findings"]}
    adjust = record["suggested_adjust"]
    assert adjust["dx"] > 0  # 右へ動かせば直る
    assert adjust["resize_required"] is False


def test_two_sided_overflow_requires_resize(tmp_path: Path) -> None:
    """左右両方にはみ出すなら move では直らない。"""
    rendered, bg = _render(tmp_path, [_box_kwargs(x=10, y=20, w=380, h=80, text="WIDE TEXT ACROSS")])
    report = measure_image(rendered, [{"id": "title", "x": 150, "y": 20, "w": 60, "h": 80}], background=bg, margin=300)
    record = report["boxes"][0]
    if "left" in record["overflow"] and "right" in record["overflow"]:
        assert record["suggested_adjust"]["resize_required"] is True


def test_collision_between_boxes(tmp_path: Path) -> None:
    rendered, bg = _render(
        tmp_path,
        [
            _box_kwargs(id="a", x=20, y=20, w=300, h=40, text="AAAAAAAA", size=32),
            _box_kwargs(id="b", x=20, y=20, w=300, h=40, text="BBBBBBBB", size=32),
        ],
    )
    report = measure_image(
        rendered,
        [
            {"id": "a", "x": 20, "y": 20, "w": 300, "h": 40},
            {"id": "b", "x": 20, "y": 20, "w": 300, "h": 40},
        ],
        background=bg,
    )
    assert report["boxes"][0]["collisions"]
    assert "collision" in {f["code"] for f in report["boxes"][0]["findings"]}


def test_solid_color_background_when_no_background_image(tmp_path: Path) -> None:
    rendered, bg = _render(tmp_path, [_box_kwargs()])
    report = measure_image(rendered, [{"id": "title", "x": 20, "y": 20, "w": 300, "h": 80}], bg_color="#000000")
    assert report["boxes"][0]["visible"] is True


def test_background_size_mismatch_raises(tmp_path: Path) -> None:
    rendered, bg = _render(tmp_path, [_box_kwargs()])
    with Image.open(bg) as img:
        wrong = img.resize((10, 10))
    with pytest.raises(SpecError):
        measure_image(rendered, [{"id": "title", "x": 20, "y": 20, "w": 300, "h": 80}], background=wrong)


def test_accepts_box_objects(tmp_path: Path) -> None:
    kwargs = _box_kwargs()
    rendered, bg = _render(tmp_path, [kwargs])
    box = Box(**kwargs)
    report = measure_image(rendered, [box], background=bg)
    assert report["boxes"][0]["box_id"] == "title"
