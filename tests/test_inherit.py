"""Step 5: spec inheritance (extends) のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestResolveInheritance:
    def test_no_extends(self, tmp_path):
        from pailow.inherit import resolve_inheritance

        spec = {"canvas": {"width": 100, "height": 100}, "boxes": []}
        out = resolve_inheritance(spec, tmp_path)
        assert out == spec

    def test_simple_extends(self, tmp_path):
        from pailow.inherit import resolve_inheritance

        base = _write(
            tmp_path / "base.json",
            {
                "canvas": {"width": 200, "height": 100, "background": "#000000"},
                "boxes": [
                    {"id": "t", "x": 0, "y": 0, "w": 200, "h": 100, "text": "base"}
                ],
            },
        )
        child = {"extends": "base.json", "boxes": [{"id": "t", "text": "override"}]}
        out = resolve_inheritance(child, tmp_path)
        assert "extends" not in out
        assert out["canvas"]["width"] == 200
        assert out["canvas"]["background"] == "#000000"  # base から継承
        assert out["boxes"][0]["text"] == "override"  # 上書き
        assert out["boxes"][0]["x"] == 0  # base から継承

    def test_deep_extends(self, tmp_path):
        from pailow.inherit import resolve_inheritance

        _write(
            tmp_path / "base.json",
            {"canvas": {"width": 200, "height": 100}, "boxes": []},
        )
        _write(
            tmp_path / "mid.json",
            {"extends": "base.json", "canvas": {"background": "#FF0000"}},
        )
        child = {"extends": "mid.json"}
        out = resolve_inheritance(child, tmp_path)
        assert out["canvas"]["width"] == 200  # base
        assert out["canvas"]["background"] == "#FF0000"  # mid

    def test_missing_base(self, tmp_path):
        from pailow.inherit import resolve_inheritance

        child = {"extends": "missing.json"}
        with pytest.raises(FileNotFoundError, match="not found"):
            resolve_inheritance(child, tmp_path)

    def test_circular_extends(self, tmp_path):
        from pailow.inherit import resolve_inheritance

        _write(tmp_path / "a.json", {"extends": "b.json"})
        _write(tmp_path / "b.json", {"extends": "a.json"})
        spec = json.loads((tmp_path / "a.json").read_text())
        with pytest.raises(ValueError, match="circular"):
            resolve_inheritance(spec, tmp_path)

    def test_boxes_id_based_merge(self, tmp_path):
        """boxes は id ベースで deep merge: 未知の id は追加、base のみは残す。"""
        from pailow.inherit import resolve_inheritance

        _write(
            tmp_path / "base.json",
            {"boxes": [{"id": "a", "x": 0, "text": "a"}, {"id": "b", "x": 0}]},
        )
        child = {"extends": "base.json", "boxes": [{"id": "c", "text": "c"}]}
        out = resolve_inheritance(child, tmp_path)
        ids = [b["id"] for b in out["boxes"]]
        assert "c" in ids  # 新規追加
        assert "a" in ids  # base から残す
        assert "b" in ids  # base から残す
        assert len(out["boxes"]) == 3


class TestPresets:
    def test_apply_headline(self):
        from pailow.presets import apply_preset

        box = {"id": "t", "x": 0, "y": 0, "w": 100, "h": 50, "preset": "headline"}
        out = apply_preset(box, "headline")
        assert "preset" not in out
        assert out["size"] == 64  # preset
        assert out["align"] == "center"
        assert out["fit"] == "shrink"
        assert out["id"] == "t"  # 元の値は保持

    def test_box_field_overrides_preset(self):
        from pailow.presets import apply_preset

        box = {
            "id": "t", "x": 0, "y": 0, "w": 100, "h": 50,
            "preset": "headline",
            "color": "#FF0000",  # preset の "#FFFFFF" より優先
        }
        out = apply_preset(box, "headline")
        assert out["color"] == "#FF0000"

    def test_unknown_preset(self):
        from pailow.presets import apply_preset

        with pytest.raises(KeyError, match="unknown preset"):
            apply_preset({"id": "t"}, "does_not_exist")

    def test_resolve_presets_spec(self):
        from pailow.presets import resolve_presets

        spec = {
            "canvas": {"width": 200, "height": 100},
            "boxes": [
                {"id": "h", "x": 0, "y": 0, "w": 200, "h": 50, "preset": "headline"},
                {"id": "b", "x": 0, "y": 50, "w": 200, "h": 50, "preset": "body"},
            ],
        }
        out = resolve_presets(spec)
        for box in out["boxes"]:
            assert "preset" not in box
        assert out["boxes"][0]["size"] == 64  # headline
        assert out["boxes"][1]["size"] == 18  # body

    def test_resolve_presets_no_preset(self):
        from pailow.presets import resolve_presets

        spec = {
            "canvas": {"width": 200, "height": 100},
            "boxes": [{"id": "t", "x": 0, "y": 0, "w": 100, "h": 50, "size": 20}],
        }
        out = resolve_presets(spec)
        assert out["boxes"][0]["size"] == 20  # そのまま


class TestEndToEnd:
    """Step 5: load_spec で extends + preset が両方解決されることを確認。"""

    def test_load_spec_with_extends(self, tmp_path):
        from pailow.layout import load_spec

        _write(
            tmp_path / "base.json",
            {
                "canvas": {"width": 100, "height": 50, "background": "#000000"},
                "boxes": [{"id": "t", "x": 0, "y": 0, "w": 100, "h": 50, "size": 12}],
            },
        )
        _write(
            tmp_path / "child.json",
            {"extends": "base.json", "canvas": {"background": "#FF0000"}},
        )
        canvas, boxes = load_spec(tmp_path / "child.json")
        assert canvas.background == "#FF0000"
        assert len(boxes) == 1

    def test_load_spec_with_preset(self, tmp_path):
        from pailow.layout import load_spec

        _write(
            tmp_path / "spec.json",
            {
                "canvas": {"width": 200, "height": 100, "background": "#FFFFFF"},
                "boxes": [
                    {
                        "id": "h", "x": 0, "y": 0, "w": 200, "h": 50,
                        "preset": "headline",
                    }
                ],
            },
        )
        canvas, boxes = load_spec(tmp_path / "spec.json")
        assert boxes[0].size == 64  # headline preset
        assert boxes[0].align.value == "center" if hasattr(boxes[0].align, "value") else boxes[0].align == "center"


class TestBatchCLI:
    def test_batch_no_match(self, tmp_path):
        result = __import__("subprocess").run(
            [
                "pailow", "batch", str(tmp_path / "spec.json"),
                "--pattern", str(tmp_path / "imgs/*.jpg"),
                "-o", str(tmp_path / "out"),
            ],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 1
        assert "no images matched" in result.stderr

    def test_batch_help(self):
        result = __import__("subprocess").run(
            ["pailow", "batch", "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "spec" in result.stdout
        assert "pattern" in result.stdout