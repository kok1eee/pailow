"""Render history (Step 4): watch の各レンダリングを保存して遡れるようにする。"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Optional


DEFAULT_HISTORY_DIR = Path(".pailow") / "history"
DEFAULT_MAX_KEEP = 50


def get_history_dir(base_dir: Optional[Path] = None) -> Path:
    """履歴ディレクトリを返す (無ければ作る)。"""
    hdir = base_dir if base_dir is not None else DEFAULT_HISTORY_DIR
    hdir.mkdir(parents=True, exist_ok=True)
    return hdir


def save_to_history(
    png_path: Path,
    spec_path: Optional[Path] = None,
    history_dir: Optional[Path] = None,
    max_keep: int = DEFAULT_MAX_KEEP,
) -> Path:
    """png を履歴ディレクトリにコピーして新しいパスを返す。

    spec があれば一緒にコピー。max_keep を超えたら古いものから削除。
    """
    hdir = get_history_dir(history_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    history_id = f"{timestamp}-{png_path.stem}"
    target = hdir / f"{history_id}.png"
    shutil.copy2(png_path, target)

    if spec_path is not None and spec_path.exists():
        spec_target = hdir / f"{history_id}.json"
        shutil.copy2(spec_path, spec_target)

    _prune_history(hdir, max_keep)
    return target


def _prune_history(hdir: Path, max_keep: int) -> None:
    """古い履歴を max_keep 件までに保つ。"""
    files = sorted(hdir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[max_keep:]:
        old.unlink()
        spec_old = old.with_suffix(".json")
        if spec_old.exists():
            spec_old.unlink()


def list_history(history_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """履歴を新しい順に並べて返す。各要素は id / png / spec / mtime / size。

    タイムスタンプ prefix (`YYYYMMDD-HHMMSS-`) 付きのファイルのみを対象とする。
    """
    import re

    pattern = re.compile(r"^\d{8}-\d{6}-")
    hdir = get_history_dir(history_dir)
    items = []
    for png in sorted(hdir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not pattern.match(png.stem):
            continue
        spec = png.with_suffix(".json")
        items.append(
            {
                "id": png.stem,
                "png": str(png),
                "spec": str(spec) if spec.exists() else None,
                "mtime": png.stat().st_mtime,
                "size": png.stat().st_size,
            }
        )
    return items


def get_history_entry(history_id: str, history_dir: Optional[Path] = None) -> dict[str, Any]:
    """ID で履歴エントリを取得する。未登録なら KeyError。"""
    for item in list_history(history_dir):
        if item["id"] == history_id:
            return item
    raise KeyError(f"history id not found: {history_id!r}")