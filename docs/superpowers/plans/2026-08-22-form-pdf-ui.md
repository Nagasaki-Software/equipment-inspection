# 様式レイアウト画面と入力画面の改善 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 様式PDF上の配置を画面から作れるようにし、点検入力画面で数値項目を扱いやすくする。

**Architecture:** 新規画面 `/layout` は、既存の PDF.js（`static/pdfjs/pdf.mjs`）で様式PDFをキャンバスに描き、クリック位置を `viewport.convertToPdfPoint()` でPDF座標に変換して `layout.json` に保存する。点検入力画面は既存の `static/app.js` に数値入力欄・前回値・テンキー・全角変換を足す。

**Tech Stack:** PDF.js（既存）/ Vanilla JS（既存の書き方に合わせる）/ Flask / pytest

**設計書:** `docs/superpowers/specs/2026-08-22-inspection-form-pdf-design.md`

**前提:** `docs/superpowers/plans/2026-08-22-form-pdf-core.md` が完了していること。`/api/forms`、`/api/forms/<id>/layout`、`/api/forms/<id>/pdf` が動いている必要がある。

---

## 中核計画の実装で判明したこと（この計画に影響する）

第0〜2段階を実装した際に判明した事実。**同じことを再発見しないよう、着手前に必ず読むこと。**

| # | 事実 | この計画への影響 |
|---|---|---|
| 1 | `require_admin` は権限不足のとき **401** を返す（403ではない） | 画面側でエラー表示を出し分けるなら401を見る。テストの期待値も401 |
| 2 | 点検結果の `equipment_name` には**大分類**が入っている。機器を表すのはトップレベルの `category_minor` | `values` のキーは `"<category_minor>\|<点検項目名>"`。改善案5（前回値表示）のキーもこれに揃える |
| 3 | 数値項目の判定は `category_major` + `category_minor` + `inspection_item` の3つで絞る必要がある。項目名だけでは別機器の判定項目を巻き込む | 画面側で入力方式を判定するときも、表示中の機器の行だけを見ること |
| 4 | Flask の `send_file()` が返すレスポンスは direct passthrough モードで、`get_data()` を呼ぶと `RuntimeError` になる。`response.direct_passthrough = False` が必要 | 試し刷りAPIで既存レスポンスを読む場合に同じ罠がある |
| 5 | `layout.json` は UTF-8 必須。cp932 で保存されると `LayoutError` になる | レイアウト画面の保存は必ずAPI経由で行う（メモ帳での直接編集を促さない） |
| 6 | 様式PDFが0ページだと様式が黙って出ない問題があり、フォールバック扱いに修正済み | 新規様式のアップロード時に**ページ数が1以上か**を検証すること |
| 7 | `axis_position` は n が1未満だと `ValueError` を投げる | 画面側で欄番号を扱うときは1始まりに揃える |
| 8 | 様式IDは半角英数字とアンダースコアのみ、64文字以内。Windows予約名（`CON`/`NUL`等）も不可 | 新規作成画面で入力チェックと分かりやすいエラー文言を出すこと |
| 9 | `app.config['MAX_CONTENT_LENGTH']` は現在 **10MB** | 様式PDFの上限50MBを受けるには引き上げが必要（Task 7） |
| 10 | pypdf は `requirements.txt` で `>=6.16.1,<7` に固定済み | `merge_page` はページを writer に追加した**後**に呼ぶこと（順序を逆にすると非推奨警告が出る） |

---

## ファイル構成

| ファイル | 新規/変更 | 責務 |
|---|---|---|
| `static/layout.html` | 新規 | レイアウト画面のマークアップ |
| `static/layout.css` | 新規 | レイアウト画面のスタイル |
| `static/layout.js` | 新規 | 様式の読み込み、配置の作成・移動・保存、軸の設定、複製 |
| `app.py` | 変更 | `/layout` ルート、様式の新規作成、試し刷り |
| `static/app.js` | 変更 | 数値入力欄、全角変換、前回値、テンキー |
| `static/style.css` | 変更 | 数値入力欄とテンキーのスタイル |
| `static/inspection.html` | 変更 | 設定モーダルに様式フォルダと割り当て一覧を追加 |
| `tests/test_app.py` | 変更 | サーバ側のテストを追記 |

`static/layout.js` は600行前後になる見込み。1000行を超えるようなら、配置編集（`layout.js`）と様式管理（`layout-forms.js`）に分ける。

---

## Task 1: レイアウト画面の骨格

**Files:**
- Create: `static/layout.html`, `static/layout.css`, `static/layout.js`
- Modify: `app.py`（ルート追加）
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== レイアウト画面 ==========

def test_layout_page_returns_200(client):
    """レイアウト画面が開けること"""
    c, _ = client
    res = c.get("/layout")
    assert res.status_code == 200
    assert b"layout.js" in res.data
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k layout_page -v`
Expected: FAIL（404）

- [ ] **Step 3: ルートを追加する**

`app.py` の `def documents():` の後に追加する。

```python
@app.route("/layout")
@require_admin
def layout_editor():
    return send_from_directory(app.static_folder, "layout.html")
```

既存の `/inspection` などと同じ書き方に合わせること。既存が `render_template` を使っている場合はそちらに合わせる。

- [ ] **Step 4: 画面を作る**

`static/layout.html` を新規作成する。

```html
<!DOCTYPE html>
<html lang="ja">

<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>様式レイアウト</title>
    <link rel="stylesheet" href="/layout.css?v=1" />
</head>

<body>
    <header id="layout-header">
        <label>様式</label>
        <select id="form-select"></select>
        <button id="btn-new-form" type="button">新しい様式を追加</button>
        <button id="btn-preview" type="button">試し刷り</button>
        <button id="btn-save" type="button">保存</button>
        <a href="/inspection" id="btn-back">点検画面へ戻る</a>
        <span id="save-status"></span>
    </header>

    <main id="layout-main">
        <aside id="item-panel">
            <div class="panel-title">配置する項目</div>
            <div id="item-list"></div>
        </aside>

        <section id="pdf-panel">
            <div id="page-bar">
                <button id="btn-page-prev" type="button">◀</button>
                <span id="page-label">1 / 1</span>
                <button id="btn-page-next" type="button">▶</button>
            </div>
            <div id="canvas-wrap">
                <canvas id="form-canvas"></canvas>
                <div id="marker-layer"></div>
            </div>
        </section>

        <aside id="prop-panel">
            <div class="panel-title">選択中の設定</div>
            <div id="prop-body">
                <p class="hint">左の一覧から項目を選び、様式の上をクリックすると配置されます。</p>
            </div>
        </aside>
    </main>

    <footer id="axis-bar">
        <span>軸：</span>
        <button id="btn-axis-first" type="button">1つ目の欄を指定</button>
        <button id="btn-axis-second" type="button">2つ目の欄を指定</button>
        <span id="axis-step">ズレ x:0.0 y:0.0</span>
        <label>欄の数</label>
        <input type="number" id="axis-count" min="1" max="31" value="12" />
    </footer>

    <script type="module" src="/layout.js?v=1"></script>
</body>

</html>
```

`static/layout.css` を新規作成する。

```css
/* 様式レイアウト画面 */
* { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
    height: 100%;
    font-family: 'Meiryo', 'メイリオ', sans-serif;
    background: #f4f6f8;
    color: #222;
}

body { display: flex; flex-direction: column; }

#layout-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    background: #1a3a5c;
    color: #fff;
    font-size: 14px;
}

#layout-header select,
#layout-header input { font-size: 14px; padding: 4px 6px; }

#layout-header button,
#layout-header a {
    padding: 6px 14px;
    border: none;
    border-radius: 4px;
    background: #0096d6;
    color: #fff;
    font-size: 13px;
    cursor: pointer;
    text-decoration: none;
}

#btn-back { background: #547a9c; margin-left: auto; }
#save-status { font-size: 13px; min-width: 160px; }

#layout-main { flex: 1; display: flex; min-height: 0; }

#item-panel, #prop-panel {
    width: 260px;
    background: #fff;
    border-right: 1px solid #d5dbe0;
    overflow-y: auto;
    padding: 12px;
}

#prop-panel { border-right: none; border-left: 1px solid #d5dbe0; }

.panel-title {
    font-weight: 700;
    font-size: 13px;
    color: #1a3a5c;
    border-bottom: 1px solid #d5dbe0;
    padding-bottom: 6px;
    margin-bottom: 8px;
}

.item-group { font-weight: 700; font-size: 12px; margin: 10px 0 4px; color: #547a9c; }

.item-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 6px;
    font-size: 13px;
    cursor: pointer;
    border-radius: 4px;
}

.item-row:hover { background: #eef4fa; }
.item-row.selected { background: #d5e8f7; font-weight: 700; }
.item-row .placed { color: #27ae60; font-weight: 700; }

#pdf-panel { flex: 1; display: flex; flex-direction: column; min-width: 0; }

#page-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 12px;
    background: #e7ecf1;
    font-size: 13px;
}

#canvas-wrap {
    flex: 1;
    position: relative;
    overflow: auto;
    padding: 12px;
    text-align: center;
}

#form-canvas {
    box-shadow: 0 0 8px rgba(0, 0, 0, 0.25);
    background: #fff;
    cursor: crosshair;
}

#marker-layer { position: absolute; top: 12px; left: 0; right: 0; pointer-events: none; }

.marker {
    position: absolute;
    width: 14px;
    height: 14px;
    margin: -7px 0 0 -7px;
    border-radius: 50%;
    background: rgba(0, 150, 214, 0.75);
    border: 2px solid #fff;
    pointer-events: auto;
    cursor: move;
}

.marker.selected { background: #e67e22; }

#axis-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 16px;
    background: #fff;
    border-top: 1px solid #d5dbe0;
    font-size: 13px;
}

#axis-bar button {
    padding: 5px 12px;
    border: 1px solid #0096d6;
    border-radius: 4px;
    background: #fff;
    color: #0096d6;
    cursor: pointer;
}

#axis-bar button.active { background: #0096d6; color: #fff; }

.prop-row { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 13px; }
.prop-row label { min-width: 82px; color: #547a9c; font-weight: 600; }
.prop-row input[type="number"], .prop-row input[type="text"] { width: 90px; padding: 4px 6px; }
.hint { font-size: 12px; color: #888; line-height: 1.6; }
```

`static/layout.js` を新規作成する。この段階では「様式を選んでPDFを表示する」ところまで。

```js
import * as pdfjsLib from '/pdfjs/pdf.mjs';
pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdfjs/pdf.worker.mjs';

const state = {
    forms: [],          // /api/forms の結果
    formId: "",         // 選択中の様式ID
    layout: null,       // 選択中の layout.json
    pdfDoc: null,
    pageIndex: 0,       // 0始まり
    viewport: null,     // 現在描画に使った viewport
    equipment: [],      // /api/equipment の結果
    selectedItem: null, // 左の一覧で選んでいる項目のキー
    selectedField: -1,  // layout.fields のインデックス
    axisPick: 0,        // 0=なし 1=1つ目待ち 2=2つ目待ち
    axisFirst: null,    // 1つ目の欄のPDF座標
};

const $ = id => document.getElementById(id);

async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url} の取得に失敗しました (${res.status})`);
    return res.json();
}

function showStatus(msg, isError = false) {
    const el = $("save-status");
    el.textContent = msg;
    el.style.color = isError ? "#ffb4b4" : "#b7f0c4";
    clearTimeout(el._timer);
    el._timer = setTimeout(() => { el.textContent = ""; }, 5000);
}

/** 様式一覧を読み、プルダウンを作る */
async function loadForms() {
    state.forms = await fetchJson("/api/forms");
    const sel = $("form-select");
    sel.innerHTML = state.forms
        .map(f => `<option value="${f.id}">${f.error ? "⚠ " : ""}${f.form_name}</option>`)
        .join("");
    if (state.forms.length) {
        await selectForm(state.forms[0].id);
    }
}

/** 様式を1つ選んで、layout.json と様式PDFを読み込む */
async function selectForm(formId) {
    state.formId = formId;
    state.selectedField = -1;
    try {
        state.layout = await fetchJson(`/api/forms/${formId}/layout`);
    } catch (e) {
        showStatus(e.message, true);
        return;
    }
    const task = pdfjsLib.getDocument({
        url: `/api/forms/${formId}/pdf`,
        cMapUrl: "/pdfjs/cmaps/",
        cMapPacked: true,
    });
    state.pdfDoc = await task.promise;
    state.pageIndex = 0;
    $("axis-count").value = (state.layout.axis || {}).count || 12;
    updateAxisLabel();
    await renderPage();
}

/** 現在のページを描く */
async function renderPage() {
    if (!state.pdfDoc) return;
    const page = await state.pdfDoc.getPage(state.pageIndex + 1);
    const wrap = $("canvas-wrap");
    const base = page.getViewport({ scale: 1.0 });
    // 横幅に合わせる（縦に長い様式でもスクロールで見られるようにする）
    const scale = Math.min((wrap.clientWidth - 40) / base.width, 2.0);
    const viewport = page.getViewport({ scale });
    state.viewport = viewport;
    const canvas = $("form-canvas");
    const ctx = canvas.getContext("2d");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    canvas.style.width = viewport.width + "px";
    canvas.style.height = viewport.height + "px";
    await page.render({ canvasContext: ctx, viewport }).promise;
    $("page-label").textContent = `${state.pageIndex + 1} / ${state.pdfDoc.numPages}`;
}

function updateAxisLabel() {
    const axis = (state.layout && state.layout.axis) || {};
    $("axis-step").textContent =
        `ズレ x:${(axis.step_x || 0).toFixed(1)} y:${(axis.step_y || 0).toFixed(1)}`;
}

async function init() {
    state.equipment = await fetchJson("/api/equipment");
    await loadForms();
    $("form-select").addEventListener("change", e => selectForm(e.target.value));
    $("btn-page-prev").addEventListener("click", async () => {
        if (state.pageIndex > 0) { state.pageIndex--; await renderPage(); }
    });
    $("btn-page-next").addEventListener("click", async () => {
        if (state.pageIndex < state.pdfDoc.numPages - 1) {
            state.pageIndex++; await renderPage();
        }
    });
    window.addEventListener("resize", () => renderPage());
}

document.addEventListener("DOMContentLoaded", () => {
    init().catch(e => showStatus(e.message, true));
});

export { state, renderPage, selectForm };
```

- [ ] **Step 5: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k layout_page -v`
Expected: 1 passed

- [ ] **Step 6: ブラウザで確認**

`起動.bat` で起動し、`http://localhost:5000/layout` を開く。前計画の Task 15 で作った `forms/sample_daily` が選択され、様式PDFが表示されることを確認する。コンソールにエラーが出ていないことも確認する。

- [ ] **Step 7: コミット**

```bash
git add app.py static/layout.html static/layout.css static/layout.js tests/test_app.py
git commit -m "feat: add form layout editor screen skeleton"
```

---

## Task 2: 項目一覧とクリック配置

**Files:**
- Modify: `static/layout.js`

- [ ] **Step 1: 項目一覧を作る**

`layout.js` の `updateAxisLabel` の後に追加する。

```js
/** この様式に載る機器の点検項目を一覧化する */
function collectItems() {
    const targets = new Set((state.layout.targets || []));
    const groups = [{
        name: "共通",
        items: [
            { key: "meta.month", label: "タイトルの月" },
            { key: "meta.year", label: "タイトルの年" },
            { key: "meta.day", label: "日にち（土日祝は丸）" },
            { key: "meta.inspection_date", label: "点検日" },
            { key: "meta.inspector", label: "点検者名" },
            { key: "meta.department", label: "所属" },
            { key: "meta.building_name", label: "建物名" },
            { key: "meta.general_remark", label: "備考" },
        ],
    }];
    for (const name of state.layout.targets || []) {
        const items = state.equipment
            .filter(r => r.category_minor === name)
            .map(r => ({
                key: `item:${name}|${r.inspection_item}`,
                label: r.inspection_item,
            }));
        groups.push({ name, items });
    }
    if (!targets.size) groups.push({ name: "（対象機器が未設定です）", items: [] });
    return groups;
}

/** 左の一覧を描く。配置済みの項目には ✓ を付ける。 */
function renderItemList() {
    const placed = new Set((state.layout.fields || []).map(f => f.source));
    const html = collectItems().map(group => {
        const rows = group.items.map(it => `
            <div class="item-row" data-key="${it.key}">
              <span class="placed">${placed.has(it.key) ? "✓" : "　"}</span>
              <span>${escapeHtml(it.label)}</span>
            </div>`).join("");
        return `<div class="item-group">${escapeHtml(group.name)}</div>${rows}`;
    }).join("");
    $("item-list").innerHTML = html;
    $("item-list").querySelectorAll(".item-row").forEach(row => {
        row.addEventListener("click", () => {
            state.selectedItem = row.dataset.key;
            $("item-list").querySelectorAll(".item-row")
                .forEach(r => r.classList.remove("selected"));
            row.classList.add("selected");
        });
    });
}

function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
```

- [ ] **Step 2: クリックで配置する**

`layout.js` に追加する。

```js
/** キャンバス上の座標をPDF座標に変換する */
function toPdfPoint(clientX, clientY) {
    const canvas = $("form-canvas");
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const [px, py] = state.viewport.convertToPdfPoint(x, y);
    return [Math.round(px * 10) / 10, Math.round(py * 10) / 10];
}

/** PDF座標をキャンバス上の座標に戻す */
function toViewportPoint(px, py) {
    return state.viewport.convertToViewportPoint(px, py);
}

/** クリックした場所に、選択中の項目を配置する */
function placeSelectedItem(clientX, clientY) {
    if (!state.selectedItem) {
        showStatus("先に左の一覧から項目を選んでください", true);
        return;
    }
    const [x, y] = toPdfPoint(clientX, clientY);
    const fields = state.layout.fields || (state.layout.fields = []);
    const index = fields.findIndex(f => f.source === state.selectedItem
        && f.page === state.pageIndex);
    const field = {
        source: state.selectedItem,
        page: state.pageIndex,
        x, y,
        on_axis: state.layout.period !== "single",
    };
    if (index >= 0) {
        fields[index] = { ...fields[index], ...field };
        state.selectedField = index;
    } else {
        fields.push(field);
        state.selectedField = fields.length - 1;
    }
    renderItemList();
    renderMarkers();
    renderProps();
}
```

- [ ] **Step 3: 配置の印を描く**

```js
/** 配置済みの印をPDFの上に重ねて表示する */
function renderMarkers() {
    const layer = $("marker-layer");
    const canvas = $("form-canvas");
    layer.style.width = canvas.width + "px";
    layer.style.height = canvas.height + "px";
    layer.style.left = canvas.offsetLeft + "px";
    const fields = state.layout.fields || [];
    layer.innerHTML = fields.map((f, i) => {
        if (f.page !== state.pageIndex) return "";
        const [vx, vy] = toViewportPoint(f.x, f.y);
        const cls = i === state.selectedField ? "marker selected" : "marker";
        return `<div class="${cls}" data-index="${i}" style="left:${vx}px; top:${vy}px" title="${escapeHtml(f.source)}"></div>`;
    }).join("");
    layer.querySelectorAll(".marker").forEach(m => {
        m.addEventListener("mousedown", e => {
            e.stopPropagation();
            state.selectedField = Number(m.dataset.index);
            renderMarkers();
            renderProps();
            startDrag(e);
        });
    });
}
```

- [ ] **Step 4: 右パネルに設定を出す**

```js
/** 選択中の配置の設定を右パネルに描く */
function renderProps() {
    const f = (state.layout.fields || [])[state.selectedField];
    if (!f) {
        $("prop-body").innerHTML =
            '<p class="hint">左の一覧から項目を選び、様式の上をクリックすると配置されます。</p>';
        return;
    }
    const isDay = f.source === "meta.day";
    $("prop-body").innerHTML = `
      <div class="prop-row"><label>項目</label><span>${escapeHtml(f.source)}</span></div>
      <div class="prop-row"><label>X</label>
        <input type="number" id="p-x" step="0.1" value="${f.x}" /></div>
      <div class="prop-row"><label>Y</label>
        <input type="number" id="p-y" step="0.1" value="${f.y}" /></div>
      <div class="prop-row"><label>文字サイズ</label>
        <input type="number" id="p-size" step="0.5" value="${f.font_size || ""}" /></div>
      <div class="prop-row"><label>色</label>
        <input type="text" id="p-color" value="${f.color || "#000000"}" /></div>
      ${isDay ? `<div class="prop-row"><label>丸の半径</label>
        <input type="number" id="p-radius" step="0.5" value="${f.circle_radius || ""}" /></div>` : ""}
      <div class="prop-row"><label>軸に沿う</label>
        <input type="checkbox" id="p-axis" ${f.on_axis ? "checked" : ""} /></div>
      <div class="prop-row">
        <button id="p-delete" type="button">この配置を削除</button></div>
    `;
    const bind = (id, key, isNumber) => {
        const el = $(id);
        if (!el) return;
        el.addEventListener("change", () => {
            const v = isNumber ? Number(el.value) : el.value;
            if (isNumber && el.value === "") delete f[key];
            else f[key] = v;
            renderMarkers();
        });
    };
    bind("p-x", "x", true);
    bind("p-y", "y", true);
    bind("p-size", "font_size", true);
    bind("p-color", "color", false);
    bind("p-radius", "circle_radius", true);
    const axisEl = $("p-axis");
    if (axisEl) axisEl.addEventListener("change", () => {
        f.on_axis = axisEl.checked;
    });
    $("p-delete").addEventListener("click", () => {
        state.layout.fields.splice(state.selectedField, 1);
        state.selectedField = -1;
        renderItemList();
        renderMarkers();
        renderProps();
    });
}
```

- [ ] **Step 5: 画面の初期化に組み込む**

`selectForm()` の `await renderPage();` の後に追加する。

```js
    renderItemList();
    renderMarkers();
    renderProps();
```

`renderPage()` の末尾（`$("page-label").textContent = ...` の後）に追加する。

```js
    renderMarkers();
```

`init()` に追加する。

```js
    $("form-canvas").addEventListener("click", e => {
        if (state.axisPick) { handleAxisPick(e); return; }
        placeSelectedItem(e.clientX, e.clientY);
    });
```

`handleAxisPick` は Task 4 で実装する。それまでは次の仮実装を置いておく。

```js
function handleAxisPick(e) { /* Task 4 で実装する */ }
```

- [ ] **Step 6: ブラウザで確認**

`/layout` を開き、左の一覧から「点検者名」を選び、様式の上をクリックする。印が付き、一覧に✓が付き、右パネルに座標が出ることを確認する。

- [ ] **Step 7: コミット**

```bash
git add static/layout.js
git commit -m "feat: place fields by clicking the form PDF"
```

---

## Task 3: ドラッグ移動と矢印キーの微調整

**Files:**
- Modify: `static/layout.js`

- [ ] **Step 1: ドラッグを実装する**

```js
/** 印をドラッグして位置を調整する */
function startDrag(downEvent) {
    const f = (state.layout.fields || [])[state.selectedField];
    if (!f) return;
    const move = e => {
        const [x, y] = toPdfPoint(e.clientX, e.clientY);
        f.x = x;
        f.y = y;
        renderMarkers();
    };
    const up = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
        renderProps();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
    downEvent.preventDefault();
}
```

- [ ] **Step 2: 矢印キーの微調整を実装する**

`init()` に追加する。

```js
    document.addEventListener("keydown", e => {
        // 入力欄の中では矢印キーを本来の用途に譲る
        const tag = (e.target.tagName || "").toLowerCase();
        if (tag === "input" || tag === "select" || tag === "textarea") return;
        const f = (state.layout && state.layout.fields || [])[state.selectedField];
        if (!f) return;
        const step = e.shiftKey ? 10 : 1;
        if (e.key === "ArrowLeft") f.x -= step;
        else if (e.key === "ArrowRight") f.x += step;
        else if (e.key === "ArrowUp") f.y += step;      // PDF座標は上が正
        else if (e.key === "ArrowDown") f.y -= step;
        else return;
        e.preventDefault();
        f.x = Math.round(f.x * 10) / 10;
        f.y = Math.round(f.y * 10) / 10;
        renderMarkers();
        renderProps();
    });
```

PDF座標は左下が原点で上が正のため、**上キーで y を増やす**。画面座標と符号が逆になる点に注意する。

- [ ] **Step 3: ブラウザで確認**

配置した印をドラッグして動かせること、選択した状態で矢印キーを押すと1ずつ、Shift＋矢印キーで10ずつ動くことを確認する。右パネルのXとYの数値も追随することを確認する。

- [ ] **Step 4: コミット**

```bash
git add static/layout.js
git commit -m "feat: drag markers and nudge with arrow keys"
```

---

## Task 4: 軸の設定

**Files:**
- Modify: `static/layout.js`

- [ ] **Step 1: 2点クリックでズレ幅を求める**

`handleAxisPick` の仮実装を次で置き換える。

```js
/** 「1つ目の欄」「2つ目の欄」をクリックしてズレ幅を求める */
function handleAxisPick(e) {
    const [x, y] = toPdfPoint(e.clientX, e.clientY);
    if (state.axisPick === 1) {
        state.axisFirst = [x, y];
        state.axisPick = 2;
        $("btn-axis-first").classList.remove("active");
        $("btn-axis-second").classList.add("active");
        showStatus("2つ目の欄をクリックしてください");
        return;
    }
    if (state.axisPick === 2 && state.axisFirst) {
        const axis = state.layout.axis || (state.layout.axis = {});
        axis.step_x = Math.round((x - state.axisFirst[0]) * 10) / 10;
        axis.step_y = Math.round((y - state.axisFirst[1]) * 10) / 10;
        axis.count = Number($("axis-count").value) || 12;
        state.axisPick = 0;
        state.axisFirst = null;
        $("btn-axis-second").classList.remove("active");
        updateAxisLabel();
        showStatus(`ズレ幅を x:${axis.step_x} y:${axis.step_y} に設定しました`);
    }
}
```

- [ ] **Step 2: ボタンを配線する**

`init()` に追加する。

```js
    $("btn-axis-first").addEventListener("click", () => {
        state.axisPick = 1;
        state.axisFirst = null;
        $("btn-axis-first").classList.add("active");
        $("btn-axis-second").classList.remove("active");
        showStatus("1つ目の欄をクリックしてください");
    });
    $("btn-axis-second").addEventListener("click", () => {
        if (!state.axisFirst) {
            showStatus("先に1つ目の欄を指定してください", true);
            return;
        }
        state.axisPick = 2;
        $("btn-axis-second").classList.add("active");
    });
    $("axis-count").addEventListener("change", () => {
        const axis = state.layout.axis || (state.layout.axis = {});
        axis.count = Number($("axis-count").value) || 12;
    });
```

- [ ] **Step 3: ブラウザで確認**

「1つ目の欄を指定」を押して様式の1番目の欄をクリック、続けて2番目の欄をクリックする。フッターの「ズレ x:… y:…」が更新されることを確認する。

- [ ] **Step 4: コミット**

```bash
git add static/layout.js
git commit -m "feat: set axis step by clicking two adjacent cells"
```

---

## Task 5: 保存と未配置チェック

**Files:**
- Modify: `static/layout.js`

- [ ] **Step 1: 保存処理を書く**

```js
/** 配置していない項目の数を数える */
function countUnplaced() {
    const placed = new Set((state.layout.fields || []).map(f => f.source));
    let n = 0;
    for (const group of collectItems()) {
        for (const it of group.items) {
            // 共通項目は必須ではないので数えない
            if (it.key.startsWith("meta.")) continue;
            if (!placed.has(it.key)) n++;
        }
    }
    return n;
}

/** layout.json を保存する */
async function saveLayout() {
    if (!state.formId || !state.layout) return;
    const unplaced = countUnplaced();
    if (unplaced > 0) {
        const ok = confirm(
            `配置していない点検項目が ${unplaced} 件あります。このまま保存しますか？`);
        if (!ok) return;
    }
    const res = await fetch(`/api/forms/${state.formId}/layout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state.layout),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showStatus(err.error || `保存に失敗しました (${res.status})`, true);
        return;
    }
    showStatus("✓ 保存しました");
}
```

- [ ] **Step 2: ボタンを配線する**

`init()` に追加する。

```js
    $("btn-save").addEventListener("click", () => {
        saveLayout().catch(e => showStatus(e.message, true));
    });
```

- [ ] **Step 3: ブラウザで確認**

配置を1つ足して「保存」を押す。未配置がある場合に確認ダイアログが出ること、OKすると「✓ 保存しました」が出ることを確認する。画面を再読み込みして配置が残っていることも確認する。

- [ ] **Step 4: コミット**

```bash
git add static/layout.js
git commit -m "feat: save layout with unplaced item warning"
```

---

## Task 6: 配置のまるごと複製

**Files:**
- Modify: `static/layout.js`

- [ ] **Step 1: 複製のUIと処理を書く**

`renderProps()` の `<button id="p-delete" ...>` の行の後に、複製ボタンを足す。

```js
      <div class="prop-row">
        <button id="p-copy" type="button">機器ごと複製...</button></div>
```

`renderProps()` の末尾（`$("p-delete").addEventListener(...)` の後）に追加する。

```js
    const copyBtn = $("p-copy");
    if (copyBtn) copyBtn.addEventListener("click", openCopyDialog);
```

`layout.js` に追加する。

```js
/** 機器を選び、その機器の配置一式を別の機器へずらして複製する */
function openCopyDialog() {
    const targets = state.layout.targets || [];
    if (targets.length < 2) {
        showStatus("複製するには対象機器が2つ以上必要です", true);
        return;
    }
    const from = prompt(`複製元の機器名\n候補: ${targets.join(" / ")}`, targets[0]);
    if (!from) return;
    const to = prompt(`複製先の機器名\n候補: ${targets.join(" / ")}`, targets[1]);
    if (!to || to === from) return;
    const dx = Number(prompt("X方向にいくつずらしますか（右が正）", "0"));
    const dy = Number(prompt("Y方向にいくつずらしますか（上が正）", "-20"));
    if (Number.isNaN(dx) || Number.isNaN(dy)) {
        showStatus("ずらす量は数値で入力してください", true);
        return;
    }
    copyFields(from, to, dx, dy);
}

/** 複製の本体。複製先に無い点検項目は飛ばして件数を返す。 */
function copyFields(from, to, dx, dy) {
    const prefixFrom = `item:${from}|`;
    const toItems = new Set(state.equipment
        .filter(r => r.category_minor === to)
        .map(r => r.inspection_item));
    const fields = state.layout.fields || [];
    let copied = 0, skipped = 0;
    for (const f of [...fields]) {
        if (!f.source.startsWith(prefixFrom)) continue;
        const itemName = f.source.slice(prefixFrom.length);
        if (!toItems.has(itemName)) { skipped++; continue; }
        const newSource = `item:${to}|${itemName}`;
        const existing = fields.findIndex(
            g => g.source === newSource && g.page === f.page);
        const clone = { ...f, source: newSource,
                        x: Math.round((f.x + dx) * 10) / 10,
                        y: Math.round((f.y + dy) * 10) / 10 };
        if (existing >= 0) fields[existing] = clone;
        else fields.push(clone);
        copied++;
    }
    renderItemList();
    renderMarkers();
    showStatus(skipped
        ? `${copied}件を複製しました（対応する項目が無い ${skipped}件は飛ばしました）`
        : `${copied}件を複製しました`);
}
```

- [ ] **Step 2: ブラウザで確認**

対象機器が2つ以上ある様式で、1つ目の機器の項目をいくつか配置してから「機器ごと複製...」を押す。複製先の機器の項目に✓が付き、印がずらした位置に増えることを確認する。

- [ ] **Step 3: コミット**

```bash
git add static/layout.js
git commit -m "feat: copy field placements from one equipment to another"
```

---

## Task 7: 新しい様式の追加

**Files:**
- Modify: `app.py`（`POST /api/forms`）、`static/layout.js`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_api_create_form(client, monkeypatch, tmp_path):
    """様式PDFをアップロードして様式を作れること"""
    import io as _io
    import app as flask_app
    forms_dir = tmp_path / "forms"
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    pdf_path = _make_form_pdf(tmp_path / "src.pdf")
    c, _ = client
    res = c.post("/api/forms", data={
        "form_id": "new_form",
        "form_name": "新しい様式",
        "period": "month",
        "inspection_type": "使用前",
        "targets": json.dumps(["A-1"]),
        "file": (_io.BytesIO(pdf_path.read_bytes()), "form.pdf"),
    }, content_type="multipart/form-data")
    assert res.status_code == 200
    assert (forms_dir / "new_form" / "form.pdf").exists()
    assert (forms_dir / "new_form" / "layout.json").exists()


def test_api_create_form_rejects_non_pdf(client, monkeypatch, tmp_path):
    """PDFでないファイルは400になること"""
    import io as _io
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: tmp_path / "forms")
    c, _ = client
    res = c.post("/api/forms", data={
        "form_id": "bad_form",
        "form_name": "だめな様式",
        "period": "month",
        "inspection_type": "使用前",
        "targets": json.dumps([]),
        "file": (_io.BytesIO(b"this is not a pdf"), "form.pdf"),
    }, content_type="multipart/form-data")
    assert res.status_code == 400


def test_api_create_form_rejects_bad_id(client, monkeypatch, tmp_path):
    """様式IDに使えない文字があると400になること"""
    import io as _io
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: tmp_path / "forms")
    pdf_path = _make_form_pdf(tmp_path / "src.pdf")
    c, _ = client
    res = c.post("/api/forms", data={
        "form_id": "../escape",
        "form_name": "脱出",
        "period": "month",
        "inspection_type": "使用前",
        "targets": json.dumps([]),
        "file": (_io.BytesIO(pdf_path.read_bytes()), "form.pdf"),
    }, content_type="multipart/form-data")
    assert res.status_code == 400
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k create_form -v`
Expected: FAIL（405 または 404）

- [ ] **Step 3: APIを実装する**

`app.py` の `api_get_form_pdf` の後に追加する。

```python
MAX_FORM_PDF_BYTES = 50 * 1024 * 1024


@app.route("/api/forms", methods=["POST"])
@require_admin
def api_create_form():
    form_id = Path(request.form.get("form_id", "")).name
    if not forms_layout.is_valid_form_id(form_id):
        return jsonify({"error": "様式IDは半角英数字とアンダースコアで指定してください"}), 400
    forms_dir = get_forms_directory()
    form_dir = forms_dir / form_id
    if form_dir.exists():
        return jsonify({"error": "同じ様式IDが既にあります"}), 400

    upload = request.files.get("file")
    if upload is None:
        return jsonify({"error": "様式PDFを選んでください"}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDFファイルを選んでください"}), 400
    content = upload.read()
    if len(content) > MAX_FORM_PDF_BYTES:
        return jsonify({"error": "様式PDFが大きすぎます（上限50MB）"}), 400
    if content[:5] != b"%PDF-":
        return jsonify({"error": "PDFファイルではありません"}), 400

    try:
        targets = json.loads(request.form.get("targets", "[]"))
    except json.JSONDecodeError:
        return jsonify({"error": "targets の形式が不正です"}), 400
    if not isinstance(targets, list):
        return jsonify({"error": "targets は配列で指定してください"}), 400

    period = request.form.get("period", "month")
    layout = {
        "form_name": request.form.get("form_name", form_id),
        "period": period,
        "inspection_type": request.form.get("inspection_type", "使用前"),
        "targets": targets,
        "default_font_size": 11,
        "fields": [],
    }
    if period in forms_layout.DEFAULT_AXIS_COUNT:
        layout["axis"] = {"step_x": 0.0, "step_y": 0.0,
                          "count": forms_layout.DEFAULT_AXIS_COUNT[period]}

    form_dir.mkdir(parents=True)
    try:
        # save_layout が内容を検証する。不正ならフォルダを作り直さず消して戻す。
        forms_layout.save_layout(form_dir, layout)
    except forms_layout.LayoutError as e:
        form_dir.rmdir()
        return jsonify({"error": str(e)}), 400
    (form_dir / forms_layout.FORM_PDF_FILENAME).write_bytes(content)
    logger.info("様式を新規作成: %s", form_id)
    return jsonify({"status": "ok", "id": form_id})
```

`app.config['MAX_CONTENT_LENGTH']` は現在10MBのため、50MBの様式を受け付けるには引き上げが必要になる。**アップロードの上限は50MBに合わせて `app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024` に変更する。** 変更したら、既存の「大きすぎるリクエストを弾く」テストが通ることを確認すること。

- [ ] **Step 4: 画面から使えるようにする**

`layout.js` に追加する。

```js
/** 新しい様式を追加する */
async function createForm() {
    const formId = prompt("様式ID（半角英数字とアンダースコア）", "");
    if (!formId) return;
    const formName = prompt("様式の名前（日本語可）", formId);
    if (!formName) return;
    const period = prompt("様式の型\nyear=1枚に1年分 / month=1枚に1サイクル分 / single=1回1枚",
                          "month");
    if (!["year", "month", "single"].includes(period)) {
        showStatus("様式の型は year / month / single のいずれかです", true);
        return;
    }
    const inspectionType = prompt("点検種別（使用前 または 月例）", "使用前");
    const minors = [...new Set(state.equipment.map(r => r.category_minor))];
    const targets = (prompt(
        `この様式に載る機器をカンマ区切りで\n候補: ${minors.join(" / ")}`, "") || "")
        .split(",").map(s => s.trim()).filter(Boolean);

    const picker = document.createElement("input");
    picker.type = "file";
    picker.accept = "application/pdf";
    picker.addEventListener("change", async () => {
        const file = picker.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append("form_id", formId);
        fd.append("form_name", formName);
        fd.append("period", period);
        fd.append("inspection_type", inspectionType);
        fd.append("targets", JSON.stringify(targets));
        fd.append("file", file);
        const res = await fetch("/api/forms", { method: "POST", body: fd });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            showStatus(err.error || `作成に失敗しました (${res.status})`, true);
            return;
        }
        showStatus("✓ 様式を作成しました");
        await loadForms();
        $("form-select").value = formId;
        await selectForm(formId);
    });
    picker.click();
}
```

`init()` に追加する。

```js
    $("btn-new-form").addEventListener("click", () => {
        createForm().catch(e => showStatus(e.message, true));
    });
```

- [ ] **Step 5: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: すべて passed

- [ ] **Step 6: ブラウザで確認**

「新しい様式を追加」から様式PDFを選び、作成した様式が一覧に増えて選択されることを確認する。

- [ ] **Step 7: コミット**

```bash
git add app.py static/layout.js tests/test_app.py
git commit -m "feat: create a new form by uploading a form PDF"
```

---

## Task 8: 試し刷り

**Files:**
- Modify: `app.py`（`GET /api/forms/<id>/preview`）、`static/layout.js`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_api_form_preview(client, monkeypatch, tmp_path):
    """試し刷りPDFが生成できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/preview?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert res.data[:5] == b"%PDF-"


def test_api_form_preview_fills_all_slots(client, monkeypatch, tmp_path):
    """試し刷りは全欄を埋めること（28日サイクルでも29〜31に「ー」が入る）"""
    from pypdf import PdfReader
    import io as _io
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/preview?display_year=2026&display_month=3")
    text = PdfReader(_io.BytesIO(res.data)).pages[0].extract_text()
    assert "○" in text
    assert "ー" in text


def test_api_form_preview_not_found(client, monkeypatch, tmp_path):
    """存在しない様式は404になること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: tmp_path / "forms")
    c, _ = client
    assert c.get("/api/forms/nothing/preview").status_code == 404
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k form_preview -v`
Expected: FAIL（404）

- [ ] **Step 3: サンプルデータの生成を pdf_forms.py に足す**

```python
SAMPLE_INSPECTOR = "見本 太郎"
SAMPLE_DEPARTMENT = "見本部"
SAMPLE_NUMBER = "0.00"


def build_sample_records(layout: dict, cycle_dates: list, display_year: int,
                         number_items: set) -> list:
    """試し刷り用のダミー記録を作る。全欄が埋まるように日付を網羅する。"""
    records = []
    targets = layout.get("targets", [])
    item_names = layout_item_names(layout)
    if layout.get("period") == "year":
        dates = [f"{display_year}-{m:02d}-01" for m in range(1, 13)]
    else:
        dates = [d.strftime("%Y-%m-%d") for d in cycle_dates] or \
                [f"{display_year}-01-01"]
    for name in targets:
        for date_str in dates:
            results = [
                {"equipment_name": name, "inspection_item": item,
                 "result": SAMPLE_NUMBER if item in number_items else "○",
                 "remark": ""}
                for (equip, item) in item_names if equip == name
            ]
            records.append({
                "inspection_date": date_str,
                "inspection_type": layout.get("inspection_type", "使用前"),
                "category_minor": name,
                "inspector_name": SAMPLE_INSPECTOR,
                "department": SAMPLE_DEPARTMENT,
                "general_remark": "",
                "building_name": "見本ビル",
                "results": results,
                "submitted_at": f"{date_str}T09:00:00",
            })
    return records


def layout_item_names(layout: dict) -> list:
    """layout.json の fields から (機器名, 点検項目名) の一覧を取り出す"""
    names = []
    for field in layout.get("fields", []):
        source = field.get("source", "")
        if not source.startswith("item:"):
            continue
        body = source[len("item:"):]
        if "|" in body:
            equip, item = body.split("|", 1)
            names.append((equip, item))
    return names
```

- [ ] **Step 4: APIを実装する**

`app.py` の `api_create_form` の後に追加する。

```python
@app.route("/api/forms/<form_id>/preview")
@require_admin
def api_form_preview(form_id):
    form_dir = _resolve_form_dir(form_id)
    if form_dir is None:
        return jsonify({"error": "Not found"}), 404
    try:
        display_year = int(request.args.get("display_year", datetime.now().year))
        display_month = int(request.args.get("display_month", datetime.now().month))
    except (ValueError, TypeError):
        return jsonify({"error": "パラメータが不正です"}), 400
    try:
        layout = forms_layout.load_layout(form_dir)
    except forms_layout.LayoutError as e:
        return jsonify({"error": str(e)}), 400
    cycle_dates = get_cycle_dates(display_year, display_month)
    records = pdf_forms.build_sample_records(
        layout, cycle_dates, display_year, _number_item_keys())
    try:
        writer = pdf_forms.build_form_writer(
            form_dir, layout, records, display_year, display_month,
            cycle_dates, _load_custom_holidays())
    except FileNotFoundError:
        return jsonify({"error": "様式PDFがありません"}), 404
    if writer is None:
        return jsonify({"error": "試し刷りするデータを作れませんでした"}), 400
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    response = make_response(buf.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'inline; filename="preview_{form_dir.name}.pdf"')
    return response
```

- [ ] **Step 5: 画面から使えるようにする**

`layout.js` の `init()` に追加する。

```js
    $("btn-preview").addEventListener("click", async () => {
        if (!state.formId) return;
        // 保存していない配置も試したいので、先に保存する
        await saveLayout();
        const ym = prompt(
            "どの月で試し刷りしますか（YYYY-MM）\n" +
            "28日サイクルの月と31日サイクルの月の両方で確認すると確実です",
            new Date().toISOString().slice(0, 7));
        if (!ym) return;
        const [y, m] = ym.split("-").map(Number);
        if (!y || !m) { showStatus("YYYY-MM の形式で入力してください", true); return; }
        window.open(
            `/api/forms/${state.formId}/preview?display_year=${y}&display_month=${m}`,
            "_blank");
    });
```

- [ ] **Step 6: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: すべて passed

- [ ] **Step 7: ブラウザで確認**

「試し刷り」を押し、2026-03 を指定する。日にちと丸、○が全欄に入り、29〜31番目に「ー」が入っていることを確認する。2026-09 でも試し、余りマスが無いことを確認する。

- [ ] **Step 8: コミット**

```bash
git add app.py pdf_forms.py static/layout.js tests/test_app.py
git commit -m "feat: add sample print preview for form layouts"
```

---

## Task 9: 点検入力画面の数値入力欄

**Files:**
- Modify: `static/app.js`（点検表の描画部分、`static/app.js:322-352` 付近）、`static/style.css`

- [ ] **Step 1: 入力方式を引くヘルパーを足す**

`static/app.js` のユーティリティ（`escapeHtml` の後）に追加する。

```js
/** 点検項目の入力方式を返す（マスタに列が無ければ「判定」） */
function itemInputType(row) {
    const v = (row.input_type || "").trim();
    return v === "数値" ? "数値" : "判定";
}

/** 点検項目の単位を返す（数値項目以外は空文字） */
function itemUnit(row) {
    return itemInputType(row) === "数値" ? (row.unit || "").trim() : "";
}
```

- [ ] **Step 2: 描画を分岐させる**

`static/app.js:330` 付近の `<div class="result-btns">` を生成している箇所を、入力方式で分岐させる。判定項目の既存のHTMLは**そのまま残す**。

```js
        const inputType = itemInputType(row);
        const cell = inputType === "数値"
            ? `
        <div class="result-number">
          <input type="text" class="num-input" inputmode="decimal"
                 data-key="${key}" value="${escapeHtml(saved.result || "")}"
                 ${disabledAttr} />
          <span class="num-unit">${escapeHtml(itemUnit(row))}</span>
          <button class="btn-dash btn-num-na${saved.result === "ー" ? " selected" : ""}"
                  data-key="${key}" ${disabledAttr} title="点検対象外">ー</button>
        </div>`
            : `
        <div class="result-btns">
          <button class="btn-maru${saved.result === "○" ? " selected" : ""}"
                  data-key="${key}" data-val="○" ${disabledAttr}>○</button>
          <button class="btn-batsu${saved.result === "×" ? " selected" : ""}"
                  data-key="${key}" data-val="×" ${disabledAttr}>×</button>
          <button class="btn-dash${saved.result === "ー" ? " selected" : ""}"
                  data-key="${key}" data-val="ー" ${disabledAttr}>ー</button>
        </div>`;
```

既存のテンプレートの `<div class="result-btns">...</div>` を `${cell}` に置き換える。`row` はその行の点検項目マスタのオブジェクト。この関数に `row` が渡っていない場合は、呼び出し元から渡すよう引数を足す。

- [ ] **Step 3: 数値入力を state に反映する**

既存の `.btn-maru` などにイベントを付けている箇所（`static/app.js:348` 付近）の後に追加する。

```js
    document.querySelectorAll(".num-input").forEach(input => {
        input.addEventListener("input", () => {
            const key = input.dataset.key;
            if (!state.inspectionResults[key]) {
                state.inspectionResults[key] = { result: "", remark: "" };
            }
            state.inspectionResults[key].result = input.value;
        });
    });

    // 「ー」ボタン：その日は点検対象外、という記録。もう一度押すと解除する。
    document.querySelectorAll(".btn-num-na").forEach(btn => {
        btn.addEventListener("click", () => {
            const key = btn.dataset.key;
            if (!state.inspectionResults[key]) {
                state.inspectionResults[key] = { result: "", remark: "" };
            }
            const isOn = state.inspectionResults[key].result === "ー";
            state.inspectionResults[key].result = isOn ? "" : "ー";
            const input = document.querySelector(`.num-input[data-key="${key}"]`);
            if (input) input.value = state.inspectionResults[key].result;
            btn.classList.toggle("selected", !isOn);
        });
    });
```

- [ ] **Step 4: スタイルを足す**

`static/style.css` の末尾に追加する。

```css
/* ===== 数値入力項目 ===== */
.result-number {
    display: flex;
    align-items: center;
    gap: 6px;
    justify-content: center;
}

.num-input {
    width: 90px;
    padding: 8px 10px;
    font-size: 18px;
    text-align: right;
    border: 1px solid #b7c3cd;
    border-radius: 4px;
}

.num-input:focus {
    outline: none;
    border-color: #0096d6;
    box-shadow: 0 0 0 2px rgba(0, 150, 214, 0.2);
}

.num-unit { font-size: 13px; color: #547a9c; min-width: 32px; }
```

- [ ] **Step 5: 確認用にマスタへ数値項目を1行足す**

`data/equipment_master.csv` の見出し行に `,input_type,unit` を足し、確認用に1行だけ数値項目を加える。

```csv
category_major,category_minor,inspection_item,inspection_type,input_type,unit
クレーン,床上操作式クレーン,傷はないか,使用前,判定,
設備A,A-1,油圧,使用前,数値,MPa
```

既存の行は `input_type` / `unit` が空欄のままでよい（判定として読まれる）。

- [ ] **Step 6: ブラウザで確認**

点検画面で「設備A / A-1」を開き、「油圧」の行が数値入力欄＋「MPa」になっていること、他の行が今までどおり○×ーボタンであることを確認する。値を入れて保存し、再読み込みで復元されることも確認する。

- [ ] **Step 7: コミット**

```bash
git add static/app.js static/style.css data/equipment_master.csv
git commit -m "feat: show numeric input for number-type inspection items"
```

---

## Task 10: 全角数字の自動変換

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: 変換関数を足す**

`itemUnit` の後に追加する。

```js
/** 全角数字・全角ピリオド・全角マイナスを半角に直す */
function normalizeNumberInput(value) {
    if (typeof value !== "string") return value;
    return value
        .replace(/[０-９]/g, ch => String.fromCharCode(ch.charCodeAt(0) - 0xFEE0))
        .replace(/[．。]/g, ".")
        .replace(/[－−ー―]/g, "-")
        .replace(/[　\s]/g, "")
        .trim();
}
```

`ー`（長音）も半角マイナスに変換する。数値項目にしか適用しないため、判定項目の「ー」には影響しない。

- [ ] **Step 2: フォーカスが外れたときに変換する**

Task 9 の `.num-input` のイベント登録に追加する。

```js
        input.addEventListener("blur", () => {
            const normalized = normalizeNumberInput(input.value);
            if (normalized !== input.value) input.value = normalized;
            const key = input.dataset.key;
            if (!state.inspectionResults[key]) {
                state.inspectionResults[key] = { result: "", remark: "" };
            }
            state.inspectionResults[key].result = normalized;
        });
```

- [ ] **Step 3: ブラウザで確認**

日本語入力をONにして数値欄に「０．５２」と入力し、欄の外をクリックすると「0.52」に変わることを確認する。保存後に結果ファイルでも半角になっていることを確認する（サーバ側でも正規化されるため二重に守られる）。

- [ ] **Step 4: コミット**

```bash
git add static/app.js
git commit -m "feat: convert full-width digits to half-width on numeric input"
```

---

## Task 11: 前回値の表示

**Files:**
- Modify: `app.py`（`GET /api/results/previous`）、`static/app.js`、`static/style.css`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_api_previous_values(client, monkeypatch, tmp_path):
    """直近の数値記録を取得できること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "2026-03-02",
        "category_major": "設備A",
        "category_minor": "A-1",
        "inspector_name": "テスト",
        "department": "テスト部",
        "results": [{"equipment_name": "設備A", "inspection_item": "油圧",
                     "result": "0.52", "remark": ""}],
    }
    c.post("/api/results", data=json.dumps(payload),
           content_type="application/json")
    res = c.get("/api/results/previous?type=使用前&category_minor=A-1"
                "&before=2026-03-05")
    assert res.status_code == 200
    assert res.get_json()["設備A|油圧"] == "0.52"


def test_api_previous_values_excludes_same_day(client, monkeypatch, tmp_path):
    """指定日そのものは前回値に含めないこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "2026-03-05",
        "category_major": "設備A",
        "category_minor": "A-1",
        "inspector_name": "テスト",
        "department": "テスト部",
        "results": [{"equipment_name": "設備A", "inspection_item": "油圧",
                     "result": "0.60", "remark": ""}],
    }
    c.post("/api/results", data=json.dumps(payload),
           content_type="application/json")
    res = c.get("/api/results/previous?type=使用前&category_minor=A-1"
                "&before=2026-03-05")
    assert res.get_json() == {}


def test_api_previous_values_invalid_date(client):
    """日付が不正なら400になること"""
    c, _ = client
    res = c.get("/api/results/previous?type=使用前&category_minor=A-1&before=xx")
    assert res.status_code == 400
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k previous_values -v`
Expected: FAIL（404）

- [ ] **Step 3: APIを実装する**

`app.py` の `api_get_results` の後に追加する。

```python
PREVIOUS_LOOKBACK_MONTHS = 3


@app.route("/api/results/previous")
def api_get_previous_values():
    """指定日より前の、直近の点検結果を返す（数値項目の前回値表示に使う）"""
    inspection_type = request.args.get("type", "使用前")
    category_minor = request.args.get("category_minor", "")
    before_str = request.args.get("before", "")
    if not _DATE_RE.match(before_str):
        return jsonify({"error": "before の日付形式が不正です"}), 400
    try:
        before = datetime.strptime(before_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "before が無効な日付です"}), 400

    records = []
    year, month = before.year, before.month
    for _ in range(PREVIOUS_LOOKBACK_MONTHS + 1):
        records.extend(_read_json_safe(
            get_result_file_path(inspection_type, year, month)))
        month -= 1
        if month == 0:
            month, year = 12, year - 1

    candidates = [r for r in records
                  if r.get("category_minor") == category_minor
                  and r.get("inspection_date", "") < before_str]
    if not candidates:
        return jsonify({})
    latest = max(candidates, key=lambda r: (r.get("inspection_date", ""),
                                            r.get("submitted_at", "")))
    values = {
        f"{r.get('equipment_name', '')}|{r.get('inspection_item', '')}":
            r.get("result", "")
        for r in latest.get("results", [])
    }
    return jsonify(values)
```

- [ ] **Step 4: 画面に出す**

`static/app.js` の `state` に追加する。

```js
    previousValues: {}, // 数値項目の前回値（"機器名|点検項目" → 値）
```

数値項目のセルに前回値を出す。Task 9 の数値セルのテンプレートを次に差し替える。

```js
            ? `
        <div class="result-number">
          <input type="text" class="num-input" inputmode="decimal"
                 data-key="${key}" value="${escapeHtml(saved.result || "")}"
                 ${disabledAttr} />
          <span class="num-unit">${escapeHtml(itemUnit(row))}</span>
        </div>
        <div class="num-prev">${previousLabel(row)}</div>`
```

`previousLabel` を追加する。

```js
/** 「前回 0.52 MPa」の表示を作る。前回値が無ければ空文字。 */
function previousLabel(row) {
    const key = `${state.currentMinor}|${row.inspection_item}`;
    const value = state.previousValues[key];
    if (!value) return "";
    const unit = itemUnit(row);
    return escapeHtml(`前回 ${value}${unit ? " " + unit : ""}`);
}
```

前回値の取得を追加する。

```js
/** 選択中の機器の前回値を読み込む */
async function loadPreviousValues(dateStr) {
    if (!state.currentMinor) { state.previousValues = {}; return; }
    const params = new URLSearchParams({
        type: state.currentMode,
        category_minor: state.currentMinor,
        before: dateStr,
    });
    try {
        state.previousValues = await fetchJson(`/api/results/previous?${params}`);
    } catch (e) {
        state.previousValues = {};   // 前回値は補助情報なので、取れなくても止めない
    }
}
```

`previousValues` のキーは API が返す `"機器名|点検項目"` の形。`previousLabel` の `state.currentMinor` は `category_minor` にあたるが、結果の `equipment_name` は行の `category_major` が入っている場合がある。**キーの作り方は `saveInspection()` で結果を組み立てているコード（`static/app.js:784` 付近）と必ず揃えること。**

機器を切り替えたときに読み込む。`renderMinorTabs()` で小分類を選んだ後の処理と、`loadInspectionResultsForDate()` の中に次を足す。

```js
    await loadPreviousValues(state.selectedDate);
```

- [ ] **Step 5: スタイルを足す**

`static/style.css` に追加する。

```css
.num-prev {
    font-size: 11px;
    color: #96a5b2;
    text-align: center;
    margin-top: 2px;
}
```

- [ ] **Step 6: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: すべて passed

- [ ] **Step 7: ブラウザで確認**

数値項目に値を入れて保存し、翌日の日付に切り替えると入力欄の下に「前回 0.52 MPa」が薄く出ることを確認する。

- [ ] **Step 8: コミット**

```bash
git add app.py static/app.js static/style.css tests/test_app.py
git commit -m "feat: show previous numeric value under the input field"
```

---

## Task 12: 画面上のテンキー

**Files:**
- Modify: `static/app.js`, `static/style.css`

- [ ] **Step 1: テンキーを作る**

`static/app.js` に追加する。

```js
/** 数値入力欄の下に出すテンキー。同時に1つだけ表示する。 */
let activeKeypad = null;

function closeKeypad() {
    if (activeKeypad) { activeKeypad.remove(); activeKeypad = null; }
}

function openKeypad(input) {
    closeKeypad();
    const pad = document.createElement("div");
    pad.className = "keypad";
    const keys = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0", ".", "-"];
    pad.innerHTML =
        keys.map(k => `<button type="button" data-k="${k}">${k}</button>`).join("")
        + '<button type="button" data-k="BS" class="wide">←</button>'
        + '<button type="button" data-k="OK" class="wide ok">確定</button>';
    input.parentElement.appendChild(pad);
    activeKeypad = pad;

    pad.addEventListener("mousedown", e => e.preventDefault()); // 入力欄のフォーカスを保つ
    pad.addEventListener("click", e => {
        const k = e.target.dataset.k;
        if (!k) return;
        if (k === "OK") { input.blur(); closeKeypad(); return; }
        if (k === "BS") input.value = input.value.slice(0, -1);
        else input.value += k;
        input.dispatchEvent(new Event("input", { bubbles: true }));
    });
}
```

- [ ] **Step 2: 入力欄に配線する**

Task 9 の `.num-input` のイベント登録に追加する。

```js
        input.addEventListener("focus", () => openKeypad(input));
```

`blur` のハンドラの末尾に追加する。

```js
            // 別の場所をクリックしたときにテンキーを閉じる
            setTimeout(() => {
                if (document.activeElement !== input) closeKeypad();
            }, 150);
```

物理キーボードからの入力は `<input type="text">` のまま受け付けられるため、追加の配線は不要。

- [ ] **Step 3: スタイルを足す**

`static/style.css` に追加する。

```css
/* ===== 画面上のテンキー ===== */
.result-number { position: relative; }

.keypad {
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    z-index: 50;
    display: grid;
    grid-template-columns: repeat(3, 56px);
    gap: 4px;
    padding: 8px;
    margin-top: 4px;
    background: #fff;
    border: 1px solid #b7c3cd;
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.keypad button {
    height: 46px;
    font-size: 20px;
    border: 1px solid #d5dbe0;
    border-radius: 5px;
    background: #f7f9fb;
    cursor: pointer;
}

.keypad button:active { background: #d5e8f7; }
.keypad button.wide { grid-column: span 3; height: 40px; font-size: 15px; }
.keypad button.ok { background: #0096d6; color: #fff; border-color: #0096d6; }
```

- [ ] **Step 4: ブラウザで確認**

数値欄をクリックするとテンキーが出て、数字・小数点・←・確定が動くことを確認する。物理キーボードからも入力できること、別の欄をクリックするとテンキーが閉じることも確認する。

タッチ端末があれば、指での操作も確認する。無ければブラウザの開発者ツールでモバイル表示に切り替えて確認する。

- [ ] **Step 5: コミット**

```bash
git add static/app.js static/style.css
git commit -m "feat: add on-screen keypad for numeric inspection input"
```

---

## Task 13: 設定画面の様式フォルダと割り当て一覧

**Files:**
- Modify: `static/inspection.html`, `static/app.js`

- [ ] **Step 1: 設定モーダルに入力欄を足す**

`static/inspection.html` の「ファイルサーバ保存先パス」の `form-row` の直後に追加する。

```html
                <div class="form-row">
                    <label>様式フォルダパス（空白=アプリ内 forms）</label>
                    <input type="text" id="cfg-forms-dir" placeholder="例: \\server\share\forms" />
                </div>
                <div class="form-row">
                    <label>点検サイクルの締め日</label>
                    <input type="number" id="cfg-cycle-start-day" min="1" max="31" style="width:80px;" />
                </div>
                <div class="form-row">
                    <label>様式の割り当て</label>
                    <div id="cfg-form-assignments" style="font-size:12px; line-height:1.7;"></div>
                </div>
```

`app.js` の読み込みクエリ（`?v=`）を1つ進める。

- [ ] **Step 2: 設定の読み書きに繋ぐ**

`static/app.js` の設定モーダルを開く処理（`openSettings` 相当。`static/app.js:947` 付近）に追加する。

```js
    document.getElementById("cfg-forms-dir").value =
        state.config.forms_directory || "";
    document.getElementById("cfg-cycle-start-day").value =
        state.config.cycle_start_day || 24;
    renderFormAssignments();
```

保存時のペイロード（`handleSettingsSave` 内）に追加する。

```js
        forms_directory: document.getElementById("cfg-forms-dir").value,
        cycle_start_day: Number(document.getElementById("cfg-cycle-start-day").value) || 24,
```

- [ ] **Step 3: 割り当て一覧を描く**

```js
/** どの機器が様式PDF出力で、どれが表出力かを一覧表示する */
async function renderFormAssignments() {
    const el = document.getElementById("cfg-form-assignments");
    if (!el) return;
    el.textContent = "読み込み中...";
    let assignments = {};
    try {
        assignments = await fetchJson("/api/forms/assignments");
    } catch (e) {
        el.textContent = "様式の情報を取得できませんでした";
        return;
    }
    const minors = [...new Set(state.equipmentData.map(r => r.category_minor))];
    const withForm = minors.filter(m => assignments[m]);
    const withoutForm = minors.filter(m => !assignments[m]);
    // 同じ機器が複数の様式に載っていると同じ結果が2枚に印字される。気づけるよう目立たせる。
    const duplicated = withForm.filter(m => assignments[m].length > 1);
    el.innerHTML =
        `<div><strong>様式PDFに出力（${withForm.length}件）</strong><br>` +
        (withForm.map(m => {
            const forms = escapeHtml(assignments[m].join(", "));
            const warn = assignments[m].length > 1
                ? ' <span style="color:#c62828;">⚠ 複数の様式に載っています</span>' : "";
            return `${escapeHtml(m)} → ${forms}${warn}`;
        }).join("<br>") || "（なし）") +
        `</div><div style="margin-top:6px;"><strong>表で出力（${withoutForm.length}件）</strong><br>` +
        (withoutForm.map(escapeHtml).join(" / ") || "（なし）") + "</div>" +
        (duplicated.length
            ? `<div style="margin-top:6px; color:#c62828;">${duplicated.length}件の機器が複数の様式に紐づいています。同じ結果が複数の様式に印字されます。</div>`
            : "");
}
```

- [ ] **Step 4: レイアウト画面への入口を足す**

`static/inspection.html` のヘッダーのボタン群（`btn-settings` の隣）に追加する。

```html
                <a href="/layout" class="btn btn-secondary" id="btn-to-layout">🗂 様式レイアウト</a>
```

- [ ] **Step 5: ブラウザで確認**

設定画面を開き、様式フォルダのパスと締め日が表示されること、割り当て一覧に「様式PDFに出力」と「表で出力」が分かれて出ることを確認する。締め日を20に変えて保存し、カレンダーの範囲が変わることも確認する。確認後は24に戻す。

- [ ] **Step 6: コミット**

```bash
git add static/inspection.html static/app.js
git commit -m "feat: add forms directory, cycle day and assignment list to settings"
```

---

## Task 14: 通し確認

- [ ] **Step 1: 全テストを走らせる**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: すべて passed

- [ ] **Step 2: 様式を1つ、画面だけで作りきる**

アプリを起動し、次を画面操作だけで行う。

1. `/layout` を開き「新しい様式を追加」から様式PDFを登録する
2. 「日にち（土日祝は丸）」を1番目の欄に配置する
3. 「1つ目の欄を指定」「2つ目の欄を指定」で軸を設定し、欄の数を31にする
4. 点検項目をいくつか配置する
5. 1つの機器に配置し終えたら「機器ごと複製...」で別の機器へ複製する
6. 「試し刷り」で 2026-03 を指定し、位置がずれていないか確認する
7. ずれていれば矢印キーで微調整し、再度試し刷りする
8. 「保存」を押す

- [ ] **Step 3: 点検して出力する**

点検画面で数値項目を含む点検を入力・保存し、「PDF出力」で様式と表が1つのPDFになって出ることを確認する。

- [ ] **Step 4: 目視で確認する**

1. 日にちが 24…31, 1…23 の順に並んでいる
2. 土曜が青丸、日曜・祝日・会社の休業日が赤丸
3. 28日の月で29〜31番目に「ー」が入り、日にちと丸が無い
4. タイトルの月にその月の数字が入っている
5. 様式を紐づけていない機器が表のページに出ている
6. 数値項目の値が様式に印字されている

- [ ] **Step 5: 未確認の点を報告する**

タッチ端末が無い場合など、実機で確認できなかった項目は「未検証」と明記してユーザーに報告する。

---

## この計画の完了条件

- `pytest tests/test_app.py` が全件パスする
- 様式の作成から配置、試し刷り、保存までを画面操作だけで完結できる
- 点検入力画面で数値項目が入力でき、全角で打っても半角で保存される
- 前回値とテンキーが表示される
- 設定画面から様式フォルダ・締め日・割り当て一覧を確認できる
