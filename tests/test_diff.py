"""Step 4: pailow diff (spec / image) のテスト。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image


PAILOW = ["pailow"]


def _write_spec(path: Path, **box_overrides) -> Path:
    spec = {
        "canvas": {"width": 200, "height": 100, "background": "#FFFFFF"},
        "boxes": [
            {
                "id": "t", "x": 10, "y": 10, "w": 180, "h": 80,
                "text": "hello",
                "size": 24,
            }
        ],
    }
    for box in spec["boxes"]:
        box.update(box_overrides)
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


class TestDiffSpecs:
    def test_identical_specs(self, tmp_path):
        from pailow.diff import diff_specs

        a = _write_spec(tmp_path / "a.json")
        b = _write_spec(tmp_path / "b.json")
        assert diff_specs(a, b) == ""

    def test_different_text(self, tmp_path):
        from pailow.diff import diff_specs

        a = _write_spec(tmp_path / "a.json", text="hello")
        b = _write_spec(tmp_path / "b.json", text="world")
        text = diff_specs(a, b)
        assert "hello" in text or "world" in text  # unified diff shows old/new
        assert "-" in text or "+" in text

    def test_different_size(self, tmp_path):
        from pailow.diff import diff_specs

        a = _write_spec(tmp_path / "a.json", size=24)
        b = _write_spec(tmp_path / "b.json", size=48)
        text = diff_specs(a, b)
        assert "24" in text
        assert "48" in text


class TestDiffImages:
    def test_identical_images(self, tmp_path):
        from pailow.diff import diff_images

        a = tmp_path / "a.png"
        b = tmp_path / "b.png"
        Image.new("RGB", (50, 50), (255, 0, 0)).save(a)
        Image.new("RGB", (50, 50), (255, 0, 0)).save(b)
        result = diff_images(a, b)
        assert result["status"] == "identical"
        assert result["identical_pixels"] == result["total_pixels"]

    def test_different_images(self, tmp_path):
        from pailow.diff import diff_images

        a = tmp_path / "a.png"
        b = tmp_path / "b.png"
        Image.new("RGB", (50, 50), (255, 0, 0)).save(a)
        Image.new("RGB", (50, 50), (0, 0, 255)).save(b)
        result = diff_images(a, b)
        assert result["status"] == "different"
        assert result["mean_abs_diff"] > 0

    def test_size_mismatch(self, tmp_path):
        from pailow.diff import diff_images

        a = tmp_path / "a.png"
        b = tmp_path / "b.png"
        Image.new("RGB", (50, 50), (0, 0, 0)).save(a)
        Image.new("RGB", (100, 100), (0, 0, 0)).save(b)
        result = diff_images(a, b)
        assert result["status"] == "size_mismatch"


class TestDiffCLI:
    def test_diff_specs_identical(self, tmp_path):
        a = _write_spec(tmp_path / "a.json")
        b = _write_spec(tmp_path / "b.json")
        result = subprocess.run(
            [*PAILOW, "diff", str(a), str(b)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "identical" in result.stdout

    def test_diff_specs_different(self, tmp_path):
        a = _write_spec(tmp_path / "a.json", text="hello")
        b = _write_spec(tmp_path / "b.json", text="world")
        result = subprocess.run(
            [*PAILOW, "diff", str(a), str(b)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        # unified diff 出力に "-" や "+" が出る
        assert "-" in result.stdout or "+" in result.stdout

    def test_diff_images_json(self, tmp_path):
        a = tmp_path / "a.png"
        b = tmp_path / "b.png"
        Image.new("RGB", (10, 10), (255, 0, 0)).save(a)
        Image.new("RGB", (10, 10), (255, 0, 0)).save(b)
        result = subprocess.run(
            [*PAILOW, "diff", str(a), str(b), "--json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["status"] == "identical"

    def test_diff_missing_left(self, tmp_path):
        b = _write_spec(tmp_path / "b.json")
        result = subprocess.run(
            [*PAILOW, "diff", str(tmp_path / "missing.json"), str(b)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_diff_mixed_types(self, tmp_path):
        a = _write_spec(tmp_path / "a.json")
        img = tmp_path / "a.png"
        Image.new("RGB", (10, 10), (0, 0, 0)).save(img)
        result = subprocess.run(
            [*PAILOW, "diff", str(a), str(img)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "different file types" in result.stderr