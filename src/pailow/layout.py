from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pailow.box import Box, Canvas, parse_color
from pailow.errors import _MAX_ERRORS, SpecError


_ALIGN_VALUES = ("left", "center", "right")
_VALIGN_VALUES = ("top", "middle", "bottom")
_FIT_VALUES = ("wrap", "shrink", "truncate")

_BOX_ALLOWED_KEYS = frozenset(
    {
        "id",
        "x",
        "y",
        "w",
        "h",
        "text",
        "pad",
        "font",
        "size",
        "color",
        "align",
        "valign",
        "fit",
        "line_spacing",
        "min_size",
        "char_size_steps",
        "parent",
    }
)
_CANVAS_ALLOWED_KEYS = frozenset({"width", "height", "background"})
_ROOT_ALLOWED_KEYS = frozenset({"canvas", "boxes"})


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate_canvas(spec: dict, errors: list[SpecError], strict: bool) -> Optional[Canvas]:
    if strict:
        for unknown in set(spec) - _ROOT_ALLOWED_KEYS:
            errors.append(
                SpecError(
                    code="unknown_field",
                    path=f"/{unknown}",
                    value=unknown,
                    expected="one of " + ", ".join(sorted(_ROOT_ALLOWED_KEYS)),
                    fix=f"unknown root field {unknown!r}; remove it (allowed: {sorted(_ROOT_ALLOWED_KEYS)})",
                )
            )

    raw = spec.get("canvas")
    if raw is None:
        errors.append(
            SpecError(
                code="missing_field",
                path="/canvas",
                value=None,
                expected="object",
                fix="add a 'canvas' object with 'width' and 'height'",
            )
        )
        return None
    if not isinstance(raw, dict):
        errors.append(
            SpecError(
                code="invalid_type",
                path="/canvas",
                value=raw,
                expected="object",
                fix="'canvas' must be a JSON object",
            )
        )
        return None
    if strict:
        for unknown in set(raw) - _CANVAS_ALLOWED_KEYS:
            errors.append(
                SpecError(
                    code="unknown_field",
                    path=f"/canvas/{unknown}",
                    value=unknown,
                    expected="one of " + ", ".join(sorted(_CANVAS_ALLOWED_KEYS)),
                    fix=f"unknown canvas field {unknown!r}; remove it (allowed: {sorted(_CANVAS_ALLOWED_KEYS)})",
                )
            )

    for field in ("width", "height"):
        if field not in raw:
            errors.append(
                SpecError(
                    code="missing_field",
                    path=f"/canvas/{field}",
                    value=None,
                    expected="integer",
                    fix=f"canvas.{field} is required (positive integer, in pixels)",
                )
            )
            continue
        v = raw[field]
        if not _is_int(v):
            errors.append(
                SpecError(
                    code="invalid_type",
                    path=f"/canvas/{field}",
                    value=v,
                    expected="integer",
                    fix=f"canvas.{field} must be a positive integer (got {type(v).__name__})",
                )
            )
        elif v <= 0:
            errors.append(
                SpecError(
                    code="out_of_range",
                    path=f"/canvas/{field}",
                    value=v,
                    expected="> 0",
                    fix=f"canvas.{field} must be positive (got {v})",
                )
            )

    if "background" in raw:
        bg = raw["background"]
        if not isinstance(bg, str):
            errors.append(
                SpecError(
                    code="invalid_type",
                    path="/canvas/background",
                    value=bg,
                    expected="string",
                    fix="canvas.background must be a color string",
                )
            )
        else:
            try:
                parse_color(bg)
            except ValueError:
                errors.append(
                    SpecError(
                        code="invalid_color",
                        path="/canvas/background",
                        value=bg,
                        expected="#RGB / #RRGGBB / #RRGGBBAA",
                        fix=f"canvas.background {bg!r} is not a valid color; use '#RGB', '#RRGGBB', or '#RRGGBBAA'",
                    )
                )

    if any(e.path.startswith("/canvas/width") or e.path.startswith("/canvas/height") for e in errors):
        return None

    return Canvas(
        width=raw["width"],
        height=raw["height"],
        background=raw.get("background", "#FFFFFF"),
    )


def _validate_boxes(
    raw_boxes: Any,
    canvas: Optional[Canvas],
    errors: list[SpecError],
    strict: bool = False,
) -> list[Box]:
    if raw_boxes is None:
        errors.append(
            SpecError(
                code="missing_field",
                path="/boxes",
                value=None,
                expected="array",
                fix="add a 'boxes' array; each element is a box with id, x, y, w, h",
            )
        )
        return []
    if not isinstance(raw_boxes, list):
        errors.append(
            SpecError(
                code="invalid_type",
                path="/boxes",
                value=raw_boxes,
                expected="array",
                fix="'boxes' must be a JSON array",
            )
        )
        return []

    seen_ids: set[str] = set()
    boxes: list[Box] = []
    for i, raw in enumerate(raw_boxes):
        box_path = f"/boxes/{i}"
        if not isinstance(raw, dict):
            errors.append(
                SpecError(
                    code="invalid_type",
                    path=box_path,
                    value=raw,
                    expected="object",
                    fix=f"{box_path} must be a JSON object",
                )
            )
            continue

        if strict:
            for unknown in set(raw) - _BOX_ALLOWED_KEYS:
                errors.append(
                    SpecError(
                        code="unknown_field",
                        path=f"{box_path}/{unknown}",
                        value=unknown,
                        expected="one of " + ", ".join(sorted(_BOX_ALLOWED_KEYS)),
                        fix=f"unknown box field {unknown!r}; remove it (allowed: {sorted(_BOX_ALLOWED_KEYS)})",
                    )
                )

        box_id = raw.get("id", "?")
        box_errors_before = len(errors)

        for field in ("id", "x", "y", "w", "h"):
            if field not in raw:
                errors.append(
                    SpecError(
                        code="missing_field",
                        path=f"{box_path}/{field}",
                        value=None,
                        expected=_expected_for(field),
                        fix=f"{box_path}.{field} ({box_id!r}) is required",
                    )
                )

        if any(f not in raw for f in ("id", "x", "y", "w", "h")):
            continue

        if not isinstance(raw["id"], str):
            errors.append(
                SpecError(
                    code="invalid_type",
                    path=f"{box_path}/id",
                    value=raw["id"],
                    expected="string",
                    fix=f"{box_path}.id must be a string",
                )
            )
        elif not raw["id"]:
            errors.append(
                SpecError(
                    code="invalid_value",
                    path=f"{box_path}/id",
                    value=raw["id"],
                    expected="non-empty string",
                    fix=f"{box_path}.id must be a non-empty string",
                )
            )
        elif raw["id"] in seen_ids:
            errors.append(
                SpecError(
                    code="duplicate_id",
                    path=f"{box_path}/id",
                    value=raw["id"],
                    expected="unique id",
                    fix=f"id {raw['id']!r} is duplicated; each box needs a unique id",
                )
            )
        else:
            seen_ids.add(raw["id"])

        coords_valid = True
        for field in ("x", "y", "w", "h"):
            v = raw[field]
            if not _is_int(v):
                errors.append(
                    SpecError(
                        code="invalid_type",
                        path=f"{box_path}/{field}",
                        value=v,
                        expected="integer",
                        fix=f"{box_path}.{field} must be an integer (got {type(v).__name__})",
                    )
                )
                coords_valid = False
            elif field in ("x", "y") and v < 0:
                errors.append(
                    SpecError(
                        code="out_of_range",
                        path=f"{box_path}/{field}",
                        value=v,
                        expected=">= 0",
                        fix=f"{box_path}.{field} must be non-negative (got {v})",
                    )
                )
                coords_valid = False
            elif field in ("w", "h") and v <= 0:
                errors.append(
                    SpecError(
                        code="out_of_range",
                        path=f"{box_path}/{field}",
                        value=v,
                        expected="> 0",
                        fix=f"{box_path}.{field} must be positive (got {v})",
                    )
                )
                coords_valid = False

        if "text" in raw and not isinstance(raw["text"], str):
            errors.append(
                SpecError(
                    code="invalid_type",
                    path=f"{box_path}/text",
                    value=raw["text"],
                    expected="string",
                    fix=f"{box_path}.text must be a string",
                )
            )

        pad = raw.get("pad", 0)
        if not _is_int(pad):
            errors.append(
                SpecError(
                    code="invalid_type",
                    path=f"{box_path}/pad",
                    value=pad,
                    expected="integer",
                    fix=f"{box_path}.pad must be an integer (got {type(pad).__name__})",
                )
            )
        elif pad < 0:
            errors.append(
                SpecError(
                    code="out_of_range",
                    path=f"{box_path}/pad",
                    value=pad,
                    expected=">= 0",
                    fix=f"{box_path}.pad must be non-negative (got {pad})",
                )
            )

        if "font" in raw and raw["font"] is not None and not isinstance(raw["font"], str):
            errors.append(
                SpecError(
                    code="invalid_type",
                    path=f"{box_path}/font",
                    value=raw["font"],
                    expected="string or null",
                    fix=f"{box_path}.font must be a string path or null",
                )
            )

        size = raw.get("size", 24)
        if not _is_int(size):
            errors.append(
                SpecError(
                    code="invalid_type",
                    path=f"{box_path}/size",
                    value=size,
                    expected="integer",
                    fix=(
                        f"`size` must be an integer (got {type(size).__name__}). "
                        f"Common mistake: writing size as a string like \"24\". "
                        f"Example: \"size\": 24 for 24-point font."
                    ),
                )
            )
        elif size <= 0:
            errors.append(
                SpecError(
                    code="out_of_range",
                    path=f"{box_path}/size",
                    value=size,
                    expected="> 0",
                    fix=(
                        f"`size` must be a positive integer (got {size}). "
                        f"Omitting `size` falls back to 24. "
                        f"Example: \"size\": 32"
                    ),
                )
            )

        if "color" in raw:
            color = raw["color"]
            if not isinstance(color, str):
                errors.append(
                    SpecError(
                        code="invalid_type",
                        path=f"{box_path}/color",
                        value=color,
                        expected="string",
                        fix=(
                            f"`color` must be a hex color string (got {type(color).__name__}). "
                            f"Example: \"color\": \"#FF0000\""
                        ),
                    )
                )
            else:
                try:
                    parse_color(color)
                except ValueError:
                    errors.append(
                        SpecError(
                            code="invalid_color",
                            path=f"{box_path}/color",
                            value=color,
                            expected="#RGB / #RRGGBB / #RRGGBBAA",
                            fix=(
                                f"`color` must be a hex color starting with '#' "
                                f"(got {color!r}). CSS color names like 'red', 'white', "
                                f"or 'rgb(255,0,0)' are NOT supported. "
                                f"Example: \"color\": \"#FF0000\" for red"
                            ),
                        )
                    )

        for field, allowed in (
            ("align", _ALIGN_VALUES),
            ("valign", _VALIGN_VALUES),
            ("fit", _FIT_VALUES),
        ):
            if field in raw:
                v = raw[field]
                if not isinstance(v, str):
                    allowed_repr = ", ".join(repr(s) for s in allowed)
                    errors.append(
                        SpecError(
                            code="invalid_type",
                            path=f"{box_path}/{field}",
                            value=v,
                            expected="string",
                            fix=(
                                f"`{field}` must be a string (got {type(v).__name__}). "
                                f"Allowed values: {allowed_repr}. "
                                f"Example: \"{field}\": \"{allowed[0]}\""
                            ),
                        )
                    )
                elif v not in allowed:
                    allowed_repr = ", ".join(repr(s) for s in allowed)
                    hint = {
                        "fit": (
                            "Use 'wrap' to word-wrap into multiple lines, "
                            "'shrink' to scale the font size down until it fits, "
                            "or 'truncate' for single-line with ellipsis on overflow."
                        ),
                        "align": (
                            "Use 'left' for left edge, 'center' for centered, "
                            "'right' for right edge."
                        ),
                        "valign": (
                            "Use 'top' for top edge, 'middle' for centered, "
                            "'bottom' for bottom edge."
                        ),
                    }.get(field, "")
                    errors.append(
                        SpecError(
                            code="invalid_enum",
                            path=f"{box_path}/{field}",
                            value=v,
                            expected=", ".join(allowed),
                            fix=(
                                f"`{field}` must be one of: {allowed_repr} "
                                f"(got {v!r}). {hint} "
                                f"Example: \"{field}\": \"{allowed[0]}\""
                            ),
                        )
                    )

        line_spacing = raw.get("line_spacing", 1.2)
        if not _is_number(line_spacing):
            errors.append(
                SpecError(
                    code="invalid_type",
                    path=f"{box_path}/line_spacing",
                    value=line_spacing,
                    expected="number",
                    fix=f"{box_path}.line_spacing must be a number (got {type(line_spacing).__name__})",
                )
            )
        elif line_spacing <= 0:
            errors.append(
                SpecError(
                    code="out_of_range",
                    path=f"{box_path}/line_spacing",
                    value=line_spacing,
                    expected="> 0",
                    fix=f"{box_path}.line_spacing must be positive (got {line_spacing})",
                )
            )

        if _is_int(pad) and pad >= 0:
            if _is_int(raw.get("w")) and pad * 2 > raw["w"]:
                errors.append(
                    SpecError(
                        code="padding_too_large",
                        path=f"{box_path}/pad",
                        value=pad,
                        expected=f"<= {raw['w'] // 2}",
                        fix=f"box {box_id!r}: pad {pad} * 2 > w {raw['w']}; reduce pad to {raw['w'] // 2} or smaller, or increase w",
                    )
                )
            if _is_int(raw.get("h")) and pad * 2 > raw["h"]:
                errors.append(
                    SpecError(
                        code="padding_too_large",
                        path=f"{box_path}/pad",
                        value=pad,
                        expected=f"<= {raw['h'] // 2}",
                        fix=f"box {box_id!r}: pad {pad} * 2 > h {raw['h']}; reduce pad to {raw['h'] // 2} or smaller, or increase h",
                    )
                )

        if canvas is not None and coords_valid:
            if raw["x"] + raw["w"] > canvas.width:
                errors.append(
                    SpecError(
                        code="out_of_bounds",
                        path=f"{box_path}/x",
                        value=f"x={raw['x']}, w={raw['w']}",
                        expected=f"x + w <= {canvas.width}",
                        fix=f"box {box_id!r}: x ({raw['x']}) + w ({raw['w']}) = {raw['x'] + raw['w']} exceeds canvas width {canvas.width}; reduce w to {canvas.width - raw['x']} or move x left",
                    )
                )
            if raw["y"] + raw["h"] > canvas.height:
                errors.append(
                    SpecError(
                        code="out_of_bounds",
                        path=f"{box_path}/y",
                        value=f"y={raw['y']}, h={raw['h']}",
                        expected=f"y + h <= {canvas.height}",
                        fix=f"box {box_id!r}: y ({raw['y']}) + h ({raw['h']}) = {raw['y'] + raw['h']} exceeds canvas height {canvas.height}; reduce h to {canvas.height - raw['y']} or move y up",
                    )
                )

        if len(errors) > box_errors_before:
            continue

        try:
            box = Box(
                id=str(raw["id"]),
                x=int(raw["x"]),
                y=int(raw["y"]),
                w=int(raw["w"]),
                h=int(raw["h"]),
                text=str(raw.get("text", "")),
                pad=int(raw.get("pad", 0)),
                font=raw.get("font") if isinstance(raw.get("font"), str) else None,
                size=int(raw.get("size", 24)),
                color=str(raw.get("color", "#FFFFFF")),
                align=str(raw.get("align", "left")),
                valign=str(raw.get("valign", "middle")),
                fit=str(raw.get("fit", "wrap")),
                line_spacing=float(raw.get("line_spacing", 1.2)),
                min_size=(
                    int(raw["min_size"])
                    if isinstance(raw.get("min_size"), int)
                    and not isinstance(raw.get("min_size"), bool)
                    else None
                ),
                char_size_steps=(
                    tuple((int(s[0]), int(s[1])) for s in raw["char_size_steps"])
                    if isinstance(raw.get("char_size_steps"), list)
                    else None
                ),
                parent=(
                    str(raw["parent"])
                    if isinstance(raw.get("parent"), str)
                    and raw["parent"]  # 空文字を除外
                    else None
                ),
            )
        except (ValueError, TypeError) as e:
            errors.append(
                SpecError(
                    code="box_construction_failed",
                    path=box_path,
                    value=str(e),
                    expected="valid box",
                    fix=f"box {box_id!r}: {e}",
                )
            )
            continue

        boxes.append(box)

    return boxes


def _expected_for(field: str) -> str:
    return {
        "id": "string",
        "x": "integer",
        "y": "integer",
        "w": "integer",
        "h": "integer",
    }.get(field, "value")


def validate_spec(data: Any, *, level: str = "schema", strict: bool = False) -> list[SpecError]:
    errors: list[SpecError] = []

    if not isinstance(data, dict):
        errors.append(
            SpecError(
                code="not_an_object",
                path="",
                value=data,
                expected="object",
                fix="spec must be a JSON object with 'canvas' and 'boxes'",
            )
        )
        return _truncate(errors)

    if strict:
        for unknown in set(data) - _ROOT_ALLOWED_KEYS:
            errors.append(
                SpecError(
                    code="unknown_field",
                    path=f"/{unknown}",
                    value=unknown,
                    expected="one of " + ", ".join(sorted(_ROOT_ALLOWED_KEYS)),
                    fix=f"unknown root field {unknown!r}; remove it (allowed: {sorted(_ROOT_ALLOWED_KEYS)})",
                )
            )

    canvas = _validate_canvas(data, errors, strict)
    boxes = _validate_boxes(data.get("boxes"), canvas, errors, strict)

    if level in ("preflight", "all"):
        _validate_preflight(data, canvas, boxes, errors)

    return _truncate(errors)


def _validate_preflight(
    data: dict[str, Any],
    canvas: Optional[Canvas],
    boxes: list[Box],
    errors: list[SpecError],
) -> None:
    for i, box in enumerate(boxes):
        box_path = f"/boxes/{i}/font"
        if box.font:
            from pathlib import Path

            if not Path(box.font).exists():
                errors.append(
                    SpecError(
                        code="font_not_found",
                        path=box_path,
                        value=box.font,
                        expected="existing file path",
                        fix=f"font file {box.font!r} does not exist; check the path or omit 'font' to use the system default",
                    )
                )


def _truncate(errors: list[SpecError]) -> list[SpecError]:
    if len(errors) > _MAX_ERRORS:
        summary = SpecError(
            code="too_many_errors",
            path="",
            value=len(errors),
            expected=f"<= {_MAX_ERRORS}",
            fix=f"validation stopped after {_MAX_ERRORS} errors; {len(errors) - _MAX_ERRORS} additional issues suppressed",
        )
        return errors[:_MAX_ERRORS] + [summary]
    return errors


def load_spec_from_mapping(data: Any, *, level: str = "schema") -> tuple[Canvas, list[Box]]:
    errors = validate_spec(data, level=level)
    if errors:
        raise errors[0]
    if not isinstance(data, dict):
        raise SpecError(
            code="not_an_object",
            path="",
            value=data,
            expected="object",
            fix="spec must be a JSON object",
        )

    raw_canvas = data["canvas"]
    canvas = Canvas(
        width=raw_canvas["width"],
        height=raw_canvas["height"],
        background=raw_canvas.get("background", "#FFFFFF"),
    )

    boxes: list[Box] = []
    for raw in data["boxes"]:
        boxes.append(
            Box(
                id=raw["id"],
                x=raw["x"],
                y=raw["y"],
                w=raw["w"],
                h=raw["h"],
                text=raw.get("text", ""),
                pad=raw.get("pad", 0),
                font=raw.get("font"),
                size=raw.get("size", 24),
                color=raw.get("color", "#FFFFFF"),
                align=raw.get("align", "left"),
                valign=raw.get("valign", "middle"),
                fit=raw.get("fit", "wrap"),
                line_spacing=raw.get("line_spacing", 1.2),
                parent=(
                    str(raw["parent"])
                    if isinstance(raw.get("parent"), str)
                    and raw["parent"]
                    else None
                ),
            )
        )

    # Step 5: box ネスト (parent) を解決
    from pailow.nesting import resolve_nesting
    boxes = resolve_nesting(boxes, errors)

    # nesting が errors を追加した場合は raise
    if errors:
        raise errors[0]

    return canvas, boxes


def load_spec(path: str | Path, *, level: str = "schema") -> tuple[Canvas, list[Box]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"spec not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SpecError(
            code="invalid_json",
            path="",
            value=str(e),
            expected="valid JSON",
            fix=f"file is not valid JSON: {e.msg} at line {e.lineno} column {e.colno}",
        ) from e

    # Step 5: spec 継承 (extends) を解決
    from pailow.inherit import resolve_inheritance
    data = resolve_inheritance(data, p.parent)

    # Step 5: タイポグラフィ presets を展開 (box 単位)
    from pailow.presets import resolve_presets
    data = resolve_presets(data)

    return load_spec_from_mapping(data, level=level)
