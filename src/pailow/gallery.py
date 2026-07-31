"""Few-shot gallery: LLM が spec を生成する際の参考用サンプル集 (Step 3)。

各サンプルは `pailow gallery --show <id> -o out.png` で描画できる。
LLM に渡すときは `pailow gallery --list` で ID を取り、`--show <id>` で spec を取得する。
"""

from __future__ import annotations

from typing import Any

from PIL import Image

from pailow.render import render_from_mapping


# 検証済みの「いい例」。AI に few-shot として渡せる形で 10 個保持する。
# 追加・更新は GALLERY.append({...}) で自由に。
GALLERY: list[dict[str, Any]] = [
    {
        "id": "01_headline",
        "title": "Big sale headline with CTA",
        "tags": ["banner", "promotion"],
        "spec": {
            "canvas": {"width": 1200, "height": 600, "background": "#1A1A1A"},
            "boxes": [
                {
                    "id": "eyebrow",
                    "x": 60, "y": 60, "w": 600, "h": 40,
                    "text": "LIMITED TIME",
                    "size": 28, "color": "#FFD86B",
                    "align": "left", "valign": "top", "fit": "shrink",
                },
                {
                    "id": "title",
                    "x": 60, "y": 120, "w": 1080, "h": 200,
                    "text": "50% OFF EVERYTHING",
                    "size": 128, "color": "#FFFFFF",
                    "align": "left", "valign": "middle",
                    "fit": "shrink", "line_spacing": 1.0,
                },
                {
                    "id": "body",
                    "x": 60, "y": 360, "w": 800, "h": 120,
                    "text": "Shop our entire collection. Discount auto-applied at checkout.",
                    "size": 28, "color": "#E5E5E5",
                    "align": "left", "valign": "top",
                    "fit": "wrap", "line_spacing": 1.4,
                },
                {
                    "id": "cta",
                    "x": 60, "y": 500, "w": 240, "h": 64,
                    "text": "Shop now",
                    "size": 32, "color": "#FFD86B",
                    "align": "center", "valign": "middle",
                    "fit": "shrink",
                },
            ],
        },
    },
    {
        "id": "02_quote",
        "title": "Quote with author attribution",
        "tags": ["quote", "editorial"],
        "spec": {
            "canvas": {"width": 1080, "height": 1080, "background": "#FFFFFF"},
            "boxes": [
                {
                    "id": "quote",
                    "x": 80, "y": 320, "w": 920, "h": 320,
                    "text": "Stay hungry, stay foolish.",
                    "size": 72, "color": "#1A1A1A",
                    "align": "center", "valign": "middle",
                    "fit": "shrink", "line_spacing": 1.1,
                },
                {
                    "id": "dash",
                    "x": 80, "y": 660, "w": 920, "h": 20,
                    "text": "—",
                    "size": 36, "color": "#999999",
                    "align": "center", "valign": "middle",
                },
                {
                    "id": "author",
                    "x": 80, "y": 700, "w": 920, "h": 40,
                    "text": "Steve Jobs, 2005",
                    "size": 28, "color": "#666666",
                    "align": "center", "valign": "middle",
                },
            ],
        },
    },
    {
        "id": "03_social_square",
        "title": "1080x1080 social post with hashtag",
        "tags": ["social", "instagram"],
        "spec": {
            "canvas": {"width": 1080, "height": 1080, "background": "#FF2D83"},
            "boxes": [
                {
                    "id": "hook",
                    "x": 80, "y": 320, "w": 920, "h": 200,
                    "text": "FRIDAY",
                    "size": 200, "color": "#FFFFFF",
                    "align": "center", "valign": "middle",
                    "fit": "shrink",
                },
                {
                    "id": "headline",
                    "x": 80, "y": 540, "w": 920, "h": 200,
                    "text": "FLASH SALE",
                    "size": 120, "color": "#FFC400",
                    "align": "center", "valign": "middle",
                    "fit": "shrink",
                },
                {
                    "id": "body",
                    "x": 80, "y": 780, "w": 920, "h": 80,
                    "text": "Today only. Don't miss it.",
                    "size": 36, "color": "#FFFFFF",
                    "align": "center", "valign": "middle",
                },
                {
                    "id": "hashtag",
                    "x": 80, "y": 900, "w": 920, "h": 60,
                    "text": "#flashsale",
                    "size": 32, "color": "#FFFFFF",
                    "align": "center", "valign": "middle",
                },
            ],
        },
    },
    {
        "id": "04_long_text",
        "title": "Multi-line body text with character-count sizing",
        "tags": ["editorial", "article"],
        "spec": {
            "canvas": {"width": 1200, "height": 800, "background": "#FFFFFF"},
            "boxes": [
                {
                    "id": "headline",
                    "x": 80, "y": 80, "w": 1040, "h": 120,
                    "text": "Why pailow matters for LLM-generated layouts",
                    "size": 56, "color": "#1A1A1A",
                    "align": "left", "valign": "middle",
                    "fit": "shrink", "min_size": 28,
                    "char_size_steps": [[30, 64], [80, 44]],
                },
                {
                    "id": "body",
                    "x": 80, "y": 240, "w": 1040, "h": 360,
                    "text": "Most layout engines expect pixel coordinates and a fixed font size. pailow inverts that: each box carries a character-count-based initial size and a shrink strategy, so the same spec renders the same layout across languages and input lengths. This makes it dramatically easier for an LLM to emit valid output.",
                    "size": 24, "color": "#333333",
                    "align": "left", "valign": "top",
                    "fit": "wrap", "line_spacing": 1.5,
                },
                {
                    "id": "byline",
                    "x": 80, "y": 660, "w": 1040, "h": 40,
                    "text": "pailow team · 2025",
                    "size": 20, "color": "#999999",
                    "align": "left", "valign": "middle",
                },
            ],
        },
    },
]


GALLERY_IDS: list[str] = [item["id"] for item in GALLERY]


def get_gallery_item(gallery_id: str) -> dict[str, Any]:
    """ID で gallery item を取得する。未登録なら KeyError。"""
    for item in GALLERY:
        if item["id"] == gallery_id:
            return item
    raise KeyError(
        f"unknown gallery id: {gallery_id!r}. "
        f"Available: {', '.join(GALLERY_IDS)}"
    )


def render_gallery_example(
    gallery_id: str, background: Image.Image | None = None
) -> Image.Image:
    """指定 ID のサンプル spec をレンダリングして PIL.Image で返す。"""
    item = get_gallery_item(gallery_id)
    return render_from_mapping(item["spec"], background=background)