"""Box nesting (Step 5).

box.parent で親 box を指定すると、子の x/y は親 box の
pad 内側を基準とした相対座標になる (CSS position: relative 風)。

例:
  {
    "boxes": [
      {"id": "card", "x": 100, "y": 100, "w": 400, "h": 200, "pad": 20},
      {"id": "title", "parent": "card", "x": 0, "y": 0, "w": 360, "h": 60}
    ]
  }

title は card の pad 20px 内側 (つまり (120, 120) 起点) を (0, 0) として描画される。
結果として title は (120, 120) - (480, 180) の位置にレンダリングされる。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from pailow.box import Box
from pailow.errors import SpecError


def resolve_nesting(
    boxes: list[Box],
    errors: list[SpecError],
    box_path_prefix: str = "/boxes",
) -> list[Box]:
    """box.parent を解決して絶対座標の Box を返す。

    - parent がない box はそのまま
    - parent がある box は親 pad 内側基準で絶対座標に変換
    - 存在しない parent / 循環 / 親が小さすぎる場合は errors に追加
    - 解決後、box.parent は None にリセット
    """
    if not any(b.parent for b in boxes):
        return boxes

    by_id = {b.id: b for b in boxes}

    result: list[Box] = []
    for i, b in enumerate(boxes):
        if b.parent is None:
            result.append(b)
            continue

        parent = by_id.get(b.parent)
        if parent is None:
            errors.append(
                SpecError(
                    code="invalid_parent",
                    path=f"{box_path_prefix}/{i}/parent",
                    value=b.parent,
                    expected="existing box id",
                    fix=(
                        f"box {b.id!r} has parent {b.parent!r} but no box with that id. "
                        f"Define a box with id {b.parent!r} first, or remove the parent field."
                    ),
                )
            )
            result.append(b)
            continue

        parent_inner_w = parent.w - 2 * parent.pad
        parent_inner_h = parent.h - 2 * parent.pad
        if parent_inner_w <= 0 or parent_inner_h <= 0:
            errors.append(
                SpecError(
                    code="parent_too_small",
                    path=f"{box_path_prefix}/{i}/parent",
                    value=parent.id,
                    expected="positive inner size (w - 2*pad > 0, h - 2*pad > 0)",
                    fix=(
                        f"parent {parent.id!r} (w={parent.w}, h={parent.h}, pad={parent.pad}) "
                        f"is too small for nested box {b.id!r}; reduce pad or enlarge parent"
                    ),
                )
            )
            result.append(b)
            continue

        new_x = parent.x + parent.pad + b.x
        new_y = parent.y + parent.pad + b.y
        result.append(replace(b, x=new_x, y=new_y, parent=None))

    return result