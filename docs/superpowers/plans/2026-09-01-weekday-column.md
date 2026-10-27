# 様式PDF 曜日の表示 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 日常点検表の日付欄に、日にちと並べて曜日（月・火・…）を、土日祝は色を変えて印字できるようにする。

**Architecture:** 曜日は日にちと同じ「1文字を中央に置く」項目として、専用の描画関数を新設する。色の判定は日にちと同じ `_circle_color()` を使い回し、日にちの描画（`_draw_day_field`）には一切触らない。画面と印字プレビューにも同じ規則を入れる。

**Tech Stack:** Python 3 / Flask / reportlab / pytest / 素のJavaScript（ビルドなし）

**設計書:** `docs/superpowers/specs/2026-09-01-weekday-column-design.md`

**ブランチ:** `master`（現在ここ。新しく切らない）

**着手前の基準値:** `.venv/Scripts/python.exe -m pytest tests/ -q` が **362 passed**（2026-09-01 実測）。

---

## 前提知識（この計画を実行する人へ）

- **日にちの色分けはすでに動いている。**土曜＝青、日曜・祝日・会社休日＝赤、平日＝黒。判定は `pdf_forms._day_mark()` が `slot["mark"]` に `"saturday"` / `"holiday"` / `""` を入れ、`_circle_color()` が色に変換している。**土曜かつ祝日の日は `holiday`（赤）が優先される。**
- **この計画で `_draw_day_field`（日にちの描画）を変更してはいけない。**既存の出力が1文字も変わらないことが条件。
- **PDFの座標は左下が原点。**`drawCentredString` の y は文字の下端なので、中心に置くには `y - 文字サイズ × 0.35` する（日にちと同じ）。
- **JavaScript の `getDay()` は日曜が0、Python の `weekday()` は月曜が0。**取り違えると画面とPDFで曜日が1つずれ、しかも気づきにくい。
- `static/` のJS・CSSに版数（`?v=`）は付けない。ブラウザに毎回確認させる設定になっている。**復活させないこと。**
- テストは1ファイル `tests/test_app.py`。実行は `.venv/Scripts/python.exe -m pytest tests/ -q`。

---

## ファイル構成

| ファイル | この計画での役割 |
|---|---|
| `pdf_forms.py` | 曜日の文字表と描画関数を新設し、振り分けに1分岐を足す |
| `static/layout.js` | 左の一覧に項目を追加。右パネルの出し分けを2種類に分ける |
| `static/layout-preview.js` | 薄い文字のプレビューに曜日を出す（色は同じ、丸は出さない） |
| `tests/test_app.py` | Task 1 のテストを追記する |

---

### Task 1: 曜日を描く（`pdf_forms.py`）

**Files:**
- Modify: `pdf_forms.py`（`_draw_day_field()` の直後に関数を追加、`_draw_slot_field()` に分岐を1つ追加、ファイル上部に定数を1つ追加）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_app.py` の末尾に追記する。

```python
# ========== 曜日の表示 ==========

class _DrawRecorder:
    """キャンバスのふりをして、呼ばれた描画命令を記録する。

    色はPDFを解析しても読み取りにくいので、描画命令を直接受け止めて確かめる。
    """
    def __init__(self):
        self.fill = None
        self.text = None
        self.circled = False

    def setFont(self, *a, **k):
        pass

    def setFillColor(self, color):
        self.fill = str(color)

    def setStrokeColor(self, color):
        pass

    def setLineWidth(self, *a, **k):
        pass

    def drawCentredString(self, x, y, text):
        self.text = text

    def drawString(self, x, y, text):
        self.text = text

    def circle(self, *a, **k):
        self.circled = True


def _slot_for(target, custom=None):
    """その日1日ぶんのスロットを作る（mark が入った状態になる）"""
    from datetime import timedelta
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 1}}
    slots = pdf_forms.build_slots(layout, target.year, target.month, [target],
                                  {}, custom or {},
                                  today=target + timedelta(days=1))
    return slots[1]


def _draw_weekday(target, custom=None, field=None):
    """曜日を1つ描いて、記録した命令を返す"""
    import pdf_forms
    rec = _DrawRecorder()
    pdf_forms._draw_weekday_field(rec, field or {"source": "meta.weekday"},
                                  100.0, 500.0, _slot_for(target, custom), 9)
    return rec


def _expect_color(hex_value):
    """reportlab が受け取る色の文字列表現に直す"""
    from reportlab.lib.colors import HexColor
    return str(HexColor(hex_value))


def test_weekday_characters_match_the_day():
    """月曜から日曜まで、正しい1文字が印字されること"""
    from datetime import date
    # 2026-09-07 は月曜
    expected = ["月", "火", "水", "木", "金", "土", "日"]
    for i, want in enumerate(expected):
        d = date(2026, 9, 7 + i)
        assert _draw_weekday(d).text == want, d


def test_weekday_saturday_is_blue():
    """土曜の曜日が青になること"""
    from datetime import date
    import pdf_forms
    assert _draw_weekday(date(2026, 9, 12)).fill == _expect_color(
        pdf_forms.COLOR_SATURDAY)


def test_weekday_sunday_is_red():
    """日曜の曜日が赤になること"""
    from datetime import date
    import pdf_forms
    assert _draw_weekday(date(2026, 9, 13)).fill == _expect_color(
        pdf_forms.COLOR_HOLIDAY)


def test_weekday_national_holiday_is_red():
    """祝日の曜日が赤になること（2026-09-21 は敬老の日）"""
    from datetime import date
    import jpholiday
    import pdf_forms
    assert jpholiday.is_holiday(date(2026, 9, 21)), "前提：この日は祝日"
    assert _draw_weekday(date(2026, 9, 21)).fill == _expect_color(
        pdf_forms.COLOR_HOLIDAY)


def test_weekday_custom_holiday_is_red():
    """会社の休業日の曜日が赤になること"""
    from datetime import date
    import pdf_forms
    rec = _draw_weekday(date(2026, 9, 8), custom={"2026-09-08": "会社休日"})
    assert rec.fill == _expect_color(pdf_forms.COLOR_HOLIDAY)


def test_weekday_plain_day_is_black():
    """平日の曜日が黒になること"""
    from datetime import date
    assert _draw_weekday(date(2026, 9, 8)).fill == _expect_color("#000000")


def test_weekday_saturday_holiday_is_red():
    """土曜と休業日が重なった日は赤になること（日にちと同じ優先順位）"""
    from datetime import date
    import pdf_forms
    rec = _draw_weekday(date(2026, 9, 12), custom={"2026-09-12": "会社休日"})
    assert rec.fill == _expect_color(pdf_forms.COLOR_HOLIDAY)


def test_weekday_uses_field_color_on_plain_days():
    """平日は様式で指定した色を使うこと"""
    from datetime import date
    rec = _draw_weekday(date(2026, 9, 8),
                        field={"source": "meta.weekday", "color": "#00aa00"})
    assert rec.fill == _expect_color("#00aa00")


def test_weekday_saturday_ignores_field_color():
    """土日祝は様式の色指定より、青・赤を優先すること"""
    from datetime import date
    import pdf_forms
    rec = _draw_weekday(date(2026, 9, 12),
                        field={"source": "meta.weekday", "color": "#00aa00"})
    assert rec.fill == _expect_color(pdf_forms.COLOR_SATURDAY)


def test_weekday_draws_no_circle():
    """曜日には丸を描かないこと（丸は日にちだけ）"""
    from datetime import date
    assert _draw_weekday(date(2026, 9, 13)).circled is False


def test_weekday_blank_on_extra_cell():
    """その月に無い日（余りマス）には何も描かないこと"""
    import pdf_forms
    rec = _DrawRecorder()
    pdf_forms._draw_slot_field(rec, {"source": "meta.weekday"}, 100.0, 500.0,
                               {"exists": False, "date": None}, {}, 9)
    assert rec.text is None
    assert rec.circled is False


def test_weekday_is_dispatched_by_draw_slot_field():
    """_draw_slot_field から曜日の描画へ振り分けられること"""
    from datetime import date
    import pdf_forms
    rec = _DrawRecorder()
    pdf_forms._draw_slot_field(rec, {"source": "meta.weekday"}, 100.0, 500.0,
                               _slot_for(date(2026, 9, 13)), {}, 9)
    assert rec.text == "日"


def test_day_field_still_circles_and_colours():
    """日にちの描画が変わっていないこと（丸と色）"""
    from datetime import date
    import pdf_forms
    rec = _DrawRecorder()
    pdf_forms._draw_day_field(rec, {"source": "meta.day"}, 100.0, 500.0,
                              _slot_for(date(2026, 9, 12)), 9)
    assert rec.text == "12"
    assert rec.fill == _expect_color(pdf_forms.COLOR_SATURDAY)
    assert rec.circled is True
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k weekday`
Expected: FAIL（`AttributeError: module 'pdf_forms' has no attribute '_draw_weekday_field'`）

- [ ] **Step 3: 実装する**

**3-a.** `pdf_forms.py` の `COLOR_HOLIDAY = "#ff0000"` の**次の行**に定数を足す。

```python
WEEKDAY_NAMES = "月火水木金土日"   # date.weekday() は月曜が0
```

**3-b.** `_draw_day_field()` の**直後**（`_draw_slot_field()` の前）に関数を追加する。

```python
def _draw_weekday_field(c, field: dict, x: float, y: float, slot: dict,
                        default_size: int):
    """曜日を1文字、日にちと同じ中央基準で描く。

    色の規則は日にちと同じ（_circle_color を使い回す）。別に判定を書くと、
    祝日の扱いを変えたときに日にちと曜日で色が食い違う。
    丸は描かない（丸は日にちだけ）。
    x, y は文字の中央を指す。
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

**3-c.** `_draw_slot_field()` の中、`meta.day` の分岐の**直後**に足す。

```python
    if source == "meta.weekday":
        _draw_weekday_field(c, field, x, y, slot, default_size)
        return
```

`_draw_day_field()` と `_field_value()` には手を入れないこと。

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（`375 passed`）。基準は 362 で、13件追加した。
件数が違う、または既存のテストが落ちたら、**テストを弱めずに**内容を報告して止まること。

- [ ] **Step 5: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: print the weekday with the same colour rule as the date"
```

---

### Task 2: 画面の項目を増やす（`static/layout.js`）

**Files:**
- Modify: `static/layout.js`（左の一覧、右パネルの出し分け）

- [ ] **Step 1: 左の一覧に足す**

`collectItems()` の「共通」の中、`{ key: "meta.day", label: "日にち（土日祝は丸）" },` の**次の行**に足す。

```javascript
            { key: "meta.weekday", label: "曜日（土日祝は色つき）" },
```

- [ ] **Step 2: 右パネルの出し分けを2種類に分ける**

`renderProps()` の中の

```javascript
    const isDay = f.source === "meta.day";
```

を、次の2行にする。

```javascript
    const isDay = f.source === "meta.day";
    // 1文字を中央に置く項目。縦書きは意味がないので選ばせない。
    const isCentred = isDay || f.source === "meta.weekday";
```

そのうえで、**「縦書きにする」の出し分けだけ** `isDay` を `isCentred` に変える。

変更前：

```javascript
      ${isDay ? "" : `<div class="prop-row"><label>縦書きにする</label>
        <input type="checkbox" id="p-vertical" ${f.vertical ? "checked" : ""} /></div>`}
```

変更後：

```javascript
      ${isCentred ? "" : `<div class="prop-row"><label>縦書きにする</label>
        <input type="checkbox" id="p-vertical" ${f.vertical ? "checked" : ""} /></div>`}
```

**「丸の半径」の行は `isDay` のまま変えない。**曜日に丸は付かないので、半径の欄も出さない。

- [ ] **Step 3: 構文とテストを確認する**

```
node --check static/layout.js
.venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: `node --check` は出力なし。pytest は `375 passed`（Pythonは触っていないので変わらない）。

- [ ] **Step 4: コミット**

```bash
git add static/layout.js
git commit -m "feat: offer the weekday item on the layout screen"
```

---

### Task 3: プレビューに曜日を出す（`static/layout-preview.js`）

**Files:**
- Modify: `static/layout-preview.js`（`sampleValue()` と `renderPreview()`）

- [ ] **Step 1: 見本の文字を返す分岐を足す**

`sampleValue()` の中、`meta.day` の分岐

```javascript
    if (source === "meta.day") {
        const d = ctx.dates[n - 1];
        return d ? String(d.getDate()) : "";
    }
```

の**直後**に足す。

```javascript
    if (source === "meta.weekday") {
        // JavaScript の getDay() は日曜が0。Python の weekday()（月曜が0）に
        // 合わせないと、画面とPDFで曜日が1つずれる。
        const d = ctx.dates[n - 1];
        return d ? "月火水木金土日"[(d.getDay() + 6) % 7] : "";
    }
```

- [ ] **Step 2: 中央そろえと色を曜日にも効かせる**

`renderPreview()` の中の

```javascript
            const isDay = field.source === "meta.day";
```

を、次の2行にする。

```javascript
            const isDay = field.source === "meta.day";
            // 曜日も1文字を中央に置く。ただし丸は描かない。
            const isCentred = isDay || field.source === "meta.weekday";
```

続く `if (isDay) {` を `if (isCentred) {` に変える。**そのブロックの中の丸を描く行だけは `isDay` の条件を残す。**

変更後のブロックはこうなる。

```javascript
            if (isCentred) {
                // 日にちはクリック位置が「丸の中心」。文字も中央に置く。
                const color = dayColor(dateKey(ctx.dates[n - 1]), ctx.holidays);
                el.style.color = color || field.color || "#000000";
                el.style.left = `${vx}px`;
                el.style.top = `${vy}px`;
                el.style.transform = "translate(-50%, -50%)";
                container.appendChild(el);
                if (isDay && color) {
                    container.appendChild(dayCircle(vx, vy, field, size, color, scale));
                }
            } else {
```

`else` 以降（横書き・縦書きの処理）は変更しない。

- [ ] **Step 3: 構文とテストを確認する**

```
node --check static/layout-preview.js
.venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: `node --check` は出力なし。pytest は `375 passed`。

- [ ] **Step 4: コミット**

```bash
git add static/layout-preview.js
git commit -m "feat: preview the weekday with the same colours as the date"
```

---

### Task 4: 実機で確かめる

**テストだけでは足りない。**画面を開き、PDFを実際に開いて目で見る。

**Files:** なし（確認のみ）

- [ ] **Step 1: 全テストが通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: `375 passed`

- [ ] **Step 2: サーバーを起動して `/layout` を開く**

Run: `.venv/Scripts/python.exe app.py`
ブラウザで `http://localhost:5000/layout` を開く。

- [ ] **Step 3: 項目が出ることを確かめる**

左の一覧の「共通」に **「曜日（土日祝は色つき）」** があること。

- [ ] **Step 4: 置いて、プレビューを見る**

曜日を選び、**日にちの真下**をクリックして置く。「マスの数だけ繰り返す」を入れる。確認すること:

- 薄い文字で **月・火・水…** がマスの数だけ並ぶ
- **日にちと列がそろっている**（中央そろえが効いている）
- **土曜が青、日曜・祝日・会社休日が赤、平日が黒**
- **曜日に丸が付いていない**（丸は日にちだけ）
- 右パネルに「縦書きにする」が出ていないこと

- [ ] **Step 5: 画面とPDFで曜日がずれていないことを確かめる**

**これがこの機能でいちばん間違えやすいところ。**

「試し刷り」を押してPDFを開き、**画面の薄い文字とPDFの曜日を、同じマスで見比べる。**
1つでもずれていたら `getDay()` の変換（`(getDay() + 6) % 7`）を疑うこと。

暦で答え合わせもする。2026年8月分（7/24〜8/23）なら、**1マス目の 7/24 は金曜**。

- [ ] **Step 6: 日にちが変わっていないことを確かめる**

同じPDFで、**日にちの丸と色がこれまでどおり**であることを確認する。

- [ ] **Step 7: 結果を報告する**

Step 3〜6 で見たことを、**確認できた／できなかった**を分けて報告する。
できなかったものがあれば、そこで止めて報告する（「動くはずです」は書かない）。

---

## 完了の条件

- `.venv/Scripts/python.exe -m pytest tests/ -q` が全件通る（375 passed の見込み）
- Task 4 の Step 3〜6 をすべて実機で確認した
- **画面のプレビューとPDFで曜日が一致している**
- `_draw_day_field`（日にちの描画）に手を入れていない（`git diff` で確認できる）
