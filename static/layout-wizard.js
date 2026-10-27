/** 様式追加ウィザード。
 *
 *  prompt() の連続だと、途中で戻れず、何を入力すればよいかも分からない。
 *  4手順の画面にして、進める条件を満たすまで「次へ」を押せなくする。
 */
import * as pdfjsLib from '/pdfjs/pdf.mjs';

const $ = id => document.getElementById(id);

const STEP_COUNT = 4;
const MAX_PDF_BYTES = 50 * 1024 * 1024;

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
let lastDoc = null;   // 直前に読み込んだPDF（pdf.js）。差し替え時に破棄してメモリを解放する

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

/** 送信中に操作されないよう、下部のボタンをまとめて止める */
function setFootEnabled(enabled) {
    $("wizard-next").disabled = !enabled;
    $("wizard-back").disabled = !enabled;
    $("wizard-cancel").disabled = !enabled;
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

function escapeAttr(s) {
    return escapeText(s).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

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

/** 付けられるフォルダ名（様式ID）。layout.js と同じ規則で決める。 */
function nextIdPreview() {
    const used = new Set(existingIds);
    for (let n = 1; n <= 9999; n++) {
        const id = n < 100 ? `form_${String(n).padStart(2, "0")}` : `form_${n}`;
        if (!used.has(id)) return id;
    }
    return "form_9999";
}

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
    // 前回読み込んだPDFが残っていると解放されないので、差し替え前に破棄する
    if (lastDoc) { try { await lastDoc.destroy(); } catch (e) { /* 破棄できなくても続ける */ } }
    lastDoc = doc;
    draft.file = file;
    draft.pageCount = doc.numPages;
    await showAcceptedFile(doc);
    renderFoot();
}

/** 受け入れたPDFの1ページ目を小さく描いて確認させる */
async function showAcceptedFile(doc) {
    const box = $("pdf-check");
    if (!box) return;
    box.innerHTML = `<div><b>${escapeText(draft.file.name)}</b><br>${draft.pageCount} ページ</div>`;
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

function escapeText(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderStep() {
    showError("");
    if (step === 1) renderStep1();
    else if (step === 2) renderStep2();
    else if (step === 3) renderStep3();
    else if (step === 4) renderStep4();
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
    setFootEnabled(true);
    if (lastDoc) { lastDoc.destroy().catch(() => { /* 破棄できなくても続ける */ }); lastDoc = null; }
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

/** 手順4まで終わったら、様式を作る */
async function submit() {
    showError("");
    // 送信中に「やめる」を押されると、通信は止まらないのに画面だけ閉じてしまい、
    // 様式フォルダだけができた状態になる。終わるまで操作させない。
    setFootEnabled(false);
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
        setFootEnabled(true);
        return;
    }
    if (res.status === 401) {
        showError("様式の作成には管理者権限が必要です。"
            + "アプリを動かしているPCで操作してください。");
        setFootEnabled(true);
        return;
    }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        // 別の人が先に様式を作っていると、同じIDで作ろうとして失敗し続ける。
        // 一覧を取り直して、次の空き番号から作れるようにする。
        try {
            const forms = await (await fetch("/api/forms")).json();
            existingIds = forms.map(f => f.id);
        } catch (e) { /* 取れなくても、元のエラーは表示する */ }
        showError((err.error || `作成に失敗しました（${res.status}）`)
            + "　もう一度「この内容で作成」を押すと、別のフォルダ名でやり直します。");
        setFootEnabled(true);
        return;
    }
    close(formId);
}
