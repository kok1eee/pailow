# pailow — `inspect`: 実ピクセル測定と修正ループ

goal id: g-mw34eb32

## goal理解

ユーザーの依頼は「pailow に統合しようか。pailow は完全に Pillow の強化版ってイメージ。
画像を見てループを回して、正しいと思われる位置を言ってほしい」。
解釈は次の 3 点。

- pailow の identity を **「Pillow の強化版」** に確定する。絶対座標 + Canvas/Box モデルと
  PNG 出力を正とし、Pillow に無い「測定・検証・自動修正」を足す。
- 新機能は **`inspect`**: 描画 → 実ピクセル測定 → 「正しい位置」を数値で提示 → 直すループ。
- agentloupe は archived。HTML レンダラは取り込まない。

提供する体験は「描く → 測る → 数値で言われる → 直す → また測る」。

## 現状

pailow には既に 12 コマンドがある(`new` / `fit` / `render` / `schema` / `validate` /
`prompt` / `gallery` / `watch` / `tui` / `diff` / `history` / `batch`)が、
測定は **フォントメトリクスによる予測** に留まり、描画後のピクセルを見ていない。

- `README.md:28` が「Check whether text fits each box (**no rendering**)」と明記しており、
  `fit` は描画せずに判定する設計。
- `CLAUDE.md:25` が「`analyze()` measures text fit; `render()` draws」と役割を分けており、
  測定と描画が別経路。
- `README.md:103` も `fit <spec>` を「Fit analysis **without rendering**」と説明する。
- `pyproject.toml:14` で `pillow>=10.0` をピン。Pillow 12 系では
  `ImageDraw.textlength` が複数行文字列で `ValueError` を投げるため、実測系は版差の影響を受ける。

結果として現状は、はみ出しの**方向と量**、box 間の**衝突**、**可視性**、**コントラスト**、
**位置ズレ**を検査できない。「画像を見て正しい位置を言う」機能は存在しない。

## 設計判断

1. **`layout_box()` を抽出し、`render()` と `inspect` が同一の layout 実装を共有する**
   - 理由: `render()` の `auto` 色はその時点の累積 canvas から決まり、重なりや `draw_boxes` の有無で変わる。inspect が背景のみを基準に別実装で測り直すと、色・マスク・コントラストが必ずズレる。
   - 代替案: inspect 側で render を再実装し、描画結果を事後解析する案。実装は速いが、2 実装が乖離した時点で「測っている対象が render の出力でなくなる」ため棄却。
   - 反証条件: 重なる 2 box（暗い文字 → `auto`）で inspect の選色とマスクが render と一致しない場合、この判断は成立しない。

2. **インク測定は「背景のみ + その box だけを描いた画像」の RGBA 差分で行う**
   - 理由: 他 box のインクに汚染されず、`auto` の選色は累積 canvas から取れる。1 box ずつ描くので重なりに強い。
   - 代替案: render 全体を 1 回描いて box 領域ごとに切り出す案。重なる box で他者のインクが混入し、box の帰属が決まらないため棄却。
   - 反証条件: 同一 box について、差分マスクの bbox が `render()` の描画位置と ±2px を超えて食い違う場合、この測定は信用できない。

3. **overflow は片側チェック + ±2px 許容、underflow は報告しない**
   - 理由: 正しい描画でも短い 1 行は inner rect より小さく、`valign: middle` では上下マージンが非対称になりうる。inner rect との単純差分を「ズレ」と呼ぶと正常画出が常に誤報になる。
   - 代替案: inner rect との完全一致を要求する案。日本語の descender や行送りの内部 leading で必ず失敗するため棄却。
   - 反証条件: align=left / valign=top の短い 1 行が error 判定されるなら、許容の設計が誤り。

4. **`set_size` は `layout_box()` で再検証してから採用し、`fit=shrink` では `min_size` を動かす**
   - 理由: `fit=shrink` は既に自動で縮小しており、`size` を書き換えても `_initial_size_for` と shrink ループに上書きされて no-op になる。溢れが残るのは `min_size` に達した場合だけ。
   - 代替案: 線形推定値（`size * inner_w / used_w`）をそのまま採用する案。折り返し位置が変わると高さが増え、推定が外れるため棄却。
   - 反証条件: 提案適用後の再描画で overflow が減らない、または反復で振動する場合、この判断は不成立。

5. **`--fix` / `--loop` の書き込み契約を 4 通りで固定し、収束は spec ハッシュで判定する**
   - 理由: 「ループはメモリだけ」「fix は書き出す」を混ぜると、保存された spec と表示された report が別状態になる。周期 2 以上の振動は「前回と同一提案」比較では検出できない。
   - 代替案: 提案文字列の前回比較だけで停止する案。A→B→A の周期を見逃すため棄却。
   - 反証条件: `--fix` 単体で書き出したファイルを再 inspect した結果と、表示 report が一致しないなら契約が破綻している。

6. **注釈は ASCII ラベル + `alpha_composite` で描く**
   - 理由: `find_default_font_path()` は Latin フォントしか返さず、box id に日本語が入ると豆腐になる。RGBA への直接描画は合成ではなく上書きになり、半透明の赤が不透明になる。
   - 代替案: CJK フォントを同梱する案。配布サイズとライセンスの負担が大きく、ラベルは識別子で足りるため棄却。
   - 反証条件: 16×16 の canvas で注釈が例外を出す、または半透明塗りが不透明に見えるなら設計不足。

7. **agentloupe は archived とし、HTML レンダラは取り込まない**
   - 理由: Pillow は reflow しないため grid/flex を忠実に描けず、「PNG を正とする」identity と両立しない。HTML 出力を抱えると 2 つの正ができる。
   - 代替案: agentloupe の HTML レンダラを pailow の第 2 backend として移植する案。spec モデルが二重化し、`inspect` の対象も二重になるため棄却。
   - 反証条件: HTML 出力が主目的のユーザーが実際に一定数いて、PNG だけでは代替できないと判明した場合、この判断は再考対象になる。

## 仕様

### layout_box の共有

```
@dataclass(frozen=True)
class BoxLayout:
    font; lines; line_positions; color; font_size

layout_box(box, img, draw) -> BoxLayout | None   # inner_w/inner_h <= 0 なら None
```

`render()` は `layout_box()` の結果を `draw.text()` するだけにする(振る舞い不変)。
`inspect` も同じ関数を呼ぶ。

### 測定

1. `bg_only = render(canvas, boxes=[], background=bg)`
2. box 順に `img` を累積し、`layout_box(box, img, ...)` で色を決める(render と同一)
3. マスクは `bg_only` に**その box だけ**を描いた画像との差分(RGBA 4ch、閾値 8)
4. `painted = mask.bbox()`

### 判定

| 項目 | 定義 | severity |
|---|---|---|
| overflow | painted が inner rect を超えた px、±2px 超 | error |
| collision | 他 box の painted と交差。parent 関係は無視(render と同じ) | error |
| box_too_small | inner_w/inner_h <= 0(render が描かない) | error |
| invisible | text があるのにマスク画素 0 | error |
| outside_canvas | painted が canvas 外 | error |
| contrast | 実測背景(WCAG 相対輝度、画像背景は中央値) < 4.5 | warning |
| min_size | 実効 font_size < 11 | warning |
| alpha_not_blended | color の alpha < 255(render は合成しない) | info |

underflow は報告しない。`within_tolerance` は report に残す。

### CLI と書き込み契約

```
pailow inspect <spec> [--json] [--annotate PATH] [--fix [PATH]] [--loop N] [--image BG]
```

| --fix | --loop | 書き出し | report | exit |
|---|---|---|---|---|
| なし | 0 | なし | 初回 | 0/1 |
| なし | N | なし | 最終 | 0/1/2 |
| あり | 0 | `<stem>.fixed.json` | 書き出し後に再 inspect | 0/2 |
| あり | N | `<stem>.fixed.json` | 書き出し後に再 inspect | 0/2 |

- `--loop` 上限 8(超過は警告 + clamp)
- 停止条件: 提案が空、または spec 全体の SHA256 が再出現(周期検出)
- `--fix` は `json.dump(indent=2, ensure_ascii=False)`。整形・コメントは保持しない

### 注釈 PNG

ASCII ラベルのみ(`#0 headline`、非 ASCII は `?`)。`--label-font` で差し替え可。
破線は手描き、半透明塗りは別レイヤー + `Image.alpha_composite`、
座標は canvas に clamp、1×1 でも例外を出さない。

## タスク

- [ ] 1. `render.py` に `BoxLayout` と `layout_box()` を抽出し、`render()` をそれ経由に書き換える（判断1）
- [ ] 2. `inspect.py` に実測（bg_only + box 単独の RGBA 差分）と判定 8 項目を実装する（判断2、3）
- [ ] 3. `suggest.py` に提案生成・`layout_box` 検証付きの適用・SHA256 収束ループを実装する（判断4、5）
- [ ] 4. `annotate.py` に ASCII ラベル注釈と `alpha_composite` 描画を実装する（判断6）
- [ ] 5. `cli.py` に `inspect` を追加し、4 通りの書き込み契約と exit code を実装する（判断5）
- [ ] 6. `__init__.py` に `inspect_spec` / `inspect_from_mapping` を公開する（判断1）
- [ ] 7. `tests/test_inspect.py` に乖離検出 9 ケースを追加する（判断2、3）
- [ ] 8. `tests/test_annotate.py` と `tests/test_cli.py` を更新する（判断5、6）
- [ ] 9. README / SKILL を更新し、agentloupe を archived にする（判断7）

## テスト

乖離を捕まえる 9 ケース（許容 ±2px を明示）。

1. mask equivalence: 重なりの無い box で、inspect のマスク == diff(render(all), render(all - this box))
2. auto in context: 重なる 2 box（暗 → auto）で inspect の色とマスクが render と一致
3. alpha text: `#FFFFFF80` を暗背景に置き、RGBA diff と contrast が仕様通り
4. background image: 非一様背景で `auto` の色が render と一致
5. box_too_small: `pad*2 == w` で `invisible` ではなく `box_too_small`
6. left/top の短い 1 行: 正しい描画で error が 0
7. shrink no-op 検出: `fit=shrink` の overflow で提案が `min_size` を変え、再描画で実際に直る
8. oscillation: A→B→A する fixture でハッシュ検出により停止
9. fix write: `--fix` 単体で `<stem>.fixed.json` のみ書かれ、入力が byte-identical

## スコープ外

- HTML+CSS レンダラ: 取り込まない（Pillow を正とする identity と両立しない）
- YAML spec / grid / 7 layer types: pailow の JSON + 絶対座標を維持するため採用しない
- `compare`（N 案の並列比較）と `shoot`（スクショ）: 本 goal では実装しない
- `render()` の auto 色を WCAG 最適化へ変更: 既存 tests と既存 spec を壊すため別 goal とする
- `parent` の containment 免除: render が parent を無視しているため実装しない
- `fit` の deprecated 化: v1 では警告も出さず黙って残す
- spec のコメント・整形保持: JSON のため保証しない

## 完了条件

```
uv run pytest -q
```

- 既存 198 tests が green のまま
- 新規テストが green
- `pailow inspect <spec> --json` が妥当な JSON を返す
- `pailow inspect <spec> --annotate /tmp/a.png` が画像を生成する
