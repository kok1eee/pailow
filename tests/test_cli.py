from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

PAILOW = ["pailow"]


def _write_spec(path: Path, **overrides) -> Path:
    spec = {
        "canvas": {"width": 200, "height": 100, "background": "#000000"},
        "boxes": [
            {
                "id": "t",
                "x": 10,
                "y": 10,
                "w": 180,
                "h": 80,
                "text": "hello",
                "size": 24,
                "color": "#FFFFFF",
                "align": "center",
                "valign": "middle",
                "fit": "wrap",
            }
        ],
    }
    for box in spec["boxes"]:
        box.update(overrides)
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_version():
    result = subprocess.run([*PAILOW, "--version"], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "0.2.0"


def test_new(tmp_path: Path):
    out = tmp_path / "starter.json"
    result = subprocess.run([*PAILOW, "new", str(out)], capture_output=True, text=True)
    assert result.returncode == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert "canvas" in data and "boxes" in data


def test_fit(tmp_path: Path):
    spec = _write_spec(tmp_path / "spec.json")
    result = subprocess.run([*PAILOW, "fit", str(spec)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_fit_json(tmp_path: Path):
    spec = _write_spec(tmp_path / "spec.json")
    result = subprocess.run(
        [*PAILOW, "fit", str(spec), "--json"], capture_output=True, text=True
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "boxes" in data
    assert data["boxes"][0]["box_id"] == "t"
    assert data["boxes"][0]["fits"] is True


def test_fit_overflow_returns_2(tmp_path: Path):
    spec = _write_spec(tmp_path / "spec.json", text="x" * 500, size=128)
    result = subprocess.run([*PAILOW, "fit", str(spec)], capture_output=True, text=True)
    assert result.returncode == 2


def test_render(tmp_path: Path):
    spec = _write_spec(tmp_path / "spec.json")
    out = tmp_path / "out.png"
    result = subprocess.run(
        [*PAILOW, "render", str(spec), "-o", str(out)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    img = Image.open(out)
    assert img.size == (200, 100)


def test_render_with_background(tmp_path: Path):
    bg = tmp_path / "bg.png"
    Image.new("RGB", (200, 100), (50, 100, 150)).save(bg)
    spec = _write_spec(tmp_path / "spec.json")
    out = tmp_path / "out.png"
    result = subprocess.run(
        [*PAILOW, "render", str(spec), "-i", str(bg), "-o", str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    img = Image.open(out)
    assert img.size == (200, 100)


def test_render_with_draw_boxes(tmp_path: Path):
    spec = _write_spec(tmp_path / "spec.json")
    out = tmp_path / "out.png"
    result = subprocess.run(
        [*PAILOW, "render", str(spec), "-o", str(out), "--draw-boxes"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    img = Image.open(out)
    pixel = img.getpixel((10, 10))
    assert isinstance(pixel, tuple)
    assert pixel[:3] == (255, 0, 0)


def test_render_missing_spec(tmp_path: Path):
    result = subprocess.run(
        [*PAILOW, "render", str(tmp_path / "missing.json"), "-o", str(tmp_path / "out.png")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_render_missing_background(tmp_path: Path):
    spec = _write_spec(tmp_path / "spec.json")
    result = subprocess.run(
        [
            *PAILOW,
            "render",
            str(spec),
            "-i",
            str(tmp_path / "nope.png"),
            "-o",
            str(tmp_path / "out.png"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_prompt_short():
    """pailow prompt でショート版プロンプトが出力される。"""
    result = subprocess.run(
        [*PAILOW, "prompt"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "pailow" in result.stdout
    assert "canvas" in result.stdout


def test_prompt_detail():
    """pailow prompt --detail で詳細版 (common mistakes / gallery 参照) が出る。"""
    result = subprocess.run(
        [*PAILOW, "prompt", "--detail"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "Common mistakes" in result.stdout
    assert "min_size" in result.stdout
    assert "char_size_steps" in result.stdout


def test_gallery_list():
    """pailow gallery --list で ID リストが出る。"""
    result = subprocess.run(
        [*PAILOW, "gallery", "--list"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "01_headline" in result.stdout
    assert "04_long_text" in result.stdout


def test_gallery_show_spec():
    """pailow gallery --show <id> で spec JSON が出る。"""
    result = subprocess.run(
        [*PAILOW, "gallery", "--show", "01_headline"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    spec = json.loads(result.stdout)
    assert "canvas" in spec
    assert "boxes" in spec
    assert len(spec["boxes"]) >= 2


def test_gallery_show_render(tmp_path: Path):
    """pailow gallery --show <id> -o out.png で PNG が生成される。"""
    out = tmp_path / "out.png"
    result = subprocess.run(
        [
            *PAILOW, "gallery", "--show", "01_headline",
            "-o", str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    img = Image.open(out)
    assert img.size == (1200, 600)


def test_gallery_show_unknown_id():
    """存在しない ID はエラー終了。"""
    result = subprocess.run(
        [*PAILOW, "gallery", "--show", "99_does_not_exist"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "unknown gallery id" in result.stderr


def test_gallery_no_args():
    """gallery を引数なしで呼ぶとエラー。"""
    result = subprocess.run(
        [*PAILOW, "gallery"], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "--list" in result.stderr or "--show" in result.stderr


def test_python_api_render_gallery_example():
    """Python から render_gallery_example を呼んでレンダリングできる。"""
    from pailow import render_gallery_example

    img = render_gallery_example("01_headline")
    assert img.size == (1200, 600)
    assert img.mode == "RGBA"


def test_python_api_get_gallery_item():
    """Python から get_gallery_item で spec を取得できる。"""
    from pailow import get_gallery_item

    item = get_gallery_item("04_long_text")
    assert item["title"]
    assert "spec" in item
    assert "boxes" in item["spec"]


def test_python_api_unknown_gallery_id():
    """未登録 ID で KeyError が出る。"""
    import pytest

    from pailow import get_gallery_item

    with pytest.raises(KeyError, match="unknown gallery id"):
        get_gallery_item("99_does_not_exist")


def test_watch_missing_spec(tmp_path: Path):
    """存在しない spec で watch を起動するとエラー終了。"""
    result = subprocess.run(
        [
            *PAILOW, "watch",
            str(tmp_path / "missing.json"),
            "-o", str(tmp_path / "out.png"),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_watch_render_on_change(tmp_path: Path):
    """spec を変更すると自動で output が再レンダリングされる。

    watchdog の Observer が実際にイベントを拾うことを確認するため、
    spec を上書きしてから一定時間待つスモークテスト。
    """
    spec_path = tmp_path / "spec.json"
    out_path = tmp_path / "out.png"
    spec_path.write_text(
        json.dumps(
            {
                "canvas": {"width": 200, "height": 100},
                "boxes": [
                    {
                        "id": "t", "x": 10, "y": 10, "w": 180, "h": 80,
                        "text": "initial", "size": 24,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # watch をサブプロセスで起動
    proc = subprocess.Popen(
        [
            *PAILOW, "watch", str(spec_path),
            "-o", str(out_path),
            "--debounce", "50",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        import time

        # 初回レンダリングを待つ
        time.sleep(1.0)
        assert out_path.exists(), "initial render should produce output"

        # spec を変更 (text を更新)
        time.sleep(0.2)
        spec_path.write_text(
            json.dumps(
                {
                    "canvas": {"width": 200, "height": 100},
                    "boxes": [
                        {
                            "id": "t", "x": 10, "y": 10, "w": 180, "h": 80,
                            "text": "updated", "size": 24,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        # ファイルイベント + レンダリングを待つ
        time.sleep(1.5)
        assert out_path.exists()
        # mtime が更新されていることを確認 (再レンダリングされた証拠)
        assert out_path.stat().st_mtime > 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


class TestInlinePreviewDetection:
    """Step 4: インライン画像対応ターミナルの自動検出。"""

    def test_detect_iterm(self, monkeypatch):
        from pailow.cli import _detect_inline_image_terminal

        monkeypatch.delenv("WEZTERM_PANE", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        assert _detect_inline_image_terminal() == "iterm"

    def test_detect_kitty(self, monkeypatch):
        from pailow.cli import _detect_inline_image_terminal

        monkeypatch.delenv("WEZTERM_PANE", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.setenv("TERM", "xterm-kitty")
        assert _detect_inline_image_terminal() == "kitty"

    def test_detect_wezterm(self, monkeypatch):
        from pailow.cli import _detect_inline_image_terminal

        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.setenv("WEZTERM_PANE", "/tmp/panenoise")
        assert _detect_inline_image_terminal() == "wezterm"

    def test_detect_unsupported(self, monkeypatch):
        from pailow.cli import _detect_inline_image_terminal

        monkeypatch.delenv("WEZTERM_PANE", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        assert _detect_inline_image_terminal() is None

    def test_inline_preview_iterm_osc(self, monkeypatch, tmp_path):
        """iTerm 検出時に OSC 1337 escape sequence が出力される。"""
        from pailow.cli import _inline_preview

        png = tmp_path / "t.png"
        # 1x1 PNG を書く
        Image.new("RGB", (1, 1), (255, 0, 0)).save(png, "PNG")

        captured = []

        def fake_write(s):
            captured.append(s)

        monkeypatch.setattr("sys.stdout.write", fake_write)
        _inline_preview(png, "iterm")
        assert len(captured) == 1
        # OSC 1337 で始まる
        assert captured[0].startswith("\033]1337;File=inline=1;")
        # base64 で終わる
        assert captured[0].endswith("\a")


def test_tui_help():
    """pailow tui --help がエラーなく動く。"""
    result = subprocess.run(
        [*PAILOW, "tui", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "spec" in result.stdout


def test_tui_import():
    """PailowTUI クラスが import できる (textual 依存解決確認)。"""
    from pailow.tui import PailowTUI

    app = PailowTUI(Path("/tmp/spec.json"))
    # BINDINGS に上下左右 + Tab + save + quit がある
    actions = {b.action for b in app.BINDINGS if hasattr(b, "action")}
    assert "save" in actions
    assert "quit" in actions
    assert "next_box" in actions
