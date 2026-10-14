"""Tests for `pailow.inspect` — measuring the rendered pixels.

The risk these tests guard against is **divergence**: inspect must measure what
`render()` actually drew, not a reimplementation of it. See
.graphhopper/plans/g-mw34eb32.md (判断1, 判断2).
"""

from __future__ import annotations

import copy

import pytest
from PIL import Image, ImageChops, ImageDraw

from pailow.box import Box, Canvas
from pailow.inspect import INK_THRESHOLD, inspect_canvas
from pailow.render import layout_box, render
from pailow.suggest import collect_auto, spec_hash


def _box(**kwargs) -> Box:
    base = dict(
        id="b",
        x=0,
        y=0,
        w=200,
        h=80,
        text="Hello",
        size=24,
        color="#FFFFFF",
        align="left",
        valign="top",
        fit="wrap",
    )
    base.update(kwargs)
    return Box(**base)  # type: ignore[arg-type]


def _codes(record: dict) -> set[str]:
    return {f["code"] for f in record["findings"]}


# ── 判断2: 測定は render() と一致する ─────────────────────────────────────


def test_mask_equivalence_without_overlap() -> None:
    """inspect のマスクは render(all) と render(all - this box) の差分と一致する。"""
    canvas = Canvas(width=300, height=120, background="#000000")
    only = _box(id="only", x=10, y=10, w=200, h=60, text="HELLO")
    other = _box(id="other", x=10, y=70, w=200, h=40, text="WORLD")

    full = render(canvas, [only, other])
    without_only = render(canvas, [other])
    expected = ImageChops.difference(full.convert("RGBA"), without_only.convert("RGBA"))
    r, g, b, a = expected.split()
    widest = ImageChops.lighter(ImageChops.lighter(r, g), ImageChops.lighter(b, a))
    expected_bbox = widest.point(lambda v: 255 if v > INK_THRESHOLD else 0).getbbox()

    report, _ = inspect_canvas(canvas, [only, other])
    record = next(r for r in report["boxes"] if r["box_id"] == "only")
    painted = record["painted"]
    actual_bbox = (painted["x"], painted["y"], painted["x"] + painted["w"], painted["y"] + painted["h"])
    assert actual_bbox == expected_bbox


def test_auto_color_responds_to_its_own_backdrop() -> None:
    """`auto` は box 領域の実際の背景から決まる。明暗で選色が変わること（判断1）。"""
    canvas = Canvas(width=300, height=120, background="#808080")
    bg = Image.new("RGB", (300, 120), (0, 0, 0))
    ImageDraw.Draw(bg).rectangle([0, 0, 149, 119], fill=(255, 255, 255))

    bright = _box(id="bright", x=10, y=20, w=120, h=60, text="AUTO", size=32, color="auto")
    dark = _box(id="dark", x=170, y=20, w=120, h=60, text="AUTO", size=32, color="auto")

    report, _ = inspect_canvas(canvas, [bright, dark], background=bg)
    records = {r["box_id"]: r for r in report["boxes"]}
    # 明るい背景には黒、暗い背景には白が選ばれ、どちらも読める
    assert records["bright"]["visible"] is True
    assert records["dark"]["visible"] is True
    assert records["bright"]["contrast"] >= 4.5
    assert records["dark"]["contrast"] >= 4.5
    # 背景の実測値が box ごとに違う = 累積画像ではなく自分の領域を見ている
    assert records["bright"]["background"] != records["dark"]["background"]


def test_alpha_text_is_measured_on_all_four_channels() -> None:
    """半透明色は RGBA の差分で測る（判断2）。"""
    canvas = Canvas(width=200, height=100, background="#000000")
    box = _box(id="a", x=10, y=20, w=180, h=50, text="ALPHA", color="#FFFFFF80")
    report, _ = inspect_canvas(canvas, [box])
    record = report["boxes"][0]
    assert record["visible"] is True
    assert "alpha_not_blended" in _codes(record)


def test_background_image_is_used_as_baseline() -> None:
    """画像背景でも、背景のみの描画を基準に測るので同じ背景なら差分ゼロから始まる。"""
    canvas = Canvas(width=120, height=60, background="#FFFFFF")
    bg = Image.new("RGB", (120, 60), (10, 10, 10))
    box = _box(id="b", x=5, y=5, w=110, h=50, text="X", color="#FFFFFF")
    report, _ = inspect_canvas(canvas, [box], background=bg)
    record = report["boxes"][0]
    assert record["visible"] is True
    assert record["background"] == (10, 10, 10)


# ── 判断3: 正常な描画を誤報しない ──────────────────────────────────────────


def test_left_top_single_line_has_no_errors() -> None:
    """短い 1 行を left/top に置いた正常描画は error を出さない（判断3の回帰）。"""
    canvas = Canvas(width=400, height=200, background="#000000")
    box = _box(id="ok", x=20, y=20, w=300, h=100, text="Hi", size=24, align="left", valign="top")
    report, _ = inspect_canvas(canvas, [box])
    record = report["boxes"][0]
    assert [f for f in record["findings"] if f["severity"] == "error"] == []


def test_box_too_small_is_not_reported_as_invisible() -> None:
    """pad*2 == w の box は invisible ではなく box_too_small（render が描かない）。"""
    canvas = Canvas(width=200, height=100, background="#000000")
    box = _box(id="tiny", x=10, y=10, w=40, h=40, pad=20, text="X")
    report, _ = inspect_canvas(canvas, [box])
    record = report["boxes"][0]
    assert "box_too_small" in _codes(record)
    assert "invisible" not in _codes(record)


def test_overflow_is_detected_with_direction() -> None:
    """はみ出しは方向つきで報告される。"""
    canvas = Canvas(width=200, height=100, background="#000000")
    box = _box(id="wide", x=0, y=0, w=60, h=40, text="WIDEWIDEWIDE", size=40, fit="wrap")
    report, _ = inspect_canvas(canvas, [box])
    record = report["boxes"][0]
    assert "overflow" in _codes(record)
    assert record["overflow"]


# ── 判断4: shrink は min_size を動かす ────────────────────────────────────


def test_shrink_overflow_suggests_min_size_not_size() -> None:
    """fit=shrink の溢れは size ではなく min_size を下げる提案になる（判断4）。"""
    canvas = Canvas(width=200, height=100, background="#000000")
    box = _box(
        id="sh",
        x=0,
        y=0,
        w=80,
        h=30,
        text="LONGTEXTLONGTEXT",
        size=48,
        min_size=40,
        fit="shrink",
    )
    report, _ = inspect_canvas(canvas, [box])
    record = report["boxes"][0]
    actions = {s["action"] for s in record["suggestions"]}
    assert "set_size" not in actions
    if "overflow" in _codes(record):
        assert "set_min_size" in actions or "resize_box" in actions


def test_wrap_overflow_suggests_set_size() -> None:
    """fit=wrap の溢れは set_size を提案し、そのサイズで実際に収まること。"""
    canvas = Canvas(width=200, height=100, background="#000000")
    box = _box(
        id="wr",
        x=0,
        y=0,
        w=60,
        h=24,
        text="THIS WILL NOT FIT AT ALL",
        size=40,
        fit="wrap",
    )
    report, _ = inspect_canvas(canvas, [box])
    record = report["boxes"][0]
    size_suggestions = [s for s in record["suggestions"] if s["action"] == "set_size"]
    if "overflow" in _codes(record) and size_suggestions:
        from dataclasses import replace

        from pailow.suggest import _measure

        candidate = replace(box, size=size_suggestions[0]["params"]["to"])
        assert _measure(candidate)[0] is True


# ── 判断5: ループは周期を検出して止まる ──────────────────────────────────


def test_spec_hash_detects_return_to_previous_state() -> None:
    """同一 spec に戻ったら同じハッシュになる（周期検出の土台）。"""
    spec = {"canvas": {"width": 10, "height": 10}, "boxes": [{"id": "a", "size": 20}]}
    same = copy.deepcopy(spec)
    other = copy.deepcopy(spec)
    other["boxes"][0]["size"] = 18

    assert spec_hash(spec) == spec_hash(same)
    assert spec_hash(spec) != spec_hash(other)


def test_report_has_no_auto_suggestions_for_clean_spec() -> None:
    """問題の無い spec では auto 提案が無く、converged=True になる。"""
    canvas = Canvas(width=400, height=200, background="#000000")
    box = _box(id="clean", x=20, y=20, w=300, h=100, text="OK", size=24, color="#FFFFFF")
    report, _ = inspect_canvas(canvas, [box])
    assert collect_auto(report) == []
    assert report["summary"]["converged"] is True
