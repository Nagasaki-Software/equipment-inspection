import * as pdfjsLib from "/pdfjs/pdf.mjs";
pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.mjs";

const params = new URLSearchParams(location.search);
const categoryId = params.get("category_id") || "";
const file = params.get("file") || "";
const label = params.get("label") || file.replace(/\.pdf$/i, "");

document.title = label;
const titleEl = document.getElementById("viewer-title");
if (titleEl) titleEl.textContent = label;

const backBtn = document.getElementById("btn-back");
if (backBtn) {
    backBtn.href = "/documents/list?" + new URLSearchParams({ category_id: categoryId, label }).toString();
}

let pdfDoc = null;
let currentPage = 1;
let zoomFactor = 1.0;
const DRAG_THRESHOLD = 80;

const canvas = document.getElementById("pdf-canvas");
const ctx = canvas.getContext("2d");

function getFitZoom(page) {
    const container = document.getElementById("viewer-main");
    const vp = page.getViewport({ scale: 1.0 });
    if (vp.width === 0 || vp.height === 0) return 1.0;
    return Math.min(container.clientWidth / vp.width, container.clientHeight / vp.height) * 0.95;
}

let isRendering = false;
let pendingPage = null;
async function renderPage(num) {
    if (!pdfDoc) return;
    if (isRendering) { pendingPage = num; return; }
    isRendering = true;
    try {
        const page = await pdfDoc.getPage(num);
        const scale = getFitZoom(page) * zoomFactor;
        const viewport = page.getViewport({ scale });
        const dpr = window.devicePixelRatio || 1;
        canvas.width = viewport.width * dpr;
        canvas.height = viewport.height * dpr;
        canvas.style.width = viewport.width + "px";
        canvas.style.height = viewport.height + "px";
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        await page.render({ canvasContext: ctx, viewport }).promise;
        const el = document.getElementById("page-counter");
        if (el) el.textContent = currentPage + " / " + pdfDoc.numPages;
        try { page.cleanup(); } catch (_) {}
    } finally {
        isRendering = false;
        if (pendingPage !== null) {
            const p = pendingPage;
            pendingPage = null;
            renderPage(p);
        }
    }
}

function goNext() {
    if (pdfDoc && currentPage < pdfDoc.numPages) { currentPage++; renderPage(currentPage); }
}
function goPrev() {
    if (pdfDoc && currentPage > 1) { currentPage--; renderPage(currentPage); }
}

// ナビゲーションボタン
document.getElementById("viewer-btn-prev").addEventListener("click", goPrev);
document.getElementById("viewer-btn-next").addEventListener("click", goNext);

// マウスドラッグ（ページ送り）
let dragStartX = null;
let dragStartY = null;
canvas.addEventListener("mousedown", e => { dragStartX = e.clientX; dragStartY = e.clientY; });
canvas.addEventListener("mouseup", e => {
    if (dragStartX === null) return;
    const dx = e.clientX - dragStartX;
    const dy = e.clientY - dragStartY;
    dragStartX = null;
    dragStartY = null;
    if (Math.abs(dx) > DRAG_THRESHOLD && Math.abs(dx) > Math.abs(dy)) {
        if (dx < 0) goNext(); else goPrev();
    }
});

// タッチ（スワイプ・ピンチ統合）
let touchStartX = null;
let touchStartY = null;
let pinchDist = null;

canvas.addEventListener("touchstart", e => {
    e.preventDefault();
    if (e.touches.length === 1) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        pinchDist = null;
    } else if (e.touches.length === 2) {
        touchStartX = null;
        touchStartY = null;
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        pinchDist = Math.sqrt(dx * dx + dy * dy);
    }
});

canvas.addEventListener("touchmove", e => {
    e.preventDefault();
    if (e.touches.length !== 2 || !pinchDist) return;
    const dx = e.touches[0].clientX - e.touches[1].clientX;
    const dy = e.touches[0].clientY - e.touches[1].clientY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    // スケール計算のみ行い、レンダリングはtouchendで実行する
    zoomFactor = Math.max(0.2, Math.min(6.0, zoomFactor * dist / pinchDist));
    pinchDist = dist;
});

canvas.addEventListener("touchend", e => {
    e.preventDefault();
    const wasPinch = pinchDist !== null;
    pinchDist = null;
    if (wasPinch) {
        // ピンチ操作完了時に1回だけレンダリングする
        renderPage(currentPage);
        return;
    }
    if (touchStartX === null) return;
    const dx = e.changedTouches[0].clientX - touchStartX;
    const dy = e.changedTouches[0].clientY - touchStartY;
    touchStartX = null;
    touchStartY = null;
    if (Math.abs(dx) > DRAG_THRESHOLD && Math.abs(dx) > Math.abs(dy)) {
        if (dx < 0) goNext(); else goPrev();
    }
});

// ホイールズーム
canvas.addEventListener("wheel", e => {
    e.preventDefault();
    zoomFactor = e.deltaY < 0
        ? Math.min(zoomFactor * 1.1, 6.0)
        : Math.max(zoomFactor * 0.9, 0.2);
    renderPage(currentPage);
}, { passive: false });

// リサイズ（デバウンス付き）
let resizeTimer = null;
window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderPage(currentPage), 300);
});

// ページ離脱時にPDFドキュメントを破棄（メモリリーク防止）
window.addEventListener("beforeunload", () => {
    if (pdfDoc) {
        try { pdfDoc.destroy(); } catch (_) {}
        pdfDoc = null;
    }
});

// PDF読み込み
if (!categoryId || !file) {
    document.getElementById("viewer-error").style.display = "block";
} else {
    (async () => {
        try {
            const url = "/api/documents/pdf/" + encodeURIComponent(file)
                + "?category_id=" + encodeURIComponent(categoryId);
            pdfDoc = await pdfjsLib.getDocument({
                url,
                cMapUrl: "/pdfjs/cmaps/",
                cMapPacked: true,
            }).promise;
            await renderPage(1);
        } catch (e) {
            console.error("PDF load error:", e);
            document.getElementById("viewer-error").style.display = "block";
        }
    })();
}
