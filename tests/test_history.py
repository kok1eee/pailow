"""Step 4: pailow history のテスト。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image


PAILOW = ["pailow"]


def _write_spec(path: Path) -> Path:
    spec = {
        "canvas": {"width": 100, "height": 50, "background": "#FFFFFF"},
        "boxes": [
            {"id": "t", "x": 5, "y": 5, "w": 90, "h": 40, "text": "hi", "size": 12}
        ],
    }
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def _write_png(path: Path) -> Path:
    Image.new("RGB", (50, 50), (200, 100, 50)).save(path)
    return path


class TestHistoryPython:
    def test_save_and_list(self, tmp_path):
        from pailow.history import list_history, save_to_history

        # png は tmp_path/src に、history は tmp_path/hist に分けて作成
        src = tmp_path / "src"
        src.mkdir()
        hist = tmp_path / "hist"
        png = _write_png(src / "out.png")
        save_to_history(png, history_dir=hist)
        items = list_history(history_dir=hist)
        assert len(items) == 1
        assert items[0]["id"].endswith("-out")
        assert items[0]["png"].endswith(".png")

    def test_save_with_spec(self, tmp_path):
        from pailow.history import list_history, save_to_history

        src = tmp_path / "src"
        src.mkdir()
        hist = tmp_path / "hist"
        png = _write_png(src / "out.png")
        spec = _write_spec(src / "spec.json")
        save_to_history(png, spec_path=spec, history_dir=hist)
        items = list_history(history_dir=hist)
        assert items[0]["spec"] is not None

    def test_prune_old(self, tmp_path):
        from pailow.history import save_to_history

        for i in range(5):
            png = _write_png(tmp_path / f"out_{i}.png")
            save_to_history(png, history_dir=tmp_path, max_keep=3)
        # max_keep=3 なので古い 2 つは削除
        assert len(list(tmp_path.glob("*.png"))) == 3

    def test_get_entry_not_found(self, tmp_path):
        from pailow.history import get_history_entry

        with pytest.raises(KeyError):
            get_history_entry("not-there", history_dir=tmp_path)


class TestHistoryCLI:
    def test_history_list_empty(self, tmp_path):
        result = subprocess.run(
            [*PAILOW, "history", "--list", "--dir", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "no history" in result.stdout

    def test_history_no_args_error(self):
        result = subprocess.run(
            [*PAILOW, "history"], capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "--list" in result.stderr or "--show" in result.stderr

    def test_history_show_unknown(self, tmp_path):
        result = subprocess.run(
            [*PAILOW, "history", "--show", "not-there", "--dir", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1

    def test_history_show_after_save(self, tmp_path):
        from pailow.history import save_to_history

        png = _write_png(tmp_path / "out.png")
        target = save_to_history(png, history_dir=tmp_path)
        # history --show でパスを取得できるか
        result = subprocess.run(
            [
                *PAILOW, "history", "--show", target.stem,
                "--dir", str(tmp_path),
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert target.name in result.stdout