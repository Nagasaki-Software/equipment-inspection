# 様式PDF 曜日の表示 設計書

**作成日:** 2026-09-01
**状態:** 未承認
**前提:** `2026-08-31-pdf-page-order-design.md` の実装完了後（master 取り込み済み）

## 目的

日常点検表の日付欄に、日にちと並べて**曜日**を印字できるようにする。紙の上で「この列は何曜日か」がすぐ分かるようにするため。

## いまの状態（変更しない部分）

**日にちの色分けは、すでに要望どおり動いている。**描画命令を記録して実測した結果が次のとおり。

| 種別 | 文字色 | 丸 |
|---|---|---|
| 平日 | 黒 | — |
| 土曜 | **青**（`#0000ff`） | あり |
| 日曜・祝日・会社休日 | **赤**（`#ff0000`） | あり |

判定は `pdf_forms._day_mark()` が行い、`slot["mark"]` に `"saturday"` / `"holiday"` / `""` を入れている。
**土曜と祝日が重なった日は `holiday`（赤）を優先する。**

したがって今回の作業は **曜日の項目を足すことだけ**で、日にちの描画（`_draw_day_field`）には手を入れない。

---

## 追加する項目

`layout.json` の `fields[].source` に `meta.weekday` を追加する。

| | 内容 |
|---|---|
| 左の一覧での表示 | 「曜日（土日祝は色つき）」（「共通」グループ） |
| 印字される文字 | `月` `火` `水` `木` `金` `土` `日` の1文字 |
| 色 | 平日＝`field.color`（既定は黒）／土曜＝青／日曜・祝日・会社休日＝赤 |
| 色の判定 | **日にちと同じ `slot["mark"]` を見る。**新しい判定は作らない |
| 丸 | **描かない**（丸は日にちだけ） |
| クリック位置 | **文字の中央**（日にちと同じ）。日にちの真下をクリックすれば列がそろう |
| その月に無い日（余りマス） | 空欄 |

`meta.day` と同じく「マスの数だけ繰り返す」を入れて1つ置けば、全マスに出る。

---

## サーバー側（`pdf_forms.py`）

### 曜日の文字

```python
WEEKDAY_NAMES = "月火水木金土日"   # date.weekday() は月曜が0
```

### 描画

`_draw_day_field()` の直後に、次の関数を新設する。

```python
def _draw_weekday_field(c, field: dict, x: float, y: float, slot: dict,
                        default_size: int):
    """曜日を1文字、丸の中心と同じ基準（中央）で描く。

    色の規則は日にちと同じ。丸は描かない（丸は日にちだけ）。
    x, y は文字の中央を指す（他のフィールドは文字の左下基準）。
    """
    d = slot.get("date")
    if not d:
        return
    size = float(field.get("font_size", default_size))
    color = _circle_color(slot.get("mark", "")) or field.get("color", "#000000")
    c.setFont(FONT_NAME, size)
    c.setFillColor(HexColor(color))
    # drawCentredString の y は文字の下端なので、中心に来るよう少し下げる
    c.drawCentredString(x, y - size * 0.35, WEEKDAY_NAMES[d.weekday()])
```

`_circle_color()` を色の判定にそのまま使う。**日にちと曜日で色がずれないための唯一の担保**なので、独自に判定し直さない。

### 振り分け

`_draw_slot_field()` の `meta.day` の分岐の直後に1つ足す。

```python
    if source == "meta.weekday":
        _draw_weekday_field(c, field, x, y, slot, default_size)
        return
```

余りマスの扱いは既存のまま。`_draw_slot_field()` は `exists=False` のとき `item:` だけ「ー」を描いて戻るので、**曜日は自動的に空欄になる。**

`_field_value()` には手を入れない（`meta.day` と同じく、中央そろえの専用描画が要るため）。

---

## 画面（`static/layout.js`）

### 左の一覧

「共通」の `meta.day` の直後に足す。

```javascript
            { key: "meta.weekday", label: "曜日（土日祝は色つき）" },
```

### 右パネル

いまは `const isDay = f.source === "meta.day";` が2つのことを決めている。

| | `meta.day` | `meta.weekday` |
|---|---|---|
| 「丸の半径」を出す | 出す | **出さない** |
| 「縦書きにする」を出す | 出さない | **出さない**（1文字なので意味がない） |

そこで判定を2つに分ける。

```javascript
    const isDay = f.source === "meta.day";
    // 1文字を中央に置く項目。縦書きの選択肢は出さない。
    const isCentred = isDay || f.source === "meta.weekday";
```

「丸の半径」の出し分けは `isDay` のまま、「縦書きにする」の出し分けを `isCentred` に変える。

---

## プレビュー（`static/layout-preview.js`）

**サーバーと同じ見え方にする。片方だけ直すとプレビューが嘘をつく。**

### 見本の文字

`sampleValue()` の `meta.day` の分岐の直後に足す。

```javascript
    if (source === "meta.weekday") {
        const d = ctx.dates[n - 1];
        return d ? "月火水木金土日"[(d.getDay() + 6) % 7] : "";
    }
```

**JavaScript の `getDay()` は日曜が0。**Python の `weekday()`（月曜が0）と基準が違うため `(getDay() + 6) % 7` で揃える。ここを間違えると画面とPDFで曜日が1つずれる。

### 中央そろえと色

いまは `const isDay = field.source === "meta.day";` が「中央に置く」と「丸を描く」の両方を決めている。曜日は**中央に置くが丸は描かない**ので、判定を分ける。

```javascript
            const isDay = field.source === "meta.day";
            const isCentred = isDay || field.source === "meta.weekday";
```

- 位置の分岐（`translate(-50%, -50%)`）と色（`dayColor(...)`）は `isCentred` を使う
- 丸を描く処理（`dayCircle(...)`）は `isDay` のまま

---

## 変えないもの

- **日にちの描画（`_draw_day_field`）。**丸も色もそのまま
- 日にちの色の判定（`_day_mark` / `_circle_color`）
- 表出力・点検画面・保存されるJSON・CSV
- ポート5000・締め日区切り・`utf-8-sig`

## 対象外（今回やらないこと）

- 曜日を「(月)」「月曜」などの別の形で出す指定
- 曜日に丸を付けること
- 曜日だけ違う色にする設定
- 曜日を英語（Mon, Tue）で出すこと

## 実装で間違えやすいところ

- **JavaScript の `getDay()` は日曜が0、Python の `weekday()` は月曜が0。**そのまま使うと画面とPDFで曜日が1つずれる。しかも「ずれている」と気づきにくい
- **色の判定を新しく書かない。**`_circle_color()`（サーバー）と `dayColor()`（画面）を使う。別々に判定を書くと、祝日の追加時に片方だけ直して食い違う
- プレビューで**丸まで描いてしまわない**。曜日に丸は付けない

## 検証方法

### pytest（追加するテスト）

1. 月曜〜日曜の7日それぞれで、正しい1文字が印字される
2. 土曜は青、日曜は赤、祝日は赤、会社休日は赤、平日は黒
3. **土曜かつ祝日の日は赤**（日にちと同じ優先順位）
4. 丸を描かない
5. その月に無い日（余りマス）は何も描かない
6. `field.color` を指定した平日はその色になる
7. **日にちの出力が変わらない**（変更前のコードと突き合わせる）

### 実機（テストだけでは足りない）

- 様式に曜日を置き、**日にちの真下で列がそろうこと**を画面の薄い文字で確認
- **試し刷りのPDFを開いて、曜日の文字と色を目で見る**
- 画面のプレビューとPDFで**曜日が1つもずれていないこと**（`getDay()` の取り違えの確認）
