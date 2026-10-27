# 様式レイアウト画面 UI改善 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 様式レイアウト画面を、配布先の現場担当者がサポート無しで最後まで設定できる画面にする。

**Architecture:** サーバー側は一切変更しない。`static/layout.js`（現在705行）を3つのESモジュールに分け、`prompt()` による入力をすべて画面内UIに置き換え、PDF上に「実際に印字される文字」を重ねて表示する。印字プレビューを作ると、軸の繰り返し表示（ゴースト）が同じ仕組みで手に入る。

**Tech Stack:** 素のJavaScript（ESモジュール、フレームワークなし）／PDF.js（`/pdfjs/pdf.mjs`）／Flask（変更なし）／pytest（既存276件の回帰確認のみ）

**設計書:** `docs/superpowers/specs/2026-08-30-layout-ui-redesign-design.md`（承認済み）

---

## このプロジェクトのテスト事情（先に読むこと）

**このプロジェクトにJavaScriptのテスト実行環境はありません。** テストは `pytest` で Flask API を叩くものだけです。今回の変更はサーバーに触らないため、次の2本立てで検証します。

1. **回帰確認** — `pytest` 276件が全部通ること。サーバーを変えていない証明になります。
2. **ブラウザでの実機確認** — 各タスクに「何をして、何が表示されれば合格か」を具体的に書いてあります。**必ず実際に操作して確かめてください。**

`CLAUDE.md` にあるとおり「画面を変えたらブラウザで開いて確認する。テストだけでは足りない」がこのプロジェクトの決まりです。過去に、テンキーが枠からはみ出す不具合をテストで見逃した実績があります。

### 検証用サーバーの起動

```cmd
.venv\Scripts\python.exe app.py
```

ブラウザで `http://localhost:5000/layout` を開きます。**ポート5000は固定です。変更しないでください。**

静的ファイル（html/css/js）はリクエストのたびにディスクから読まれるので、**サーバーの再起動は不要**です。ブラウザの再読み込み（Ctrl+F5）だけで反映されます。

---

## ファイル構成

| ファイル | 状態 | 責任 |
|---|---|---|
| `static/layout.js` | 変更 | 画面の組み立て、状態、様式の選択、保存、項目の配置 |
| `static/layout-wizard.js` | **新規** | 様式追加ウィザード（4手順） |
| `static/layout-preview.js` | **新規** | 印字プレビューとゴースト表示 |
| `static/layout.html` | 変更 | 表示月セレクタ、通知欄、ウィザードの器を追加 |
| `static/layout.css` | 変更 | ウィザード用・プレビュー用のクラスを追加 |

`layout-preview.js` は `layout.js` の状態を参照しません。必要な材料はすべて引数で受け取ります。

---

## 用語の対応表（実装中に迷ったら見る）

| コード上の名前 | 画面に出す言葉 |
|---|---|
| axis | 並び方 |
| step_x / step_y | （画面には出さない。ゴースト表示で代替する） |
| 1つ目の欄 | 1日目のマス（`year` 型では「1月目のマス」） |
| period=month | 1枚に1か月分 |
| period=year | 1枚に1年分 |
| period=single | 1回の点検で1枚 |
| on_axis | 欄の数だけ繰り返す |

---

## Task 1: 壊れた様式で画面が真っ白にならないようにする

**Files:**
- Modify: `static/layout.html`（`#pdf-panel` に通知欄を追加）
- Modify: `static/layout.css`（通知欄のスタイル）
- Modify: `static/layout.js`（`loadForms` / `selectForm`）

いまは一覧の先頭が壊れていると自動で選ばれ、エラーで止まって何も表示されません。2026-08-30に実際に発生しました。

- [ ] **Step 1: 通知欄を HTML に足す**

`static/layout.html` の `#canvas-wrap` の直前に入れます。

```html
            <div id="pdf-notice" hidden></div>
            <div id="canvas-wrap">
```

- [ ] **Step 2: 通知欄のスタイルを足す**

`static/layout.css` の `#layout-main` の定義の直前に追記します。

```css
/* 様式を開けないときに、中央へ理由と直し方を出す */
#pdf-notice {
    margin: 24px;
    padding: 18px 20px;
    border: 1px solid #e0a9a2;
    border-left: 4px solid #c0392b;
    border-radius: 4px;
    background: #fdf3f2;
    color: #5a2a25;
    font-size: 13px;
    line-height: 1.9;
    white-space: pre-wrap;
}

#pdf-notice[hidden] { display: none; }
#pdf-notice b { color: #c0392b; }
```

- [ ] **Step 3: 判定用の関数を足す**

`static/layout.js` の `loadForms` の直前に追加します。

```js
/** その様式をレイアウト画面で開けるか */
function isOpenable(entry) {
    return !entry.error && entry.editable !== false && entry.has_pdf !== false;
}

/** 開けない理由を返す。開ける様式なら空文字。 */
function openBlockReason(entry) {
    if (entry.editable === false) {
        return entry.warning || "フォルダ名が様式IDの規則から外れています。";
    }
    if (entry.error) {
        return `設定ファイル（layout.json）を読めません：${entry.error}`;
    }
    if (entry.has_pdf === false) {
        return "様式PDFがありません。このフォルダに form.pdf という名前でPDFを置いてください。";
    }
    return "";
}

/** 通知欄に理由を出す（空文字なら隠す） */
function showNotice(html) {
    const el = $("pdf-notice");
    if (!el) return;
    if (!html) { el.hidden = true; el.innerHTML = ""; return; }
    el.innerHTML = html;
    el.hidden = false;
}
```

- [ ] **Step 4: `loadForms` を差し替える**

`static/layout.js` の `loadForms` を丸ごと次に置き換えます。

```js
/** 様式一覧を読み、プルダウンを作る */
async function loadForms() {
    state.forms = await fetchJson("/api/forms");
    const sel = $("form-select");
    if (!state.forms.length) {
        sel.innerHTML = '<option value="">（様式がありません）</option>';
        showNotice("<b>様式がまだ1つもありません。</b><br>"
            + "上の「新しい様式を追加」から、紙の様式のPDFを取り込んでください。");
        return;
    }
    sel.innerHTML = state.forms
        .map(f => `<option value="${escapeHtml(f.id)}">`
            + `${isOpenable(f) ? "" : "⚠ "}${escapeHtml(f.form_name)}</option>`)
        .join("");

    // 壊れている様式を自動で開くと画面が真っ白になるので、開けるものを選ぶ
    const first = state.forms.find(isOpenable);
    if (!first) {
        const lines = state.forms
            .map(f => `・${escapeHtml(f.form_name)}：${escapeHtml(openBlockReason(f))}`)
            .join("<br>");
        showNotice(`<b>開ける様式がありません。</b><br>次を直してください。<br><br>${lines}`);
        return;
    }
    sel.value = first.id;
    await selectForm(first.id);
}
```

- [ ] **Step 5: `selectForm` の先頭を差し替える**

`static/layout.js` の `selectForm` の中で、`editable === false` を見ている部分を次に置き換えます。

```js
    // 開けない様式は、404の代わりに理由を出して止める
    const entry = state.forms.find(f => f.id === formId);
    if (entry && !isOpenable(entry)) {
        showNotice(`<b>この様式は開けません。</b><br>${escapeHtml(openBlockReason(entry))}`);
        showStatus(openBlockReason(entry), true);
        return;
    }
    showNotice("");
```

- [ ] **Step 6: ブラウザで確認する**

わざと壊した様式を3つ作ります。

```cmd
mkdir forms\_t_nopdf
echo {"form_name":"PDFなし","period":"single","inspection_type":"使用前","targets":[],"fields":[]} > forms\_t_nopdf\layout.json
mkdir forms\_t_broken
echo { > forms\_t_broken\layout.json
```

`http://localhost:5000/layout` を開いて次を確かめます。

1. プルダウンに `⚠ PDFなし` `⚠ _t_broken` `確認用 日常点検表` が並ぶ
2. **画面が真っ白にならず、`確認用 日常点検表` が自動で開く**
3. `⚠ PDFなし` を選ぶと「様式PDFがありません。…form.pdf という名前で…」と中央に出る
4. `⚠ _t_broken` を選ぶと「設定ファイル（layout.json）を読めません」と出る

確認できたら、作った `forms\_t_nopdf` と `forms\_t_broken` を消してよいかユーザーに確認してから消します。

- [ ] **Step 7: 回帰確認**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `276 passed`

- [ ] **Step 8: コミット**

```bash
git add static/layout.html static/layout.css static/layout.js
git commit -m "fix: never auto-open a broken form on the layout screen"
```

---

## Task 2: 機器名がマスタに無いことを知らせる

**Files:**
- Modify: `static/layout.js`

`targets` の機器名が点検項目マスタの `category_minor` と1文字でも違うと、**印字が1つも出ないのにエラーも出ません。** これは `CLAUDE.md` にも「気づきにくい」と書かれている罠です。

- [ ] **Step 1: 突き合わせ関数を足す**

`static/layout.js` の `openBlockReason` の直後に追加します。

```js
/** layout の targets のうち、点検項目マスタに無い機器名を返す */
function unknownTargets(layout, equipment) {
    const known = new Set((equipment || []).map(r => r.category_minor));
    return ((layout && layout.targets) || []).filter(t => !known.has(t));
}
```

- [ ] **Step 2: `selectForm` の最後で警告を出す**

`selectForm` の中の `renderProps();` の直後に追加します。

```js
    const missing = unknownTargets(state.layout, state.equipment);
    if (missing.length) {
        showNotice(`<b>点検項目マスタに無い機器名があります。</b><br>`
            + missing.map(escapeHtml).map(n => `・${n}`).join("<br>")
            + "<br><br>このままでは、その機器の点検結果は様式に印字されません。"
            + "<br>点検項目マスタ（data/equipment_master.csv）の「小分類」と、"
            + "文字が完全に一致している必要があります。");
    }
```

- [ ] **Step 3: ブラウザで確認する**

`forms/sample_daily/layout.json` の `targets` を一時的に `["存在しない機器"]` に書き換えて保存し、レイアウト画面を再読み込みします。

期待：「点検項目マスタに無い機器名があります ・存在しない機器」と中央に出る。PDFは表示されたままで、操作は止まらない。

確認できたら `targets` を元の `["床上操作式クレーン"]` に戻します。

- [ ] **Step 4: コミット**

```bash
git add static/layout.js
git commit -m "feat: warn when a form targets an equipment name missing from the master"
```

---

## Task 3: 表示月を画面で選べるようにし、試し刷りの入力窓をやめる

**Files:**
- Modify: `static/layout.html`
- Modify: `static/layout.css`
- Modify: `static/layout.js`

試し刷りのたびに `YYYY-MM` を手打ちさせるのをやめます。この月はあとでプレビューの日付計算にも使います。

- [ ] **Step 1: ヘッダーに月の入力欄を足す**

`static/layout.html` の `<button id="btn-preview" ...>` の直前に入れます。

```html
        <label for="display-month">月</label>
        <input type="month" id="display-month" />
```

- [ ] **Step 2: スタイルを足す**

`static/layout.css` の `#layout-header select,` の行を次に置き換えます。

```css
#layout-header select,
#layout-header input[type="month"],
#layout-header input { font-size: 14px; padding: 4px 6px; }
```

- [ ] **Step 3: 既定値を今月にする関数を足す**

`static/layout.js` の `updateAxisLabel` の直前に追加します。

```js
/** 表示月の入力欄を今月で初期化する */
function initDisplayMonth() {
    const el = $("display-month");
    if (!el || el.value) return;
    const now = new Date();
    el.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** 表示月の入力欄から [年, 月] を返す。空なら今月。 */
function displayYearMonth() {
    const el = $("display-month");
    const m = /^(\d{4})-(\d{2})$/.exec((el && el.value) || "");
    if (!m) {
        const now = new Date();
        return [now.getFullYear(), now.getMonth() + 1];
    }
    return [Number(m[1]), Number(m[2])];
}
```

- [ ] **Step 4: 試し刷りのハンドラを差し替える**

`static/layout.js` の `$("btn-preview").addEventListener(...)` を丸ごと次に置き換えます。

```js
    $("btn-preview").addEventListener("click", async () => {
        if (!state.formId) { showStatus("様式が選ばれていません", true); return; }
        // 保存していない配置も試したいので、先に保存する
        const saved = await saveLayout();
        if (!saved) return;
        const [y, mo] = displayYearMonth();
        showStatus("試し刷りを別のタブで開きました。紙に印刷して、元の様式と重ねて確認してください。");
        window.open(
            `/api/forms/${encodeURIComponent(state.formId)}/preview`
            + `?display_year=${y}&display_month=${mo}`, "_blank");
    });
```

- [ ] **Step 5: 初期化で呼ぶ**

`static/layout.js` の `init()` の中、`showFormsDir();` の直後に追加します。

```js
    initDisplayMonth();
```

- [ ] **Step 6: ブラウザで確認する**

1. ヘッダーに「月 [2026-08]」が出て、今月が入っている
2. 「試し刷り」を押すと**入力窓が出ずに**別タブでPDFが開く
3. 月を `2026-03` に変えて試し刷りすると、28日サイクルのPDF（余りマスに「ー」）が出る

- [ ] **Step 7: コミット**

```bash
git add static/layout.html static/layout.css static/layout.js
git commit -m "feat: pick the preview month from the header instead of a prompt"
```

---

## Task 4: 様式IDの自動採番

**Files:**
- Modify: `static/layout.js`

利用者に様式ID（フォルダ名）を入力させないための土台です。

- [ ] **Step 1: 採番関数を足す**

`static/layout.js` の `isOpenable` の直前に追加します。

```js
/** 未使用のいちばん小さい様式IDを返す（form_01, form_02, …）
 *
 *  様式IDはフォルダ名になる。利用者に入力させると日本語・ハイフン・パスなどで
 *  失敗するため、アプリが決める。is_valid_form_id() の規則
 *  （半角英数字とアンダースコアのみ・64文字以内）を必ず満たす形にする。
 */
function nextFormId(existingIds) {
    const used = new Set(existingIds || []);
    for (let n = 1; n <= 9999; n++) {
        const id = n < 100 ? `form_${String(n).padStart(2, "0")}` : `form_${n}`;
        if (!used.has(id)) return id;
    }
    throw new Error("様式IDの空きがありません");
}
```

- [ ] **Step 2: export に足す**

`static/layout.js` の末尾の `export { ... }` に `nextFormId` を加えます。

```js
export { state, renderPage, selectForm, escapeHtml, fetchJson, showStatus, showFormsDir,
         renderItemList, renderMarkers, renderProps, toPdfPoint, toViewportPoint,
         collectItems, placeSelectedItem, startDrag, handleAxisPick,
         countUnplaced, saveLayout, copyFields, openCopyDialog, createForm,
         nextFormId, isOpenable, openBlockReason, unknownTargets, displayYearMonth };
```

- [ ] **Step 3: ブラウザのコンソールで確認する**

`http://localhost:5000/layout` を開き、開発者ツールのコンソールで実行します。

```js
const m = await import('/layout.js?probe=' + Date.now());
[m.nextFormId([]), m.nextFormId(['form_01']), m.nextFormId(['form_01','form_02'])]
```

Expected: `["form_01", "form_02", "form_03"]`

さらに99件埋まった場合を確認します。

```js
const many = Array.from({length: 99}, (_, i) => i < 99 ? `form_${String(i+1).padStart(2,'0')}` : '');
m.nextFormId(many)
```

Expected: `"form_100"`

- [ ] **Step 4: コミット**

```bash
git add static/layout.js
git commit -m "feat: auto-number form ids so users never type a folder name"
```

---

## Task 5: 追加ウィザードの器と手順1（PDFを置く）

**Files:**
- Create: `static/layout-wizard.js`
- Modify: `static/layout.html`
- Modify: `static/layout.css`
- Modify: `static/layout.js`

`prompt()` 6連発を置き換えます。まず器と手順1を作り、手順2〜4は Task 6 で足します。

- [ ] **Step 1: ウィザードの器を HTML に足す**

`static/layout.html` の `</body>` の直前、`<script>` タグの直前に入れます。

```html
    <div id="wizard-overlay" hidden>
        <div id="wizard-modal">
            <div id="wizard-head">
                <span id="wizard-title">新しい様式を追加</span>
                <span id="wizard-step">手順 1 / 4</span>
            </div>
            <div id="wizard-bar"><div id="wizard-bar-fill"></div></div>
            <div id="wizard-body"></div>
            <div id="wizard-error" hidden></div>
            <div id="wizard-foot">
                <button id="wizard-cancel" type="button">やめる</button>
                <span class="wizard-spacer"></span>
                <button id="wizard-back" type="button">戻る</button>
                <button id="wizard-next" type="button">次へ</button>
            </div>
        </div>
    </div>
```

- [ ] **Step 2: ウィザードのスタイルを足す**

`static/layout.css` の末尾に追記します。

```css
/* ===== 様式追加ウィザード ===== */
#wizard-overlay {
    position: fixed;
    inset: 0;
    background: rgba(10, 20, 35, 0.55);
    z-index: 50;
    display: flex;
    align-items: center;
    justify-content: center;
}

#wizard-overlay[hidden] { display: none; }

#wizard-modal {
    background: #fff;
    border-radius: 8px;
    width: min(720px, 92vw);
    max-height: 88vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
}

#wizard-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 14px 20px;
    background: #1a3a5c;
    color: #fff;
    border-radius: 8px 8px 0 0;
    font-size: 15px;
    font-weight: 700;
}

#wizard-step { font-size: 12px; font-weight: 400; opacity: 0.85; }

#wizard-bar { height: 4px; background: #e2e8ee; }
#wizard-bar-fill { height: 4px; background: #0096d6; transition: width 0.2s; }

#wizard-body {
    padding: 20px;
    overflow-y: auto;
    font-size: 14px;
    line-height: 1.8;
}

#wizard-body h4 {
    margin: 0 0 12px;
    font-size: 15px;
    color: #1a3a5c;
}

#wizard-error {
    margin: 0 20px 12px;
    padding: 10px 14px;
    border-left: 4px solid #c0392b;
    background: #fdf3f2;
    color: #5a2a25;
    font-size: 13px;
    line-height: 1.8;
}

#wizard-error[hidden] { display: none; }

#wizard-foot {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 20px;
    border-top: 1px solid #d5dbe0;
}

.wizard-spacer { flex: 1; }

#wizard-foot button {
    padding: 8px 20px;
    border: none;
    border-radius: 4px;
    font-size: 14px;
    cursor: pointer;
}

#wizard-next { background: #0096d6; color: #fff; }
#wizard-next:disabled { background: #b9c6d0; cursor: not-allowed; }
#wizard-back, #wizard-cancel { background: #eef2f6; color: #3a4a5a; }

/* 手順1：PDFの置き場 */
#drop-zone {
    border: 2px dashed #9fb4c6;
    border-radius: 6px;
    padding: 36px 20px;
    text-align: center;
    color: #5a6a7a;
    background: #fafbfc;
    cursor: pointer;
}

#drop-zone.over { border-color: #0096d6; background: #eef7fc; }
#drop-zone strong { display: block; font-size: 15px; color: #1a3a5c; margin-bottom: 6px; }
#pdf-check { margin-top: 14px; display: flex; gap: 14px; align-items: flex-start; }
#pdf-check canvas { border: 1px solid #d5dbe0; max-width: 220px; height: auto; }
```

- [ ] **Step 3: `layout-wizard.js` を作る（器と手順1）**

`static/layout-wizard.js` を新規作成します。

```js
/** 様式追加ウィザード。
 *
 *  prompt() の連続だと、途中で戻れず、何を入力すればよいかも分からない。
 *  4手順の画面にして、進める条件を満たすまで「次へ」を押せなくする。
 */
import * as pdfjsLib from '/pdfjs/pdf.mjs';

const $ = id => document.getElementById(id);

const STEP_COUNT = 4;

/** ウィザードの入力内容。開くたびに作り直す。 */
function emptyDraft() {
    return {
        file: null,        // 手順1で選んだPDF
        pageCount: 0,
        period: "",        // 手順2
        targets: [],       // 手順3
        formName: "",      // 手順4
        inspectionType: "使用前",
    };
}

let draft = emptyDraft();
let step = 1;
let equipment = [];
let existingIds = [];
let resolveFn = null;

function showError(msg) {
    const el = $("wizard-error");
    if (!msg) { el.hidden = true; el.textContent = ""; return; }
    el.textContent = msg;
    el.hidden = false;
}

/** 「次へ」を押せる状態か */
function canGoNext() {
    if (step === 1) return !!draft.file && draft.pageCount > 0;
    if (step === 2) return !!draft.period;
    if (step === 3) return draft.targets.length > 0;
    if (step === 4) return draft.formName.trim().length > 0;
    return false;
}

function renderFoot() {
    $("wizard-step").textContent = `手順 ${step} / ${STEP_COUNT}`;
    $("wizard-bar-fill").style.width = `${(step / STEP_COUNT) * 100}%`;
    $("wizard-back").style.visibility = step === 1 ? "hidden" : "visible";
    $("wizard-next").textContent = step === STEP_COUNT ? "この内容で作成" : "次へ";
    $("wizard-next").disabled = !canGoNext();
}

/** 手順1：PDFを置く */
function renderStep1() {
    $("wizard-body").innerHTML = `
      <h4>紙の様式のPDFを用意してください</h4>
      <p>点検結果を印字したい、元の様式のPDFです。中身は書き換わりません。</p>
      <div id="drop-zone">
        <strong>ここにPDFをドラッグしてください</strong>
        クリックしてファイルを選ぶこともできます（PDFのみ・50MBまで）
      </div>
      <div id="pdf-check"></div>`;

    const zone = $("drop-zone");
    const picker = document.createElement("input");
    picker.type = "file";
    picker.accept = "application/pdf";
    picker.addEventListener("change", () => acceptFile(picker.files[0]));

    zone.addEventListener("click", () => picker.click());
    zone.addEventListener("dragover", e => {
        e.preventDefault();
        zone.classList.add("over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", e => {
        e.preventDefault();
        zone.classList.remove("over");
        acceptFile(e.dataTransfer.files[0]);
    });

    if (draft.file) showAcceptedFile();
}

const MAX_PDF_BYTES = 50 * 1024 * 1024;

/** 選ばれたファイルを検査して受け入れる */
async function acceptFile(file) {
    showError("");
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        showError("PDFファイルを選んでください。"); return;
    }
    if (file.size > MAX_PDF_BYTES) {
        showError("ファイルが大きすぎます（50MBまで）。"); return;
    }
    const head = new Uint8Array(await file.slice(0, 5).arrayBuffer());
    if (String.fromCharCode(...head) !== "%PDF-") {
        showError("PDFファイルではないようです。別のファイルを選んでください。"); return;
    }
    let doc;
    try {
        doc = await pdfjsLib.getDocument({
            data: new Uint8Array(await file.arrayBuffer()),
            cMapUrl: "/pdfjs/cmaps/",
            cMapPacked: true,
        }).promise;
    } catch (e) {
        showError("PDFを読み込めませんでした。別のファイルを選んでください。"); return;
    }
    if (doc.numPages < 1) {
        showError("このPDFにはページがありません。"); return;
    }
    draft.file = file;
    draft.pageCount = doc.numPages;
    await showAcceptedFile(doc);
    renderFoot();
}

/** 受け入れたPDFの1ページ目を小さく描いて確認させる */
async function showAcceptedFile(doc) {
    const box = $("pdf-check");
    if (!box) return;
    box.innerHTML = `<div><b>${draft.file.name}</b><br>${draft.pageCount} ページ</div>`;
    if (!doc) return;
    const page = await doc.getPage(1);
    const base = page.getViewport({ scale: 1.0 });
    const viewport = page.getViewport({ scale: Math.min(220 / base.width, 1) });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
    box.prepend(canvas);
}

function renderStep() {
    showError("");
    if (step === 1) renderStep1();
    renderFoot();
}

/** ウィザードを開く。作成できたら様式ID、やめたら null を返す。 */
export function openWizard(equipmentList, existingFormIds) {
    equipment = equipmentList || [];
    existingIds = existingFormIds || [];
    draft = emptyDraft();
    step = 1;
    $("wizard-overlay").hidden = false;
    renderStep();
    return new Promise(resolve => { resolveFn = resolve; });
}

function close(result) {
    $("wizard-overlay").hidden = true;
    $("wizard-body").innerHTML = "";
    showError("");
    if (resolveFn) { resolveFn(result); resolveFn = null; }
}

/** 一度だけボタンにイベントを付ける */
export function initWizard() {
    $("wizard-cancel").addEventListener("click", () => {
        if (step > 1 && !confirm("入力した内容は失われます。やめますか？")) return;
        close(null);
    });
    $("wizard-back").addEventListener("click", () => {
        if (step > 1) { step--; renderStep(); }
    });
    $("wizard-next").addEventListener("click", async () => {
        if (!canGoNext()) return;
        if (step < STEP_COUNT) { step++; renderStep(); return; }
        await submit();
    });
}

/** 手順4まで終わったら作成する（Task 6 で実装する） */
async function submit() {
    showError("作成処理は Task 6 で実装します。");
}
```

- [ ] **Step 4: `layout.js` からウィザードを呼ぶようにする**

`static/layout.js` の先頭の import の直後に追加します。

```js
import { openWizard, initWizard } from '/layout-wizard.js';
```

`init()` の中の `$("btn-new-form").addEventListener(...)` を次に置き換えます。

```js
    initWizard();
    $("btn-new-form").addEventListener("click", async () => {
        const newId = await openWizard(state.equipment, state.forms.map(f => f.id));
        if (!newId) return;
        await loadForms();
        const sel = $("form-select");
        if (sel) sel.value = newId;
        await selectForm(newId);
    });
```

- [ ] **Step 5: ブラウザで確認する**

1. 「新しい様式を追加」を押すと**入力窓ではなくモーダルが開く**
2. 「手順 1 / 4」と出て、進捗バーが1/4まで伸びている
3. 「次へ」が押せない（灰色）
4. `forms/sample_daily/form.pdf` をドラッグすると、**1ページ目の絵とファイル名・ページ数**が出て「次へ」が押せるようになる
5. 適当なテキストファイルをドラッグすると「PDFファイルを選んでください。」と赤で出る
6. 「やめる」で閉じる

- [ ] **Step 6: コミット**

```bash
git add static/layout-wizard.js static/layout.html static/layout.css static/layout.js
git commit -m "feat: add form wizard shell with a drag-and-drop PDF step"
```

---

## Task 6: ウィザードの手順2〜4と作成処理

**Files:**
- Modify: `static/layout-wizard.js`
- Modify: `static/layout.css`
- Modify: `static/layout.js`

- [ ] **Step 1: 手順2〜4のスタイルを足す**

`static/layout.css` の末尾に追記します。

```css
/* 手順2：様式の形を選ぶカード */
.shape-cards { display: flex; gap: 12px; flex-wrap: wrap; }

.shape-card {
    flex: 1 1 190px;
    border: 2px solid #d5dbe0;
    border-radius: 6px;
    padding: 14px;
    cursor: pointer;
    background: #fff;
    text-align: left;
}

.shape-card.selected { border-color: #0096d6; background: #eef7fc; }
.shape-card b { display: block; color: #1a3a5c; margin: 10px 0 4px; }
.shape-card span { font-size: 12px; color: #5a6a7a; line-height: 1.7; }
.shape-card svg { display: block; width: 100%; height: 52px; }

/* 手順3：機器を選ぶ */
#target-filter { width: 100%; padding: 6px 8px; margin-bottom: 10px; font-size: 14px; }

#target-list {
    max-height: 260px;
    overflow-y: auto;
    border: 1px solid #d5dbe0;
    border-radius: 4px;
    padding: 6px;
}

#target-list label {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 5px 6px;
    border-radius: 3px;
    cursor: pointer;
}

#target-list label:hover { background: #eef3f8; }
#target-count { font-size: 12px; color: #5a6a7a; margin-top: 8px; }

/* 手順4 */
.wizard-field { margin-bottom: 14px; }
.wizard-field label { display: block; font-weight: 700; color: #1a3a5c; margin-bottom: 4px; }
.wizard-field input[type="text"] { width: 100%; padding: 7px 9px; font-size: 14px; }
.wizard-radio { display: flex; gap: 18px; }
.wizard-radio label { display: flex; gap: 6px; align-items: center; font-weight: 400; }
.wizard-summary {
    background: #f4f6f8;
    border: 1px solid #d5dbe0;
    border-radius: 4px;
    padding: 12px 14px;
    font-size: 13px;
    line-height: 1.9;
}
```

- [ ] **Step 2: 手順2（形を選ぶ）を実装する**

`static/layout-wizard.js` の `renderStep1` の直後に追加します。

```js
/** 様式の形。図と説明は紙の見た目に合わせる。 */
const SHAPES = [
    {
        period: "month",
        title: "1枚に1か月分",
        desc: "日付が横に並ぶ日常点検表。1日〜31日のマスがある様式です。",
        svg: `<svg viewBox="0 0 200 52"><g fill="none" stroke="#7a8896">
              <rect x="4" y="10" width="192" height="14"/><rect x="4" y="24" width="192" height="14"/>
              <path d="M28 10v28M52 10v28M76 10v28M100 10v28M124 10v28M148 10v28M172 10v28"/>
              </g></svg>`,
    },
    {
        period: "year",
        title: "1枚に1年分",
        desc: "1月〜12月が並ぶ月例点検表。1枚で1年分を記録する様式です。",
        svg: `<svg viewBox="0 0 200 52"><g fill="none" stroke="#7a8896">
              <rect x="60" y="4" width="80" height="44"/>
              <path d="M60 15h80M60 26h80M60 37h80M100 4v44"/>
              </g></svg>`,
    },
    {
        period: "single",
        title: "1回の点検で1枚",
        desc: "点検のたびに1枚起こす様式。日付ごとにマスが並んでいないものです。",
        svg: `<svg viewBox="0 0 200 52"><g fill="none" stroke="#7a8896">
              <rect x="70" y="4" width="60" height="44"/>
              </g></svg>`,
    },
];

/** 手順2：様式の形を選ぶ */
function renderStep2() {
    $("wizard-body").innerHTML = `
      <h4>この様式は、どの形に近いですか？</h4>
      <p>手元の紙の様式と見比べて選んでください。あとから画面では変更できません。</p>
      <div class="shape-cards">
        ${SHAPES.map(s => `
          <button type="button" class="shape-card${draft.period === s.period ? " selected" : ""}"
                  data-period="${s.period}">
            ${s.svg}<b>${s.title}</b><span>${s.desc}</span>
          </button>`).join("")}
      </div>`;

    $("wizard-body").querySelectorAll(".shape-card").forEach(card => {
        card.addEventListener("click", () => {
            draft.period = card.dataset.period;
            renderStep2();
            renderFoot();
        });
    });
}
```

- [ ] **Step 3: 手順3（機器を選ぶ）を実装する**

`renderStep2` の直後に追加します。

```js
/** 手順3：この様式に載る機器を選ぶ */
function renderStep3() {
    const minors = [...new Set(equipment.map(r => r.category_minor))].filter(Boolean);
    $("wizard-body").innerHTML = `
      <h4>この様式には、どの機器が載っていますか？</h4>
      <p>点検項目マスタに登録されている機器から選びます。1つ以上選んでください。</p>
      <input type="text" id="target-filter" placeholder="機器名で絞り込む" />
      <div id="target-list"></div>
      <div id="target-count"></div>`;

    const listEl = $("target-list");
    const countEl = $("target-count");

    const draw = (keyword) => {
        const shown = minors.filter(n => !keyword || n.includes(keyword));
        listEl.innerHTML = shown.length
            ? shown.map(n => `<label><input type="checkbox" value="${escapeAttr(n)}"
                ${draft.targets.includes(n) ? "checked" : ""} />${escapeText(n)}</label>`).join("")
            : `<div style="padding:8px;color:#7a8896">該当する機器がありません</div>`;
        listEl.querySelectorAll("input[type=checkbox]").forEach(box => {
            box.addEventListener("change", () => {
                const name = box.value;
                if (box.checked) {
                    if (!draft.targets.includes(name)) draft.targets.push(name);
                } else {
                    draft.targets = draft.targets.filter(t => t !== name);
                }
                countEl.textContent = `${draft.targets.length} 件選択中`;
                renderFoot();
            });
        });
        countEl.textContent = `${draft.targets.length} 件選択中`;
    };

    draw("");
    $("target-filter").addEventListener("input", e => draw(e.target.value.trim()));
}

function escapeText(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttr(s) {
    return escapeText(s).replace(/"/g, "&quot;");
}
```

- [ ] **Step 4: 手順4（名前と点検種別）を実装する**

`renderStep3` の直後に追加します。

```js
/** 手順4：名前と点検種別 */
function renderStep4() {
    const shape = SHAPES.find(s => s.period === draft.period);
    $("wizard-body").innerHTML = `
      <h4>この様式に名前をつけてください</h4>
      <div class="wizard-field">
        <label for="wz-name">様式の名前</label>
        <input type="text" id="wz-name" value="${escapeAttr(draft.formName)}"
               placeholder="例：クレーン日常点検表" />
      </div>
      <div class="wizard-field">
        <label>どちらの点検の結果を印字しますか</label>
        <div class="wizard-radio">
          <label><input type="radio" name="wz-type" value="使用前"
            ${draft.inspectionType === "使用前" ? "checked" : ""} />使用前点検（毎日）</label>
          <label><input type="radio" name="wz-type" value="月例"
            ${draft.inspectionType === "月例" ? "checked" : ""} />月例点検（月1回）</label>
        </div>
      </div>
      <div class="wizard-summary">
        <b>この内容で作成します</b><br>
        PDF：${escapeText(draft.file ? draft.file.name : "")}（${draft.pageCount} ページ）<br>
        形：${escapeText(shape ? shape.title : "")}<br>
        機器：${escapeText(draft.targets.join("、"))}<br>
        フォルダ名：${escapeText(nextIdPreview())}（アプリが自動でつけます）
      </div>`;

    $("wz-name").addEventListener("input", e => {
        draft.formName = e.target.value;
        renderFoot();
    });
    $("wizard-body").querySelectorAll("input[name=wz-type]").forEach(r => {
        r.addEventListener("change", () => { draft.inspectionType = r.value; });
    });
}

/** 手順4の確認欄に出すフォルダ名 */
function nextIdPreview() {
    const used = new Set(existingIds);
    for (let n = 1; n <= 9999; n++) {
        const id = n < 100 ? `form_${String(n).padStart(2, "0")}` : `form_${n}`;
        if (!used.has(id)) return id;
    }
    return "form_9999";
}
```

- [ ] **Step 5: `renderStep` を差し替える**

`static/layout-wizard.js` の `renderStep` を次に置き換えます。

```js
function renderStep() {
    showError("");
    if (step === 1) renderStep1();
    else if (step === 2) renderStep2();
    else if (step === 3) renderStep3();
    else if (step === 4) renderStep4();
    renderFoot();
}
```

- [ ] **Step 6: 作成処理を実装する**

`static/layout-wizard.js` の `submit` を次に置き換えます。

```js
/** 手順4まで終わったら、様式を作る */
async function submit() {
    showError("");
    $("wizard-next").disabled = true;
    const formId = nextIdPreview();
    const fd = new FormData();
    fd.append("form_id", formId);
    fd.append("form_name", draft.formName.trim());
    fd.append("period", draft.period);
    fd.append("inspection_type", draft.inspectionType);
    fd.append("targets", JSON.stringify(draft.targets));
    fd.append("file", draft.file);

    let res;
    try {
        res = await fetch("/api/forms", { method: "POST", body: fd });
    } catch (e) {
        showError("アプリとの通信に失敗しました。");
        $("wizard-next").disabled = false;
        return;
    }
    if (res.status === 401) {
        showError("様式の作成には管理者権限が必要です。"
            + "アプリを動かしているPCで操作してください。");
        $("wizard-next").disabled = false;
        return;
    }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showError(err.error || `作成に失敗しました（${res.status}）`);
        $("wizard-next").disabled = false;
        return;
    }
    close(formId);
}
```

- [ ] **Step 7: 古い `createForm` を消す**

`static/layout.js` の `createForm` 関数（`/** 新しい様式を追加する */` から始まる関数）を丸ごと削除し、末尾の `export { ... }` から `createForm` を取り除きます。ウィザードに置き換わったため使われません。

- [ ] **Step 8: ブラウザで確認する**

「新しい様式を追加」から最後まで通します。

1. 手順1：`forms/sample_daily/form.pdf` をドラッグ →「次へ」
2. 手順2：「1枚に1か月分」を選ぶと枠が青くなる →「次へ」
3. 手順3：絞り込み欄に「クレーン」と打つと候補が絞られる。`床上操作式クレーン` にチェック →「1 件選択中」→「次へ」
4. 手順4：名前に「テスト様式」と入れる。確認欄に**PDF名・形・機器・フォルダ名 `form_01`** が出る
5. 「この内容で作成」→ モーダルが閉じ、**一覧に「テスト様式」が現れて選ばれている**
6. エクスプローラーで `forms\form_01\` に **`form.pdf` と `layout.json` が揃っている**ことを確認

確認できたら、`forms\form_01` を消してよいかユーザーに確認してから消します。

- [ ] **Step 9: 回帰確認**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `276 passed`

- [ ] **Step 10: コミット**

```bash
git add static/layout-wizard.js static/layout.css static/layout.js
git commit -m "feat: complete the form wizard and drop the prompt-based flow"
```

---

## Task 7: 印字プレビューの土台

**Files:**
- Create: `static/layout-preview.js`
- Modify: `static/layout.css`
- Modify: `static/layout.js`

置いた印を「点」から「実際に印字される文字」に変えます。ここが今回の中心です。

**座標の注意：** PDFのY座標は左下が原点で上が正。画面とは上下が逆です。`viewport.convertToViewportPoint(x, y)` が変換してくれます。文字はPDF上で「ベースライン」の位置に描かれるので、画面では文字サイズの約0.8倍だけ上にずらして配置します。

- [ ] **Step 1: プレビューのスタイルを足す**

`static/layout.css` の末尾に追記します。

```css
/* ===== 印字プレビュー ===== */
.pf {
    position: absolute;
    white-space: nowrap;
    line-height: 1;
    pointer-events: none;
    font-family: 'Meiryo', 'メイリオ', sans-serif;
}

/* 1つ目の欄。ここだけドラッグして動かせる */
.pf-anchor { pointer-events: auto; cursor: move; }

/* 2つ目以降の欄。並び方が正しいかを確かめるための表示 */
.pf-ghost { opacity: 0.45; }

.pf-selected {
    outline: 2px solid #0096d6;
    outline-offset: 2px;
    background: rgba(0, 150, 214, 0.08);
}

.pf-circle {
    position: absolute;
    border-radius: 50%;
    border: 1.5px solid currentColor;
    pointer-events: none;
}
```

- [ ] **Step 2: `layout-preview.js` を作る**

`static/layout-preview.js` を新規作成します。

```js
/** 印字プレビュー。
 *
 *  PDFの上に「実際に印字される文字」を重ねて表示する。
 *  on_axis の項目は欄の数だけ描かれるので、これがそのまま
 *  「並び方が正しいか」を確かめるゴースト表示になる。
 *
 *  この モジュールは layout.js の状態を見ない。必要な材料は ctx で受け取る。
 */

const SAMPLE = {
    inspector: "見本 太郎",
    department: "見本部",
    remark: "見本",
    number: "0.00",
    judgment: "✓",
};

const COLOR_SATURDAY = "#0000ff";
const COLOR_HOLIDAY = "#ff0000";
const CIRCLE_RATIO = 0.9;

/** 軸の n 番目（1始まり）の位置を返す。Python の axis_position と同じ式。 */
export function axisPosition(field, axis, n) {
    const x = Number(field.x) || 0;
    const y = Number(field.y) || 0;
    if (!field.on_axis) return [x, y];
    const sx = Number((axis || {}).step_x) || 0;
    const sy = Number((axis || {}).step_y) || 0;
    return [x + sx * (n - 1), y + sy * (n - 1)];
}

/** その様式の欄の数。single 型は1。 */
export function slotCount(layout) {
    if (!layout || layout.period === "single") return 1;
    const c = Number((layout.axis || {}).count);
    if (!Number.isFinite(c) || c < 1) return layout.period === "year" ? 12 : 31;
    return Math.min(Math.round(c), 400);
}

/** n 番目の欄に印字される見本の文字を返す。空文字なら描かない。 */
export function sampleValue(field, n, ctx) {
    const source = String(field.source || "");
    if (source === "meta.month") return String(ctx.month);
    if (source === "meta.year") return String(ctx.year);
    if (source === "meta.day") {
        const d = ctx.dates[n - 1];
        return d ? String(d.getDate()) : "";
    }
    if (source === "meta.unused") {
        return ctx.dates[n - 1] ? SAMPLE.judgment : "";
    }
    if (source === "meta.inspection_date") return `${ctx.year}-${pad(ctx.month)}-01`;
    if (source === "meta.inspector") return SAMPLE.inspector;
    if (source === "meta.department") return SAMPLE.department;
    if (source === "meta.building_name") return ctx.buildingName || "";
    if (source === "meta.general_remark") return SAMPLE.remark;
    if (source.startsWith("remark:")) return SAMPLE.remark;
    if (source.startsWith("item:")) {
        const body = source.slice(5);
        const sep = body.indexOf("|");
        if (sep < 0) return SAMPLE.judgment;
        const item = body.slice(sep + 1);
        return ctx.numberItems.has(item) ? SAMPLE.number : SAMPLE.judgment;
    }
    return "";
}

function pad(n) { return String(n).padStart(2, "0"); }

/** 日にちの色。平日は空文字（丸を描かない）。 */
export function dayColor(dateStr, holidays) {
    const h = (holidays || {})[dateStr];
    if (!h) return "";
    if (h.is_sunday || h.is_holiday || h.is_custom_holiday) return COLOR_HOLIDAY;
    if (h.is_saturday) return COLOR_SATURDAY;
    return "";
}

/** container の中身をプレビューで描き直す。
 *
 *  ctx = { layout, viewport, dates, holidays, year, month,
 *          buildingName, numberItems, selectedField, defaultFontSize }
 */
export function renderPreview(container, ctx) {
    container.innerHTML = "";
    const layout = ctx.layout;
    if (!layout || !ctx.viewport) return;
    const fields = layout.fields || [];
    const axis = layout.axis || {};
    const count = slotCount(layout);
    const scale = ctx.viewport.scale;
    const defaultSize = Number(layout.default_font_size) || ctx.defaultFontSize || 11;

    fields.forEach((field, index) => {
        if (field.page !== ctx.pageIndex) return;
        const size = (Number(field.font_size) || defaultSize) * scale;
        const repeat = field.on_axis ? count : 1;
        for (let n = 1; n <= repeat; n++) {
            const text = sampleValue(field, n, ctx);
            if (!text) continue;
            const [px, py] = axisPosition(field, axis, n);
            const [vx, vy] = ctx.viewport.convertToViewportPoint(px, py);
            const isDay = field.source === "meta.day";
            const el = document.createElement("div");
            el.className = "pf " + (n === 1 ? "pf-anchor" : "pf-ghost");
            if (n === 1) el.dataset.index = String(index);
            if (n === 1 && index === ctx.selectedField) el.classList.add("pf-selected");
            el.style.fontSize = `${size}px`;
            el.textContent = text;

            if (isDay) {
                // 日にちはクリック位置が「丸の中心」。文字も中央に置く。
                const color = dayColor(dateKey(ctx.dates[n - 1]), ctx.holidays);
                el.style.color = color || field.color || "#000000";
                el.style.left = `${vx}px`;
                el.style.top = `${vy}px`;
                el.style.transform = "translate(-50%, -50%)";
                container.appendChild(el);
                if (color) container.appendChild(dayCircle(vx, vy, field, size, color, scale));
            } else {
                el.style.color = field.color || "#000000";
                el.style.left = `${vx}px`;
                el.style.top = `${vy - size * 0.8}px`;
                container.appendChild(el);
            }
        }
    });
}

function dateKey(d) {
    if (!d) return "";
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 土日祝の丸 */
function dayCircle(vx, vy, field, size, color, scale) {
    const raw = Number(field.circle_radius);
    const r = (Number.isFinite(raw) ? raw * scale : size * CIRCLE_RATIO);
    const c = document.createElement("div");
    c.className = "pf-circle";
    c.style.left = `${vx - r}px`;
    c.style.top = `${vy - r}px`;
    c.style.width = `${r * 2}px`;
    c.style.height = `${r * 2}px`;
    c.style.color = color;
    return c;
}
```

- [ ] **Step 3: ブラウザのコンソールで純関数を確認する**

`http://localhost:5000/layout` を開き、コンソールで実行します。

```js
const p = await import('/layout-preview.js?probe=' + Date.now());
JSON.stringify([
  p.axisPosition({x: 100, y: 700, on_axis: true}, {step_x: 20, step_y: 0}, 1),
  p.axisPosition({x: 100, y: 700, on_axis: true}, {step_x: 20, step_y: 0}, 3),
  p.axisPosition({x: 100, y: 700, on_axis: false}, {step_x: 20, step_y: 0}, 5),
  p.slotCount({period: 'month', axis: {count: 31}}),
  p.slotCount({period: 'single'}),
  p.slotCount({period: 'year', axis: {}}),
])
```

Expected: `[[100,700],[140,700],[100,700],31,1,12]`

```js
const ctx = {year: 2026, month: 8, dates: [new Date(2026,7,24)],
             buildingName: 'ホンカン', numberItems: new Set(['油圧'])};
JSON.stringify([
  p.sampleValue({source: 'meta.month'}, 1, ctx),
  p.sampleValue({source: 'meta.day'}, 1, ctx),
  p.sampleValue({source: 'item:クレーン|傷はないか'}, 1, ctx),
  p.sampleValue({source: 'item:クレーン|油圧'}, 1, ctx),
  p.sampleValue({source: 'meta.building_name'}, 1, ctx),
])
```

Expected: `["8","24","✓","0.00","ホンカン"]`

- [ ] **Step 4: コミット**

```bash
git add static/layout-preview.js static/layout.css
git commit -m "feat: add a print-preview module for the layout screen"
```

---

## Task 8: プレビューを画面につなぐ

**Files:**
- Modify: `static/layout.js`

`renderMarkers`（点を描いていた関数）をプレビューに置き換えます。ドラッグと選択は1つ目の欄（`.pf-anchor`）で今までどおり効くようにします。

- [ ] **Step 1: import を足す**

`static/layout.js` の import 群の末尾に追加します。

```js
import { renderPreview } from '/layout-preview.js';
```

- [ ] **Step 2: 材料をそろえる関数を足す**

`static/layout.js` の `renderMarkers` の直前に追加します。

```js
/** サイクル内の日付を並べて返す（app.py の get_cycle_dates と同じ考え方） */
function cycleDates(year, month, startDay) {
    const clamp = (y, m, d) => new Date(y, m - 1, Math.min(d, new Date(y, m, 0).getDate()));
    const prevY = month > 1 ? year : year - 1;
    const prevM = month > 1 ? month - 1 : 12;
    const start = clamp(prevY, prevM, startDay);
    const end = clamp(year, month, startDay);
    const days = [];
    for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
        days.push(new Date(d));
    }
    return days;
}

/** プレビューに必要な材料を集める（祝日と締め日はサーバーから貰う） */
async function loadPreviewContext() {
    const [year, month] = displayYearMonth();
    let startDay = 24;
    let buildingName = "";
    try {
        const cfg = await fetchJson("/api/config");
        const d = Number(cfg.cycle_start_day);
        if (Number.isInteger(d) && d >= 1 && d <= 31) startDay = d;
        buildingName = (cfg.building_info || {}).building_name || "";
    } catch (e) { /* 既定値のまま進める */ }

    const dates = cycleDates(year, month, startDay);
    const holidays = {};
    if (dates.length) {
        const fmt = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
            + `-${String(d.getDate()).padStart(2, "0")}`;
        try {
            const list = await fetchJson(
                `/api/holidays?start=${fmt(dates[0])}&end=${fmt(dates[dates.length - 1])}`);
            list.forEach(h => { holidays[h.date] = h; });
        } catch (e) { /* 色を諦めて黒で描く */ }
    }

    const numberItems = new Set(
        (state.equipment || [])
            .filter(r => (r.input_type || "").trim() === "数値")
            .map(r => r.inspection_item));

    state.previewCtx = { year, month, dates, holidays, buildingName, numberItems };
}
```

- [ ] **Step 3: `state` に置き場を足す**

`static/layout.js` の `state` の定義に1行加えます。

```js
    axisFirst: null,    // 1つ目の欄のPDF座標
    previewCtx: null,   // プレビュー用の材料（日付・祝日・建物名など）
```

- [ ] **Step 4: `renderMarkers` を差し替える**

`static/layout.js` の `renderMarkers` を丸ごと次に置き換えます。

```js
/** 印字プレビューをPDFの上に重ねて表示する */
function renderMarkers() {
    const layer = $("marker-layer");
    const canvas = $("form-canvas");
    if (!state.viewport || !state.layout) { layer.innerHTML = ""; return; }
    layer.style.width = canvas.width + "px";
    layer.style.height = canvas.height + "px";
    layer.style.left = canvas.offsetLeft + "px";

    const ctx = state.previewCtx || {
        year: new Date().getFullYear(), month: new Date().getMonth() + 1,
        dates: [], holidays: {}, buildingName: "", numberItems: new Set(),
    };
    try {
        renderPreview(layer, {
            layout: state.layout,
            viewport: state.viewport,
            pageIndex: state.pageIndex,
            selectedField: state.selectedField,
            defaultFontSize: 11,
            ...ctx,
        });
    } catch (e) {
        // プレビューが描けなくても、配置と保存は続けられるようにする
        console.warn("プレビューの描画に失敗しました:", e);
    }

    layer.querySelectorAll(".pf-anchor").forEach(el => {
        el.addEventListener("mousedown", e => {
            e.stopPropagation();
            state.selectedField = Number(el.dataset.index);
            renderMarkers();
            renderProps();
            startDrag(e);
        });
    });
}
```

- [ ] **Step 5: 材料を読むタイミングをつなぐ**

`static/layout.js` の `selectForm` の中、`await renderPage();` の直前に追加します。

```js
    await loadPreviewContext();
```

`init()` の中、`$("display-month")` の変更でプレビューを描き直すようにします。`initDisplayMonth();` の直後に追加します。

```js
    $("display-month").addEventListener("change", async () => {
        await loadPreviewContext();
        renderMarkers();
    });
```

- [ ] **Step 6: ブラウザで確認する**

`確認用 日常点検表`（`sample_daily`）を開きます。

1. **点ではなく「24」「25」…という日にちの数字**がPDF上に並ぶ
2. 土曜の日にちが**青い丸**、日曜・祝日が**赤い丸**で囲まれる
3. 判定項目を置いた場所には **✓** が31個並ぶ
4. 1つ目の欄の文字は**ドラッグで動かせる**。2つ目以降は薄く表示され、動かせない
5. 動かすと2つ目以降も一緒に動く
6. ヘッダーの月を `2026-03` に変えると、日にちが 2/24〜3/23 に変わり、余りマスには何も出ない

- [ ] **Step 7: 回帰確認**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `276 passed`

- [ ] **Step 8: コミット**

```bash
git add static/layout.js
git commit -m "feat: show real printed text on the form instead of dot markers"
```

---

## Task 9: 「軸」を「並び方」に言い換える

**Files:**
- Modify: `static/layout.html`
- Modify: `static/layout.js`

Task 8 でゴースト表示が手に入ったので、言葉を分かるものに変えます。

- [ ] **Step 1: 下部バーの文言を変える**

`static/layout.html` の `<footer id="axis-bar">` の中身を次に置き換えます。

```html
        <span>並び方：</span>
        <button id="btn-axis-first" type="button">1つ目のマスを指定</button>
        <button id="btn-axis-second" type="button">2つ目のマスを指定</button>
        <span id="axis-step">まだ指定していません</span>
        <label>マスの数</label>
        <input type="number" id="axis-count" min="1" max="400" value="12" />
```

- [ ] **Step 2: 案内文を型に合わせて変える**

`static/layout.js` の `updateAxisLabel` を次に置き換えます。

```js
/** 型に応じた「マス」の呼び方 */
function slotWord() {
    return (state.layout && state.layout.period === "year") ? "月目" : "日目";
}

function updateAxisLabel() {
    const axis = (state.layout && state.layout.axis) || {};
    const sx = Number(axis.step_x || 0), sy = Number(axis.step_y || 0);
    const el = $("axis-step");
    if (!sx && !sy) {
        el.textContent = "まだ指定していません";
        return;
    }
    el.textContent = `ズレ x:${sx.toFixed(1)} y:${sy.toFixed(1)}`;
}

/** ボタンの文言を型に合わせる */
function updateAxisButtons() {
    const w = slotWord();
    $("btn-axis-first").textContent = `1${w}のマスを指定`;
    $("btn-axis-second").textContent = `2${w}のマスを指定`;
}
```

- [ ] **Step 3: 案内メッセージを差し替える**

`static/layout.js` の `handleAxisPick` の中のメッセージを次に置き換えます。

```js
        showStatus(`つぎに、2${slotWord()}のマスをクリックしてください`);
```

および、指定完了時のメッセージを次に置き換えます。

```js
        if (axis.step_x === 0 && axis.step_y === 0) {
            showStatus("同じ場所を2回クリックしたようです。離れた2つのマスを指定してください。",
                       true);
        } else {
            showStatus("並び方を設定しました。点線が紙のマスと重なっているか確かめてください。");
        }
```

`$("btn-axis-first")` のクリックハンドラのメッセージも変えます。

```js
        showStatus(`1${slotWord()}のマスをクリックしてください`);
```

`period === "single"` のときのメッセージも変えます。

```js
            showStatus("この様式は「1回の点検で1枚」なので、並び方の指定は要りません", true);
```

- [ ] **Step 4: ボタン文言の更新を呼ぶ**

`static/layout.js` の `selectForm` の中、`updateAxisLabel();` の直後に追加します。

```js
    updateAxisButtons();
```

- [ ] **Step 5: 指定のたびにプレビューを描き直す**

`handleAxisPick` の中、`updateAxisLabel();` の直後に追加します。

```js
        renderMarkers();
```

`$("axis-count")` の `change` ハンドラの末尾にも追加します。

```js
        renderMarkers();
```

- [ ] **Step 6: ブラウザで確認する**

1. 下部が「並び方： [1日目のマスを指定] [2日目のマスを指定] まだ指定していません マスの数 [31]」になる
2. 「1日目のマスを指定」を押すと「1日目のマスをクリックしてください」と出る
3. クリックすると「つぎに、2日目のマスをクリックしてください」に変わる
4. 2つ目をクリックすると、**その場で31日分の文字が点線状（薄く）に並ぶ**
5. 同じ場所を2回クリックすると警告が出る
6. `year` 型の様式では「1月目のマスを指定」と表示される（`period` を `year` にした様式で確認）

- [ ] **Step 7: コミット**

```bash
git add static/layout.html static/layout.js
git commit -m "feat: rename the axis controls to plain language and refresh the ghosts live"
```

---

## Task 10: 残り項目カウンタと仕上げ

**Files:**
- Modify: `static/layout.html`
- Modify: `static/layout.css`
- Modify: `static/layout.js`

- [ ] **Step 1: カウンタの置き場を足す**

`static/layout.html` の `#item-panel` の中、`<div class="panel-title">配置する項目</div>` の直後に入れます。

```html
            <div id="place-progress"></div>
```

- [ ] **Step 2: スタイルを足す**

`static/layout.css` の末尾に追記します。

```css
/* 残り項目のカウンタ */
#place-progress { margin-bottom: 10px; font-size: 12px; }

#place-progress .done {
    display: block;
    padding: 5px 8px;
    border-radius: 3px;
    background: #e8f2ec;
    border: 1px solid #2f7d51;
    color: #2f7d51;
    font-weight: 700;
}

#place-progress .todo {
    display: block;
    margin-top: 6px;
    color: #5a6a7a;
}

#place-progress button {
    display: block;
    width: 100%;
    margin-top: 3px;
    padding: 4px 8px;
    text-align: left;
    border: 1px solid #d5dbe0;
    border-radius: 3px;
    background: #fff;
    font-size: 12px;
    cursor: pointer;
}

#place-progress button:hover { background: #eef3f8; }
```

- [ ] **Step 3: カウンタを描く関数を足す**

`static/layout.js` の `countUnplaced` の直後に追加します。

```js
/** まだ置いていない点検項目のキーと表示名を返す */
function unplacedItems() {
    const placed = new Set(((state.layout && state.layout.fields) || [])
        .map(f => f.source));
    const rows = [];
    for (const group of collectItems()) {
        for (const it of group.items) {
            if (!it.key) continue;
            // 共通項目と備考は、置かない運用も普通にある
            if (it.key.startsWith("meta.")) continue;
            if (it.key.startsWith("remark:")) continue;
            if (!placed.has(it.key)) rows.push(it);
        }
    }
    return rows;
}

/** 置いた数と残りを左パネルの上に出す */
function renderProgress() {
    const el = $("place-progress");
    if (!el) return;
    const todo = unplacedItems();
    const total = (() => {
        let n = 0;
        for (const g of collectItems()) {
            for (const it of g.items) {
                if (!it.key) continue;
                if (it.key.startsWith("meta.") || it.key.startsWith("remark:")) continue;
                n++;
            }
        }
        return n;
    })();
    const done = total - todo.length;
    if (!total) { el.innerHTML = ""; return; }
    if (!todo.length) {
        el.innerHTML = `<span class="done">✓ ${done} / ${total} すべて置きました</span>`;
        return;
    }
    el.innerHTML = `<span class="done">置いた ${done} / ${total}</span>`
        + `<span class="todo">あと ${todo.length} 項目</span>`
        + todo.slice(0, 5).map(it =>
            `<button type="button" data-key="${escapeHtml(it.key)}">${escapeHtml(it.label)}</button>`
          ).join("")
        + (todo.length > 5 ? `<span class="todo">ほか ${todo.length - 5} 件</span>` : "");

    el.querySelectorAll("button[data-key]").forEach(btn => {
        btn.addEventListener("click", () => {
            state.selectedItem = btn.dataset.key;
            renderItemList();
            $("item-list").querySelectorAll(".item-row").forEach(r => {
                r.classList.toggle("selected", r.dataset.key === state.selectedItem);
            });
            showStatus("様式の上の、置きたい場所をクリックしてください");
        });
    });
}
```

- [ ] **Step 4: カウンタを描くタイミングをつなぐ**

`static/layout.js` の `renderItemList` の末尾（関数の最後の `}` の直前）に追加します。

```js
    renderProgress();
```

- [ ] **Step 5: 保存時の確認文を分かりやすくする**

`static/layout.js` の `saveLayout` の中の `confirm(...)` を次に置き換えます。

```js
        const ok = confirm(
            `まだ置いていない点検項目が ${unplaced} 件あります。\n`
            + "このまま保存すると、その項目は様式に印字されません。\n\n"
            + "保存しますか？");
```

- [ ] **Step 6: 通しで確認する**

`sample_daily` を開いて次を確かめます。

1. 左パネルの上に「置いた 1 / 1 …」または「あと N 項目」が出る
2. 「あと N 項目」の下のボタンを押すと、その項目が選択状態になり「様式の上の、置きたい場所をクリックしてください」と出る
3. 置くと数が減る
4. 全部置くと「✓ すべて置きました」に変わる

- [ ] **Step 7: 新規作成から試し刷りまで通す（総合確認）**

**これが最終確認です。必ず実施してください。**

1. 「新しい様式を追加」→ PDFをドラッグ → 「1枚に1か月分」→ 機器を1つ選ぶ → 名前をつけて作成
2. 下部の「1日目のマスを指定」→ 2か所クリック → **31日分のゴーストが並ぶ**
3. 左の一覧から項目を選び、PDF上をクリック → **✓ が31個並ぶ**
4. 「あと N 項目」が減る
5. 「保存」→「✓ 保存しました」
6. 「試し刷り」→ 別タブでPDFが開き、画面で見たとおりの位置に印字されている

**画面のプレビューと試し刷りのPDFで、文字の位置がずれていないこと**を必ず見比べてください。ずれていた場合は `layout-preview.js` の `top: vy - size * 0.8` の係数を調整します。

- [ ] **Step 8: 既存の様式が壊れていないか確認する（後方互換）**

`sample_daily` を開き、保存せずに試し刷りを出して、**この計画に着手する前と同じPDFが出ること**を確認します。

- [ ] **Step 9: 回帰確認**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `276 passed`

- [ ] **Step 10: 版数を上げる**

`static/layout.html` の `?v=` を上げて、利用者のブラウザが古いファイルを使わないようにします。

```html
    <link rel="stylesheet" href="/layout.css?v=3" />
```

```html
    <script type="module" src="/layout.js?v=3"></script>
```

- [ ] **Step 11: コミット**

```bash
git add static/layout.html static/layout.css static/layout.js
git commit -m "feat: show placement progress and remaining items on the layout screen"
```

---

## Task 11: 手引きの更新

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: `CLAUDE.md` に申し送りを足す**

`## 様式PDF（forms/）` の節の末尾に追加します。

```markdown
- **レイアウト画面は3つのESモジュールに分かれている。** `layout.js`（画面と状態）/ `layout-wizard.js`（様式追加）/ `layout-preview.js`（印字プレビュー）。プレビューは `layout.js` の状態を見ず、材料を引数で受け取る。
- **様式IDはアプリが自動採番する**（`form_01`…）。利用者には入力させない。手でフォルダを作ると規則から外れやすい。
- **印字プレビューの位置合わせ**：PDFは文字のベースラインに描くので、画面では `vy - 文字サイズ × 0.8` に置いている。ずれたらこの係数を疑う。
```

- [ ] **Step 2: `README.md` の様式の説明を更新する**

`### 📋 点検画面` より前に節がある場合はその流れに合わせ、様式レイアウトについて触れている箇所を探して、様式の追加手順を「画面の案内に従って4手順」に書き換えます。該当箇所が無ければ追加は不要です。

- [ ] **Step 3: コミット**

```bash
git add CLAUDE.md README.md
git commit -m "docs: record the layout screen module split and auto-numbered form ids"
```

---

## 自己レビュー結果

**設計書との照合：**

| 設計書の項目 | 対応するタスク |
|---|---|
| 追加ウィザード（4手順） | Task 5, 6 |
| 様式IDの自動採番 | Task 4, 6 |
| 印字プレビュー | Task 7, 8 |
| 「軸」の言い換えとゴースト | Task 9（ゴーストは Task 8 で実現済み） |
| 残り項目の表示 | Task 10 |
| 状態バッジとエラーの可視化 | Task 1, 2 |
| 試し刷りの `prompt()` 廃止 | Task 3 |
| ファイル構成（3分割） | Task 5（wizard）, Task 7（preview） |
| サーバー側は変更なし | 全タスクで `pytest 276 passed` を確認 |
| 対象外（機器ごと複製、Undo、削除） | 触れない |

**未対応なし。**

**型・名前の一貫性：**

- `isOpenable` / `openBlockReason` / `unknownTargets`（Task 1, 2）は Task 4 で export に追加済み
- `displayYearMonth`（Task 3）を Task 8 の `loadPreviewContext` で使用
- `nextFormId`（Task 4）と `nextIdPreview`（Task 6）は同じ規則。ウィザード側は `layout.js` に依存しないよう独自に持つ
- `renderPreview` の ctx のキー（`layout` `viewport` `pageIndex` `selectedField` `defaultFontSize` `year` `month` `dates` `holidays` `buildingName` `numberItems`）は Task 7 の定義と Task 8 の呼び出しで一致
- `slotWord()`（Task 9）は `state.layout.period` を見る
