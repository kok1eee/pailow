# g-mw34eb32 — implementation log

design.md は designing で凍結。実装中の決定・逸脱・進捗はここに追記する。

## 実装順（完了）

1. `render.py` — `BoxLayout` / `layout_box()` / `draw_layout()` を抽出。`render()` は
   `layout_box()` 経由に置換（198 tests green を維持して挙動不変を確認）
2. `inspect.py` — 背景のみ + box 単独の RGBA 差分（閾値 8）、片側 overflow ±2px、
   collision、invisible、contrast（backdrop の median + WCAG）、min_size、
   box_too_small、outside_canvas
3. `suggest.py` — `set_size` / `set_min_size` / `set_color`、`apply_suggestions`、
   `spec_hash`
4. `annotate.py` — ASCII ラベル、破線、`alpha_composite`、clamp
5. `cli.py` — `inspect`（`--json` / `--annotate` / `--label-font` / `--fix` / `--fix-out` / `--loop`）
6. `__init__.py` — `inspect_spec` / `inspect_from_mapping` / `inspect_canvas` / `layout_box`
7. tests — `test_inspect.py`（11）と `test_annotate.py`（8）。合計 217 passed

## 設計からの逸脱（意図的）

| 設計 | 実装 | 理由 |
|---|---|---|
| `--fix [PATH]`（任意値） | `--fix` + `--fix-out <PATH>` | typer は任意値オプションを表現できない。既定 `<stem>.fixed.json` は維持 |
| `line_density` 警告 | **削除** | ピクセル計測ではなく spec の静的検査。scope creep の指摘を受け削除 |
| `align_drift` / `valign_drift` | `severity: info` で実装 | フォントのベアリング/リーディングで完全対称は不可能。warning にすると正常描画が常時失敗する |
| contrast の背景 | **backdrop（その box を描く直前の累積画像）の median** | `bg_only` だと手前の box のインクを無視してしまう。`auto` が見る画像と一致させる |
| `outside_canvas` | メトリクス推定 **かつ** 実インクが canvas 端に到達している場合のみ | ディセンダだけで誤検知するのを防ぐ |

## 追加した安全策

- `set_size` の初期候補に **実測 overflow からの線形推定** `size * inner_w / (inner_w + overflow)`
  を使い、そこから `layout_box`/`fit_text` で下行探索する（メトリクスだけだと
  「メトリクスは収まるがインクは溢れる」ケースで 1px ずつしか縮まない）
- 収束ループの `seen` に **元 spec のハッシュを初期値として投入**（A→B→A の初回検出）

## 既知の制約

- 1 box ずつ描いて測るため描画は O(N)。N < 50 を想定
- `_bg_rgb` は `Image.getdata()` を使うため Pillow 14 で DeprecationWarning（既存コードと同じ）
- `parent` は v1 では無視（`render()` も参照していない）

## 副産物: 実バグの発見

`examples/sale.json` と `examples/gallery/01_poster.json` の `cta` box は
文字色 `#1A1A1A` が背景 `#1A1A1A` と同色で、**実際に不可視**。`inspect` が検出した
（`--fix` で `#FFFFFF` に直り contrast 17.4 になることを確認）。examples の修正は
本 goal のスコープ外として未対応。
