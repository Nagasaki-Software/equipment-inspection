/**
 * 設備点検システム - フロントエンドロジック（機能強化版）
 */
"use strict";

// ============================================================
// 状態管理
// ============================================================
// 点検サイクルの締め日。/api/config 読み込み後に上書きする。
let cycleStartDay = 24;

// 判定の記号。サーバー側（forms_layout.py）と同じ内容にすること。
const MARK_OK = "✓";        // 良
const MARK_ADJUST = "A";    // 要調整
const MARK_REPAIR = "△";    // 修理
const MARK_REPLACE = "×";   // 要取替
const MARK_NA = "ー";       // 点検対象外
const LEGACY_MARK_OK = "○"; // 旧仕様の「良」。保存済みの記録に残っている

// 不合格として扱う記号。ラベルは画面と警告文で使う。
const NG_MARKS = [
    { mark: MARK_ADJUST, label: "要調整" },
    { mark: MARK_REPAIR, label: "修理" },
    { mark: MARK_REPLACE, label: "要取替" },
];

/** 保存済みの判定を今の記号に読み替える。記録そのものは書き換えない。 */
function normalizeJudgment(value) {
    if (typeof value !== "string") return "";
    return value === LEGACY_MARK_OK ? MARK_OK : value;
}

/** 不合格（要調整・修理・要取替）かどうか */
function isNgMark(value) {
    return NG_MARKS.some(m => m.mark === normalizeJudgment(value));
}

const state = {
    currentMode: "使用前",
    currentMajor: "",
    currentMinor: "",
    equipmentData: [],
    inspectorList: [],
    holidayMap: {},
    inspectionResults: {},
    selectedDate: today(),
    targetYearMonth: getDefaultTargetMonth(),
    config: {},
    todayCompleted: [],
    monthlyCompleted: [], // 当月に月例点検が完了した設備キーを保持
    currentInspectorJson: "", // 点検者テーブルフッターで選択された値
    inspectorsByEquipment: {}, // 各設備ごとの点検者を保持
    generalRemarks: {}, // 各設備ごとの全体備考を保持
    previousValues: {} // 数値項目の前回値（"点検項目名" → 値）
};

// ============================================================
// ユーティリティ
// ============================================================
function pad(n) { return String(n).padStart(2, "0"); }

/** HTMLエスケープ（XSS対策） */
function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/** 点検項目の入力方式を返す（マスタに列が無ければ「判定」） */
function itemInputType(row) {
    const v = ((row && row.input_type) || "").trim();
    return v === "数値" ? "数値" : "判定";
}

/** 点検項目の単位を返す（数値項目以外は空文字） */
function itemUnit(row) {
    return itemInputType(row) === "数値" ? ((row && row.unit) || "").trim() : "";
}

/** 全角数字・全角ピリオド・全角マイナスを半角に直す。
 *  長音「ー」は点検対象外の記録に使うので変換しない。 */
function normalizeNumberInput(value) {
    if (typeof value !== "string") return value;
    if (value.trim() === "ー") return "ー";
    return value
        .replace(/[０-９]/g, ch => String.fromCharCode(ch.charCodeAt(0) - 0xFEE0))
        .replace(/[．。]/g, ".")
        .replace(/[－−―‐]/g, "-")
        .replace(/[\s　]/g, "")
        .trim();
}

/** 選択中の機器の前回値を読み込む。取れなくても点検の入力は続けられるようにする。 */
async function loadPreviousValues() {
    if (!state.currentMinor || !state.selectedDate) {
        state.previousValues = {};
        return;
    }
    const params = new URLSearchParams({
        type: state.currentMode,
        category_major: state.currentMajor,
        category_minor: state.currentMinor,
        before: state.selectedDate,
    });
    try {
        state.previousValues = await fetchJson(`/api/results/previous?${params}`);
    } catch (e) {
        // 前回値は補助情報なので、取れなくても止めない
        state.previousValues = {};
    }
}

/** 「前回 0.52 MPa」の表示を作る。前回値が無ければ空文字。 */
function previousLabel(row) {
    const value = state.previousValues[row.inspection_item];
    if (value === undefined || value === null || value === "") return "";
    const unit = itemUnit(row);
    return escapeHtml(`前回 ${value}${unit ? " " + unit : ""}`);
}

/** 数値項目の「ー」ボタンの選択状態を、いまの値に合わせる */
function syncNaButton(key, value) {
    document.querySelectorAll(`.btn-num-na[data-key="${CSS.escape(key)}"]`)
        .forEach(b => b.classList.toggle("selected", value === "ー"));
}

// ============================================================
// 数値入力用のテンキー（同時に1つだけ表示する）
// ============================================================
let activeKeypad = null;

function closeKeypad() {
    if (activeKeypad) { activeKeypad.remove(); activeKeypad = null; }
}

function openKeypad(input) {
    if (input.disabled) return;
    closeKeypad();
    const pad = document.createElement("div");
    pad.className = "keypad";
    const keys = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0", ".", "-"];
    pad.innerHTML =
        keys.map(k => `<button type="button" data-k="${k}">${k}</button>`).join("")
        + '<button type="button" data-k="BS" class="wide">← 1文字消す</button>'
        + '<button type="button" data-k="OK" class="wide ok">確定</button>';
    // 入力欄の親（.result-number）に入れる。position:relative を効かせるため。
    (input.parentElement || document.body).appendChild(pad);
    activeKeypad = pad;

    // スクロール枠の下にはみ出すと「確定」が押せなくなる。
    // 下に入らないなら入力欄の上に出し、それでも駄目なら枠をスクロールする。
    const wrap = input.closest(".inspection-table-wrap");
    if (wrap) {
        const padRect = pad.getBoundingClientRect();
        const wrapRect = wrap.getBoundingClientRect();
        const inputRect = input.getBoundingClientRect();
        const overflowsBelow = padRect.bottom > wrapRect.bottom;
        const fitsAbove = inputRect.top - wrapRect.top >= padRect.height + 8;
        if (overflowsBelow && fitsAbove) {
            pad.classList.add("above");
        } else if (overflowsBelow) {
            pad.scrollIntoView({ block: "nearest" });
        }
    }

    // 押しても入力欄のフォーカスを外さない（外すと blur でテンキーが閉じる）
    pad.addEventListener("mousedown", e => e.preventDefault());
    pad.addEventListener("click", e => {
        const k = e.target && e.target.dataset ? e.target.dataset.k : null;
        if (!k) return;
        if (k === "OK") { input.blur(); closeKeypad(); return; }
        if (k === "BS") input.value = input.value.slice(0, -1);
        else input.value += k;
        input.dispatchEvent(new Event("input", { bubbles: true }));
    });
}

function today() {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * デフォルト表示月を計算する。
 * 24日以降なら翌月、それ以前なら当月が「点検月（表示月）」。
 */
function getDefaultTargetMonth() {
    const now = new Date();
    if (now.getDate() >= cycleStartDay) {
        const next = new Date(now.getFullYear(), now.getMonth() + 1, 1);
        return `${next.getFullYear()}-${pad(next.getMonth() + 1)}`;
    }
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
}

/**
 * 表示月（displayYearMonth）から点検カレンダー範囲を計算する。
 * 範囲：前月の締め日 〜 表示月の締め日の前日（既定なら前月24日〜表示月23日）。
 * 月末に存在しない日（2月31日など）はその月の末日に丸める。
 */
function getCalendarRange(displayYearMonth) {
    const [y, m] = displayYearMonth.split("-").map(Number);
    const prevM = m === 1 ? 12 : m - 1;
    const prevY = m === 1 ? y - 1 : y;
    const start = clampDay(prevY, prevM, cycleStartDay);
    const end = new Date(clampDay(y, m, cycleStartDay).getTime() - 86400000);
    return { start, end };
}

/** その月に存在しない日は月末に丸める（year, month は1始まり） */
function clampDay(year, month, day) {
    const last = new Date(year, month, 0).getDate();
    return new Date(year, month - 1, Math.min(day, last));
}

function showStatus(msg, isError = false) {
    const el = document.getElementById("save-status");
    el.textContent = msg;
    el.style.color = isError ? "#e74c3c" : "#27ae60";
    clearTimeout(el._timer);
    el._timer = setTimeout(() => (el.textContent = ""), 5000);
}

// ============================================================
// カスタムNGアラートの表示
// ============================================================
function showNgAlert(ngCounts) {
    const overlay = document.createElement("div");
    overlay.style.position = "fixed";
    overlay.style.top = "0"; overlay.style.left = "0";
    overlay.style.width = "100%"; overlay.style.height = "100%";
    overlay.style.backgroundColor = "rgba(0,0,0,0.6)";
    overlay.style.display = "flex"; overlay.style.alignItems = "center"; overlay.style.justifyContent = "center";
    overlay.style.zIndex = "9999";

    const box = document.createElement("div");
    box.style.background = "#fff";
    box.style.padding = "30px 40px";
    box.style.borderRadius = "8px";
    box.style.boxShadow = "0 4px 20px rgba(0,0,0,0.3)";
    box.style.textAlign = "center";
    box.style.maxWidth = "450px";

    const breakdown = (ngCounts && ngCounts.length)
        ? ngCounts.map(m => `${escapeHtml(m.label)}（${escapeHtml(m.mark)}）${m.count}件`).join("　")
        : "";

    box.innerHTML = `
        <div style="color:#e74c3c; font-size:50px; margin-bottom:15px; line-height:1;">⚠️</div>
        <h3 style="margin:0 0 15px; color:#c0392b; font-size:20px;">不合格の項目があります</h3>
        <p style="margin:0 0 25px; color:#333; line-height:1.6; font-size:15px;">
            ${breakdown ? `<span style="font-weight:bold;">${breakdown}</span><br>` : ""}
            <strong>点検結果が不合格のため、直ちに管理者へ連絡してください。</strong>
        </p>
        <button class="btn btn-primary" style="padding:10px 40px; font-size:16px;">確認</button>
    `;

    box.querySelector("button").onclick = () => overlay.remove();
    overlay.appendChild(box);
    document.body.appendChild(overlay);
}

// ============================================================
// リアルタイム時計
// ============================================================
let _clockIntervalId = null;

function startClock() {
    const el = document.getElementById("clock-display");
    function tick() {
        const n = new Date();
        el.textContent = `${n.getFullYear()}/${pad(n.getMonth() + 1)}/${pad(n.getDate())} ${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
    }
    tick();
    if (_clockIntervalId) clearInterval(_clockIntervalId);
    _clockIntervalId = setInterval(tick, 1000);
}

// ============================================================
// API 通信
// ============================================================
async function fetchWithRetry(url, options = {}, retries = 2) {
    for (let i = 0; i <= retries; i++) {
        try {
            const res = await fetch(url, options);
            if (res.ok || i === retries) return res;
            await new Promise(r => setTimeout(r, 1000 * (i + 1)));
        } catch (e) {
            if (i === retries) throw e;
            await new Promise(r => setTimeout(r, 1000 * (i + 1)));
        }
    }
}

async function fetchJson(url) {
    const res = await fetchWithRetry(url);
    if (!res.ok) throw new Error(`Failed: ${url}`);
    return res.json();
}

async function fetchConfig() { return fetchJson("/api/config"); }
async function fetchEquipment() { return fetchJson("/api/equipment"); }
async function fetchInspectors() { return fetchJson("/api/inspectors"); }

async function fetchHolidays(start, end) {
    return fetchJson(`/api/holidays?start=${start}&end=${end}`);
}

async function fetchResults(type, year, month) {
    return fetchJson(`/api/results?type=${encodeURIComponent(type)}&year=${year}&month=${month}`);
}

async function postConfig(data) {
    const headers = { "Content-Type": "application/json" };
    const adminKey = document.getElementById("cfg-admin-key")?.value.trim();
    if (adminKey) headers["X-Admin-Key"] = adminKey;
    const res = await fetch("/api/config", {
        method: "POST", headers,
        body: JSON.stringify(data)
    });
    if (res.status === 401) throw new Error("管理者キーが正しくありません");
    if (!res.ok) throw new Error("設定の保存に失敗しました");
    return res.json();
}

async function postResults(payload) {
    const res = await fetchWithRetry("/api/results", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    }, 1);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存に失敗しました");
    return data;
}

// ============================================================
// サイドバー更新
// ============================================================
function updateSidebar(config) {
    const bi = config.building_info || {};
    document.getElementById("sb-building-name").textContent = bi.building_name || "-";

    const managers = bi.managers || [];
    const listEl = document.getElementById("sb-managers-list");
    listEl.innerHTML = managers.filter(m => m.name).map(m => {
        let phones = [];
        if (m.phone_ext) phones.push(`外線: ${escapeHtml(m.phone_ext)}`);
        if (m.phone_int) phones.push(`内線: ${escapeHtml(m.phone_int)}`);
        return `
    <div class="info-row">
      <div class="info-role">${escapeHtml(m.title || "")}</div>
      <div class="info-value">${escapeHtml(m.name)}</div>
      <div class="info-label">${phones.join("<br>")}</div>
    </div>
  `}).join("");

    const [y, m] = state.targetYearMonth.split("-").map(Number);
    document.getElementById("sb-period").textContent = `${y}年 ${m}月`;
}

// ============================================================
// タブ（大分類・小分類）
// ============================================================
function getFiltered(equip) {
    return equip.filter(r =>
        r.inspection_type === "両方" ||
        (state.currentMode === "使用前" && r.inspection_type === "使用前") ||
        (state.currentMode === "月例" && r.inspection_type === "月例")
    );
}

function renderMajorTabs() {
    const container = document.getElementById("major-tabs");
    container.innerHTML = "";
    // 使用前・月例共通category_majorを大分類タブに使用する
    const majors = [...new Set(getFiltered(state.equipmentData).map(r => r.category_major))];
    if (!majors.includes(state.currentMajor)) state.currentMajor = majors[0] || "";
    majors.forEach(maj => {
        const btn = document.createElement("div");
        btn.className = "major-tab" + (maj === state.currentMajor ? " active" : "");
        btn.textContent = maj;
        btn.addEventListener("click", () => {
            state.currentMajor = maj;
            state.currentMinor = "";
            // 大分類切替時は小分類未決定なのでinspectorはリセットする
            state.currentInspectorJson = "";
            renderMajorTabs(); renderMinorTabs(); renderInspectionTable();
            renderDailySummary();
        });
        container.appendChild(btn);
    });
}

function renderMinorTabs() {
    const container = document.getElementById("minor-tabs");
    container.style.display = "flex";
    container.innerHTML = "";
    const minors = [...new Set(
        getFiltered(state.equipmentData)
            .filter(r => r.category_major === state.currentMajor)
            .map(r => r.category_minor)
            .filter(m => m) // 空の小分類は除外する
    )];
    if (!minors.includes(state.currentMinor)) state.currentMinor = minors[0] || "";
    // 小分類が1つだけなら再描画は不要
    if (minors.length <= 1) {
        container.style.display = minors.length === 0 ? "none" : "flex";
    }
    minors.forEach(min => {
        const btn = document.createElement("div");
        btn.className = "minor-tab" + (min === state.currentMinor ? " active" : "");
        btn.textContent = min;
        btn.addEventListener("click", () => {
            state.currentMinor = min;
            // 小分類切替時に各設備に対応するinspectorを復元する
            const equipKey = `${state.currentMajor}|${min}`;
            state.currentInspectorJson = state.inspectorsByEquipment[equipKey] || "";
            renderMinorTabs(); renderInspectionTable();
            renderDailySummary(); // 小分類切替時に下部サマリー表も更新する
            // 前回値は機器ごとに違うので取り直す（取得後に表だけ描き直す）
            loadPreviousValues().then(() => renderInspectionTable());
        });
        container.appendChild(btn);
    });
}

// ============================================================
// 点検表
// ============================================================
function getCurrentItems() {
    const filtered = getFiltered(state.equipmentData);
    // 使用前・月例共通でcategory_major + category_minorでフィルタする
    return filtered.filter(
        r => r.category_major === state.currentMajor && r.category_minor === state.currentMinor
    );
}

function renderInspectionTable() {
    const panel = document.getElementById("inspection-panel");
    const banner = document.getElementById("completed-banner");
    const tbody = document.getElementById("inspection-tbody");

    // 大分類・小分類のキーで完了判定する
    const currentEquipKey = `${state.currentMajor}|${state.currentMinor}`;
    const isDailyCompleted = state.currentMode === "使用前" && state.todayCompleted.includes(currentEquipKey);
    const isMonthlyCompleted = state.currentMode === "月例" && state.monthlyCompleted.includes(currentEquipKey);
    const isCompleted = isDailyCompleted || isMonthlyCompleted;
    panel.classList.toggle("completed", isCompleted);
    banner.style.display = isCompleted ? "block" : "none";
    // バナーメッセージを使用前/月例で切り替える
    const msgEl = banner.querySelector(".completed-msg");
    if (msgEl) {
        msgEl.textContent = isMonthlyCompleted ? "✅ 今月の点検は終了しました" : "✅ 本日の点検は終了しました";
    }

    const rows = getCurrentItems();
    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="2" style="text-align:center;padding:20px;color:#aaa">対象データがありません</td></tr>`;
        return;
    }

    // 使用前点検は当日のみ入力可、月例点検は当月完了済みなら入力不可
    const isToday = state.selectedDate === today();
    const isReadonly = (state.currentMode === "使用前" && (isDailyCompleted || !isToday))
                     || (state.currentMode === "月例" && isMonthlyCompleted);

    closeKeypad();   // 表を描き直すと入力欄が消えるので、先にテンキーを片付ける
    tbody.innerHTML = "";
    rows.forEach(row => {
        const key = `${state.currentMajor}|||${state.currentMinor}|||${row.category_major}|||${row.inspection_item}`;
        const saved = state.inspectionResults[key] || { result: "", remark: "" };
        const tr = document.createElement("tr");

        const disabledAttr = isReadonly ? "disabled" : "";

        const inputType = itemInputType(row);
        // 旧仕様の「○」で保存された記録も「良」のボタンが選ばれた状態にする
        const cur = normalizeJudgment(saved.result);
        const cell = inputType === "数値"
            ? `
        <div class="result-number">
          <input type="text" class="num-input" inputmode="decimal"
                 data-key="${key}" value="${escapeHtml(saved.result || "")}"
                 ${disabledAttr} />
          <span class="num-unit">${escapeHtml(itemUnit(row))}</span>
          <button class="btn-dash btn-num-na${saved.result === "ー" ? " selected" : ""}"
                  data-key="${key}" ${disabledAttr} title="その日は点検対象外">ー</button>
        </div>
        <div class="num-prev">${previousLabel(row)}</div>`
            : `
        <div class="result-btns">
          <button class="btn-ok${cur === MARK_OK ? " selected" : ""}"
                  data-key="${key}" data-val="${MARK_OK}" ${disabledAttr}
                  title="良">${MARK_OK}</button>
          <button class="btn-adjust${cur === MARK_ADJUST ? " selected" : ""}"
                  data-key="${key}" data-val="${MARK_ADJUST}" ${disabledAttr}
                  title="要調整">${MARK_ADJUST}</button>
          <button class="btn-repair${cur === MARK_REPAIR ? " selected" : ""}"
                  data-key="${key}" data-val="${MARK_REPAIR}" ${disabledAttr}
                  title="修理">${MARK_REPAIR}</button>
          <button class="btn-replace${cur === MARK_REPLACE ? " selected" : ""}"
                  data-key="${key}" data-val="${MARK_REPLACE}" ${disabledAttr}
                  title="要取替">${MARK_REPLACE}</button>
          <button class="btn-dash${cur === MARK_NA ? " selected" : ""}"
                  data-key="${key}" data-val="${MARK_NA}" ${disabledAttr}
                  title="点検対象外">${MARK_NA}</button>
        </div>`;

        tr.innerHTML = `
      <td>${escapeHtml(row.inspection_item)}</td>
      <td>${cell}</td>
    `;
        tbody.appendChild(tr);
    });

    tbody.querySelectorAll(".btn-ok, .btn-adjust, .btn-repair, .btn-replace, .btn-dash:not(.btn-num-na)").forEach(btn => {
        btn.addEventListener("click", () => {
            if (isReadonly) return;
            const key = btn.dataset.key;
            const val = btn.dataset.val;
            if (!state.inspectionResults[key]) state.inspectionResults[key] = { result: "", remark: "" };
            const prev = normalizeJudgment(state.inspectionResults[key].result);
            state.inspectionResults[key].result = (prev === val) ? "" : val;

            renderInspectionTable();
        });
    });

    // 数値入力欄。判定ボタンと違い、表全体を描き直すと入力中にフォーカスが飛ぶため
    // ここでは state だけを更新する。
    tbody.querySelectorAll(".num-input").forEach(input => {
        const key = input.dataset.key;
        const setValue = value => {
            if (!state.inspectionResults[key]) {
                state.inspectionResults[key] = { result: "", remark: "" };
            }
            state.inspectionResults[key].result = value;
        };
        input.addEventListener("input", () => setValue(input.value));
        input.addEventListener("focus", () => openKeypad(input));
        input.addEventListener("blur", () => {
            const normalized = normalizeNumberInput(input.value);
            if (normalized !== input.value) input.value = normalized;
            setValue(normalized);
            syncNaButton(key, normalized);
            // 別の場所をクリックしたときにテンキーを閉じる。
            // テンキー自身を押したときは focus が戻るので閉じない。
            setTimeout(() => {
                if (document.activeElement !== input) closeKeypad();
            }, 150);
        });
    });

    // 「ー」ボタン：その日は点検対象外、という記録。もう一度押すと解除する。
    tbody.querySelectorAll(".btn-num-na").forEach(btn => {
        btn.addEventListener("click", () => {
            if (isReadonly) return;
            const key = btn.dataset.key;
            if (!state.inspectionResults[key]) {
                state.inspectionResults[key] = { result: "", remark: "" };
            }
            const isOn = state.inspectionResults[key].result === "ー";
            const next = isOn ? "" : "ー";
            state.inspectionResults[key].result = next;
            const input = tbody.querySelector(`.num-input[data-key="${CSS.escape(key)}"]`);
            if (input) input.value = next;
            syncNaButton(key, next);
        });
    });

    // 点検表最下段に点検者・保存ボタン行を追加する
    const table = document.getElementById("inspection-table");
    renderTableFoot(table, isReadonly);
}

/** 点検者プルダウンと保存ボタンをテーブルの最下段に描画する */
function renderTableFoot(table, isReadonly) {
    const existing = table.querySelector("tfoot");
    if (existing) existing.remove();

    const tfoot = document.createElement("tfoot");
    tfoot.id = "inspection-tfoot";

    const disabledAttr = isReadonly ? "disabled" : "";

    // 部署一覧の抽出
    const depts = [...new Set(state.inspectorList.map(p => p.department).filter(Boolean))];
    const deptOptions = depts.map(d => `<option value="${d}">${d}</option>`).join("");

    // コントロールバー等で保持された点検者情報から初期部署を特定する
    let selectedDept = "";
    if (state.currentInspectorJson) {
        try {
            const parsed = JSON.parse(state.currentInspectorJson);
            selectedDept = parsed.dept || "";
        } catch (e) { }
    }

    // 全体備考を取得
    const currentEquipKey = `${state.currentMajor}|${state.currentMinor}`;
    const savedGeneralRemark = state.generalRemarks[currentEquipKey] || "";

    tfoot.innerHTML = `
        <tr class="table-foot-row" style="background:#f9fbfe;">
          <td colspan="2" style="padding:10px;">
             <textarea id="table-general-remark" rows="2" style="width:100%; border:1px solid #ccc; border-radius:4px; padding:8px; font-size:14px;" placeholder="備考（特記事項があれば入力してください）" ${disabledAttr}>${savedGeneralRemark}</textarea>
          </td>
        </tr>
        <tr class="table-foot-row">
          <td class="table-foot-label" style="vertical-align:middle;">点検者</td>
          <td class="table-foot-action" style="padding:10px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <div class="inspector-select-group" style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <select id="table-dept-select" ${disabledAttr}>
                  <option value="">―― 部署を選択 ――</option>
                  ${deptOptions}
                </select>
                <select id="table-inspector-select" ${disabledAttr}>
                  <option value="">―― 氏名を選択 ――</option>
                </select>
              </div>
            </div>
          </td>
        </tr>
        <tr class="table-foot-row" style="background:#f4f7fa; border-top:1px solid var(--color-border);">
          <td colspan="2" style="padding:12px; text-align:right;">
            <div style="display:flex; justify-content:flex-end; align-items:center; gap:12px;">
              <span class="save-status" id="table-save-status" style="font-size:13px; font-weight:bold;"></span>
              ${state.currentMode === "月例" ? `<button class="btn" id="table-all-ok-btn" ${disabledAttr} style="white-space:nowrap; padding:8px 24px; font-size:15px; background:#2196F3; color:#fff; border:none; border-radius:4px; cursor:pointer;">✅ 全て${MARK_OK}</button>` : ""}
              <button class="btn btn-success" id="table-save-btn" ${disabledAttr} style="white-space:nowrap; padding:8px 24px; font-size:15px;">💾 保存</button>
            </div>
          </td>
        </tr>`;
    table.appendChild(tfoot);

    const generalRemarkInput = document.getElementById("table-general-remark");
    if (generalRemarkInput) {
        generalRemarkInput.addEventListener("input", e => {
            state.generalRemarks[currentEquipKey] = e.target.value;
        });
    }

    const deptSelect = document.getElementById("table-dept-select");
    const inspSelect = document.getElementById("table-inspector-select");

    // 氏名プルダウン更新用関数
    const updateInspectorOptions = (dept) => {
        inspSelect.innerHTML = '<option value="">―― 氏名を選択 ――</option>';
        if (!dept) return;
        state.inspectorList.filter(p => p.department === dept).forEach(p => {
            const v = JSON.stringify({ name: p.inspector_name, dept: p.department });
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = p.inspector_name;
            if (state.currentInspectorJson === v) opt.selected = true;
            inspSelect.appendChild(opt);
        });
    };

    if (selectedDept) {
        deptSelect.value = selectedDept;
    }
    updateInspectorOptions(deptSelect.value);

    // 部署が変更されたら氏名プルダウンを更新
    deptSelect.addEventListener("change", e => {
        state.currentInspectorJson = "";
        updateInspectorOptions(e.target.value);
    });

    inspSelect.addEventListener("change", e => {
        state.currentInspectorJson = e.target.value;
    });

    const saveBtn = document.getElementById("table-save-btn");
    if (saveBtn) {
        saveBtn.addEventListener("click", () => handleSave(true));
    }

    // 「全て✓」ボタン：現在表示中の判定項目を✓（良）に設定する。
    // 数値項目は測った値を入れる欄なので触らない。
    const allOkBtn = document.getElementById("table-all-ok-btn");
    if (allOkBtn) {
        allOkBtn.addEventListener("click", () => {
            const rows = getCurrentItems();
            rows.forEach(row => {
                if (itemInputType(row) === "数値") return;
                const key = `${state.currentMajor}|||${state.currentMinor}|||${row.category_major}|||${row.inspection_item}`;
                if (!state.inspectionResults[key]) {
                    state.inspectionResults[key] = { result: "", remark: "" };
                }
                state.inspectionResults[key].result = MARK_OK;
            });
            renderInspectionTable();
        });
    }
}

// ============================================================
// 月間点検表（使用前点検用）の丸対描画
// ============================================================
async function renderDailySummary() {
    const section = document.getElementById("daily-summary-section");
    if (state.currentMode !== "使用前") { section.style.display = "none"; return; }
    section.style.display = "block";
    // デバウンス：タブ連打時のAPI多重コールを抑制する
    if (renderDailySummary._timer) clearTimeout(renderDailySummary._timer);
    await new Promise(resolve => {
        renderDailySummary._timer = setTimeout(resolve, 150);
    });

    const [y, m] = state.targetYearMonth.split("-").map(Number);
    const { start, end } = getCalendarRange(state.targetYearMonth);
    const startStr = start.toLocaleDateString("sv-SE");
    const endStr = end.toLocaleDateString("sv-SE");
    const startYear = start.getFullYear(), startMonth = start.getMonth() + 1;

    // データ取得
    const [r1, r2, holidayList] = await Promise.all([
        fetchResults("使用前", startYear, startMonth).catch(() => []),
        startMonth !== m ? fetchResults("使用前", y, m).catch(() => []) : Promise.resolve([]),
        fetchHolidays(startStr, endStr).catch(() => [])
    ]);

    // 日付ごとの結果マップを作る（現在の大分類・小分類のレコードのみ使用する）
    const currentMajor = state.currentMajor;
    const currentMinor = state.currentMinor;
    // 現在表示中の設備の点検項目キー一覧（旧形式データとの照合用）
    const currentItems = getCurrentItems();
    const currentItemSet = new Set(currentItems.map(r => `${r.category_major}|${r.inspection_item}`));
    const resultByDate = {};
    [...r1, ...r2].forEach(rec => {
        const recMajor = rec.category_major || "";
        const recMinor = rec.category_minor || "";
        const isNewFormat = recMajor !== "" || recMinor !== "";
        if (isNewFormat) {
            // 新形式: category_major / category_minor が一致するレコードのみ対象
            if (recMajor !== currentMajor || recMinor !== currentMinor) return;
        } else {
            // 旧形式: 現在設備の点検項目を含むレコードのみ対象
            const hasMatchingItem = (rec.results || []).some(r =>
                currentItemSet.has(`${r.equipment_name}|${r.inspection_item}`)
            );
            if (!hasMatchingItem) return;
        }
        const d = rec.inspection_date;
        if (!resultByDate[d]) resultByDate[d] = { inspector: rec.inspector_name, generalRemark: rec.general_remark || "", byEquipItem: {} };
        (rec.results || []).forEach(r => {
            resultByDate[d].byEquipItem[`${r.equipment_name}|${r.inspection_item}`] = r.result;
        });
    });

    const holidayMap = {};
    holidayList.forEach(h => { holidayMap[h.date] = h; });

    // 日付一覧を生成する
    const dates = [];
    let cur = new Date(start);
    while (cur <= end) { dates.push(new Date(cur)); cur.setDate(cur.getDate() + 1); }

    // 現在の設備の点検項目を取得する
    const items = getCurrentItems();

    const weekNames = ["月", "火", "水", "木", "金", "土", "日"];

    // 休日情報（土日祝日など）で色のクラスを決定する
    const getDayCls = (dateStr) => {
        const h = holidayMap[dateStr] || {};
        if (h.is_saturday) return "summary-sat";
        if (h.is_sunday || h.is_holiday) return "summary-sun";
        if (h.is_custom_holiday) return "summary-cust";
        return "";
    };

    // 月グループ表示用 → 月グループ集計
    const monthGroups = {};
    dates.forEach(d => {
        const k = `${d.getFullYear()}-${d.getMonth() + 1}`;
        if (!monthGroups[k]) monthGroups[k] = { label: `${d.getMonth() + 1}月`, count: 0 };
        monthGroups[k].count++;
    });

    const thead = document.getElementById("daily-summary-thead");
    const tbody = document.getElementById("daily-summary-tbody");
    const titleEl = document.getElementById("daily-summary-title");
    // タイトルを大分類・小分類付きに表示する
    titleEl.textContent = `${start.getFullYear()}年${start.getMonth() + 1}月${start.getDate()}日 〜 ${y}年${m}月${end.getDate()}日　使用前点検表（${state.currentMajor} ${state.currentMinor}）`;

    // ヘッダ行1: 月名
    let row1 = `<tr><th rowspan="2" style="min-width:90px; background:#e0e8f0; text-align:left; padding:2px 4px;">点検項目</th>`;
    Object.values(monthGroups).forEach(g => {
        row1 += `<th colspan="${g.count}" style="background:#d0dce8; font-size:13px; padding:2px;text-align:center">${escapeHtml(g.label)}</th>`;
    });
    row1 += `</tr>`;

    // ヘッダ行2: 日付+曜日
    let row2 = `<tr>`;
    dates.forEach(d => {
        const ds = d.toLocaleDateString("sv-SE");
        const cls = getDayCls(ds);
        const isToday = (ds === today());
        const bg = isToday ? "#fff3cd" : "";
        row2 += `<th class="${cls}" style="font-size:12px; padding:2px 1px; text-align:center; min-width:28px;${bg ? 'background:' + bg + ';' : ''}">${d.getDate()}<br><small>${weekNames[d.getDay() === 0 ? 6 : d.getDay() - 1]}</small></th>`;
    });
    row2 += `</tr>`;
    thead.innerHTML = row1 + row2;

    // 本体行: 点検項目ごと
    let tbodyHTML = "";
    items.forEach(item => {
        const itemKey = `${item.category_major}|${item.inspection_item}`;
        let cells = "";
        dates.forEach(d => {
            const ds = d.toLocaleDateString("sv-SE");
            const cls = getDayCls(ds);
            const isToday = (ds === today());
            const bg = isToday ? "background:#fff3cd;" : "";
            const result = normalizeJudgment(resultByDate[ds]?.byEquipItem[itemKey] || "");
            const color = result === MARK_OK ? "color:#27ae60;"
                : isNgMark(result) ? "color:#e74c3c; font-weight:bold;" : "";
            cells += `<td class="${cls}" style="text-align:center; font-size:15px; padding:2px 1px;${bg}${color}">${escapeHtml(result)}</td>`;
        });
        tbodyHTML += `<tr><td style="text-align:left; padding:2px 4px; font-size:13px; white-space:nowrap;">${escapeHtml(item.inspection_item)}</td>${cells}</tr>`;
    });

    // 使用せず行：その日の24時を過ぎた（＝今日より前の）のに記録が無ければ✓。
    // 当日と未来の日は、まだ点検されうるので空欄のままにする。
    const todayStr = today();
    let unusedCells = "";
    dates.forEach(d => {
        const ds = d.toLocaleDateString("sv-SE");
        const cls = getDayCls(ds);
        const isToday = (ds === todayStr);
        const bg = isToday ? "background:#fff3cd;" : "";
        const mark = (!resultByDate[ds] && ds < todayStr) ? MARK_OK : "";
        unusedCells += `<td class="${cls}" style="text-align:center; font-size:15px; padding:2px 1px; color:#7f8c8d;${bg}">${escapeHtml(mark)}</td>`;
    });
    tbodyHTML += `<tr><td style="text-align:left; padding:2px 4px; font-size:13px; white-space:nowrap;">使用せず</td>${unusedCells}</tr>`;

    // 点検者行
    let inspCells = "";
    dates.forEach(d => {
        const ds = d.toLocaleDateString("sv-SE");
        const cls = getDayCls(ds);
        const isToday = (ds === today());
        const bg = isToday ? "background:#fff3cd;" : "";
        const inspector = resultByDate[ds]?.inspector || "";
        inspCells += `<td class="${cls}" style="text-align:center; vertical-align:top; padding:2px 0;${bg}"><span style="writing-mode:vertical-rl; font-size:12px; display:inline-block; white-space:nowrap;">${escapeHtml(inspector)}</span></td>`;
    });
    tbodyHTML += `<tr><td style="text-align:left; padding:2px 4px; font-size:13px;">点検者</td>${inspCells}</tr>`;

    // 備考行（特記事項を日付付きで統合表示する）
    const remarkTexts = [];
    dates.forEach(d => {
        const ds = d.toLocaleDateString("sv-SE");
        const remark = resultByDate[ds]?.generalRemark || "";
        if (remark.trim()) {
            remarkTexts.push(`${d.getFullYear()}/${d.getMonth()+1}/${d.getDate()}　${escapeHtml(remark)}`);
        }
    });
    const remarkContent = remarkTexts.length > 0 ? remarkTexts.join("<br>") : "特記事項なし";
    tbodyHTML += `<tr><td style="text-align:left; padding:2px 4px; font-size:13px; vertical-align:top;">備考</td>`
        + `<td colspan="${dates.length}" style="text-align:left; vertical-align:top; padding:6px 8px; font-size:12px; min-height:60px;">${remarkContent}</td></tr>`;

    tbody.innerHTML = tbodyHTML;

    // テーブルにスタイルを当てる
    const style = `
    #daily-summary-table th, #daily-summary-table td {
        border: 1px solid #ccc;
        vertical-align: middle;
    }
    #daily-summary-table .summary-sat { background: #cce5ff; }
    #daily-summary-table .summary-sun { background: #ffcccc; }
    #daily-summary-table .summary-cust { background: #ffe8b0; }
    `;
    let styleEl = document.getElementById("daily-summary-style");
    if (!styleEl) {
        styleEl = document.createElement("style");
        styleEl.id = "daily-summary-style";
        document.head.appendChild(styleEl);
    }
    styleEl.textContent = style;
}

// ============================================================
// 指定日の点検結果をAPIから読み込んでStateに展開
// ============================================================
async function loadInspectionResultsForDate(dateStr) {
    const [y, m] = dateStr.split("-").map(Number);
    try {
        const records = await fetchResults("使用前", y, m);
        const dayRecords = records.filter(r => r.inspection_date === dateStr);
        state.inspectionResults = {};
        state.inspectorsByEquipment = {};
        state.generalRemarks = {};
        state.currentInspectorJson = "";
        dayRecords.forEach(rec => {
            const inspectorJson = JSON.stringify({ name: rec.inspector_name, dept: rec.department || "" });
            // 大分類・小分類ごとのkeyでinspectorを保持する
            const equipKey = `${rec.category_major || ""}|${rec.category_minor || ""}`;
            if (rec.inspector_name && equipKey !== "|") {
                state.inspectorsByEquipment[equipKey] = inspectorJson;
            }
            if (rec.general_remark !== undefined && equipKey !== "|") {
                state.generalRemarks[equipKey] = rec.general_remark;
            }
            (rec.results || []).forEach(res => {
                const key = `${rec.category_major || ""}|||${rec.category_minor || ""}|||${res.equipment_name}|||${res.inspection_item}`;
                state.inspectionResults[key] = { result: res.result, remark: res.remark };
            });
        });
    } catch (e) {
        console.error("過去データの読み込みに失敗しました", e);
    }
    await loadPreviousValues();
}

// ============================================================
// 当日点検の完了確認
// ============================================================
async function checkDailyCompletion() {
    const todayStr = today();
    const [y, m] = todayStr.split("-").map(Number);
    try {
        const records = await fetchResults("使用前", y, m);
        const todaysRecords = records.filter(r => r.inspection_date === todayStr);
        state.todayCompleted = [];
        todaysRecords.forEach(rec => {
            // 大分類・小分類単位で完了を判定する
            const equipKey = `${rec.category_major || ""}|${rec.category_minor || ""}`;
            if (equipKey !== "|" && !state.todayCompleted.includes(equipKey)) {
                state.todayCompleted.push(equipKey);
            }
        });
    } catch { }
}

/** 月例点検の当月完了チェック */
async function checkMonthlyCompletion() {
    const [y, m] = state.targetYearMonth.split("-").map(Number);
    try {
        const records = await fetchResults("月例", y, m);
        state.monthlyCompleted = [];
        records.forEach(rec => {
            const equipKey = `${rec.category_major || ""}|${rec.category_minor || ""}`;
            if (equipKey !== "|" && !state.monthlyCompleted.includes(equipKey)) {
                state.monthlyCompleted.push(equipKey);
            }
        });
    } catch { }
}

/** 月例点検の当月結果をサーバーから読み込んでStateに展開 */
async function loadMonthlyResults() {
    const [y, m] = state.targetYearMonth.split("-").map(Number);
    try {
        const records = await fetchResults("月例", y, m);
        records.forEach(rec => {
            const maj = rec.category_major || "";
            const min_ = rec.category_minor || "";
            const equipKey = `${maj}|${min_}`;
            if (equipKey === "|") return;
            const inspectorJson = JSON.stringify({ name: rec.inspector_name || "", dept: rec.department || "" });
            if (rec.inspector_name) state.inspectorsByEquipment[equipKey] = inspectorJson;
            if (rec.general_remark !== undefined) state.generalRemarks[equipKey] = rec.general_remark;
            (rec.results || []).forEach(res => {
                const key = `${maj}|||${min_}|||${res.equipment_name}|||${res.inspection_item}`;
                state.inspectionResults[key] = { result: res.result || "", remark: res.remark || "" };
            });
        });
    } catch (e) {
        console.error("月例点検データの読み込みに失敗しました", e);
    }
}

// ============================================================
// 保存
// ============================================================
async function handleSave(fromTable = false) {
    // 大分類・小分類単位で完了判定する
    const currentEquipKey = `${state.currentMajor}|${state.currentMinor}`;
    if (state.currentMode === "使用前" && state.todayCompleted.includes(currentEquipKey)) {
        showStatus("本日の点検は既に完了しています", true);
        return;
    }
    if (state.currentMode === "月例" && state.monthlyCompleted.includes(currentEquipKey)) {
        showStatus("今月の点検は終了しました", true);
        return;
    }
    // テーブルフッターのセレクトを使用する
    const tblSel = document.getElementById("table-inspector-select");
    const inspectorJson = tblSel ? tblSel.value : "";
    if (!inspectorJson) {
        const msg = "点検者を選択してください";
        showStatus(msg, true);
        if (fromTable) {
            const st = document.getElementById("table-save-status");
            if (st) { st.textContent = msg; st.style.color = "#e74c3c"; }
        }
        return;
    }
    const inspector = JSON.parse(inspectorJson);
    const inspectionDate = state.currentMode === "使用前"
        ? today()
        : document.getElementById("inspection-date").value;
    if (!inspectionDate) { showStatus("点検日を選択してください", true); return; }

    // 現在表示中の設備（大分類・小分類）の結果のみに絞り込んで送信する
    const currentItemKeys = new Set(getCurrentItems().map(r =>
        `${state.currentMajor}|||${state.currentMinor}|||${r.category_major}|||${r.inspection_item}`
    ));
    const results = Object.entries(state.inspectionResults)
        .filter(([key]) => currentItemKeys.has(key))
        .map(([key, val]) => {
            const parts = key.split("|||");
            return { equipment_name: parts[2], inspection_item: parts[3], result: val.result, remark: val.remark };
        });

    // 全項目が入力されているか確認する（未操作の項目も含めてチェック）
    const hasEmpty = getCurrentItems().some(row => {
        const key = `${state.currentMajor}|||${state.currentMinor}|||${row.category_major}|||${row.inspection_item}`;
        return !state.inspectionResults[key]?.result;
    });
    if (hasEmpty) {
        const msg = "全て点検されていません";
        showStatus(msg, true);
        if (fromTable) {
            const st = document.getElementById("table-save-status");
            if (st) { st.textContent = msg; st.style.color = "#e74c3c"; }
        }
        return;
    }

    // 月例点検はtargetYearMonthのファイルに保存する（inspection_dateの月とずれる場合がある）
    const [ty, tm] = state.targetYearMonth.split("-").map(Number);

    try {
        await postResults({
            inspection_type: state.currentMode,
            inspection_date: inspectionDate,
            display_year: state.currentMode === "月例" ? ty : undefined,
            display_month: state.currentMode === "月例" ? tm : undefined,
            inspector_name: inspector.name,
            department: inspector.dept,
            category_major: state.currentMajor,
            category_minor: state.currentMinor,
            general_remark: state.generalRemarks[currentEquipKey] || "",
            results
        });
        // 保存成功時に設備単位のinspectorを記録する
        state.inspectorsByEquipment[currentEquipKey] = inspectorJson;
        const msg = "✓ 保存しました";
        showStatus(msg);
        if (fromTable) {
            const st = document.getElementById("table-save-status");
            if (st) {
                st.textContent = msg; st.style.color = "#27ae60";
                setTimeout(() => { if (st) st.textContent = ""; }, 4000);
            }
        }
        // 現在の設備の結果に不合格（要調整・修理・要取替）があればアラートを表示する
        const ngCounts = NG_MARKS
            .map(m => ({
                label: m.label,
                mark: m.mark,
                count: results.filter(r => normalizeJudgment(r.result) === m.mark).length,
            }))
            .filter(m => m.count > 0);
        const hasNg = ngCounts.length > 0;

        if (state.currentMode === "使用前") {
            if (!state.todayCompleted.includes(currentEquipKey)) {
                state.todayCompleted.push(currentEquipKey);
            }
            renderInspectionTable();
            await renderDailySummary();
            if (hasNg) { showNgAlert(ngCounts); }
        }
        if (state.currentMode === "月例") {
            if (!state.monthlyCompleted.includes(currentEquipKey)) {
                state.monthlyCompleted.push(currentEquipKey);
            }
            renderInspectionTable();
            if (hasNg) { showNgAlert(ngCounts); }
        }
    } catch (e) {
        showStatus(`❌ ${e.message}`, true);
    }
}



// ============================================================
// PDF出力
// ============================================================
async function handlePdfExport() {
    const [y, m] = state.targetYearMonth.split("-").map(Number);

    // 使用前点検の全設備が一度でも点検されているか確認する
    const dailyEquipKeys = [...new Set(
        state.equipmentData
            .filter(r => r.inspection_type === "使用前" || r.inspection_type === "両方")
            .map(r => `${r.category_major}|${r.category_minor}`)
    )];
    const prevM = m === 1 ? 12 : m - 1;
    const prevY = m === 1 ? y - 1 : y;
    const [dailyRec1, dailyRec2] = await Promise.all([
        fetchResults("使用前", prevY, prevM).catch(() => []),
        fetchResults("使用前", y, m).catch(() => [])
    ]);
    const inspectedKeys = new Set(
        [...dailyRec1, ...dailyRec2].map(r => `${r.category_major}|${r.category_minor}`)
    );
    const neverInspected = dailyEquipKeys.filter(k => !inspectedKeys.has(k));
    if (neverInspected.length > 0) {
        const names = neverInspected.map(k => k.replace("|", " ")).join("、");
        alert(`一度も使用前点検をしていない設備があります\n対象: ${names}`);
        return;
    }

    // 月例点検の全設備が完了しているか確認する
    const monthlyEquipKeys = [...new Set(
        state.equipmentData
            .filter(r => r.inspection_type === "月例" || r.inspection_type === "両方")
            .map(r => `${r.category_major}|${r.category_minor}`)
    )];
    await checkMonthlyCompletion();
    const incomplete = monthlyEquipKeys.filter(k => !state.monthlyCompleted.includes(k));
    if (incomplete.length > 0) {
        const names = incomplete.map(k => k.replace("|", " ")).join("、");
        alert(`月例点検が全て終わっていません。\n未完了: ${names}`);
        return;
    }

    // PDFダウンロード
    const a = document.createElement("a");
    a.href = `/api/pdf?display_year=${y}&display_month=${m}`;
    a.target = "_blank";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    // 特記事項CSVダウンロード
    const csvA = document.createElement("a");
    csvA.href = `/api/remarks_csv?display_year=${y}&display_month=${m}`;
    csvA.download = `remarks_${y}${String(m).padStart(2,"0")}.csv`;
    document.body.appendChild(csvA);
    csvA.click();
    document.body.removeChild(csvA);
}

// ============================================================
// 点検モード切り替え
// ============================================================
function switchMode(mode) {
    state.currentMode = mode;
    state.currentMajor = "";
    state.currentMinor = "";
    state.inspectionResults = {};
    state.generalRemarks = {};
    state.currentInspectorJson = "";
    document.querySelectorAll(".mode-tab").forEach(t => {
        t.classList.toggle("active", t.dataset.mode === mode);
    });
    const dateInput = document.getElementById("inspection-date");
    dateInput.value = today();
    dateInput.disabled = (mode === "使用前");

    // 使用前・月例共通で大分類・小分類タブを描画する
    renderMajorTabs();
    renderMinorTabs();
    renderInspectionTable();
    renderDailySummary();

    // 月例モードに切り替えた際はサーバーから既存の結果を読み込む
    if (mode === "月例") {
        loadMonthlyResults().then(() => renderInspectionTable());
    }
}

// ============================================================
// 設定モーダル
// ============================================================

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
    const minors = [...new Set(
        state.equipmentData.map(r => r.category_minor).filter(m => m))];
    const withForm = minors.filter(m => assignments[m]);
    const withoutForm = minors.filter(m => !assignments[m]);
    // 同じ機器が複数の様式に載っていると同じ結果が2枚に印字される。気づけるよう目立たせる。
    const duplicated = withForm.filter(m => assignments[m].length > 1);

    const formLines = withForm.map(m => {
        const forms = escapeHtml(assignments[m].join(", "));
        const warn = assignments[m].length > 1
            ? ' <span style="color:#c62828;">⚠ 複数の様式に載っています</span>' : "";
        return `${escapeHtml(m)} → ${forms}${warn}`;
    }).join("<br>") || "（なし）";

    el.innerHTML =
        `<div><strong>様式PDFに出力（${withForm.length}件）</strong><br>${formLines}</div>`
        + `<div style="margin-top:8px;"><strong>表で出力（${withoutForm.length}件）</strong><br>`
        + (withoutForm.map(escapeHtml).join(" / ") || "（なし）") + "</div>"
        + (duplicated.length
            ? `<div style="margin-top:8px; color:#c62828;">${duplicated.length}件の機器が複数の様式に紐づいています。同じ結果が複数の様式に印字されます。</div>`
            : "");
}

/** 様式の並び順を描く。画面に出ている順が、そのままPDFの順になる。 */
async function renderFormOrder() {
    const el = document.getElementById("cfg-form-order");
    if (!el) return;
    el.textContent = "読み込み中...";
    let forms = [];
    try {
        forms = await fetchJson("/api/forms");
    } catch (e) {
        el.textContent = "様式の情報を取得できませんでした";
        return;
    }
    if (!forms.length) {
        el.textContent = "様式がありません";
        return;
    }
    // 設定に無い様式は、指定した様式のあとに元の順で続ける（サーバー側と同じ規則）
    // 手編集で配列以外が入っていることがある。サーバー側と同じく無視する。
    const rawOrder = state.config && state.config.form_order;
    const saved = Array.isArray(rawOrder) ? rawOrder : [];
    const byId = new Map(forms.map(f => [f.id, f]));
    const ordered = [];
    const used = new Set();
    for (const id of saved) {
        if (!byId.has(id) || used.has(id)) continue;
        used.add(id);
        ordered.push(byId.get(id));
    }
    for (const f of forms) {
        if (!used.has(f.id)) ordered.push(f);
    }
    el.innerHTML = ordered.map((f, i) => `
      <div class="form-order-row" data-id="${escapeHtml(f.id)}"
           style="display:flex; align-items:center; gap:6px; padding:2px 0;">
        <span style="flex:1">${escapeHtml(f.form_name)}（${escapeHtml(f.id)}）</span>
        <button type="button" class="fo-up" ${i === 0 ? "disabled" : ""}>▲</button>
        <button type="button" class="fo-down"
                ${i === ordered.length - 1 ? "disabled" : ""}>▼</button>
      </div>`).join("");

    el.querySelectorAll(".fo-up, .fo-down").forEach(btn => {
        btn.addEventListener("click", () => {
            const row = btn.closest(".form-order-row");
            const other = btn.classList.contains("fo-up")
                ? row.previousElementSibling : row.nextElementSibling;
            if (!other) return;
            if (btn.classList.contains("fo-up")) row.parentNode.insertBefore(row, other);
            else row.parentNode.insertBefore(other, row);
            refreshFormOrderButtons(el);
        });
    });
}

/** 端の行のボタンを押せなくする（入れ替えるたびに付け直す） */
function refreshFormOrderButtons(el) {
    const rows = [...el.querySelectorAll(".form-order-row")];
    rows.forEach((row, i) => {
        row.querySelector(".fo-up").disabled = (i === 0);
        row.querySelector(".fo-down").disabled = (i === rows.length - 1);
    });
}

/** アプリのバージョンを出す。版数の出どころはサーバーの APP_VERSION だけ。 */
async function renderAppVersion() {
    // 設定画面の左下と、左側の欄のいちばん下の2か所に出す
    const els = ["cfg-app-version", "sb-app-version"]
        .map(id => document.getElementById(id)).filter(Boolean);
    if (!els.length) return;
    let text = "";
    try {
        const info = await fetchJson("/api/health");
        text = info.version ? `Ver ${info.version}` : "";
    } catch (e) {
        // 取れなくても画面は使えるので、黙って空のままにする
    }
    els.forEach(el => { el.textContent = text; });
}

/** 画面に出ている順の様式IDを返す。まだ描けていなければ null。
 *
 *  null のときは保存時に form_order を送らない。空配列を送ると、
 *  サーバーが「並び順なし」として保存し、前の並びが黙って消える。
 */
function currentFormOrder() {
    const el = document.getElementById("cfg-form-order");
    if (!el) return null;
    const rows = [...el.querySelectorAll(".form-order-row")];
    return rows.length ? rows.map(r => r.dataset.id) : null;
}

function openSettings() {
    const bi = state.config.building_info || {};
    document.getElementById("cfg-save-dir").value = state.config.save_directory || "";
    document.getElementById("cfg-forms-dir").value = state.config.forms_directory || "";
    // 既存の設定ファイルにキーが無い場合があるので、その時は既定の24を表示する
    document.getElementById("cfg-cycle-start-day").value =
        state.config.cycle_start_day || 24;
    renderFormAssignments();
    renderFormOrder();
    renderAppVersion();
    document.getElementById("cfg-building-name").value = bi.building_name || "";
    const managers = bi.managers || [{}, {}, {}];
    [0, 1, 2].forEach(i => {
        const m = managers[i] || {};
        document.getElementById(`cfg-mgr-${i}-title`).value = m.title || "";
        document.getElementById(`cfg-mgr-${i}-name`).value = m.name || "";
        document.getElementById(`cfg-mgr-${i}-phone_int`).value = m.phone_int || "";
        document.getElementById(`cfg-mgr-${i}-phone_ext`).value = m.phone_ext || "";
    });
    // サイネージ・文書掲示の設定はサイネージ画面（⚙）に移したので、ここでは扱わない
    // リモートアクセス時のみ管理者キー入力欄を表示
    const isRemote = !["localhost", "127.0.0.1", "::1"].includes(location.hostname);
    const adminKeyRow = document.getElementById("cfg-admin-key-row");
    if (adminKeyRow) adminKeyRow.style.display = isRemote ? "" : "none";
    document.getElementById("settings-overlay").classList.add("open");
}

function closeSettings() {
    document.getElementById("settings-overlay").classList.remove("open");
}

async function handleSettingsSave() {
    const managers = [0, 1, 2].map(i => ({
        title: document.getElementById(`cfg-mgr-${i}-title`).value.trim(),
        name: document.getElementById(`cfg-mgr-${i}-name`).value.trim(),
        phone_int: document.getElementById(`cfg-mgr-${i}-phone_int`).value.trim(),
        phone_ext: document.getElementById(`cfg-mgr-${i}-phone_ext`).value.trim()
    }));
    // 送るのは機器点検に関する設定だけ。サイネージ・文書掲示の設定は
    // サイネージ画面が持っており、送らなければサーバー側でそのまま残る。
    const payload = {
        save_directory: document.getElementById("cfg-save-dir").value.trim(),
        forms_directory: document.getElementById("cfg-forms-dir").value.trim(),
        cycle_start_day:
            Number(document.getElementById("cfg-cycle-start-day").value) || 24,
        building_info: {
            building_name: document.getElementById("cfg-building-name").value.trim(),
            managers
        },
    };
    // 一覧をまだ描けていないときは送らない。空配列を送ると、
    // サーバーが前の並び順を消してしまう。
    const formOrder = currentFormOrder();
    if (formOrder) payload.form_order = formOrder;
    const statusEl = document.getElementById("cfg-save-status");
    if (statusEl) { statusEl.style.display = "none"; statusEl.textContent = ""; }
    try {
        await postConfig(payload);
        state.config = await fetchConfig();
        updateSidebar(state.config);
        closeSettings();
        showStatus("✓ 設定を保存しました");
    } catch (e) {
        if (statusEl) {
            statusEl.style.display = "block";
            statusEl.textContent = e.message;
            statusEl.style.color = "#c62828";
        }
        showStatus(`❌ ${e.message}`, true);
    }
}

// ============================================================
// 年月変更
// ============================================================
function handleMonthChange(val) {
    state.targetYearMonth = val;
    state.inspectionResults = {};
    updateSidebar(state.config);
    renderDailySummary();
    if (state.currentMode === "月例") {
        loadMonthlyResults().then(() => renderInspectionTable());
    }
}

// ============================================================
// 初期化
// ============================================================
async function initApp() {
    startClock();
    renderAppVersion();

    const todayStr = today();
    document.getElementById("inspection-date").value = todayStr;
    document.getElementById("inspection-date").disabled = true; // 使用前点検は当日固定
    document.getElementById("target-month").value = state.targetYearMonth;

    try {
        const [equipment, inspectors, config] = await Promise.all([
            fetchEquipment(), fetchInspectors(), fetchConfig()
        ]);
        state.equipmentData = equipment;
        state.inspectorList = inspectors;
        state.config = config;
        const cfgDay = Number(state.config.cycle_start_day);
        if (Number.isInteger(cfgDay) && cfgDay >= 1 && cfgDay <= 31) {
            cycleStartDay = cfgDay;
            // 締め日が既定と違う場合は表示月を計算し直す
            state.targetYearMonth = getDefaultTargetMonth();
            document.getElementById("target-month").value = state.targetYearMonth;
        }
        updateSidebar(config);
        await checkDailyCompletion();
        await checkMonthlyCompletion();
        await loadInspectionResultsForDate(todayStr); // 初期表示時に当日の結果をロード
        renderMajorTabs();
        renderMinorTabs();
        renderInspectionTable();
        await renderDailySummary();
    } catch (e) {
        showStatus(`❌ 初期化エラー: ${e.message}`, true);
    }
}

// ============================================================
// イベントリスナー
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".mode-tab").forEach(t =>
        t.addEventListener("click", () => switchMode(t.dataset.mode))
    );
    document.getElementById("btn-pdf").addEventListener("click", handlePdfExport);
    document.getElementById("btn-settings").addEventListener("click", openSettings);
    document.getElementById("btn-settings-cancel").addEventListener("click", closeSettings);
    document.getElementById("btn-settings-save").addEventListener("click", handleSettingsSave);
    // 入力欄から始まったドラッグ（文字選択）で誤って閉じないよう、
    // マウスを「押した場所」も背景だったときだけ閉じる
    const settingsOverlay = document.getElementById("settings-overlay");
    let settingsOverlayPressed = false;
    settingsOverlay.addEventListener("mousedown", e => {
        settingsOverlayPressed = (e.target === settingsOverlay);
    });
    settingsOverlay.addEventListener("click", e => {
        if (e.target === settingsOverlay && settingsOverlayPressed) closeSettings();
    });
    document.getElementById("target-month").addEventListener("change", e => handleMonthChange(e.target.value));

    // 数字キー（1〜9）で点検者をショートカット選択、*で全て✓
    document.addEventListener("keydown", e => {
        // テキスト入力中・設定モーダル表示中は無視する
        if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
        if (document.getElementById("settings-overlay").classList.contains("open")) return;

        // *キー：使用前点検の現在の設備の判定項目を全て✓（良）にする。
        // 数値項目は測った値を入れる欄なので触らない。
        if (e.key === "*" && state.currentMode === "使用前") {
            const rows = getCurrentItems();
            rows.forEach(row => {
                if (itemInputType(row) === "数値") return;
                const key = `${state.currentMajor}|||${state.currentMinor}|||${row.category_major}|||${row.inspection_item}`;
                if (!state.inspectionResults[key]) state.inspectionResults[key] = { result: "", remark: "" };
                state.inspectionResults[key].result = MARK_OK;
            });
            renderInspectionTable();
            return;
        }

        const num = parseInt(e.key);
        if (isNaN(num) || num < 1) return;

        const inspector = state.inspectorList[num - 1];
        if (!inspector) return;

        const deptSelect = document.getElementById("table-dept-select");
        const inspSelect = document.getElementById("table-inspector-select");
        if (!deptSelect || !inspSelect) return;

        // 部署を設定して氏名リストを更新する
        deptSelect.value = inspector.department;
        deptSelect.dispatchEvent(new Event("change"));

        // 氏名を設定する
        const val = JSON.stringify({ name: inspector.inspector_name, dept: inspector.department });
        inspSelect.value = val;
        state.currentInspectorJson = val;

        // 選択した点検者名をフィードバック表示する
        const st = document.getElementById("table-save-status");
        if (st) {
            st.textContent = `点検者：${inspector.inspector_name}`;
            st.style.color = "#1a3a5c";
            setTimeout(() => { if (st) st.textContent = ""; }, 2000);
        }
    });

    initApp().then(() => {
        if (!window.INSPECTION_ONLY) {
            initIdleDetection(state.config);
        }
        if (new URLSearchParams(location.search).get("settings") === "1") {
            openSettings();
        }
    });
});

// ============================================================
// アイドル検知（操作なし時にサイネージへ自動遷移）
// ============================================================
function initIdleDetection(config) {
    const sg = (config && config.signage) ? config.signage : {};
    const idleSecs = parseInt(sg.idle_return_seconds) || 60;
    let lastActivity = Date.now();

    function resetActivity() {
        lastActivity = Date.now();
    }

    // ユーザー操作を検知してタイマーリセット
    ["mousemove", "mousedown", "keydown", "touchstart", "click", "scroll"].forEach(ev => {
        document.addEventListener(ev, resetActivity, { passive: true });
    });

    // 設定モーダルが開いている間は遷移しない
    setInterval(() => {
        if (document.getElementById("settings-overlay").classList.contains("open")) {
            resetActivity();
            return;
        }
        if (Date.now() - lastActivity >= idleSecs * 1000) {
            window.location.href = "/";
        }
    }, 5000);
}


