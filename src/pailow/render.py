from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional, Union

from PIL import Image, ImageDraw, ImageFont

from pailow.box import Box, Canvas, parse_color
from pailow.errors import SpecError


# FreeType はフォントによって極小サイズ (概ね 7px 以下) の計測に失敗するため、
# shrink 時の縮小下限を確保する。
_MIN_SHRINK_SIZE = 8.0

_FONT_CANDIDATES = [
    "/usr/share/fonts/urw-base35/NimbusSans-Regular.otf",
    "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/google-noto/NotoSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def find_default_font_path() -> Optional[str]:
    for c in _FONT_CANDIDATES:
        if Path(c).exists():
            return c
    if shutil.which("fc-match"):
        try:
            result = subprocess.run(
                ["fc-match", "-f", "%{file}", "sans"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                if path and Path(path).exists():
                    return path
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def load_font(box: Box, size: Optional[float] = None) -> ImageFont.FreeTypeFont:
    s = box.size if size is None else size
    if box.font:
        path = Path(box.font)
        if not path.exists():
            raise SpecError(
                code="font_not_found",
                path=f"/boxes/{box.id}/font",
                value=box.font,
                expected="existing file path",
                fix=f"font file {box.font!r} does not exist; check the path or omit 'font' to use the system default",
            )
        return ImageFont.truetype(str(path), int(round(s)))
    system_font = find_default_font_path()
    if not system_font:
        raise SpecError(
            code="no_default_font",
            path="",
            value=None,
            expected="system font",
            fix=(
                "no system font is available; specify 'font' on every box, "
                "or install a font (e.g., fonts-liberation, fonts-dejavu, fonts-noto)"
            ),
        )
    return ImageFont.truetype(system_font, int(round(s)))


def line_height(font: ImageFont.FreeTypeFont, spacing: float) -> int:
    ascent, descent = font.getmetrics()
    return int(round((ascent + descent) * spacing))


def _auto_text_color(img: Image.Image, box: Box) -> tuple[int, int, int, int]:
    """box 領域の平均輝度から適切な文字色 (黒 or 白) を返す (Step 5: smart color)。

    背景が明るければ黒、背景が暗ければ白を返す。
    輝度の境界値は 128。
    """
    region = img.crop((box.x, box.y, box.x + box.w, box.y + box.h)).convert("RGB")
    pixels = list(region.get_flattened_data())
    if not pixels:
        return (0, 0, 0, 255)
    avg_lum = sum((0.299 * r + 0.587 * g + 0.114 * b) for r, g, b in pixels) / len(pixels)
    return (0, 0, 0, 255) if avg_lum > 128 else (255, 255, 255, 255)


def wrap_lines_fixed(text: str, char_wrap: int) -> list[str]:
    """text を char_wrap 文字ごとに強制改行する（幅は見ない）。

    「短いボックスで N 文字がちょうど1行に収まる」体験を、大きいボックスでも
    N 文字ごとの改行として再現したい場合に使う（fit=shrink と併用し、縦方向の
    フォントサイズ調整は shrink に任せる）。
    """
    if not text:
        return [""]
    return [text[i : i + char_wrap] for i in range(0, len(text), char_wrap)] or [""]


def wrap_lines(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int
) -> list[str]:
    """テキストを max_w に収まるように複数行に折り返す。

    0. 明示的な改行 (\n) はそのまま行区切りとして尊重する
    1. まず半角/全角スペース区切りで折り返し (英語向け)
    2. それでも max_w を超える行があれば、文字種変更位置や句読点で折り返し (日本語向け)
    """
    if not text:
        return [""]
    if "\n" in text:
        wrapped: list[str] = []
        for paragraph in text.split("\n"):
            wrapped.extend(wrap_lines(draw, paragraph, font, max_w) if paragraph else [""])
        return wrapped
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = current + " " + word
        if draw.textlength(trial, font=font) <= max_w:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)

    # 日本語対応: max_w を超える行があれば文字単位 + 文字種変更位置で折り返し
    result: list[str] = []
    for line in lines:
        if draw.textlength(line, font=font) <= max_w:
            result.append(line)
            continue
        result.extend(_wrap_japanese(draw, line, font, max_w))
    return result


# 句読点・記号など、この文字の直後は改行候補として優先する
_BREAK_AFTER = set("。、！？!?,.．;:：\n")


def _wrap_japanese(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int
) -> list[str]:
    """日本語向け折り返し。文字単位で max_w を確認し、句読点や文字種変更位置で改行。"""
    if not text:
        return [""]

    def _char_kind(ch: str) -> str:
        cp = ord(ch)
        # ひらがな・カタカナ・CJK・全角記号
        if (
            0x3040 <= cp <= 0x309F  # ひらがな
            or 0x30A0 <= cp <= 0x30FF  # カタカナ
            or 0x3400 <= cp <= 0x4DBF  # CJK 拡張 A
            or 0x4E00 <= cp <= 0x9FFF  # CJK 統合漢字
            or 0xFF00 <= cp <= 0xFFEF  # 全角
        ):
            return "wide"
        if ch.isalnum() or ch == " ":
            return "ascii"
        return "other"

    lines: list[str] = []
    current = ""
    prev_kind = _char_kind(text[0]) if text else ""

    for char in text:
        kind = _char_kind(char)
        # 折り返し候補: 句読点の直後、または文字種が変わるところ
        can_break_here = (
            prev_char in _BREAK_AFTER
            if (current and (prev_char := current[-1]) is not None)
            else False
        ) or (current and prev_kind != kind and kind == "wide")

        trial = current + char
        if draw.textlength(trial, font=font) <= max_w:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
        prev_kind = kind
        prev_char = char

    if current:
        lines.append(current)

    return lines


def truncate_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int
) -> str:
    if not text:
        return ""
    if draw.textlength(text, font=font) <= max_w:
        return text
    ellipsis = "…"
    if draw.textlength(ellipsis, font=font) > max_w:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid] + ellipsis
        if draw.textlength(candidate, font=font) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ellipsis if lo > 0 else ellipsis


def _initial_size_for(box: Box) -> float:
    """文字数ベースの char_size_steps があればそれを適用した初期サイズを返す。"""
    initial = float(box.size)
    if box.char_size_steps:
        n = len(box.text)
        for max_chars, size in box.char_size_steps:
            if n <= max_chars:
                return float(size)
    return initial


def fit_text(
    box: Box,
    inner_w: int,
    inner_h: int,
    draw: ImageDraw.ImageDraw,
) -> tuple[ImageFont.FreeTypeFont, list[str], float]:
    if not box.text:
        return load_font(box), [""], float(box.size)

    initial_size = _initial_size_for(box)

    if box.fit == "wrap":
        font = load_font(box, initial_size)
        return font, wrap_lines(draw, box.text, font, inner_w), initial_size

    if box.fit == "shrink":
        min_size = float(box.min_size) if box.min_size is not None else 1.0
        floor_size = max(min_size, _MIN_SHRINK_SIZE)

        # char_wrap 指定時: N 文字ごとに強制改行し、そのレイアウトが縦横に
        # 収まる最大サイズを探す（幅基準の自動折り返しは行わない）。
        if box.char_wrap:
            lines = wrap_lines_fixed(box.text, box.char_wrap)
            size = initial_size
            while size >= floor_size:
                font = load_font(box, size)
                max_line_w = max((draw.textlength(line, font=font) for line in lines), default=0)
                lh = line_height(font, box.line_spacing)
                total_h = len(lines) * lh
                if max_line_w <= inner_w and total_h <= inner_h:
                    return font, lines, size
                size -= 1
            font = load_font(box, int(floor_size))
            return font, lines, floor_size

        # 優先パス: 単語区切りの無い言語（日本語等）で末尾1文字だけが次行に
        # あふれる見苦しいレイアウトを避けるため、まず「1行に収まる」サイズを
        # 優先的に探す。明示的な改行を含むテキストは1行になり得ないため対象外。
        if "\n" not in box.text:
            size = initial_size
            while size >= floor_size:
                font = load_font(box, size)
                line_w = draw.textlength(box.text, font=font)
                lh = line_height(font, box.line_spacing)
                if line_w <= inner_w and lh <= inner_h:
                    return font, [box.text], size
                size -= 1

        # フォールバック: 1行に収まるサイズが無ければ複数行を許容して探す。
        size = initial_size
        while size >= floor_size:
            font = load_font(box, size)
            lines = wrap_lines(draw, box.text, font, inner_w)
            max_line_w = max((draw.textlength(line, font=font) for line in lines), default=0)
            lh = line_height(font, box.line_spacing)
            total_h = len(lines) * lh
            if max_line_w <= inner_w and total_h <= inner_h:
                return font, lines, size
            size -= 1
        # 縮小下限でも収まらなかった場合は下限サイズのフォントを返す（オーバーフロー）
        font = load_font(box, int(floor_size))
        return font, wrap_lines(draw, box.text, font, inner_w), floor_size

    if box.fit == "truncate":
        font = load_font(box, initial_size)
        return font, [truncate_text(draw, box.text, font, inner_w)], initial_size

    raise ValueError(f"unknown fit strategy: {box.fit!r}")


def analyze(box: Box, draw: ImageDraw.ImageDraw) -> dict:
    if not box.text:
        return {
            "box_id": box.id,
            "fits": True,
            "lines": 0,
            "chars": 0,
            "used_w": 0,
            "used_h": 0,
            "capacity": 0,
            "font_size": float(box.size),
            "strategy": box.fit,
        }

    inner_w = box.w - 2 * box.pad
    inner_h = box.h - 2 * box.pad
    if inner_w <= 0 or inner_h <= 0:
        return {
            "box_id": box.id,
            "fits": False,
            "lines": 0,
            "chars": len(box.text),
            "used_w": 0,
            "used_h": 0,
            "capacity": 0,
            "font_size": float(box.size),
            "strategy": box.fit,
            "error": "box too small for padding",
        }

    font, lines, final_size = fit_text(box, inner_w, inner_h, draw)

    used_w = int(max((draw.textlength(line, font=font) for line in lines), default=0))
    lh = line_height(font, box.line_spacing)
    used_h = len(lines) * lh

    cap_w = draw.textlength("M", font=font)
    capacity = int(inner_w // cap_w) if cap_w > 0 else 0

    fits = (used_w <= inner_w) and (used_h <= inner_h)

    return {
        "box_id": box.id,
        "fits": fits,
        "lines": len(lines),
        "chars": len(box.text),
        "used_w": used_w,
        "used_h": used_h,
        "capacity": capacity,
        "font_size": int(round(final_size)),
        "strategy": box.fit,
    }


def render(
    canvas: Canvas,
    boxes: list[Box],
    background: Optional[Image.Image] = None,
    draw_boxes: bool = False,
) -> Image.Image:
    if background is not None:
        if background.size != (canvas.width, canvas.height):
            raise SpecError(
                code="background_size_mismatch",
                path="/background",
                value=str(background.size),
                expected=f"({canvas.width}, {canvas.height})",
                fix=(
                    f"background image is {background.size[0]}x{background.size[1]} "
                    f"but canvas is {canvas.width}x{canvas.height}; "
                    f"resize the image or change canvas.width / canvas.height"
                ),
            )
        img = background.convert("RGBA")
    else:
        bg = parse_color(canvas.background)
        img = Image.new("RGBA", (canvas.width, canvas.height), bg)

    draw = ImageDraw.Draw(img)

    for box in boxes:
        if not box.text:
            if draw_boxes:
                _draw_debug_outline(draw, box)
            continue
        inner_x = box.x + box.pad
        inner_y = box.y + box.pad
        inner_w = box.w - 2 * box.pad
        inner_h = box.h - 2 * box.pad
        if inner_w <= 0 or inner_h <= 0:
            continue

        font, lines, _ = fit_text(box, inner_w, inner_h, draw)
        if box.color == "auto":
            color = _auto_text_color(img, box)
        else:
            color = parse_color(box.color)
        lh = line_height(font, box.line_spacing)
        total_h = len(lines) * lh

        if box.valign == "top":
            start_y = inner_y
        elif box.valign == "bottom":
            start_y = inner_y + inner_h - total_h
        else:
            start_y = inner_y + (inner_h - total_h) // 2

        for i, line in enumerate(lines):
            line_w = draw.textlength(line, font=font)
            if box.align == "left":
                x = inner_x
            elif box.align == "right":
                x = inner_x + inner_w - line_w
            else:
                x = inner_x + (inner_w - line_w) // 2
            y = start_y + i * lh
            draw.text((x, y), line, font=font, fill=color)

        if draw_boxes:
            _draw_debug_outline(draw, box)

    return img


def _resolve_background(
    canvas: Canvas,
    background: Union[None, Image.Image, str, Path],
) -> Optional[Image.Image]:
    if background is None:
        return None
    if isinstance(background, Image.Image):
        return background
    p = Path(background)
    if not p.exists():
        raise SpecError(
            code="background_not_found",
            path="/background",
            value=str(background),
            expected="existing file path",
            fix=f"background image {str(background)!r} does not exist",
        )
    try:
        return Image.open(p)
    except Exception as e:
        raise SpecError(
            code="background_open_failed",
            path="/background",
            value=str(background),
            expected="readable image",
            fix=f"failed to open background image {str(background)!r}: {e}",
        ) from e


def render_from_mapping(
    spec: Any,
    background: Union[None, Image.Image, str, Path] = None,
    draw_boxes: bool = False,
    *,
    level: str = "preflight",
) -> Image.Image:
    """Render a spec mapping (or path) directly to a Pillow image.

    Equivalent to calling load_spec_from_mapping + render, but accepts a
    spec dict, file path string, or Path.
    """
    from pailow.layout import load_spec_from_mapping, validate_spec

    if isinstance(spec, (str, Path)):
        from pailow.layout import load_spec

        canvas, boxes = load_spec(spec, level=level)
    else:
        canvas, boxes = load_spec_from_mapping(spec, level=level)

    bg = _resolve_background(canvas, background)
    return render(canvas, boxes, background=bg, draw_boxes=draw_boxes)


def analyze_from_mapping(
    spec: Any,
    *,
    level: str = "preflight",
) -> list[dict[str, Any]]:
    """Analyze a spec mapping (or path) and return per-box fit diagnostics."""
    from PIL import Image as PILImage

    from pailow.layout import load_spec_from_mapping, load_spec

    if isinstance(spec, (str, Path)):
        canvas, boxes = load_spec(spec, level=level)
    else:
        canvas, boxes = load_spec_from_mapping(spec, level=level)

    dummy = PILImage.new("RGB", (canvas.width, canvas.height))
    draw = ImageDraw.Draw(dummy)
    return [analyze(box, draw) for box in boxes]


def _draw_debug_outline(
    draw: ImageDraw.ImageDraw,
    box: Box,
) -> None:
    draw.rectangle(
        [box.x, box.y, box.x + box.w - 1, box.y + box.h - 1],
        outline=(255, 0, 0, 255),
        width=2,
    )
    if box.pad > 0:
        ix = box.x + box.pad
        iy = box.y + box.pad
        iw = box.w - 2 * box.pad
        ih = box.h - 2 * box.pad
        draw.rectangle(
            [ix, iy, ix + iw - 1, iy + ih - 1],
            outline=(0, 200, 0, 255),
            width=1,
        )
