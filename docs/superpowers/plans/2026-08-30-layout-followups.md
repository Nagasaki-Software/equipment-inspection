# 様式レイアウト 追加4機能 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 様式レイアウト画面に、ズレの手入力・縦書き・様式の削除・月の変わり目の表示を足す。

**Architecture:** ①は画面だけ。②③④はサーバー側にも手を入れる。④は新しい描画処理を作らず、「マスの数だけ繰り返す」項目として扱い、該当するマスでだけ文字を返す形にして既存の仕組みに乗せる。削除は完全削除ではなくゴミ箱（`.trash`）への移動にする。

**Tech Stack:** 素のJavaScript（ESモジュール）／Flask／reportlab／pypdf／pytest

**設計書:** `docs/superpowers/specs/2026-08-30-layout-followups-design.md`（承認済み）
**ブランチ:** `feature/layout-ui`（作り直しの22コミットの続き）

---

## 前回と違うこと（先に読むこと）

作り直しのときは「サーバー側は変更しない」を制約にしていました。**今回は②③④でサーバーを変更します。**

そのため、**「pytest 276件が通る＝サーバー未変更の証明」という検証は使えません。**新しいテストを足したうえで全件が通ることを確認してください。各タスクに、その時点での期待件数を書いてあります。

### 起動と確認

```cmd
.venv\Scripts\python.exe app.py                 :: ポート5000固定。変更しない
.venv\Scripts\python.exe -m pytest tests/ -q
```

静的ファイル（html/css/js）はリクエストのたびに読まれるので、サーバーの再起動は不要です。ブラウザの Ctrl+F5 で反映されます。**サーバー側（`app.py` `pdf_forms.py` `forms_layout.py`）を変えたときは再起動が必要です。**

### 版数（`?v=`）の決まり

画面ファイルを変えたら、**4か所すべて**を同じ数字に上げます。1つでも忘れると利用者のブラウザが古いファイルを使い続けます。

- `static/layout.html` の `layout.css?v=` と `layout.js?v=`
- `static/layout.js` の中の `layout-wizard.js?v=` と `layout-preview.js?v=`

現在は `v=11` です。

---

## Task 1: ズレ x / y を手入力できるようにする

**Files:**
- Modify: `static/layout.html`（`<footer id="axis-bar">`）
- Modify: `static/layout.css`
- Modify: `static/layout.js`（`updateAxisLabel` と `init`）

いまは `ズレ x:23.0 y:0.0` という読み取り専用の表示です。クリックだけでは正確に合わせられない（実測でも 23.0 が 69.6 になった）ので、直接打てるようにします。

- [ ] **Step 1: 下部バーの表示を入力欄に変える**

`static/layout.html` の `<span id="axis-step">まだ指定していません</span>` を次に置き換えます。

```html
        <label for="axis-step-x">ズレ x</label>
        <input type="number" id="axis-step-x" step="0.1" />
        <label for="axis-step-y">y</label>
        <input type="number" id="axis-step-y" step="0.1" />
        <span id="axis-step-mm"></span>
```

- [ ] **Step 2: 入力欄のスタイルを足す**

`static/layout.css` の末尾に追記します。

```css
/* 並び方のズレ（pt）の入力欄 */
#axis-step-x, #axis-step-y { width: 72px; }
#axis-step-mm { font-size: 12px; color: #5a6a7a; }
```

- [ ] **Step 3: `updateAxisLabel` を差し替える**

`static/layout.js` の `updateAxisLabel` を次に置き換えます。

```js
/** PDFの点（pt）をミリに直す係数。1pt = 1/72インチ。 */
const PT_TO_MM = 0.3528;

function updateAxisLabel() {
    const axis = (state.layout && state.layout.axis) || {};
    const sx = Number(axis.step_x || 0), sy = Number(axis.step_y || 0);
    const ex = $("axis-step-x"), ey = $("axis-step-y"), em = $("axis-step-mm");
    if (ex) ex.value = sx;
    if (ey) ey.value = sy;
    if (!em) return;
    // ミリは参考表示。保存される値もクリックで得られる値も pt なので、入力は pt に揃える。
    em.textContent = (!sx && !sy)
        ? "pt（まだ指定していません）"
        : `pt（≒ x:${(sx * PT_TO_MM).toFixed(1)}mm y:${(sy * PT_TO_MM).toFixed(1)}mm）`;
}
```

- [ ] **Step 4: 手入力を反映する**

`static/layout.js` の `init()` の中、`$("axis-count")` のハンドラの直前に追加します。

```js
    // 手入力でも並び方を変えられるようにする。クリックだけでは細かく合わせられない。
    ["axis-step-x", "axis-step-y"].forEach(id => {
        $(id).addEventListener("change", () => {
            if (!state.layout) return;
            const axis = state.layout.axis || (state.layout.axis = {});
            axis.step_x = Number($("axis-step-x").value) || 0;
            axis.step_y = Number($("axis-step-y").value) || 0;
            updateAxisLabel();
            renderMarkers();
        });
    });
```

- [ ] **Step 5: 版数を上げる（4か所）**

`v=11` → `v=12`。

- [ ] **Step 6: テスト**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `276 passed`（画面だけの変更なので件数は変わりません）

- [ ] **Step 7: ブラウザで確認する**

`http://localhost:5000/layout` を Ctrl+F5 で開き、`sample_daily` を選びます。

1. 下部に `ズレ x [23] y [0] pt（≒ x:8.1mm y:0.0mm）` と出る
2. x を `40` に打ち替えて Tab を押すと、**薄い文字の並びが広がる**
3. 「1日目のマスを指定」から2か所クリックすると、入力欄の値が更新される
4. 保存せずに再読み込みすると、元の値に戻る

- [ ] **Step 8: コミット**

```bash
git add static/layout.html static/layout.css static/layout.js
git commit -m "feat: let the spacing between slots be typed in as well as clicked"
```

---

## Task 2: 縦書き（サーバー側）

**Files:**
- Modify: `pdf_forms.py`（`_draw_field`）
- Modify: `tests/test_app.py`

`_draw_field` は `drawString` で横書き固定です。1文字ずつ下に積む道を足します。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_app.py` の末尾に追加します。

```python
# ==================================================================
# 縦書き
# ==================================================================

class _RecordingCanvas:
    """drawString の呼び出しを記録するだけの偽キャンバス"""

    def __init__(self):
        self.calls = []

    def setFont(self, *a):
        pass

    def setFillColor(self, *a):
        pass

    def drawString(self, x, y, text):
        self.calls.append((x, y, text))

    def drawCentredString(self, x, y, text):
        self.calls.append(("center", x, y, text))


def test_draw_field_vertical_stacks_characters():
    """縦書きは1文字ずつ下へ積むこと（PDFのYは上が正なので減らす）"""
    import pdf_forms
    c = _RecordingCanvas()
    field = {"source": "meta.inspector", "vertical": True, "font_size": 10}
    pdf_forms._draw_field(c, field, 100, 700, "見本", 11)
    assert c.calls == [(100, 700, "見"), (100, 690, "本")]


def test_draw_field_horizontal_unchanged():
    """縦書きを指定しなければ、いままでどおり1回で書くこと"""
    import pdf_forms
    c = _RecordingCanvas()
    pdf_forms._draw_field(c, {"source": "meta.inspector"}, 100, 700, "見本 太郎", 11)
    assert c.calls == [(100, 700, "見本 太郎")]


def test_draw_field_vertical_uses_default_font_size():
    """文字サイズを指定しなければ、様式の既定値で積むこと"""
    import pdf_forms
    c = _RecordingCanvas()
    pdf_forms._draw_field(c, {"source": "x", "vertical": True}, 0, 100, "ab", 20)
    assert c.calls == [(0, 100, "a"), (0, 80, "b")]


def test_draw_field_vertical_skips_empty_text():
    """空文字なら縦書きでも何も描かないこと"""
    import pdf_forms
    c = _RecordingCanvas()
    pdf_forms._draw_field(c, {"source": "x", "vertical": True}, 0, 100, "", 11)
    assert c.calls == []
```

- [ ] **Step 2: テストが落ちることを確認する**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k vertical -q`
Expected: FAIL（`_draw_field` がまだ縦書きを知らないため、1文字ずつではなく1回で書かれる）

- [ ] **Step 3: `_draw_field` に縦書きを足す**

`pdf_forms.py` の `_draw_field` を次に置き換えます。

```python
def _draw_field(c, field: dict, x: float, y: float, text: str, default_size: int):
    """1つのフィールドを描く。空文字なら何もしない。"""
    if not text:
        return
    size = float(field.get("font_size", default_size))
    c.setFont(FONT_NAME, size)
    c.setFillColor(HexColor(field.get("color", "#000000")))
    if field.get("vertical"):
        # 1文字ずつ下に積む。PDFのYは上が正なので、下へは減らす。
        # クリック位置の意味は横書きと同じ（1文字目の左下）。
        for i, ch in enumerate(text):
            c.drawString(x, y - size * i, ch)
        return
    c.drawString(x, y, text)
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `280 passed`（276 + 新規4件）

- [ ] **Step 5: 実際のPDFで確かめる**

一時ファイルはスクラッチパッドに作ってください。プロジェクト内には作らないこと。

```python
# 縦書きの点検者名が本当に縦に並ぶか、生成したPDFの文字位置で確かめる
import io, sys
sys.path.insert(0, r"（アプリのフォルダ）")
import pdf_forms
from reportlab.pdfgen import canvas as rl
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader

path = "縦書き確認.pdf"          # スクラッチパッド内
c = rl.Canvas(path, pagesize=A4)
pdf_forms._ensure_font()
pdf_forms._draw_field(c, {"source": "meta.inspector", "vertical": True}, 100, 700, "見本太郎", 11)
c.showPage(); c.save()
print(PdfReader(path).pages[0].extract_text())
```

期待：「見本太郎」の各文字が別々の行に出る（横に並ばない）。

- [ ] **Step 6: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: draw a field vertically when the layout asks for it"
```

---

## Task 3: 縦書き（画面側）

**Files:**
- Modify: `static/layout.js`（`renderProps`）
- Modify: `static/layout.css`
- Modify: `static/layout-preview.js`（`renderPreview`）
- Modify: `static/layout.html`（版数）

- [ ] **Step 1: 右パネルにチェックボックスを足す**

`static/layout.js` の `renderProps()` の中、`<div class="prop-row"><label>マスの数だけ繰り返す</label>` の**直前**に追加します。

```html
      ${isDay ? "" : `<div class="prop-row"><label>縦書きにする</label>
        <input type="checkbox" id="p-vertical" ${f.vertical ? "checked" : ""} /></div>`}
```

`isDay`（`f.source === "meta.day"`）のときは出しません。1文字を丸の中央に置く項目なので、縦書きの意味がないためです。

- [ ] **Step 2: チェックボックスの処理を足す**

`renderProps()` の中、`const axisEl = $("p-axis");` の直前に追加します。

```js
    const vertEl = $("p-vertical");
    if (vertEl) vertEl.addEventListener("change", () => {
        // 既定は横書き。既存の様式に vertical を書き足さないよう、
        // オフのときはキーごと消す。
        if (vertEl.checked) f.vertical = true;
        else delete f.vertical;
        renderMarkers();
    });
```

- [ ] **Step 3: プレビューのスタイルを足す**

`static/layout.css` の `.pf-circle` の規則の直前に追加します。

```css
/* 縦書きの項目 */
.pf-vertical { writing-mode: vertical-rl; }
```

- [ ] **Step 4: プレビューを縦書きに対応させる**

`static/layout-preview.js` の `renderPreview` の中、日にち以外を描いている `else` の中身を次に置き換えます。

```js
            } else {
                el.style.color = field.color || "#000000";
                el.style.left = `${vx}px`;
                if (field.vertical) {
                    // 縦書きは上端から下へ流れる。1文字目の位置を横書きと揃える。
                    el.classList.add("pf-vertical");
                    el.style.top = `${vy - size}px`;
                } else {
                    // PDFは文字のベースラインに描くので、画面では少し上にずらす
                    el.style.top = `${vy - size * 0.8}px`;
                }
                container.appendChild(el);
            }
```

- [ ] **Step 5: 版数を上げる（4か所）**

`v=12` → `v=13`。

- [ ] **Step 6: テスト**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `280 passed`

- [ ] **Step 7: ブラウザで確認する**

1. `sample_daily` を開き、「点検者名」を様式の上に置く
2. その配置を選び、右パネルに「**縦書きにする**」が出る
3. チェックすると、プレビューの「見本 太郎」が**縦に並ぶ**
4. 「日にち」を選ぶと、チェックボックスが**出ない**
5. 保存して「試し刷り」を開き、**PDFでも縦に並んでいる**ことを確かめる

**5番は必ず実施してください。**画面と実物が食い違っていないかの確認です。

- [ ] **Step 8: コミット**

```bash
git add static/layout.js static/layout.css static/layout-preview.js static/layout.html
git commit -m "feat: offer vertical writing for text fields on the layout screen"
```

---

## Task 4: 様式の削除（サーバー側）

**Files:**
- Modify: `forms_layout.py`（`TRASH_DIRNAME` と `list_forms`）
- Modify: `app.py`（削除API）
- Modify: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_app.py` の末尾に追加します。

```python
# ==================================================================
# 様式の削除（ゴミ箱への移動）
# ==================================================================

def _make_form(forms_dir, name, with_pdf=True):
    """テスト用の様式フォルダを1つ作る"""
    d = forms_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "layout.json").write_text(json.dumps(
        {"form_name": name, "period": "single", "inspection_type": "使用前",
         "targets": [], "fields": []}, ensure_ascii=False), encoding="utf-8")
    if with_pdf:
        _make_form_pdf(d / "form.pdf")
    return d


def test_list_forms_skips_dot_directories(tmp_path):
    """ゴミ箱（.trash）を様式として並べないこと"""
    import forms_layout
    forms_dir = tmp_path / "forms"
    _make_form(forms_dir, "crane_daily")
    (forms_dir / ".trash" / "old_20260830_120000").mkdir(parents=True)
    ids = [e["id"] for e in forms_layout.list_forms(forms_dir)]
    assert ids == ["crane_daily"]


def test_delete_form_moves_it_to_trash(client, monkeypatch, tmp_path):
    """削除すると .trash に移り、一覧から消えること"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    _make_form(forms_dir, "crane_daily")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    res = c.delete("/api/forms/crane_daily")
    assert res.status_code == 200
    assert not (forms_dir / "crane_daily").exists()
    moved = list((forms_dir / ".trash").iterdir())
    assert len(moved) == 1
    assert moved[0].name.startswith("crane_daily_")
    assert (moved[0] / "form.pdf").exists()      # PDFごと残っている
    assert c.get("/api/forms").get_json() == []


def test_delete_form_works_for_a_broken_form(client, monkeypatch, tmp_path):
    """レイアウト画面で開けない様式も削除できること（これが主目的）"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    d = forms_dir / "日常点検"          # 様式IDの規則から外れた名前
    d.mkdir(parents=True)
    (d / "layout.json").write_text("{ 壊れている", encoding="utf-8")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    assert c.delete("/api/forms/日常点検").status_code == 200
    assert not d.exists()


@pytest.mark.parametrize("bad", ["..", ".", ".trash", "a/b", "a\\b"])
def test_delete_form_rejects_unsafe_names(client, monkeypatch, tmp_path, bad):
    """パス区切りやゴミ箱自身は消させないこと"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    forms_dir.mkdir(parents=True)
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    assert c.delete(f"/api/forms/{bad}").status_code in (400, 404, 405)


def test_delete_form_returns_404_when_missing(client, monkeypatch, tmp_path):
    """存在しない様式は404にすること"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    forms_dir.mkdir(parents=True)
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    assert c.delete("/api/forms/nothing").status_code == 404


def test_delete_form_keeps_other_forms(client, monkeypatch, tmp_path):
    """他の様式は消さないこと"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    _make_form(forms_dir, "keep_me")
    _make_form(forms_dir, "delete_me")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    c.delete("/api/forms/delete_me")
    assert [e["id"] for e in c.get("/api/forms").get_json()] == ["keep_me"]
```

- [ ] **Step 2: テストが落ちることを確認する**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "trash or delete_form" -q`
Expected: FAIL（削除APIがまだ無いので405、`.trash` も一覧に出る）

- [ ] **Step 3: `forms_layout.py` にゴミ箱の名前と除外を足す**

`LAYOUT_BACKUP_GENERATIONS = 10` の次の行に追加します。

```python
TRASH_DIRNAME = ".trash"   # 削除した様式の置き場。ドットは様式IDに使えないので衝突しない
```

`list_forms` の `for d in sorted(...)` の直後に追加します。

```python
        # 先頭がドットのフォルダは様式ではない（.trash など）。
        # ドットは is_valid_form_id が通さない文字なので、正規の様式と衝突しない。
        if d.name.startswith("."):
            continue
```

- [ ] **Step 4: `app.py` に削除APIを足す**

`api_create_form` の直後に追加します。

```python
def _safe_form_dir_for_delete(form_id):
    """削除対象のフォルダを返す。名前が安全でなければ None。存在の有無は問わない。

    開けない様式（フォルダ名が様式IDの規則から外れているもの）を消せることが
    主目的なので、is_valid_form_id は使わない。パス区切りとゴミ箱だけを弾く。
    """
    if not isinstance(form_id, str) or not form_id:
        return None
    if "/" in form_id or "\\" in form_id:
        return None
    if form_id.startswith("."):     # "." ".." ".trash" をまとめて弾く
        return None
    forms_dir = get_forms_directory()
    candidate = forms_dir / form_id
    try:
        # シンボリックリンクなどで様式フォルダの外へ出ていないか確かめる
        if candidate.resolve().parent != forms_dir.resolve():
            return None
    except OSError:
        return None
    return candidate


@app.route("/api/forms/<form_id>", methods=["DELETE"])
@require_admin
def api_delete_form(form_id):
    """様式をゴミ箱（.trash）へ移す。

    完全には消さない。様式PDFは紙を取り込んだ唯一の控えであることがあり、
    このアプリの他の書き込みもすべてバックアップを残す作りになっているため。
    """
    form_dir = _safe_form_dir_for_delete(form_id)
    if form_dir is None:
        return jsonify({"error": "この名前の様式は削除できません"}), 400
    if not form_dir.is_dir():
        return jsonify({"error": "Not found"}), 404

    trash = get_forms_directory() / forms_layout.TRASH_DIRNAME
    dest = trash / f"{form_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        trash.mkdir(parents=True, exist_ok=True)
        form_dir.rename(dest)
    except OSError as e:
        logger.error("様式を削除できません %s: %s", form_id, e)
        return jsonify({
            "error": "削除できませんでした（ファイルが開かれているかもしれません）"
        }), 500
    logger.info("様式をゴミ箱へ移しました: %s -> %s", form_id, dest)
    return jsonify({"status": "ok", "moved_to": str(dest)})
```

- [ ] **Step 5: テストが通ることを確認する**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `289 passed`（280 + 新規9件）

- [ ] **Step 6: コミット**

```bash
git add forms_layout.py app.py tests/test_app.py
git commit -m "feat: move a deleted form to a trash folder instead of erasing it"
```

---

## Task 5: 様式の削除（画面側）

**Files:**
- Modify: `static/layout.html`（ヘッダーのボタンと版数）
- Modify: `static/layout.css`
- Modify: `static/layout.js`（`init`）

- [ ] **Step 1: ヘッダーにボタンを足す**

`static/layout.html` の `<button id="btn-save" type="button">保存</button>` の直後に追加します。

```html
        <button id="btn-delete-form" type="button">この様式を削除</button>
```

- [ ] **Step 2: スタイルを足す**

`static/layout.css` の `#btn-back { ... }` の行の直前に追加します。

```css
/* 削除は取り返しがつきにくい操作なので、他のボタンと色を分ける */
#layout-header #btn-delete-form { background: #a4423a; }
```

- [ ] **Step 3: 削除の処理を足す**

`static/layout.js` の `init()` の中、`$("btn-save")` のハンドラの直後に追加します。

```js
    $("btn-delete-form").addEventListener("click", async () => {
        if (!state.formId) { showStatus("様式が選ばれていません", true); return; }
        const entry = state.forms.find(f => f.id === state.formId);
        const name = (entry && entry.form_name) || state.formId;
        const ok = confirm(
            `「${name}（${state.formId}）」を削除します。\n`
            + "ゴミ箱（.trash）に移すので、あとで戻せます。\n\n削除しますか？");
        if (!ok) return;
        let res;
        try {
            res = await fetch(`/api/forms/${encodeURIComponent(state.formId)}`,
                              { method: "DELETE" });
        } catch (e) {
            showStatus("削除できませんでした（アプリとの通信に失敗しました）", true);
            return;
        }
        if (res.status === 401) {
            showStatus("削除には管理者権限が必要です"
                       + "（アプリを動かしているPCで操作してください）", true);
            return;
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            showStatus(err.error || `削除に失敗しました（${res.status}）`, true);
            return;
        }
        clearFormView();
        state.formId = "";
        showStatus(`「${name}」をゴミ箱へ移しました`);
        await loadForms();
    });
```

`clearFormView()` を先に呼ぶのは、消した様式の設定が `state.layout` に残ったまま次の保存で使われるのを防ぐためです（作り直しのときに同じ形の不具合がありました）。

- [ ] **Step 4: 版数を上げる（4か所）**

`v=13` → `v=14`。

- [ ] **Step 5: テスト**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `289 passed`

- [ ] **Step 6: ブラウザで確認する**

**消すのは、検証用に作った様式だけにしてください。**`sample_daily` は消さないこと。

1. `_t_nopdf`（⚠ が付いた開けない様式）を選ぶ
2. 「この様式を削除」を押すと、名前とフォルダ名が入った確認が出る
3. OKすると一覧から消え、`forms/.trash/_t_nopdf_（日時）/` に移っている
4. **開ける様式（`form_01`）でも削除できる**
5. `.trash` が一覧に**出ていない**

- [ ] **Step 7: コミット**

```bash
git add static/layout.html static/layout.css static/layout.js
git commit -m "feat: delete a form from the layout screen"
```

---

## Task 6: 実施月・前月の表示（サーバー側）

**Files:**
- Modify: `pdf_forms.py`（`_empty_slot` / `build_slots` / `_field_value`）
- Modify: `tests/test_app.py`

締め日が24日なら、1〜8マス目は前の月、9マス目から実施月です。紙の上で月の変わり目が分かるようにします。

**新しい描画処理は作りません。**「マスの数だけ繰り返す」項目として扱い、該当するマスでだけ文字を返します。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_app.py` の末尾に追加します。

```python
# ==================================================================
# 月の変わり目の表示
# ==================================================================

def _month_slots(year, month):
    """その表示月のスロットを作る（締め日は既定の24日）"""
    import app as flask_app
    import pdf_forms
    cycle = flask_app.get_cycle_dates(year, month)
    layout = {"period": "month", "inspection_type": "使用前", "targets": [],
              "axis": {"step_x": 10.0, "step_y": 0.0, "count": 31}, "fields": []}
    return pdf_forms.build_slots(layout, year, month, cycle, {}, {})


def test_slots_carry_their_index():
    """各マスが自分の番号を持つこと（前月の表示に使う）"""
    slots = _month_slots(2026, 8)
    assert slots[1]["index"] == 1
    assert slots[9]["index"] == 9


def test_month_start_prints_only_on_the_first_day_slot():
    """実施月は「日にちが1のマス」にだけ出ること"""
    import pdf_forms
    slots = _month_slots(2026, 8)          # 7/24〜8/23。8/1 は9マス目
    field = {"source": "meta.month_start"}
    meta = {"year": 2026, "month": 8}
    assert pdf_forms._field_value(field, slots[9], meta) == "8月"
    assert pdf_forms._field_value(field, slots[1], meta) == ""
    assert pdf_forms._field_value(field, slots[8], meta) == ""


def test_month_start_follows_the_cycle_length():
    """月によって1日のマスの位置が変わること"""
    import pdf_forms
    field = {"source": "meta.month_start"}
    meta = {"year": 2026, "month": 3}
    slots = _month_slots(2026, 3)          # 2/24〜3/23。3/1 は6マス目
    assert pdf_forms._field_value(field, slots[6], meta) == "3月"
    assert pdf_forms._field_value(field, slots[9], meta) == ""


def test_month_prev_prints_only_on_the_first_slot():
    """前月は1マス目にだけ出ること"""
    import pdf_forms
    slots = _month_slots(2026, 8)
    field = {"source": "meta.month_prev"}
    meta = {"year": 2026, "month": 8}
    assert pdf_forms._field_value(field, slots[1], meta) == "7月"
    assert pdf_forms._field_value(field, slots[2], meta) == ""
    assert pdf_forms._field_value(field, slots[9], meta) == ""


def test_month_marks_stay_empty_on_extra_slots():
    """余りマスには出ないこと"""
    import pdf_forms
    slots = _month_slots(2026, 3)          # 28日サイクル。29〜31は余りマス
    meta = {"year": 2026, "month": 3}
    for source in ("meta.month_start", "meta.month_prev"):
        assert pdf_forms._field_value({"source": source}, slots[30], meta) == ""
```

- [ ] **Step 2: テストが落ちることを確認する**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "month_start or month_prev or slots_carry" -q`
Expected: FAIL（`index` が無く、新しい source も知らないため）

- [ ] **Step 3: スロットに番号を持たせる**

`pdf_forms.py` の `_empty_slot()` の戻り値に `"index": 0,` を足します。

```python
def _empty_slot() -> dict:
    """1欄分の空のデータを作る"""
    return {"date": None, "month": None, "exists": False, "mark": "",
            "index": 0, "has_record": False, "unused": False,
            "values": {}, "remarks": {}, "meta": {}}
```

`build_slots` のループの中、`slot = _empty_slot()` の直後に足します。

```python
        slot = _empty_slot()
        slot["index"] = n      # 前月の表示は「1マス目かどうか」で決まる
```

- [ ] **Step 4: `_field_value` に2つの項目を足す**

`pdf_forms.py` の `_field_value` の中、`if source == "meta.unused":` の**直前**に追加します。

```python
    if source == "meta.month_start":
        # 締め日区切りなので、月の変わり目は月によって違うマスに来る。
        # 「日にちが1のマス」でだけ出せば、位置は自動で追従する。
        d = slot.get("date")
        return f"{d.month}月" if d and d.day == 1 else ""
    if source == "meta.month_prev":
        d = slot.get("date")
        return f"{d.month}月" if d and slot.get("index") == 1 else ""
```

- [ ] **Step 5: テストが通ることを確認する**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `295 passed`（289 + 新規6件）

- [ ] **Step 6: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: print the month where the inspection cycle changes month"
```

---

## Task 7: 実施月・前月の表示（画面側）

**Files:**
- Modify: `static/layout.js`（`collectItems`）
- Modify: `static/layout-preview.js`（`sampleValue`）
- Modify: `static/layout.html`（版数）

- [ ] **Step 1: 左の一覧に項目を足す**

`static/layout.js` の `collectItems()` の中、`groups` を作った直後（`const targets = ...` の**直前**）に追加します。

```js
    // 月の変わり目は「1枚に1か月分」の様式にしか無い概念なので、そのときだけ出す
    if (state.layout && state.layout.period === "month") {
        groups[0].items.push(
            { key: "meta.month_start", label: "実施月（1日のマスの位置）" },
            { key: "meta.month_prev", label: "前月（1マス目の位置）" });
    }
```

- [ ] **Step 2: プレビューに見本値を足す**

`static/layout-preview.js` の `sampleValue` の中、`if (source === "meta.unused")` の**直前**に追加します。

```js
    if (source === "meta.month_start") {
        // 締め日区切りなので、1日のマスは月によって位置が変わる
        const d = ctx.dates[n - 1];
        return (d && d.getDate() === 1) ? `${d.getMonth() + 1}月` : "";
    }
    if (source === "meta.month_prev") {
        const d = ctx.dates[n - 1];
        return (d && n === 1) ? `${d.getMonth() + 1}月` : "";
    }
```

- [ ] **Step 3: 版数を上げる（4か所）**

`v=14` → `v=15`。

- [ ] **Step 4: テスト**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `295 passed`

- [ ] **Step 5: ブラウザで確認する**

1. `sample_daily`（`month` 型）を開くと、左の一覧の「共通」に**2つの新しい項目**が出る
2. 「実施月（1日のマスの位置）」を選んで、1マス目の上あたりをクリックして置く
3. **8月では9マス目の上に「8月」が1つだけ**出る（他のマスには出ない）
4. 上の「月」を `2026-03` に変えると、**6マス目の上に「3月」**が移る
5. 「前月（1マス目の位置）」を置くと、8月では**1マス目の上に「7月」**が出る
6. `single` 型の様式（`_t_unknown`）を開くと、この2項目は**一覧に出ない**

- [ ] **Step 6: コミット**

```bash
git add static/layout.js static/layout-preview.js static/layout.html
git commit -m "feat: place the month-change labels from the layout screen"
```

---

## Task 8: 通しの確認と手引きの更新

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-08-30-layout-followups-design.md`（状態）

- [ ] **Step 1: 通しで確認する（必ず実施）**

`sample_daily` を**壊さないよう**、ウィザードで新しい様式を1つ作って行ってください。

1. 「新しい様式を追加」→ PDF → 1枚に1か月分 → 機器を選ぶ → 名前
2. 並び方を2か所クリックで指定し、**ズレ x を手入力で微調整**する
3. 判定項目・点検者名・実施月・前月を置く
4. 点検者名を**縦書き**にする
5. 保存 → 「試し刷り」を開く
6. **画面と実物のPDFを見比べる**
   - 点検者名が縦に並んでいるか
   - 「8月」が1日のマスの位置に出ているか
   - 「7月」が1マス目に出ているか
7. 表示月を `2026-03` にして試し刷りし、**「3月」の位置が動いている**ことを確かめる
8. 作った様式を「この様式を削除」で消し、`.trash` に移ったことを確かめる

- [ ] **Step 2: 既存の様式が壊れていないことを確かめる**

`sample_daily` を開いて保存せずに試し刷りし、**この計画に着手する前と同じPDF**が出ることを確かめます（`vertical` も新しい項目も持たないので、これまでどおり動くはずです）。

- [ ] **Step 3: `CLAUDE.md` に追記する**

「### レイアウト画面（/layout）の作り」の末尾に足します。

```markdown
- **削除は完全削除ではない。**`（様式フォルダ）/.trash/<様式ID>_<日時>/` へ移すだけ。戻すときは `.trash` の外へフォルダを移し、名前の末尾の日時を消す。先頭がドットのフォルダは一覧に出さない決まり。
- **縦書きは `fields[].vertical`。** `pdf_forms._draw_field` が1文字ずつ下に積む。行間は文字サイズと同じ。日にち（丸で囲む項目）には出さない。
- **月の変わり目の表示（`meta.month_start` / `meta.month_prev`）は、専用の描画をしていない。**「マスの数だけ繰り返す」項目として、日にちが1のマス／1マス目でだけ文字を返している。締め日区切りで1日の位置が月ごとに変わるため、位置は自動で追従する。
```

- [ ] **Step 4: 設計書を承認済みにする**

`docs/superpowers/specs/2026-08-30-layout-followups-design.md` の状態を「実装済み（2026-08-30）」に変えます。

- [ ] **Step 5: テスト**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `295 passed`

- [ ] **Step 6: コミット**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-08-30-layout-followups-design.md
git commit -m "docs: record the trash folder, vertical writing and month labels"
```

---

## 自己レビュー結果

**設計書との照合：**

| 設計書の項目 | 対応するタスク |
|---|---|
| ① ズレ x / y の手入力（pt、ミリは参考表示） | Task 1 |
| ② 縦書き（サーバーの描画） | Task 2 |
| ② 縦書き（右パネルとプレビュー、日にちは対象外） | Task 3 |
| ③ 削除API（ゴミ箱・開けない様式も対象・安全判定） | Task 4 |
| ③ 一覧からドット始まりを除外 | Task 4 Step 3 |
| ③ 削除ボタンと確認 | Task 5 |
| ④ スロットに `index` | Task 6 Step 3 |
| ④ `meta.month_start` / `meta.month_prev` | Task 6 Step 4 |
| ④ 左の一覧（month 型のときだけ） | Task 7 Step 1 |
| ④ プレビュー | Task 7 Step 2 |
| 後方互換の確認 | Task 8 Step 2 |
| 対象外（ミリ入力・戻す画面・世代管理・複製のUI・行間調整） | どのタスクでも触れない |

**未対応なし。**

**テスト件数の推移：** 276 → 280（Task 2）→ 289（Task 4）→ 295（Task 6）。

**名前の一貫性：**

- `TRASH_DIRNAME` は `forms_layout.py` で定義し、`app.py` は `forms_layout.TRASH_DIRNAME` を参照する（2か所に書かない）
- `_safe_form_dir_for_delete`（Task 4）は既存の `_resolve_form_dir` とは別物。**開けない様式も消せる必要があるため、意図的に別にしている**
- `meta.month_start` / `meta.month_prev` は、サーバー（`_field_value`）・プレビュー（`sampleValue`）・一覧（`collectItems`）の3か所に同じ名前で出てくる
- `field.vertical` は、サーバー（`_draw_field`）・右パネル（`renderProps`）・プレビュー（`renderPreview`）の3か所
