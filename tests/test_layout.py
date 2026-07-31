from __future__ import annotations

import json
from pathlib import Path

import pytest

from pailow.errors import SpecError
from pailow.layout import load_spec, validate_spec


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_minimal_spec(tmp_path: Path):
    p = _write(
        tmp_path / "spec.json",
        {
            "canvas": {"width": 100, "height": 100},
            "boxes": [
                {"id": "a", "x": 0, "y": 0, "w": 50, "h": 20, "text": "hi"}
            ],
        },
    )
    canvas, boxes = load_spec(p)
    assert canvas.width == 100
    assert canvas.height == 100
    assert len(boxes) == 1
    assert boxes[0].text == "hi"
    assert boxes[0].color == "#FFFFFF"
    assert boxes[0].fit == "wrap"


def test_full_spec(tmp_path: Path):
    p = _write(
        tmp_path / "spec.json",
        {
            "canvas": {"width": 200, "height": 100, "background": "#000000"},
            "boxes": [
                {
                    "id": "x",
                    "x": 10,
                    "y": 20,
                    "w": 180,
                    "h": 60,
                    "pad": 4,
                    "text": "hello",
                    "size": 32,
                    "color": "#FF0000",
                    "align": "center",
                    "valign": "middle",
                    "fit": "shrink",
                    "line_spacing": 1.4,
                }
            ],
        },
    )
    canvas, boxes = load_spec(p)
    assert canvas.background == "#000000"
    assert boxes[0].pad == 4
    assert boxes[0].size == 32
    assert boxes[0].color == "#FF0000"
    assert boxes[0].align == "center"
    assert boxes[0].valign == "middle"
    assert boxes[0].fit == "shrink"
    assert boxes[0].line_spacing == 1.4


def test_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_spec(tmp_path / "nope.json")


def test_invalid_json(tmp_path: Path):
    p = tmp_path / "spec.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(SpecError) as exc_info:
        load_spec(p)
    assert exc_info.value.code == "invalid_json"


def test_not_object(tmp_path: Path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(SpecError) as exc_info:
        load_spec(p)
    assert exc_info.value.code == "not_an_object"


def test_missing_canvas(tmp_path: Path):
    p = _write(tmp_path / "spec.json", {"boxes": []})
    with pytest.raises(SpecError) as exc_info:
        load_spec(p)
    assert any(e.code == "missing_field" and e.path == "/canvas" for e in [exc_info.value])


def test_missing_boxes(tmp_path: Path):
    p = _write(tmp_path / "spec.json", {"canvas": {"width": 1, "height": 1}})
    with pytest.raises(SpecError) as exc_info:
        load_spec(p)
    assert any(e.code == "missing_field" and e.path == "/boxes" for e in [exc_info.value])


def test_duplicate_id(tmp_path: Path):
    p = _write(
        tmp_path / "spec.json",
        {
            "canvas": {"width": 100, "height": 100},
            "boxes": [
                {"id": "a", "x": 0, "y": 0, "w": 10, "h": 10},
                {"id": "a", "x": 0, "y": 0, "w": 10, "h": 10},
            ],
        },
    )
    with pytest.raises(SpecError) as exc_info:
        load_spec(p)
    assert exc_info.value.code == "duplicate_id"


def test_box_missing_field(tmp_path: Path):
    p = _write(
        tmp_path / "spec.json",
        {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10}],
        },
    )
    with pytest.raises(SpecError) as exc_info:
        load_spec(p)
    assert exc_info.value.code == "missing_field"
    assert exc_info.value.path == "/boxes/0/h"


def test_box_outside_canvas(tmp_path: Path):
    p = _write(
        tmp_path / "spec.json",
        {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 50, "y": 50, "w": 100, "h": 100}],
        },
    )
    with pytest.raises(SpecError) as exc_info:
        load_spec(p)
    assert exc_info.value.code == "out_of_bounds"
    assert "exceeds canvas" in exc_info.value.fix


def test_box_invalid_value(tmp_path: Path):
    p = _write(
        tmp_path / "spec.json",
        {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "align": "middle"}],
        },
    )
    with pytest.raises(SpecError) as exc_info:
        load_spec(p)
    assert exc_info.value.code == "invalid_enum"
    assert exc_info.value.path == "/boxes/0/align"


class TestLLMFriendlyErrors:
    """Step 3: LLM が spec を吐いたときのエラーが自己記述的であることの検証。"""

    def _spec(self, **box_overrides):
        base = {"id": "t", "x": 0, "y": 0, "w": 100, "h": 100}
        base.update(box_overrides)
        return {
            "canvas": {"width": 200, "height": 100},
            "boxes": [base],
        }

    def test_fit_typo_message(self):
        spec = self._spec(text="hi", fit="scale")
        errors = validate_spec(spec, strict=True)
        assert len(errors) == 1
        err = errors[0]
        assert err.code == "invalid_enum"
        assert err.path == "/boxes/0/fit"
        msg = err.fix
        assert "fit" in msg
        assert "scale" in msg
        for allowed in ("wrap", "shrink", "truncate"):
            assert allowed in msg
        assert "Example" in msg

    def test_color_css_name_message(self):
        spec = self._spec(text="hi", color="red")
        errors = validate_spec(spec, strict=True)
        assert any(e.code == "invalid_color" for e in errors)
        msg = next(e.fix for e in errors if e.code == "invalid_color")
        assert ("CSS" in msg or "names" in msg)
        assert "Example" in msg
        assert "#FF0000" in msg

    def test_color_no_hash_message(self):
        spec = self._spec(text="hi", color="FF0000")
        errors = validate_spec(spec, strict=True)
        assert any(e.code == "invalid_color" for e in errors)

    def test_size_string_message(self):
        spec = self._spec(text="hi", size="24")
        errors = validate_spec(spec, strict=True)
        assert any(e.code == "invalid_type" and "/size" in e.path for e in errors)
        msg = next(e.fix for e in errors if "/size" in e.path)
        assert "string" in msg
        assert "Example" in msg

    def test_size_zero_message(self):
        spec = self._spec(text="hi", size=0)
        errors = validate_spec(spec, strict=True)
        assert any(e.code == "out_of_range" and e.path.endswith("/size") for e in errors)

    def test_align_invalid_message(self):
        spec = self._spec(text="hi", align="middle")
        errors = validate_spec(spec, strict=True)
        msg = next(e.fix for e in errors if e.path.endswith("/align"))
        assert "align" in msg
        assert "left" in msg
        assert "Example" in msg

    def test_valign_invalid_message(self):
        spec = self._spec(text="hi", valign="center")
        errors = validate_spec(spec, strict=True)
        msg = next(e.fix for e in errors if e.path.endswith("/valign"))
        assert "valign" in msg
        assert "top" in msg
        assert "Example" in msg
