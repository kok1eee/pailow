"""Spec / image diff utilities (Step 4)."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from PIL import Image


def diff_specs(spec1_path: Path, spec2_path: Path) -> str:
    """2 つの spec を unified diff 形式で返す。

    JSON を再整形してから比較するので、空白や key 順が違う spec でも
    実質的な変更箇所だけを diff として出せる。
    """
    a = json.loads(spec1_path.read_text(encoding="utf-8"))
    b = json.loads(spec2_path.read_text(encoding="utf-8"))
    a_lines = json.dumps(a, indent=2, ensure_ascii=False).splitlines(keepends=True)
    b_lines = json.dumps(b, indent=2, ensure_ascii=False).splitlines(keepends=True)
    diff = difflib.unified_diff(
        a_lines, b_lines,
        fromfile=str(spec1_path), tofile=str(spec2_path),
    )
    return "".join(diff)


def diff_images(img1_path: Path, img2_path: Path) -> dict[str, Any]:
    """2 つの画像を比較してサイズと pixel diff の統計を返す。

    出力 dict:
      - image1, image2: パス
      - size1, size2: (w, h)
      - status: "identical" | "size_mismatch" | "different"
      - mean_abs_diff: 平均絶対差 (R+G+B の差分の合計)
      - identical_pixels: 完全に一致したピクセル数
      - total_pixels: 総ピクセル数
    """
    a = Image.open(img1_path).convert("RGB")
    b = Image.open(img2_path).convert("RGB")

    result: dict[str, Any] = {
        "image1": str(img1_path),
        "image2": str(img2_path),
        "size1": a.size,
        "size2": b.size,
    }

    if a.size != b.size:
        result["status"] = "size_mismatch"
        return result

    a_data = list(a.get_flattened_data())
    b_data = list(b.get_flattened_data())
    diffs = [
        abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
        for (r1, g1, b1), (r2, g2, b2) in zip(a_data, b_data)
    ]

    total = len(diffs)
    identical = sum(1 for d in diffs if d == 0)
    result["identical_pixels"] = identical
    result["total_pixels"] = total
    result["mean_abs_diff"] = sum(diffs) / total if total else 0
    result["max_abs_diff"] = max(diffs) if diffs else 0

    if identical == total:
        result["status"] = "identical"
    else:
        result["status"] = "different"

    return result