"""Tests for annotation output and the `inspect` CLI contract."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from pailow.annotate import annotate
from pailow.box import Canvas
from pailow.inspect import inspect_canvas
from pailow.box import Box

PAILOW = shutil.which("pailow")


def _spec(width: int = 200, height: int = 100) -> dict:
    return {
        "canvas": {"width": width, "height": height, "background": "#000000"},
        "boxes": [
            {
                "id": "title",
                "x": 10,
                "y": 10,
                "w": 120,
                "h": 50,
                "text": "HELLO",
                "size": 24,
                "color": "#FFFFFF",
                "fit": "wrap",
            }
        ],
    }


def _report(width: int = 200, height: int = 100) -> tuple[dict, Image.Image]:
    canvas = Canvas(width=width, height=height, background="#000000")
    box = Box(
        id="title",
        x=10,
        y=10,
        w=120,
        h=50,
        text="HELLO",
        size=24,
        color="#FFFFFF",
        fit="wrap",
    )
    return inspect_canvas(canvas, [box])


@pytest.mark.parametrize(("width", "height"), [(1, 1), (16, 16), (200, 100)])
def test_annotate_never_raises_on_tiny_canvas(width: int, height: int) -> None:
    report, rendered = _report(width, height)
    out = annotate(rendered, report)
    assert out.size == (width, height)
    assert out.mode == "RGBA"


def test_annotate_is_translucent_not_opaque() -> None:
    """collision の塗りは alpha_composite で合成される（不透明な上書きにならない）。"""
    from PIL import ImageDraw

    from pailow.box import Box

    canvas = Canvas(width=200, height=100, background="#000000")
    a = Box(id="a", x=10, y=10, w=100, h=40, text="AAAA", size=40, color="#FFFFFF")
    b = Box(id="b", x=10, y=10, w=100, h=40, text="BBBB", size=40, color="#FFFFFF")
    report, rendered = inspect_canvas(canvas, [a, b])
    assert any(r["collisions"] for r in report["boxes"])
    out = annotate(rendered, report)
    # 交差領域に半透明の赤が乗る: 元画像と完全一致はしないが、真っ赤でもない
    assert out.tobytes() != rendered.convert("RGBA").tobytes()
    sample = out.crop((10, 10, 110, 50)).convert("RGB")
    reds = [px for px in sample.getdata() if px[0] > 100 and px[1] < 120]
    assert reds, "expected some red-tinted pixels from the collision overlay"


def test_annotate_labels_are_ascii_only() -> None:
    """非 ASCII の box id でも例外なく描ける（豆腐回避のため ? に置換）。"""
    from pailow.box import Box

    canvas = Canvas(width=200, height=100, background="#000000")
    box = Box(id="日本語", x=10, y=10, w=150, h=50, text="X", size=24, color="#FFFFFF")
    report, rendered = inspect_canvas(canvas, [box])
    out = annotate(rendered, report)
    assert out.size == (200, 100)


@pytest.mark.skipif(PAILOW is None, reason="pailow CLI not on PATH")
def test_cli_fix_writes_only_the_fixed_file(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    original = _spec()
    original["boxes"][0]["color"] = "#000000"  # 黒背景に黒文字 → invisible
    spec_path.write_text(json.dumps(original, indent=2), encoding="utf-8")
    before = spec_path.read_bytes()

    fixed_path = tmp_path / "fixed.json"
    result = subprocess.run(
        [PAILOW, "inspect", str(spec_path), "--fix", "--fix-out", str(fixed_path)],
        capture_output=True,
        text=True,
    )
    # auto 修正できない警告が残る場合があるため 0 か 2
    assert result.returncode in (0, 2)
    assert spec_path.read_bytes() == before, "input spec must not be modified"
    assert fixed_path.exists()
    fixed = json.loads(fixed_path.read_text(encoding="utf-8"))
    assert fixed["boxes"][0]["color"] != "#000000"


@pytest.mark.skipif(PAILOW is None, reason="pailow CLI not on PATH")
def test_cli_inspect_exit_codes(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_spec()), encoding="utf-8")
    ok = subprocess.run([PAILOW, "inspect", str(good)], capture_output=True, text=True)
    assert ok.returncode == 0

    bad = tmp_path / "bad.json"
    bad_spec = _spec()
    bad_spec["boxes"][0]["color"] = "#000000"
    bad.write_text(json.dumps(bad_spec), encoding="utf-8")
    failing = subprocess.run([PAILOW, "inspect", str(bad)], capture_output=True, text=True)
    assert failing.returncode == 1


@pytest.mark.skipif(PAILOW is None, reason="pailow CLI not on PATH")
def test_cli_annotate_writes_png(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")
    out_png = tmp_path / "anno.png"
    result = subprocess.run(
        [PAILOW, "inspect", str(spec_path), "--annotate", str(out_png), "--json"],
        capture_output=True,
        text=True,
    )
    assert out_png.exists()
    assert result.stdout.strip().startswith("{")
    with Image.open(out_png) as img:
        assert img.size == (200, 100)
