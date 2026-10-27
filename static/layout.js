import * as pdfjsLib from '/pdfjs/pdf.mjs';
import { openWizard, initWizard } from '/layout-wizard.js';
import { renderPreview } from '/layout-preview.js';
pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdfjs/pdf.worker.mjs';

// 機器名の位置に入る印。サーバー側 forms_layout.ALL_TARGETS と同じ値にすること。
// 片方だけ変えると、画面で置いた項目がPDFに出なくなる。
const ALL_TARGETS = "*";

const state = {
    forms: [],          // /api/forms の結果
    formId: "",         // 選択中の様式ID
    layout: null,       // 選択中の layout.json
    pdfDoc: null,
    pageIndex: 0,       // 0始まり
    viewport: null,     // 現在描画に使った viewport
    equipment: [],      // /api/equipment の結果
    equipmentFailed: false, // 点検項目マスタを読めなかったか
    selectedItem: null, // 左の一覧で選んでいる項目のキー
    selectedField: -1,  // layout.fields のインデックス
    axisPick: 0,        // 0=なし 1=1つ目待ち 2=2つ目待ち
    axisFirst: null,    // 1つ目の欄のPDF座標
    previewCtx: null,   // プレビュー用の材料（日付・祝日・建物名など）
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
    el._timer = setTimeout(() => { el.textContent = ""; }, 6000);
}

function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/** 未使用のいちばん小さい様式IDを返す（form_01, form_02, …）
 *
 *  様式IDはフォルダ名になる。利用者に入力させると日本語・ハイフン・パスなどで
 *  失敗するため、アプリが決める。サーバー側の is_valid_form_id() の規則
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

/** layout の targets のうち、点検項目マスタに無い機器名を返す */
function unknownTargets(layout, equipment) {
    const known = new Set((equipment || []).map(r => r.category_minor));
    return ((layout && layout.targets) || []).filter(t => !known.has(t));
}

/** 点検項目マスタが読めないときの案内文。
 *
 *  init() と selectForm() の両方で使う。文言をここ1か所にまとめないと、
 *  片方だけ直したときに「同じ意味だが違う文章」の通知が二重に出かねない。
 */
function equipmentMasterNotice() {
    return "<b>点検項目マスタを読み込めませんでした。</b><br>"
        + "機器や点検項目の一覧が出ないため、配置する項目を選べません。<br>"
        + "data/equipment_master.csv を確認してください"
        + "（Excelで保存し直すときは「CSV UTF-8（コンマ区切り）」を選びます）。";
}

/** 通知欄に理由を出す（空文字なら隠す） */
function showNotice(html) {
    const el = $("pdf-notice");
    if (!el) return;
    if (!html) { el.hidden = true; el.innerHTML = ""; return; }
    el.innerHTML = html;
    el.hidden = false;
}

/** 様式を開けないときに、前の様式の状態と表示を消す。
 *
 *  state.formId だけ新しい様式に変わり、state.layout が前の様式のまま残ると、
 *  そのまま保存したときに別の様式の設定を上書きしてしまう。
 */
function clearFormView() {
    state.layout = null;
    // 破棄してから null にする。clearFormView は同期関数なので await できず、
    // 破棄の Promise は捨てる（失敗しても続ける）。
    if (state.pdfDoc) {
        state.pdfDoc.destroy().catch(() => { /* 破棄できなくても続ける */ });
        state.pdfDoc = null;
    }
    state.selectedField = -1;
    const canvas = $("form-canvas");
    if (canvas) {
        canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
        canvas.width = 0;
        canvas.height = 0;
    }
    const layer = $("marker-layer");
    if (layer) layer.innerHTML = "";
    const list = $("item-list");
    if (list) list.innerHTML = "";
    const prog = $("place-progress");
    if (prog) prog.innerHTML = "";
    const page = $("page-label");
    if (page) page.textContent = "- / -";
    renderProps();
}

/** 様式一覧を読み、プルダウンを作る。
 *
 *  autoSelect=false のときは自動で開かない。ウィザードで作った直後など、
 *  開く様式が決まっている場合に、無関係な様式を先に読み込まないようにする。
 */
async function loadForms(autoSelect = true) {
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
            + `${isOpenable(f) ? "" : "⚠ "}${escapeHtml(f.form_name)}`
            + `（${escapeHtml(f.id)}）</option>`)
        .join("");

    if (!autoSelect) return;

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

/** 様式を1つ選んで、layout.json と様式PDFを読み込む */
async function selectForm(formId) {
    state.formId = formId;
    state.selectedField = -1;
    state.selectedItem = null;   // 別の様式の項目を持ち越さない
    state.axisPick = 0;
    state.axisFirst = null;
    closeCopyDialog();           // 前の様式の機器名が残った小窓で複製させない
    // 開けない様式は、404の代わりに理由を出して止める
    const entry = state.forms.find(f => f.id === formId);
    if (entry && !isOpenable(entry)) {
        showNotice(`<b>この様式は開けません。</b><br>${escapeHtml(openBlockReason(entry))}`);
        showStatus(openBlockReason(entry), true);
        clearFormView();
        return;
    }
    showNotice("");
    try {
        state.layout = await fetchJson(`/api/forms/${formId}/layout`);
    } catch (e) {
        showStatus(`${e.message}（設定が壊れている可能性があります）`, true);
        clearFormView();
        return;
    }
    // 前の様式のPDFを解放してから読む。参照を切るだけでは
    // PDF.js が内部で持つバッファが残る。
    if (state.pdfDoc) {
        try { await state.pdfDoc.destroy(); } catch (e) { /* 破棄できなくても続ける */ }
        state.pdfDoc = null;
    }
    try {
        state.pdfDoc = await pdfjsLib.getDocument({
            url: `/api/forms/${formId}/pdf`,
            cMapUrl: "/pdfjs/cmaps/",
            cMapPacked: true,
        }).promise;
    } catch (e) {
        showStatus("様式PDFを読み込めませんでした", true);
        clearFormView();
        return;
    }
    state.pageIndex = 0;
    $("axis-count").value = (state.layout.axis || {}).count || 12;
    updateAxisLabel();
    updateAxisButtons();
    await loadPreviewContext();
    await renderPage();
    renderItemList();
    renderMarkers();
    renderProps();

    if (state.equipmentFailed) {
        // マスタ自体が読めていない。機器名を疑わせる案内を出すと、
        // 正しい機器名を直そうとして無駄足になる。
        showNotice(equipmentMasterNotice());
    } else {
        const missing = unknownTargets(state.layout, state.equipment);
        if (missing.length) {
            showNotice(`<b>点検項目マスタに無い機器名があります。</b><br>`
                + missing.map(escapeHtml).map(n => `・${n}`).join("<br>")
                + "<br><br>このままでは、その機器の点検結果は様式に印字されません。"
                + "<br>点検項目マスタ（data/equipment_master.csv）の「小分類」と、"
                + "文字が完全に一致している必要があります。");
        }
    }
}

/** 現在のページを描く */
async function renderPage() {
    if (!state.pdfDoc) return;
    const page = await state.pdfDoc.getPage(state.pageIndex + 1);
    const wrap = $("canvas-wrap");
    const base = page.getViewport({ scale: 1.0 });
    // 横幅に合わせる。拡大しすぎないよう上限を設ける。
    const scale = Math.min(Math.max((wrap.clientWidth - 40) / base.width, 0.3), 2.0);
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
    renderMarkers();
}

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

/** 型に応じた「マス」の呼び方。month は日ごと、year は月ごとに並ぶ。 */
function slotWord() {
    return (state.layout && state.layout.period === "year") ? "月目" : "日目";
}

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

/** ボタンの文言を型に合わせる（1日目のマス／1月目のマス） */
function updateAxisButtons() {
    const w = slotWord();
    $("btn-axis-first").textContent = `1${w}のマスを指定`;
    $("btn-axis-second").textContent = `2${w}のマスを指定`;
}

/** この様式に載る機器の点検項目を一覧化する */
function collectItems() {
    const groups = [{
        name: "共通",
        items: [
            { key: "meta.month", label: "タイトルの月" },
            { key: "meta.year", label: "タイトルの年" },
            { key: "meta.day", label: "日にち（土日祝は丸）" },
            { key: "meta.weekday", label: "曜日（土日祝は色つき）" },
            { key: "meta.unused", label: "使用せず（点検の無い日に✓）" },
            { key: "meta.inspection_date", label: "点検日" },
            { key: "meta.inspector", label: "点検者名" },
            { key: "meta.department", label: "所属" },
            { key: "meta.building_name", label: "建物名" },
            { key: "meta.general_remark", label: "備考" },
        ],
    }];
    // 月の変わり目は「1枚に1か月分」の様式にしか無い概念なので、そのときだけ出す
    if (state.layout && state.layout.period === "month") {
        // 「置く場所」を先に書く。印字される場所（1日のマス）を名前にしていたため、
        // そこへ直接置かれて8マス分ずれる誤りが実際に起きた。
        groups[0].items.push(
            { key: "meta.month_start", label: "実施月（1マス目に置く）" },
            { key: "meta.month_prev", label: "前月（1マス目に置く）" });
    }
    const targets = (state.layout && state.layout.targets) || [];
    // 同じ点検項目を2つ以上の機器が持つとき、判定を1マスにまとめて置けるようにする。
    // 機器が1つだけの様式では意味が無いので出さない。
    if (targets.length >= 2) {
        const counts = new Map();   // 点検項目名 → その項目を持つ機器の数
        for (const name of targets) {
            const seen = new Set();
            for (const r of (state.equipment || [])) {
                if (r.category_minor !== name) continue;
                // 数値は2機器分を1マスに書けないので、まとめの対象にしない
                if ((r.input_type || "").trim() === "数値") continue;
                if (seen.has(r.inspection_item)) continue;
                seen.add(r.inspection_item);
                counts.set(r.inspection_item,
                           (counts.get(r.inspection_item) || 0) + 1);
            }
        }
        const shared = [...counts.keys()].filter(k => counts.get(k) >= 2);
        if (shared.length) {
            groups.push({
                name: "全機器まとめ",
                items: shared.map(item => (
                    { key: `item:${ALL_TARGETS}|${item}`, label: item })),
            });
        }
        groups.push({
            name: "対象機器",
            items: targets.map(name => ({ key: `target:${name}`, label: name })),
        });
    }
    for (const name of targets) {
        // 機器名は点検項目マスタの category_minor と一致する
        const rows = state.equipment.filter(r => r.category_minor === name);
        const items = [];
        for (const r of rows) {
            items.push({ key: `item:${name}|${r.inspection_item}`,
                         label: r.inspection_item });
            items.push({ key: `remark:${name}|${r.inspection_item}`,
                         label: `${r.inspection_item}（備考）` });
        }
        if (!rows.length) {
            items.push({ key: "", label: "（マスタに該当する点検項目がありません）" });
        }
        groups.push({ name, items });
    }
    if (!targets.length) {
        groups.push({ name: "（この様式に機器が紐づいていません）", items: [] });
    }
    return groups;
}

/** 置いた source の集合を返す。
 *
 *  item:*|X（全機器まとめ）を置いたら、その項目名を持つ全機器の
 *  item:機器名|X も置いたものとして数える。そうしないと、まとめて置いたのに
 *  「まだ置いていない項目があります」が消えない。
 */
function placedSourceSet() {
    const placed = new Set();
    const targets = (state.layout && state.layout.targets) || [];
    for (const f of ((state.layout && state.layout.fields) || [])) {
        placed.add(f.source);
        if (!String(f.source || "").startsWith("item:")) continue;
        const body = f.source.slice(5);
        const bar = body.indexOf("|");
        if (bar < 0 || body.slice(0, bar) !== ALL_TARGETS) continue;
        const item = body.slice(bar + 1);
        for (const name of targets) placed.add(`item:${name}|${item}`);
    }
    return placed;
}

/** 左の一覧を描く。配置済みの項目には ✓ を付ける。 */
function renderItemList() {
    const placed = placedSourceSet();
    const html = collectItems().map(group => {
        const rows = group.items.map(it => {
            if (!it.key) return `<div class="item-row" style="color:#aaa">${escapeHtml(it.label)}</div>`;
            return `<div class="item-row" data-key="${escapeHtml(it.key)}">
              <span class="placed">${placed.has(it.key) ? "✓" : ""}</span>
              <span>${escapeHtml(it.label)}</span>
            </div>`;
        }).join("");
        return `<div class="item-group">${escapeHtml(group.name)}</div>${rows}`;
    }).join("");
    $("item-list").innerHTML = html;
    $("item-list").querySelectorAll(".item-row[data-key]").forEach(row => {
        row.addEventListener("click", () => {
            state.selectedItem = row.dataset.key;
            $("item-list").querySelectorAll(".item-row")
                .forEach(r => r.classList.remove("selected"));
            row.classList.add("selected");
        });
    });
    renderProgress();
}

/** 画面上のクリック位置をPDF座標に変換する */
function toPdfPoint(clientX, clientY) {
    const canvas = $("form-canvas");
    const rect = canvas.getBoundingClientRect();
    const [px, py] = state.viewport.convertToPdfPoint(
        clientX - rect.left, clientY - rect.top);
    return [Math.round(px * 10) / 10, Math.round(py * 10) / 10];
}

/** PDF座標を画面上の位置に戻す */
function toViewportPoint(px, py) {
    return state.viewport.convertToViewportPoint(px, py);
}

/** クリックした場所に、選択中の項目を配置する */
function placeSelectedItem(clientX, clientY) {
    if (!state.layout) return;
    if (!state.selectedItem) {
        showStatus("先に左の一覧から項目を選んでください", true);
        return;
    }
    const [x, y] = toPdfPoint(clientX, clientY);
    if (!state.layout.fields) state.layout.fields = [];
    const fields = state.layout.fields;
    const index = fields.findIndex(
        f => f.source === state.selectedItem && f.page === state.pageIndex);
    if (index >= 0) {
        fields[index].x = x;
        fields[index].y = y;
        state.selectedField = index;
    } else {
        fields.push({
            source: state.selectedItem,
            page: state.pageIndex,
            x, y,
            // single 型以外は軸に沿って並べるのが既定。共通のタイトル項目は除く。
            on_axis: state.layout.period !== "single"
                && !["meta.month", "meta.year", "meta.building_name"]
                    .includes(state.selectedItem),
        });
        state.selectedField = fields.length - 1;
    }
    renderItemList();
    renderMarkers();
    renderProps();
}

/** サイクル内の日付を並べて返す（app.py の get_cycle_dates と同じ考え方）
 *
 *  点検サイクルは暦月ではなく締め日区切り。既定は前月24日から当月23日まで。
 *  月末が無い日（2月31日など）は月末に丸める。
 */
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

    // 点検項目名は機器をまたいで重複する（「点検項目C-1」が5機器に存在する）。
    // 機器で絞らずに名前だけで判定すると、無関係な機器の設定を巻き添えにする。
    // サーバー側の _number_items_for_targets と同じく targets で絞る。
    const targets = new Set((state.layout && state.layout.targets) || []);
    const numberItems = new Set(
        (state.equipment || [])
            .filter(r => targets.has(r.category_minor)
                         && (r.input_type || "").trim() === "数値")
            .map(r => r.inspection_item));

    state.previewCtx = { year, month, dates, holidays, buildingName, numberItems };
}

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

/** 印をドラッグして位置を調整する */
function startDrag(downEvent) {
    const fields = (state.layout && state.layout.fields) || [];
    const f = fields[state.selectedField];
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

/** 選択中の配置の設定を右パネルに描く */
function renderProps() {
    const fields = (state.layout && state.layout.fields) || [];
    const f = fields[state.selectedField];
    if (!f) {
        $("prop-body").innerHTML =
            '<p class="hint">左の一覧から項目を選び、様式の上をクリックすると配置されます。</p>';
        return;
    }
    const isDay = f.source === "meta.day";
    // 1文字を中央に置く項目。縦書きは意味がないので選ばせない。
    const isCentred = isDay || f.source === "meta.weekday";
    // 内部名（item:機器|項目 など）ではなく、左の一覧と同じ名前を出す。
    // 対応が見つからない設定のときだけ、内部名をそのまま出して手がかりにする。
    const label = (() => {
        for (const group of collectItems()) {
            for (const it of group.items) {
                if (it.key && it.key === f.source) {
                    return group.name === "共通" ? it.label : `${group.name}／${it.label}`;
                }
            }
        }
        return f.source;
    })();
    $("prop-body").innerHTML = `
      <div class="prop-row"><label>フォルダ名</label>
        <span style="font-size:12px">${escapeHtml(state.formId)}</span></div>
      <div class="prop-row"><label>項目</label>
        <span style="font-size:12px" title="${escapeHtml(f.source)}">${escapeHtml(label)}</span></div>
      <div class="prop-row"><label>ページ</label>
        <span>${f.page + 1}</span></div>
      <div class="prop-row"><label>X</label>
        <input type="number" id="p-x" step="0.1" value="${f.x}" /></div>
      <div class="prop-row"><label>Y</label>
        <input type="number" id="p-y" step="0.1" value="${f.y}" /></div>
      <div class="prop-row"><label>文字サイズ</label>
        <input type="number" id="p-size" step="0.5" value="${f.font_size ?? ""}" /></div>
      <div class="prop-row"><label>色</label>
        <input type="text" id="p-color" value="${escapeHtml(f.color || "#000000")}" /></div>
      ${isDay ? `<div class="prop-row"><label>丸の半径</label>
        <input type="number" id="p-radius" step="0.5" value="${f.circle_radius ?? ""}" /></div>` : ""}
      ${isCentred ? "" : `<div class="prop-row"><label>縦書きにする</label>
        <input type="checkbox" id="p-vertical" ${f.vertical ? "checked" : ""} /></div>`}
      <div class="prop-row"><label>マスの数だけ繰り返す</label>
        <input type="checkbox" id="p-axis" ${f.on_axis ? "checked" : ""} /></div>
      <div class="prop-row">
        <button id="p-delete" type="button">この配置を削除</button></div>
      <div class="prop-row">
        <button id="p-copy" type="button">機器ごと複製...</button></div>
    `;
    const bindNumber = (id, key) => {
        const el = $(id);
        if (!el) return;
        el.addEventListener("change", () => {
            if (el.value === "") delete f[key];
            else f[key] = Number(el.value);
            renderMarkers();
        });
    };
    bindNumber("p-x", "x");
    bindNumber("p-y", "y");
    bindNumber("p-size", "font_size");
    bindNumber("p-radius", "circle_radius");
    const colorEl = $("p-color");
    if (colorEl) colorEl.addEventListener("change", () => {
        if (colorEl.value.trim() === "") delete f.color;
        else f.color = colorEl.value.trim();
    });
    const vertEl = $("p-vertical");
    if (vertEl) vertEl.addEventListener("change", () => {
        // 既定は横書き。既存の様式に vertical を書き足さないよう、
        // オフのときはキーごと消す。
        if (vertEl.checked) f.vertical = true;
        else delete f.vertical;
        renderMarkers();
    });
    const axisEl = $("p-axis");
    if (axisEl) axisEl.addEventListener("change", () => { f.on_axis = axisEl.checked; });
    $("p-delete").addEventListener("click", () => {
        fields.splice(state.selectedField, 1);
        state.selectedField = -1;
        renderItemList();
        renderMarkers();
        renderProps();
    });
    const copyBtn = $("p-copy");
    if (copyBtn) copyBtn.addEventListener("click", openCopyDialog);
}

/** 「1つ目の欄」「2つ目の欄」をクリックしてズレ幅を求める */
function handleAxisPick(e) {
    const [x, y] = toPdfPoint(e.clientX, e.clientY);
    if (state.axisPick === 1) {
        state.axisFirst = [x, y];
        state.axisPick = 2;
        $("btn-axis-first").classList.remove("active");
        $("btn-axis-second").classList.add("active");
        showStatus(`つぎに、2${slotWord()}のマスをクリックしてください`);
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
        renderMarkers();
        if (axis.step_x === 0 && axis.step_y === 0) {
            showStatus("同じ場所を2回クリックしたようです。離れた2つのマスを指定してください。",
                       true);
        } else {
            showStatus("並び方を設定しました。薄い文字が紙のマスと重なっているか確かめてください。");
        }
    }
}

/** 配置していない点検項目の数を数える（共通項目は必須ではないので数えない） */
function countUnplaced() {
    const placed = placedSourceSet();
    let n = 0;
    for (const group of collectItems()) {
        for (const it of group.items) {
            if (!it.key) continue;
            // 共通項目（点検者名など）と備考は、置かない運用も普通にある
            if (it.key.startsWith("meta.")) continue;
            if (it.key.startsWith("remark:")) continue;
            if (!placed.has(it.key)) n++;
        }
    }
    return n;
}

/** 置くべき点検項目を列挙する。
 *
 *  共通項目（点検者名など）と備考は、置かない運用も普通にあるので数えない。
 *  countUnplaced() と同じ数え方にすること。
 */
function placeableItems() {
    const rows = [];
    for (const group of collectItems()) {
        for (const it of group.items) {
            if (!it.key) continue;
            if (it.key.startsWith("meta.")) continue;
            if (it.key.startsWith("remark:")) continue;
            rows.push(it);
        }
    }
    return rows;
}

/** 置いた数と残りを左パネルの上に出す */
function renderProgress() {
    const el = $("place-progress");
    if (!el) return;
    const all = placeableItems();
    const placed = placedSourceSet();
    const todo = all.filter(it => !placed.has(it.key));
    const done = all.length - todo.length;

    if (!all.length) { el.innerHTML = ""; return; }
    if (!todo.length) {
        el.innerHTML = `<span class="done">✓ ${done} / ${all.length} すべて置きました</span>`;
        return;
    }
    el.innerHTML = `<span class="done">置いた ${done} / ${all.length}</span>`
        + `<span class="todo">あと ${todo.length} 項目</span>`
        + todo.slice(0, 5).map(it =>
            `<button type="button" data-key="${escapeHtml(it.key)}">${escapeHtml(it.label)}</button>`
          ).join("")
        + (todo.length > 5 ? `<span class="todo">ほか ${todo.length - 5} 件</span>` : "");

    el.querySelectorAll("button[data-key]").forEach(btn => {
        btn.addEventListener("click", () => {
            state.selectedItem = btn.dataset.key;
            $("item-list").querySelectorAll(".item-row").forEach(r => {
                r.classList.toggle("selected", r.dataset.key === state.selectedItem);
            });
            showStatus("様式の上の、置きたい場所をクリックしてください");
        });
    });
}

/** layout.json を保存する */
async function saveLayout() {
    if (!state.formId || !state.layout) {
        showStatus("保存する様式が選ばれていません", true);
        return false;
    }
    const unplaced = countUnplaced();
    if (unplaced > 0) {
        const ok = confirm(
            `まだ置いていない点検項目が ${unplaced} 件あります。\n`
            + "このまま保存すると、その項目は様式に印字されません。\n\n"
            + "保存しますか？");
        if (!ok) return false;
    }
    let res;
    try {
        res = await fetch(`/api/forms/${encodeURIComponent(state.formId)}/layout`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(state.layout),
        });
    } catch (e) {
        showStatus("保存できませんでした（アプリとの通信に失敗しました）", true);
        return false;
    }
    if (res.status === 401) {
        showStatus("保存には管理者権限が必要です（アプリを動かしているPCで操作してください）",
                   true);
        return false;
    }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showStatus(err.error || `保存に失敗しました (${res.status})`, true);
        return false;
    }
    showStatus("✓ 保存しました");
    return true;
}

/** ある機器の配置一式を、別の機器へずらして複製する。
 *  複製先のマスタに無い点検項目は飛ばす。 */
function copyFields(from, to, dx, dy) {
    const prefixFrom = `item:${from}|`;
    const remarkFrom = `remark:${from}|`;
    const toItems = new Set(state.equipment
        .filter(r => r.category_minor === to)
        .map(r => r.inspection_item));
    const fields = state.layout.fields || (state.layout.fields = []);
    let copied = 0, skipped = 0;
    for (const f of [...fields]) {
        let prefix = null;
        if (f.source.startsWith(prefixFrom)) prefix = prefixFrom;
        else if (f.source.startsWith(remarkFrom)) prefix = remarkFrom;
        if (!prefix) continue;

        const itemName = f.source.slice(prefix.length);
        if (!toItems.has(itemName)) { skipped++; continue; }

        const kind = prefix.startsWith("item:") ? "item" : "remark";
        const newSource = `${kind}:${to}|${itemName}`;
        const clone = {
            ...f,
            source: newSource,
            x: Math.round((f.x + dx) * 10) / 10,
            y: Math.round((f.y + dy) * 10) / 10,
        };
        const existing = fields.findIndex(
            g => g.source === newSource && g.page === f.page);
        if (existing >= 0) fields[existing] = clone;
        else fields.push(clone);
        copied++;
    }
    state.selectedField = -1;
    renderItemList();
    renderMarkers();
    renderProps();
    if (copied === 0) {
        showStatus(`複製できる配置がありませんでした（${escapeHtml(from)} の配置を先に作ってください）`,
                   true);
    } else if (skipped) {
        showStatus(`${copied}件を複製しました（複製先に無い ${skipped}件は飛ばしました）`);
    } else {
        showStatus(`${copied}件を複製しました`);
    }
}

/** 機器を選び、その機器の配置一式を別の機器へずらして複製する小窓を開く */
function openCopyDialog() {
    const targets = (state.layout && state.layout.targets) || [];
    if (targets.length < 2) {
        showStatus("複製するには、この様式に機器が2つ以上紐づいている必要があります", true);
        return;
    }
    const options = targets.map(t =>
        `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");
    $("copy-from").innerHTML = options;
    $("copy-to").innerHTML = options;
    $("copy-from").value = targets[0];
    $("copy-to").value = targets[1];
    $("copy-dx").value = "0";
    $("copy-dy").value = "-20";
    $("copy-error").hidden = true;
    $("copy-overlay").hidden = false;
    $("copy-from").focus();
}

function closeCopyDialog() {
    $("copy-overlay").hidden = true;
}

/** 小窓の「複製」。入力に誤りがあれば小窓を閉じずに理由を出す */
function submitCopyDialog() {
    const showError = msg => {
        $("copy-error").textContent = msg;
        $("copy-error").hidden = false;
    };
    const from = $("copy-from").value;
    const to = $("copy-to").value;
    if (from === to) { showError("複製元と複製先が同じです。別の機器を選んでください。"); return; }
    // type="number" は数字として読めない入力を空文字にする。空欄を0と見なさない。
    const dxRaw = $("copy-dx").value.trim(), dyRaw = $("copy-dy").value.trim();
    const dx = Number(dxRaw), dy = Number(dyRaw);
    if (dxRaw === "" || dyRaw === "" || !Number.isFinite(dx) || !Number.isFinite(dy)) {
        showError("ずらす量は数値で入力してください。");
        return;
    }
    closeCopyDialog();
    copyFields(from, to, dx, dy);
}

/** 様式フォルダの場所を上部の帯に表示する */
async function showFormsDir() {
    const el = $("forms-dir-path");
    if (!el) return;
    try {
        const cfg = await fetchJson("/api/config");
        const dir = (cfg.forms_directory || "").trim();
        el.textContent = dir || "アプリ内の forms フォルダ（設定画面で変更できます）";
    } catch (e) {
        el.textContent = "（場所を取得できませんでした）";
    }
}

async function init() {
    // 点検項目マスタが読めなくても、画面は動かす。ここで例外を投げると
    // 以降のイベント登録が全部飛んで、ボタンが何も反応しなくなる。
    try {
        state.equipment = await fetchJson("/api/equipment");
    } catch (e) {
        state.equipment = [];
        state.equipmentFailed = true;
        showNotice(equipmentMasterNotice());
    }
    showFormsDir();   // 表示だけなので、失敗しても本編は止めない
    initDisplayMonth();
    $("display-month").addEventListener("change", async () => {
        await loadPreviewContext();
        renderMarkers();
    });
    await loadForms();
    // loadForms が様式を1つ選べたときは selectForm() が上と同じ案内を出し直すので
    // ここでは何もしなくてよい。ただし「様式が1つもない」「開ける様式が無い」で
    // 早期returnしたときは selectForm() まで辿り着かず、上の案内が消えたままになる
    // ので、そのときだけ出し直す。
    if (state.equipmentFailed) {
        const notice = $("pdf-notice");
        const shown = (notice && !notice.hidden) ? notice.innerHTML : "";
        if (!shown.includes(equipmentMasterNotice())) {
            showNotice(shown
                ? `${shown}<br><br>${equipmentMasterNotice()}`
                : equipmentMasterNotice());
        }
    }
    $("btn-save").addEventListener("click", () => {
        saveLayout().catch(e => showStatus(e.message, true));
    });
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
        // 消した様式の設定が state.layout に残ったまま次の保存で使われると、
        // 別の様式を上書きしてしまう。先に表示と状態を消す。
        clearFormView();
        state.formId = "";
        showStatus(`「${name}」をゴミ箱へ移しました`);
        await loadForms();
    });
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
    initWizard();
    $("btn-new-form").addEventListener("click", async () => {
        const newId = await openWizard(state.equipment, state.forms.map(f => f.id));
        if (!newId) return;
        // 開く様式はもう決まっているので、自動選択はさせない
        // （させると、無関係な様式を1回読んでからすぐ読み直すことになりちらつく）
        await loadForms(false);
        const sel = $("form-select");
        if (sel) sel.value = newId;
        await selectForm(newId);
    });
    $("form-canvas").addEventListener("click", e => {
        if (state.axisPick) { handleAxisPick(e); return; }
        placeSelectedItem(e.clientX, e.clientY);
    });
    $("form-select").addEventListener("change", e => {
        selectForm(e.target.value).catch(err => showStatus(err.message, true));
    });
    $("btn-page-prev").addEventListener("click", async () => {
        if (state.pageIndex > 0) { state.pageIndex--; await renderPage(); }
    });
    $("btn-page-next").addEventListener("click", async () => {
        if (state.pdfDoc && state.pageIndex < state.pdfDoc.numPages - 1) {
            state.pageIndex++; await renderPage();
        }
    });
    // 幅が変わったら描き直す（連続発火を抑える）
    let resizeTimer = null;
    window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => { renderPage(); }, 200);
    });
    $("copy-cancel").addEventListener("click", closeCopyDialog);
    $("copy-ok").addEventListener("click", submitCopyDialog);
    document.addEventListener("keydown", e => {
        // 複製の小窓が開いている間は、裏の配置を矢印キーで動かさない
        if (!$("copy-overlay").hidden) {
            if (e.key === "Escape") closeCopyDialog();
            else if (e.key === "Enter" && e.target.tagName !== "BUTTON") submitCopyDialog();
            return;
        }
        // 入力欄の中では矢印キーを本来の用途に譲る
        const tag = (e.target.tagName || "").toLowerCase();
        if (tag === "input" || tag === "select" || tag === "textarea") return;
        const fields = (state.layout && state.layout.fields) || [];
        const f = fields[state.selectedField];
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
    $("btn-axis-first").addEventListener("click", () => {
        if (!state.layout) return;
        if (state.layout.period === "single") {
            showStatus("この様式は「1回の点検で1枚」なので、並び方の指定は要りません", true);
            return;
        }
        state.axisPick = 1;
        state.axisFirst = null;
        $("btn-axis-first").classList.add("active");
        $("btn-axis-second").classList.remove("active");
        showStatus(`1${slotWord()}のマスをクリックしてください`);
    });
    $("btn-axis-second").addEventListener("click", () => {
        if (!state.axisFirst) {
            showStatus(`先に「1${slotWord()}のマスを指定」を押してください`, true);
            return;
        }
        state.axisPick = 2;
        $("btn-axis-second").classList.add("active");
    });
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
    $("axis-count").addEventListener("change", () => {
        if (!state.layout) return;
        const n = Number($("axis-count").value);
        if (!Number.isInteger(n) || n < 1 || n > 400) {
            showStatus("マスの数は1〜400で指定してください", true);
            return;
        }
        const axis = state.layout.axis || (state.layout.axis = {});
        axis.count = n;
        renderMarkers();
    });
}

document.addEventListener("DOMContentLoaded", () => {
    init().catch(e => showStatus(e.message, true));
});

export { state, renderPage, selectForm, escapeHtml, fetchJson, showStatus, showFormsDir,
         renderItemList, renderMarkers, renderProps, toPdfPoint, toViewportPoint,
         collectItems, placeSelectedItem, startDrag, handleAxisPick,
         countUnplaced, saveLayout, copyFields, openCopyDialog, displayYearMonth,
         nextFormId, isOpenable, openBlockReason, unknownTargets };
