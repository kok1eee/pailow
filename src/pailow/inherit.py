"""Spec inheritance (Step 5).

base spec + overrides でバリエーション量産。

例:
  base.json
    {
      "canvas": {"width": 1200, "height": 800, "background": "#1A1A1A"},
      "boxes": [{"id": "title", "x": 60, "y": 60, "w": 1080, "h": 200, "text": "Title", "size": 64}]
    }

  variant.json
    {
      "extends": "base.json",
      "canvas": {"background": "#FF2D83"},
      "boxes": [{"id": "title", "text": "Sale!"}]
    }

variant.json を resolve すると title は overrides され、background が置換されたものになる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


def resolve_inheritance(
    spec: dict[str, Any],
    base_dir: Path,
    seen: Optional[set[Path]] = None,
) -> dict[str, Any]:
    """spec の `extends` を再帰的に解決してマージ済み dict を返す。

    - `extends` は base_dir からの相対パス (絶対パスも可)
    - 循環継承は ValueError
    - dict は再帰マージ
    - `boxes` フィールドは id ベースで deep merge
    - その他の list は上書き
    - `extends` キーは結果から取り除かれる
    """
    if seen is None:
        seen = set()

    if not isinstance(spec, dict):
        return spec

    extends = spec.pop("extends", None)
    if extends is None:
        return spec

    base_path = (base_dir / extends).resolve()
    if base_path in seen:
        raise ValueError(
            f"circular spec inheritance detected: {base_path} (chain: {[str(p) for p in seen]})"
        )
    seen.add(base_path)

    if not base_path.exists():
        raise FileNotFoundError(f"base spec not found: {base_path}")

    base = json.loads(base_path.read_text(encoding="utf-8"))
    base = resolve_inheritance(base, base_path.parent, seen)

    return _deep_merge(base, spec)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深いマージ: dict は再帰、boxes は id ベースで deep merge。"""
    result = dict(base)
    for key, val in override.items():
        if key == "boxes" and isinstance(val, list):
            result["boxes"] = _merge_boxes(base.get("boxes", []), val)
        elif key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _merge_boxes(
    base_boxes: list[dict[str, Any]], override_boxes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """boxes を id で deep merge。

    - override に同じ id があれば base の box と deep merge
    - override に新しい id があれば追加
    - base にしかない id はそのまま残す
    """
    base_by_id = {b.get("id"): b for b in base_boxes if isinstance(b, dict)}
    override_ids = {o.get("id") for o in override_boxes if isinstance(o, dict)}

    result: list[dict[str, Any]] = []
    for over in override_boxes:
        over_id = over.get("id") if isinstance(over, dict) else None
        if over_id and over_id in base_by_id:
            result.append(_deep_merge(base_by_id[over_id], over))
        else:
            result.append(over)
    for b in base_boxes:
        bid = b.get("id") if isinstance(b, dict) else None
        if bid is not None and bid not in override_ids:
            result.append(b)
    return result