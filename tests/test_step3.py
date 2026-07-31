from __future__ import annotations

import json
from pathlib import Path

import pytest

from pailow import build_schema, validate_spec
from pailow.errors import SpecError, truncate_value


class TestSpecError:
    def test_is_value_error(self):
        e = SpecError(
            code="missing_field",
            path="/x",
            value=None,
            expected="integer",
            fix="add x",
        )
        assert isinstance(e, ValueError)
        assert "add x" in str(e)
        assert "/x" in str(e)

    def test_message_default(self):
        e = SpecError(
            code="x",
            path="/path",
            value=1,
            expected="int",
            fix="fix it",
        )
        assert e.message == "/path: fix it"

    def test_message_no_path(self):
        e = SpecError(
            code="x",
            path="",
            value=1,
            expected="int",
            fix="fix it",
        )
        assert e.message == "fix it"

    def test_message_override(self):
        e = SpecError(
            code="x",
            path="/p",
            value=1,
            expected="int",
            fix="fix",
            message="custom",
        )
        assert e.message == "custom"

    def test_to_dict(self):
        e = SpecError(
            code="missing_field",
            path="/canvas/width",
            value=None,
            expected="integer",
            fix="add canvas.width",
        )
        d = e.to_dict()
        assert d["code"] == "missing_field"
        assert d["path"] == "/canvas/width"
        assert d["value"] == "None"
        assert d["expected"] == "integer"
        assert d["fix"] == "add canvas.width"
        assert "message" in d

    def test_value_truncation(self):
        long_text = "x" * 500
        e = SpecError(
            code="x",
            path="/p",
            value=long_text,
            expected="string",
            fix="fix",
        )
        d = e.to_dict()
        # repr of a 500-char string is 502 chars; truncation gives 200 + "…" = 201
        assert len(d["value"]) <= 201
        assert d["value"].endswith("…")

    def test_to_dict_unrepresentable_value(self):
        class Weird:
            def __repr__(self):
                raise RuntimeError("nope")

        e = SpecError(
            code="x",
            path="/p",
            value=Weird(),
            expected="int",
            fix="fix",
        )
        d = e.to_dict()
        assert d["value"] == "<unrepresentable>"

    def test_truncate_value_function(self):
        assert truncate_value("short") == "'short'"
        assert truncate_value("x" * 1000).endswith("…")
        assert truncate_value(None) == "None"
        assert truncate_value(42) == "42"
        assert truncate_value([1, 2, 3]) == "[1, 2, 3]"


class TestValidateSpec:
    def _valid(self) -> dict:
        return {
            "canvas": {"width": 100, "height": 100},
            "boxes": [
                {"id": "a", "x": 0, "y": 0, "w": 50, "h": 50, "text": "hi"}
            ],
        }

    def test_valid_returns_empty(self):
        assert validate_spec(self._valid()) == []

    def test_not_object(self):
        errors = validate_spec([1, 2, 3])
        assert len(errors) == 1
        assert errors[0].code == "not_an_object"
        assert errors[0].path == ""

    def test_missing_canvas(self):
        errors = validate_spec({"boxes": []})
        assert any(e.code == "missing_field" and e.path == "/canvas" for e in errors)

    def test_missing_boxes(self):
        errors = validate_spec({"canvas": {"width": 1, "height": 1}})
        assert any(e.code == "missing_field" and e.path == "/boxes" for e in errors)

    def test_canvas_not_object(self):
        errors = validate_spec({"canvas": "bad", "boxes": []})
        assert any(e.code == "invalid_type" and e.path == "/canvas" for e in errors)

    def test_canvas_missing_dimensions(self):
        errors = validate_spec({"canvas": {}, "boxes": []})
        assert any(e.path == "/canvas/width" for e in errors)
        assert any(e.path == "/canvas/height" for e in errors)

    def test_canvas_wrong_type(self):
        errors = validate_spec({"canvas": {"width": "100", "height": 100}, "boxes": []})
        assert any(e.code == "invalid_type" and e.path == "/canvas/width" for e in errors)

    def test_canvas_negative_dimension(self):
        errors = validate_spec({"canvas": {"width": -1, "height": 100}, "boxes": []})
        assert any(e.code == "out_of_range" and e.path == "/canvas/width" for e in errors)

    def test_canvas_invalid_color(self):
        errors = validate_spec(
            {"canvas": {"width": 100, "height": 100, "background": "blue"}, "boxes": []}
        )
        assert any(e.code == "invalid_color" and e.path == "/canvas/background" for e in errors)

    def test_boxes_not_array(self):
        errors = validate_spec(
            {"canvas": {"width": 100, "height": 100}, "boxes": "bad"}
        )
        assert any(e.code == "invalid_type" and e.path == "/boxes" for e in errors)

    def test_box_not_object(self):
        errors = validate_spec(
            {"canvas": {"width": 100, "height": 100}, "boxes": ["bad"]}
        )
        assert any(e.code == "invalid_type" and e.path == "/boxes/0" for e in errors)

    def test_box_missing_required(self):
        errors = validate_spec(
            {
                "canvas": {"width": 100, "height": 100},
                "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10}],
            }
        )
        assert any(e.code == "missing_field" and e.path == "/boxes/0/h" for e in errors)

    def test_box_duplicate_id(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [
                {"id": "a", "x": 0, "y": 0, "w": 10, "h": 10},
                {"id": "a", "x": 0, "y": 0, "w": 10, "h": 10},
            ],
        }
        errors = validate_spec(spec)
        assert any(e.code == "duplicate_id" and e.path == "/boxes/1/id" for e in errors)

    def test_box_negative_coord(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": -5, "y": 0, "w": 10, "h": 10}],
        }
        errors = validate_spec(spec)
        assert any(e.code == "out_of_range" and e.path == "/boxes/0/x" for e in errors)

    def test_box_invalid_align(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "align": "middle"}],
        }
        errors = validate_spec(spec)
        assert any(e.code == "invalid_enum" and e.path == "/boxes/0/align" for e in errors)

    def test_box_invalid_color(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "color": "red"}],
        }
        errors = validate_spec(spec)
        assert any(e.code == "invalid_color" and e.path == "/boxes/0/color" for e in errors)

    def test_box_padding_too_large(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [
                {"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "pad": 20}
            ],
        }
        errors = validate_spec(spec)
        pad_errors = [e for e in errors if e.code == "padding_too_large"]
        assert len(pad_errors) == 2  # both w and h

    def test_box_out_of_bounds(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 50, "y": 0, "w": 100, "h": 10}],
        }
        errors = validate_spec(spec)
        # x+w > width → /boxes/0/x; y+h would also fail if h is too tall
        assert any(e.code == "out_of_bounds" and e.path == "/boxes/0/x" for e in errors)

    def test_multiple_errors_collected(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [
                {"id": "a", "x": -1, "y": 0, "w": 10, "h": 10, "align": "x"},
                {"id": "b", "x": 0, "y": 0, "w": 5, "h": 5, "pad": 10},
            ],
        }
        errors = validate_spec(spec)
        # Should have multiple errors
        assert len(errors) >= 3
        codes = {e.code for e in errors}
        assert "out_of_range" in codes
        assert "invalid_enum" in codes
        assert "padding_too_large" in codes

    def test_dependent_error_suppression(self):
        # x is not an int; out_of_bounds should NOT also be reported
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": "bad", "y": 0, "w": 10, "h": 10}],
        }
        errors = validate_spec(spec)
        assert not any(e.code == "out_of_bounds" for e in errors)
        assert any(e.code == "invalid_type" and e.path == "/boxes/0/x" for e in errors)

    def test_paths_are_json_pointer(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [
                {"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "color": "bad"}
            ],
        }
        errors = validate_spec(spec)
        assert errors[0].path.startswith("/")

    def test_error_ordering_deterministic(self):
        spec = {
            "canvas": {"width": "bad", "height": 100},
            "boxes": [{"id": "a", "x": -1, "y": 0, "w": 10, "h": 10}],
        }
        e1 = validate_spec(spec)
        e2 = validate_spec(spec)
        assert [str(e) for e in e1] == [str(e) for e in e2]

    def test_too_many_errors_truncated(self, monkeypatch):
        from pailow import layout

        monkeypatch.setattr(layout, "_MAX_ERRORS", 3)
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [
                {"id": "a", "x": -1, "y": -1, "w": -1, "h": -1, "align": "x", "valign": "x", "fit": "x"},
            ],
        }
        errors = validate_spec(spec)
        assert any(e.code == "too_many_errors" for e in errors)

    def test_preflight_font_not_found(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [
                {"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "font": "/nonexistent.ttf"}
            ],
        }
        errors = validate_spec(spec, level="preflight")
        assert any(e.code == "font_not_found" for e in errors)

    def test_strict_rejects_unknown_root_field(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10}],
            "made_up": True,
        }
        errors = validate_spec(spec, strict=True)
        assert any(e.code == "unknown_field" and e.path == "/made_up" for e in errors)

    def test_strict_rejects_unknown_box_field(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "vert_align": "top"}],
        }
        errors = validate_spec(spec, strict=True)
        assert any(e.code == "unknown_field" and "vert_align" in e.path for e in errors)

    def test_size_out_of_range(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "size": 0}],
        }
        errors = validate_spec(spec)
        assert any(e.code == "out_of_range" and e.path == "/boxes/0/size" for e in errors)

    def test_size_invalid_type(self):
        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "size": "big"}],
        }
        errors = validate_spec(spec)
        assert any(e.code == "invalid_type" and e.path == "/boxes/0/size" for e in errors)


class TestSchema:
    def test_build_schema_is_dict_2020_12(self):
        schema = build_schema()
        assert schema["$schema"].endswith("/2020-12/schema")
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"canvas", "boxes"}
        assert "$defs" in schema
        assert "box" in schema["$defs"]

    def test_box_schema_enum(self):
        schema = build_schema()
        box = schema["$defs"]["box"]
        assert box["properties"]["align"]["enum"] == ["left", "center", "right"]
        assert box["properties"]["valign"]["enum"] == ["top", "middle", "bottom"]
        assert box["properties"]["fit"]["enum"] == ["wrap", "shrink", "truncate"]

    def test_canvas_schema_required(self):
        schema = build_schema()
        assert schema["properties"]["canvas"]["required"] == ["width", "height"]
        assert schema["properties"]["canvas"]["additionalProperties"] is False

    def test_schema_round_trip_valid(self):
        spec = {
            "canvas": {"width": 1200, "height": 800, "background": "#000000"},
            "boxes": [
                {
                    "id": "title",
                    "x": 40,
                    "y": 40,
                    "w": 1120,
                    "h": 200,
                    "pad": 8,
                    "text": "Hello",
                    "size": 96,
                    "color": "#FFFFFF",
                    "align": "left",
                    "valign": "middle",
                    "fit": "shrink",
                    "line_spacing": 1.2,
                }
            ],
        }
        assert validate_spec(spec) == []
        schema = build_schema()
        # Spot check that all field values are within the schema's enum
        for enum_field in ("align", "valign", "fit"):
            assert spec["boxes"][0][enum_field] in schema["$defs"]["box"]["properties"][enum_field]["enum"]


class TestInMemoryAPI:
    def test_load_spec_from_mapping_roundtrip(self):
        from pailow import load_spec_from_mapping

        spec = {
            "canvas": {"width": 100, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "align": "x"}],
        }
        with pytest.raises(SpecError) as exc_info:
            load_spec_from_mapping(spec)
        assert exc_info.value.code == "invalid_enum"

    def test_render_from_mapping_dict(self):
        from pailow import render_from_mapping
        from PIL import Image

        spec = {
            "canvas": {"width": 200, "height": 100, "background": "#FF0000"},
            "boxes": [
                {"id": "a", "x": 10, "y": 10, "w": 180, "h": 80, "text": "x", "size": 20}
            ],
        }
        img = render_from_mapping(spec)
        assert isinstance(img, Image.Image)
        assert img.size == (200, 100)

    def test_render_from_mapping_with_path_background(self, tmp_path):
        from pailow import render_from_mapping
        from PIL import Image

        bg = tmp_path / "bg.png"
        Image.new("RGB", (200, 100), (0, 0, 255)).save(bg)
        spec = {
            "canvas": {"width": 200, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 100, "h": 50, "text": "x"}],
        }
        img = render_from_mapping(spec, background=bg)
        assert img.size == (200, 100)

    def test_render_from_mapping_missing_background(self, tmp_path):
        from pailow import render_from_mapping
        from pailow.errors import SpecError

        spec = {
            "canvas": {"width": 200, "height": 100},
            "boxes": [{"id": "a", "x": 0, "y": 0, "w": 100, "h": 50, "text": "x"}],
        }
        with pytest.raises(SpecError) as exc_info:
            render_from_mapping(spec, background=tmp_path / "nope.png")
        assert exc_info.value.code == "background_not_found"

    def test_analyze_from_mapping_dict(self):
        from pailow import analyze_from_mapping

        spec = {
            "canvas": {"width": 200, "height": 100},
            "boxes": [
                {"id": "ok", "x": 0, "y": 0, "w": 200, "h": 100, "text": "hi", "size": 20}
            ],
        }
        results = analyze_from_mapping(spec)
        assert len(results) == 1
        assert results[0]["box_id"] == "ok"
        assert results[0]["fits"] is True


class TestLibraryExports:
    def test_all_exports_importable(self):
        from pailow import (
            Box,
            Canvas,
            SpecError,
            analyze,
            analyze_from_mapping,
            build_schema,
            load_spec,
            load_spec_from_mapping,
            parse_color,
            render,
            render_from_mapping,
            schema_version,
            validate_spec,
        )
        # All are callable / classes
        assert callable(render)
        assert callable(load_spec)
        assert callable(validate_spec)


class TestGallery:
    def test_gallery_examples_validate(self):
        from pathlib import Path

        from pailow import validate_spec

        gallery = Path(__file__).parent.parent / "examples" / "gallery"
        for spec_path in sorted(gallery.glob("*.json")):
            if spec_path.name.endswith("_broken.json"):
                # The broken example is intentionally invalid.
                continue
            data = json.loads(spec_path.read_text(encoding="utf-8"))
            errors = validate_spec(data, level="schema")
            assert not errors, f"{spec_path.name} should be valid: {[e.to_dict() for e in errors]}"

    def test_broken_example_expected_invalid(self):
        from pathlib import Path

        from pailow import validate_spec

        broken = (
            Path(__file__).parent.parent
            / "examples"
            / "gallery"
            / "06_repair_broken.json"
        )
        data = json.loads(broken.read_text(encoding="utf-8"))
        errors = validate_spec(data, level="schema")
        assert errors, "06_repair_broken.json should fail validation (that's the point)"
        codes = {e.code for e in errors}
        assert "invalid_color" in codes
        assert "duplicate_id" in codes
        assert "invalid_enum" in codes

    def test_gallery_build_script_runs(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "scripts/build_gallery.py"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
        sheet = (
            Path(__file__).parent.parent
            / "examples"
            / "gallery"
            / "_contact_sheet.png"
        )
        assert sheet.exists()


class TestValidateCli:
    def test_schema_command_outputs_json(self):
        import subprocess
        result = subprocess.run(
            ["pailow", "schema"], capture_output=True, text=True, cwd=Path.cwd()
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["type"] == "object"
        assert "$defs" in data

    def test_schema_pretty(self):
        import subprocess
        result = subprocess.run(
            ["pailow", "schema", "--pretty"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "\n  " in result.stdout  # indented

    def test_validate_valid(self, tmp_path):
        import subprocess
        spec = tmp_path / "ok.json"
        spec.write_text(
            json.dumps(
                {
                    "canvas": {"width": 100, "height": 100},
                    "boxes": [{"id": "a", "x": 0, "y": 0, "w": 50, "h": 50}],
                }
            )
        )
        result = subprocess.run(
            ["pailow", "validate", str(spec)], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_validate_invalid_exits_1(self, tmp_path):
        import subprocess
        spec = tmp_path / "bad.json"
        spec.write_text(
            json.dumps(
                {
                    "canvas": {"width": 100, "height": 100},
                    "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "align": "x"}],
                }
            )
        )
        result = subprocess.run(
            ["pailow", "validate", str(spec)], capture_output=True, text=True
        )
        assert result.returncode == 1

    def test_validate_json_output(self, tmp_path):
        import subprocess
        spec = tmp_path / "bad.json"
        spec.write_text(
            json.dumps(
                {
                    "canvas": {"width": 100, "height": 100},
                    "boxes": [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 10, "align": "x"}],
                }
            )
        )
        result = subprocess.run(
            ["pailow", "validate", str(spec), "--json"], capture_output=True, text=True
        )
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert len(data["errors"]) >= 1
        assert data["errors"][0]["code"] == "invalid_enum"

    def test_validate_missing_spec(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["pailow", "validate", str(tmp_path / "nope.json")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_validate_invalid_json(self, tmp_path):
        import subprocess
        spec = tmp_path / "bad.json"
        spec.write_text("{not json", encoding="utf-8")
        result = subprocess.run(
            ["pailow", "validate", str(spec), "--json"], capture_output=True, text=True
        )
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["errors"][0]["code"] == "invalid_json"


def _import_validate():
    from pailow import validate_spec
    return validate_spec
