---
name: pailow
description: "画像に文字を重ねる・文字の位置を測る・既存PNGのレイアウトを検証する。Use when: 画像に文字を乗せたい、バナー/サムネ/OGP画像を作りたい、文字がはみ出している/見えない/ズレている、既存の描画パイプラインの出力を数値で検証したい、といわれたとき。テキスト以外の描画（図形・写真加工・フィルタ）には使わない。"
---

# pailow — 画像の文字レイアウトを「測って直す」

pailow は **Pillow の強化版**として使う CLI + Python ライブラリ。
JSON の spec（canvas + boxes）から決定的に PNG を描き、さらに
**描画後の実ピクセルを測って「どこがどうズレているか」を数値で返す**。

## いつ使うか

- 画像に文字を載せたい（バナー、サムネ、OGP、セール画像）
- 「文字がはみ出している」「背景と同色で見えない」「位置がズレている」を直したい
- 既存パイプラインが出した PNG のレイアウトを、テストで数値検証したい

**使わない**: 図形・帯・グラデーション・写真加工。pailow は text 専門で、
`text` が空の box は描画されない（矩形塗りはできない）。

## 3つの使い方

| 目的 | 手段 | 描くか |
|---|---|---|
| spec から画像を作る | `pailow render` / `render_from_mapping` | 描く |
| spec を描いて**測る** | `pailow inspect` / `inspect_from_mapping` | 描いて測る |
| 他所が出した画像を**測るだけ** | `pailow.measure_image` | 描かない |

## CLI の基本ループ

```bash
pailow validate spec.json              # 1. 構造の検証（全エラーを1パスで返す）
pailow fit spec.json --json            # 2. フォントメトリクスでの予測（描かない）
pailow render spec.json -i bg.png -o out.png   # 3. 描画
pailow inspect spec.json -i bg.png --json      # 4. 実ピクセルで測定
pailow inspect spec.json -i bg.png --fix --loop 3   # 5. 安全な修正だけ自動適用
```

`inspect` の読み方（`--json` の `boxes[]`）:

| フィールド | 意味 |
|---|---|
| `inner` | 意図した内側矩形（pad を引いた領域） |
| `painted` | **実測したインク矩形**（無ければ `null`） |
| `overflow` | はみ出し量（`{"right": 13}`）。±2px は許容で error にしない |
| `collisions` | 他の box のインクとの交差 |
| `contrast` | 実測背景に対する WCAG 比（4.5 未満で warning） |
| `findings` | `overflow` / `collision` / `invisible` / `contrast` / `min_size` / `box_too_small` / `outside_canvas` |
| `suggestions` | `set_size` / `set_min_size` / `set_color`（`auto: true` のみ `--fix` が適用） |

exit code: `0` 問題なし / `1` 指摘あり / `2` `--fix` 後も自動修正可能な指摘が残る。

### 目で見て確認する

```bash
pailow inspect spec.json -i bg.png --annotate debug.png
```

破線 = 意図した矩形 / 実線 = 実測インク / 赤 = 衝突。
エージェントが「見た」証拠としてこの画像を残す。

## spec の最小形

```json
{
  "canvas": {"width": 1200, "height": 630, "background": "#1A1A1A"},
  "boxes": [
    {"id": "title", "x": 64, "y": 80, "w": 1072, "h": 200,
     "text": "50% OFF", "size": 128, "color": "#FFFFFF",
     "align": "left", "valign": "middle", "fit": "shrink", "min_size": 24}
  ]
}
```

- `fit`: `wrap`（折り返し）/ `shrink`（縮小して収める）/ `truncate`（…で切る）
- `color: "auto"` は背景輝度から黒/白を選ぶ
- 使えるフィールドの正は `pailow schema --pretty`。迷ったら `pailow new out.json` から始める

## 既存パイプラインの出力をテストで検証する

`measure_image` は描画しないので、本番コードが pailow に依存しない。

```python
from pailow import measure_image

report = measure_image(
    "out/01_poster.png",                 # パイプラインの出力
    [{"id": "title", "x": 40, "y": 90, "w": 1120, "h": 240, "pad": 8}],
    background="out/01_poster_bg.png",   # 同サイズ・文字抜き（省略時は bg_color 単色）
)
box = report["boxes"][0]
assert box["painted"] is not None          # 文字が描かれている
assert not box["overflow"], box["overflow"]  # はみ出していない
assert box["contrast"] >= 4.5              # 読める
```

- `suggested_adjust` = `{"dx", "dy", "resize_required"}`。片側はみ出しを最小移動で直す値
- 両側にはみ出すと `resize_required: true`（移動では直らない → サイズ側の仕事）
- 探索窓は box の矩形。外へ大きくはみ出すなら `margin=N` を渡す

## ハマりどころ

- **図形は描けない**。帯・下地は Pillow 側で作る
- **フォントを明示する**（`"font": "/path/to/font.ttf"`）。既定はシステムフォント探索なので、
  CI（Linux）と手元（macOS）で測定値がズレる
- `fit` は**予測**、`inspect` は**実測**。見た目を保証したいなら `inspect`
- `--fix` が触るのは `size` / `min_size` / `color` だけ。`collision` と `box_too_small` は
  意図を壊すので自動適用しない（自分で判断する）
- Pillow 13 以上が必要（`pillow>=13.0.0`）

## もっと詳しく

- spec の全フィールド: `pailow schema --pretty` / `pailow schema` の Markdown 版は `--md`
- 例: `pailow gallery --list` → `pailow gallery --show <id>`
- LLM 向け契約: リポジトリの `SKILL.md` / `docs/prompt.md`
