/**
 * デジタルサイネージ - フロントエンドロジック
 * 長期安定稼働対応版 v2
 */
import * as pdfjsLib from '/pdfjs/pdf.mjs';
pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdfjs/pdf.worker.mjs';

// ============================================================
// 設定・状態
// ============================================================
const Signage = {
    config: {
        displayMs: 10000,
        sleepStart: "18:00",
        sleepEnd: "08:00",
        newsSpeed: 100,
    },
    files: [],
    newsItems: [],
    newsAnim: null,
    newsRefreshTimerId: null,
    currentFileIdx: 0,
    currentPage: 1,
    totalPages: 0,
    mediaKind: "pdf",          // 表示中のファイルの種類: "pdf" | "video" | "image"
    soundUnlocked: false,      // 利用者が「音を出す」を押したか
    videoWatchdogId: null,     // 動画が固まったときに次へ進めるための監視
    videoLastProgress: 0,      // 動画が最後に進んだ時刻
    pdfDoc: null,
    preloadDoc: null,
    preloadFilename: null,
    rendering: false,
    sleeping: false,
    sleepDismissedAt: 0,       // ユーザーがスリープを解除した時刻
    autoAdvanceTimer: null,    // 次スライドへのsetTimeoutのID
    progressIntervalId: null,  // 進捗バー更新用setIntervalのID
    sleepClockId: null,
    fileRefreshTimerId: null,
    slideStartTime: 0,         // 進捗バー計算用
    swipeStartX: 0,
    swipeActive: false,
};

// ============================================================
// 初期化
// ============================================================
async function initSignage() {
    await loadConfig();
    await refreshFileList();
    setupEventListeners();
    startProgressLoop();
    startSleepClock();
    initNewsTicker();

    // ファイルリストを5分ごとに更新
    Signage.fileRefreshTimerId = setInterval(async () => {
        const prevFiles = Signage.files.slice();
        await refreshFileList();
        const changed = JSON.stringify(prevFiles) !== JSON.stringify(Signage.files);
        if (changed) {
            console.log("ファイルリスト更新:", Signage.files);
            // プリロード済みファイルがリストから消えた場合は破棄
            if (Signage.preloadDoc && !Signage.files.includes(Signage.preloadFilename)) {
                try { Signage.preloadDoc.destroy(); } catch (_) {}
                Signage.preloadDoc = null;
                Signage.preloadFilename = null;
            }
            if (Signage.files.length === 0) {
                cancelAutoAdvance();
                showNoPdfMsg();
            }
        }
    }, 5 * 60 * 1000);

    if (Signage.files.length > 0) {
        await loadAndRenderCurrent();
    } else {
        showNoPdfMsg();
    }
}

// ============================================================
// 設定読み込み
// ============================================================
async function loadConfig() {
    try {
        const res = await fetch("/api/config");
        if (!res.ok) return;
        const cfg = await res.json();
        const sg = cfg.signage || {};
        const secs = parseInt(sg.display_seconds) || 10;
        Signage.config.displayMs = Math.max(3, secs) * 1000;
        Signage.config.sleepStart = sg.sleep_start || "18:00";
        Signage.config.sleepEnd = sg.sleep_end || "08:00";
        Signage.config.folderPath = sg.folder_path || "";
        Signage.config.idleReturnSeconds = sg.idle_return_seconds || 60;
        Signage.config.newsSpeed = Math.max(20, parseInt(sg.news_speed) || 100);
        Signage.config.webMaxStaySeconds = Math.max(60, parseInt(sg.web_max_stay_seconds) || 300);
        Signage.config.webPages = cfg.web_pages || [];
        // 文書掲示の設定。画面表示には使わないが、設定パネルで編集するため保持する
        Signage.config.documentCategories =
            cfg.document_categories || { button_count: 3, categories: [] };
        updateNavButtons();
    } catch (e) {
        console.warn("設定読み込みエラー:", e);
    }
}

// ============================================================
// ファイルリスト更新
// ============================================================
async function refreshFileList() {
    try {
        const res = await fetch("/api/signage/files");
        if (!res.ok) return;
        const list = await res.json();
        Signage.files = Array.isArray(list) ? list : [];
    } catch (e) {
        console.warn("ファイルリスト取得エラー:", e);
    }
}

// ============================================================
// ニューステロップ（PDF表示・ページ送りとは独立して動作する）
// ============================================================
async function refreshNews() {
    try {
        const res = await fetch("/api/signage/news");
        if (!res.ok) return;
        const list = await res.json();
        Signage.newsItems = Array.isArray(list) ? list : [];
    } catch (e) {
        console.warn("ニュース取得エラー:", e);
        Signage.newsItems = [];
    }
}

function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** 1項目を整形。"..." で囲まれた部分はジャンルバッジ（オレンジ長円＋黒文字）にする */
function formatNewsItem(text) {
    // "..." を境界として分割（キャプチャグループで区切り文字も残す）
    return text.split(/("[^"]*")/g).map(part => {
        const m = /^"([^"]*)"$/.exec(part);
        if (m) {
            return `<span class="news-badge">${escapeHtml(m[1])}</span>`;
        }
        return escapeHtml(part);
    }).join("");
}

function buildNewsHtml() {
    if (!Signage.newsItems || Signage.newsItems.length === 0) {
        return escapeHtml("ニュースはありません");
    }
    return Signage.newsItems.map(formatNewsItem).join("　　　　");
}

/** ニューステロップのスクロールを（再）開始する。速度・内容・幅の変更時に呼ぶ */
function startMarquee() {
    const track = document.getElementById("news-track");
    const scroll = document.getElementById("news-scroll");
    if (!track || !scroll) return;

    // 既存のアニメーションを停止
    if (Signage.newsAnim) {
        try { Signage.newsAnim.cancel(); } catch (_) {}
        Signage.newsAnim = null;
    }

    track.innerHTML = buildNewsHtml();

    const containerW = scroll.clientWidth;
    const trackW = track.scrollWidth;
    if (containerW === 0) {
        // レイアウト未確定時は少し待って再試行
        setTimeout(startMarquee, 200);
        return;
    }

    const speed = Math.max(20, Signage.config.newsSpeed || 100); // px/秒
    const distance = containerW + trackW;
    const durationMs = (distance / speed) * 1000;

    Signage.newsAnim = track.animate(
        [
            { transform: `translateX(${containerW}px)` },
            { transform: `translateX(${-trackW}px)` },
        ],
        { duration: durationMs, iterations: Infinity, easing: "linear" }
    );
}

async function initNewsTicker() {
    await refreshNews();
    startMarquee();
    // テキストファイルの変更を素早く反映するため15秒ごとに確認する。
    // 内容に変化があったときだけテロップを作り直す（変化なしならスクロールは途切れない）。
    Signage.newsRefreshTimerId = setInterval(async () => {
        const prev = JSON.stringify(Signage.newsItems);
        await refreshNews();
        if (JSON.stringify(Signage.newsItems) !== prev) {
            startMarquee();
        }
    }, 15 * 1000);
}

// ============================================================
// PDF読み込みとレンダリング
// ============================================================
async function loadAndRenderCurrent() {
    if (Signage.files.length === 0) {
        showNoPdfMsg();
        return;
    }

    // インデックスの範囲チェック
    if (Signage.currentFileIdx >= Signage.files.length) {
        Signage.currentFileIdx = 0;
    }

    const filename = Signage.files[Signage.currentFileIdx];
    hidNoPdfMsg();
    // 前のファイルが動画だったときは、音が残らないよう必ず止める
    if (Signage.mediaKind === "video") stopVideo();
    await loadPdf(filename);
}

/** ファイル名から表示方法を判定する */
function mediaKind(filename) {
    const name = (filename || "").toLowerCase();
    if (name.endsWith(".mp4") || name.endsWith(".webm")) return "video";
    if (name.endsWith(".gif") || name.endsWith(".png") ||
        name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image";
    return "pdf";
}

/** 種類に応じて表示部品を出し分ける（使わないものは必ず隠す） */
function showMediaElement(kind) {
    const canvas = document.getElementById("pdf-canvas");
    const video = document.getElementById("media-video");
    const image = document.getElementById("media-image");
    if (canvas) canvas.style.display = (kind === "pdf") ? "block" : "none";
    if (video) video.style.display = (kind === "video") ? "block" : "none";
    if (image) image.style.display = (kind === "image") ? "block" : "none";
}

/** 動画の監視・後始末をまとめて止める */
function stopVideo() {
    const video = document.getElementById("media-video");
    if (Signage.videoWatchdogId) {
        clearInterval(Signage.videoWatchdogId);
        Signage.videoWatchdogId = null;
    }
    if (video) {
        video.onended = null;
        video.onerror = null;
        video.ontimeupdate = null;
        try { video.pause(); } catch (_) {}
        video.removeAttribute("src");
        try { video.load(); } catch (_) {}
    }
    const btn = document.getElementById("btn-sound");
    if (btn) btn.classList.remove("visible");
}

/** 音付きでの再生を試し、拒否されたら無音で再生する。
 *  戻り値: 再生できたら true、まったく再生できなければ false */
async function playWithSoundFallback(video) {
    const btn = document.getElementById("btn-sound");
    video.muted = false;
    try {
        await video.play();
        if (btn) btn.classList.remove("visible");
        return true;
    } catch (_) {
        // ブラウザが音付きの自動再生を拒否した場合はここに来る
    }
    video.muted = true;
    try {
        await video.play();
        // 利用者がまだ音を許可していないときだけボタンを出す
        if (btn && !Signage.soundUnlocked) btn.classList.add("visible");
        return true;
    } catch (e) {
        console.warn("動画を再生できません:", e);
        return false;
    }
}

/** 動画を表示する。最後まで再生したら次のファイルへ進む */
async function loadVideo(filename) {
    const video = document.getElementById("media-video");
    if (!video) throw new Error("動画の表示部品がありません");

    stopVideo();
    video.src = `/api/signage/media/${encodeURIComponent(filename)}`;
    video.currentTime = 0;
    showMediaElement("video");

    Signage.totalPages = 1;
    Signage.currentPage = 1;
    Signage.slideStartTime = Date.now();
    updateSlideCounter();

    // 再生し終わったら次へ。表示秒数のタイマーは使わない（途中で切れてしまうため）
    cancelAutoAdvance();
    video.onended = () => { stopVideo(); nextSlide(); };
    video.onerror = () => {
        console.warn("動画を読み込めません:", filename);
        stopVideo();
        nextSlide();
    };

    // 固まったときの保険: 30秒進まなければ次のファイルへ
    Signage.videoLastProgress = Date.now();
    video.ontimeupdate = () => { Signage.videoLastProgress = Date.now(); };
    Signage.videoWatchdogId = setInterval(() => {
        if (Signage.sleeping) { Signage.videoLastProgress = Date.now(); return; }
        if (Date.now() - Signage.videoLastProgress > 30000) {
            console.warn("動画が30秒進まないため次へ進みます:", filename);
            stopVideo();
            nextSlide();
        }
    }, 5000);

    // スリープ中に読み込まれたときは再生を始めない。
    // ここで再生すると、画面は時計なのに音だけ鳴り続けてしまう。
    // 解除時に exitSleep から再生を開始する。
    if (Signage.sleeping) return;

    const ok = await playWithSoundFallback(video);
    if (!ok) {
        stopVideo();
        throw new Error("動画を再生できません");
    }
}

/** 画像を表示する。切り替えは既存の表示秒数タイマーに任せる */
async function loadImage(filename) {
    const image = document.getElementById("media-image");
    if (!image) throw new Error("画像の表示部品がありません");
    await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = () => reject(new Error("画像を読み込めません"));
        image.src = `/api/signage/media/${encodeURIComponent(filename)}`;
    });
    showMediaElement("image");
    Signage.totalPages = 1;
    Signage.currentPage = 1;
    Signage.slideStartTime = Date.now();
    updateSlideCounter();
    scheduleNextSlide();
}

async function loadPdf(filename) {
    // 多重レンダリング防止
    if (Signage.rendering) return;
    Signage.rendering = true;

    // 次スライドへの予約タイマーをキャンセル
    cancelAutoAdvance();

    let errorOccurred = false;
    try {
        // フェードアウト（既存コンテンツがある場合のみ）
        const canvas = document.getElementById("pdf-canvas");
        if (Signage.pdfDoc && canvas) {
            canvas.style.transition = "opacity 0.5s ease";
            canvas.style.opacity = "0";
            await new Promise(r => setTimeout(r, 500));
        }

        // 既存ドキュメントを破棄（メモリリーク防止）
        if (Signage.pdfDoc) {
            try { Signage.pdfDoc.destroy(); } catch (_) {}
            Signage.pdfDoc = null;
        }

        // PDF以外はここで処理を終える。pdfDoc が null のままなので、
        // 手動送り（nextSlide/prevSlide）は自動的に「次のファイルへ」になる。
        Signage.mediaKind = mediaKind(filename);
        if (Signage.mediaKind !== "video") stopVideo();
        if (Signage.mediaKind === "image") {
            await loadImage(filename);
            if (canvas) { canvas.style.transition = "none"; canvas.style.opacity = "1"; }
            return;
        }
        if (Signage.mediaKind === "video") {
            await loadVideo(filename);
            if (canvas) { canvas.style.transition = "none"; canvas.style.opacity = "1"; }
            return;
        }

        showMediaElement("pdf");

        // プリロード済みなら再利用、そうでなければ新規取得
        if (Signage.preloadFilename === filename && Signage.preloadDoc) {
            Signage.pdfDoc = Signage.preloadDoc;
            Signage.preloadDoc = null;
            Signage.preloadFilename = null;
        } else {
            const url = `/api/signage/pdf/${encodeURIComponent(filename)}`;
            Signage.pdfDoc = await pdfjsLib.getDocument({
                url,
                cMapUrl: "/pdfjs/cmaps/",
                cMapPacked: true,
            }).promise;
        }
        Signage.totalPages = Signage.pdfDoc.numPages;
        Signage.currentPage = 1;
        await renderPage(Signage.currentPage);

        // transition を無効にして即時表示（フェードインなし）
        if (canvas) {
            canvas.style.transition = "none";
            canvas.style.opacity = "1";
        }

        // レンダリング成功：スライドタイマーをセット
        Signage.slideStartTime = Date.now();
        updateSlideCounter();
        scheduleNextSlide();

        // 次のPDFをバックグラウンドで先読み
        preloadNext();

    } catch (e) {
        console.error(`PDF読み込み失敗 (${filename}):`, e);
        errorOccurred = true;
    } finally {
        // rendering フラグを必ず解放（エラー時も正常時も）
        Signage.rendering = false;
    }

    // エラー発生時は2秒後に次のファイルへ進む
    if (errorOccurred && Signage.files.length > 1) {
        setTimeout(() => {
            Signage.currentFileIdx = (Signage.currentFileIdx + 1) % Signage.files.length;
            loadAndRenderCurrent();
        }, 2000);
    }
}

async function preloadNext() {
    if (Signage.files.length <= 1) return;
    const nextIdx = (Signage.currentFileIdx + 1) % Signage.files.length;
    const nextFilename = Signage.files[nextIdx];
    // 先読みは pdf.js の仕組みを使うため、PDF以外は対象外
    if (mediaKind(nextFilename) !== "pdf") return;
    if (Signage.preloadFilename === nextFilename) return; // 既にプリロード済み

    // 古いプリロードを破棄
    if (Signage.preloadDoc) {
        try { Signage.preloadDoc.destroy(); } catch (_) {}
        Signage.preloadDoc = null;
        Signage.preloadFilename = null;
    }

    try {
        const url = `/api/signage/pdf/${encodeURIComponent(nextFilename)}`;
        Signage.preloadDoc = await pdfjsLib.getDocument({
            url,
            cMapUrl: "/pdfjs/cmaps/",
            cMapPacked: true,
        }).promise;
        Signage.preloadFilename = nextFilename;
    } catch (e) {
        console.warn("プリロード失敗:", nextFilename, e);
        Signage.preloadDoc = null;
        Signage.preloadFilename = null;
    }
}

async function renderPage(pageNum) {
    if (!Signage.pdfDoc) return;

    const page = await Signage.pdfDoc.getPage(pageNum);
    try {
        const canvas = document.getElementById("pdf-canvas");
        const container = document.getElementById("signage-container");
        const ctx = canvas.getContext("2d");

        const dpr = window.devicePixelRatio || 1;
        const cw = container.clientWidth;
        // PDFは全画面に表示し、下部のニューステロップ(50px)に重ねる（ラップ）。
        const ch = container.clientHeight;
        const viewport0 = page.getViewport({ scale: 1.0 });
        const scale = Math.min(cw / viewport0.width, ch / viewport0.height) * 0.97 * dpr;
        const viewport = page.getViewport({ scale });

        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.style.width = (viewport.width / dpr) + "px";
        canvas.style.height = (viewport.height / dpr) + "px";
        canvas.style.display = "block";

        await page.render({ canvasContext: ctx, viewport }).promise;
    } finally {
        // 例外が発生した場合でも必ずページリソースを解放する
        try { page.cleanup(); } catch (_) {}
    }
}

// ============================================================
// ナビゲーション
// ============================================================
function nextSlide() {
    if (Signage.files.length === 0 || Signage.rendering) return;
    if (Signage.pdfDoc && Signage.currentPage < Signage.totalPages) {
        Signage.rendering = true;
        Signage.currentPage++;
        cancelAutoAdvance();
        renderPage(Signage.currentPage).then(() => {
            Signage.slideStartTime = Date.now();
            updateSlideCounter();
            scheduleNextSlide();
            Signage.rendering = false;
        }).catch(e => { console.error(e); Signage.rendering = false; });
    } else {
        Signage.currentFileIdx = (Signage.currentFileIdx + 1) % Signage.files.length;
        loadAndRenderCurrent();
    }
}

function prevSlide() {
    if (Signage.files.length === 0 || Signage.rendering) return;
    if (Signage.pdfDoc && Signage.currentPage > 1) {
        Signage.rendering = true;
        Signage.currentPage--;
        cancelAutoAdvance();
        renderPage(Signage.currentPage).then(() => {
            Signage.slideStartTime = Date.now();
            updateSlideCounter();
            scheduleNextSlide();
            Signage.rendering = false;
        }).catch(e => { console.error(e); Signage.rendering = false; });
    } else {
        Signage.currentFileIdx = (Signage.currentFileIdx - 1 + Signage.files.length) % Signage.files.length;
        loadAndRenderCurrent();
    }
}

// ============================================================
// タイマー管理（setTimeoutベース：競合なし）
// ============================================================
function scheduleNextSlide() {
    cancelAutoAdvance();
    Signage.autoAdvanceTimer = setTimeout(() => {
        if (!Signage.sleeping && !document.hidden && Signage.files.length > 0) {
            nextSlide();
        } else {
            // スリープ中・非表示中は次のチェックを遅らせる
            scheduleNextSlide();
        }
    }, Signage.config.displayMs);
}

function cancelAutoAdvance() {
    if (Signage.autoAdvanceTimer) {
        clearTimeout(Signage.autoAdvanceTimer);
        Signage.autoAdvanceTimer = null;
    }
}

// ============================================================
// 進捗バー（setIntervalで200ms毎に更新）
// ============================================================
function startProgressLoop() {
    if (Signage.progressIntervalId) clearInterval(Signage.progressIntervalId);
    Signage.progressIntervalId = setInterval(() => {
        if (Signage.sleeping || Signage.rendering || Signage.slideStartTime === 0) {
            updateProgressBar(0);
            return;
        }
        if (Signage.mediaKind === "video") {
            // 動画は再生位置をそのまま進捗として表す
            const video = document.getElementById("media-video");
            const ratio = (video && video.duration > 0)
                ? Math.min(1.0, video.currentTime / video.duration) : 0;
            updateProgressBar(ratio);
            return;
        }
        const ratio = Math.min(1.0, (Date.now() - Signage.slideStartTime) / Signage.config.displayMs);
        updateProgressBar(ratio);
    }, 200);
}

function updateProgressBar(ratio) {
    const fill = document.getElementById("progress-fill");
    if (fill) fill.style.width = (ratio * 100) + "%";
}

// ============================================================
// スリープモード
// ============================================================
/** ユーザー操作のたびにスリープ復帰タイマーをリセットする（3分延長） */
function extendWake() {
    if (!Signage.sleeping && Signage.sleepDismissedAt > 0) {
        Signage.sleepDismissedAt = Date.now();
    }
}

function isSleepTime() {
    // ユーザーが手動解除してから3分間はスリープに入らない
    if (Date.now() - Signage.sleepDismissedAt < 3 * 60 * 1000) return false;

    const now = new Date();
    const current = now.getHours() * 60 + now.getMinutes();
    const [sh, sm] = Signage.config.sleepStart.split(":").map(Number);
    const [eh, em] = Signage.config.sleepEnd.split(":").map(Number);
    const start = sh * 60 + sm;
    const end = eh * 60 + em;

    if (start === end) return false;
    // 日をまたぐ場合（例: 18:00〜08:00）
    if (start > end) return current >= start || current < end;
    return current >= start && current < end;
}

function enterSleep() {
    if (Signage.sleeping) return;
    Signage.sleeping = true;
    cancelAutoAdvance();
    updateProgressBar(0);
    // 動画は音が鳴り続けてしまうので必ず止める
    const sleepVideo = document.getElementById("media-video");
    if (sleepVideo && Signage.mediaKind === "video") {
        try { sleepVideo.pause(); } catch (_) {}
    }
    // メモリ節約: プリロードを破棄
    if (Signage.preloadDoc) {
        try { Signage.preloadDoc.destroy(); } catch (_) {}
        Signage.preloadDoc = null;
        Signage.preloadFilename = null;
    }
    document.getElementById("sleep-overlay").classList.add("active");
}

function exitSleep() {
    if (!Signage.sleeping) return;
    Signage.sleeping = false;
    Signage.sleepDismissedAt = Date.now(); // 解除時刻を記録
    document.getElementById("sleep-overlay").classList.remove("active");
    // スリープ解除後に現在のスライドから再開
    Signage.slideStartTime = Date.now();
    if (Signage.mediaKind === "video") {
        const wakeVideo = document.getElementById("media-video");
        if (wakeVideo) {
            Signage.videoLastProgress = Date.now();
            playWithSoundFallback(wakeVideo);
        }
    } else {
        scheduleNextSlide();
    }
}

function startSleepClock() {
    if (Signage.sleepClockId) clearInterval(Signage.sleepClockId);
    const weekNames = ["日", "月", "火", "水", "木", "金", "土"];
    const clockEl = document.getElementById("sleep-clock");
    const dateEl = document.getElementById("sleep-date");

    const tick = () => {
        const n = new Date();
        const hh = String(n.getHours()).padStart(2, "0");
        const mm = String(n.getMinutes()).padStart(2, "0");
        if (clockEl) clockEl.textContent = `${hh}:${mm}`;
        if (dateEl) dateEl.textContent = `${n.getFullYear()}年${n.getMonth() + 1}月${n.getDate()}日（${weekNames[n.getDay()]}）`;

        if (isSleepTime()) {
            enterSleep();
        } else if (Signage.sleeping) {
            // 自動スリープ（手動解除ではない）は時刻が外れたら自動解除
            exitSleep();
            loadAndRenderCurrent();
        }
    };
    tick();
    Signage.sleepClockId = setInterval(tick, 5000); // 5秒ごとに確認（1秒は不要）
}

function updateNavButtons() {
    const webPages = Signage.config.webPages || [];
    [1, 2].forEach(i => {
        const btn = document.getElementById(`btn-to-web${i}`);
        const page = webPages[i - 1];
        if (btn && page && page.url) {
            btn.textContent = `🌐 ${page.label || `Web${i}`}`;
            btn.href = `/webview?url=${encodeURIComponent(page.url)}&label=${encodeURIComponent(page.label || `Web${i}`)}`;
            btn.style.display = "inline-block";
        } else if (btn) {
            btn.style.display = "none";
        }
    });
}

// ============================================================
// UI更新
// ============================================================
function updateSlideCounter() {
    const el = document.getElementById("slide-counter");
    if (!el) return;
    if (Signage.files.length === 0) { el.textContent = ""; return; }
    const fileInfo = `${Signage.currentFileIdx + 1}/${Signage.files.length}`;
    const pageInfo = Signage.totalPages > 1 ? ` p.${Signage.currentPage}/${Signage.totalPages}` : "";
    el.textContent = fileInfo + pageInfo;
}

function showNoPdfMsg(msg) {
    const el = document.getElementById("no-pdf-msg");
    const canvas = document.getElementById("pdf-canvas");
    if (el) {
        el.classList.add("visible");
        if (msg) {
            const hint = el.querySelector(".no-pdf-hint");
            if (hint) hint.textContent = msg;
        }
    }
    if (canvas) canvas.style.display = "none";
}

function hidNoPdfMsg() {
    const el = document.getElementById("no-pdf-msg");
    const canvas = document.getElementById("pdf-canvas");
    if (el) el.classList.remove("visible");
    if (canvas) canvas.style.display = "block";
}

// ============================================================
// イベントリスナー
// ============================================================
function setupEventListeners() {
    const container = document.getElementById("signage-container");
    const sleepOverlay = document.getElementById("sleep-overlay");

    // スリープ解除
    sleepOverlay.addEventListener("click", exitSleep);
    sleepOverlay.addEventListener("touchend", (e) => { e.preventDefault(); exitSleep(); });

    // 「🔊 音を出す」。押した操作そのものがブラウザの許可になるため、
    // 以降は同じページを開いている間ずっと音付きで再生できる。
    const soundBtn = document.getElementById("btn-sound");
    if (soundBtn) {
        soundBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            Signage.soundUnlocked = true;
            soundBtn.classList.remove("visible");
            const video = document.getElementById("media-video");
            if (video && Signage.mediaKind === "video") {
                video.muted = false;
                video.play().catch(err => console.warn("音付き再生に失敗:", err));
            }
        });
    }

    // ナビゲーションボタン
    document.getElementById("btn-prev").addEventListener("click", (e) => {
        e.stopPropagation();
        prevSlide();
    });
    document.getElementById("btn-next").addEventListener("click", (e) => {
        e.stopPropagation();
        nextSlide();
    });

    // タッチスワイプ
    container.addEventListener("touchstart", (e) => {
        Signage.swipeStartX = e.touches[0].clientX;
        Signage.swipeActive = true;
    }, { passive: true });

    container.addEventListener("touchend", (e) => {
        if (!Signage.swipeActive) return;
        Signage.swipeActive = false;
        const dx = e.changedTouches[0].clientX - Signage.swipeStartX;
        if (Math.abs(dx) > 50) { dx < 0 ? nextSlide() : prevSlide(); }
    }, { passive: true });

    // マウスドラッグ
    container.addEventListener("mousedown", (e) => {
        Signage.swipeStartX = e.clientX;
        Signage.swipeActive = true;
    });
    container.addEventListener("mouseup", (e) => {
        if (!Signage.swipeActive) return;
        Signage.swipeActive = false;
        const dx = e.clientX - Signage.swipeStartX;
        if (Math.abs(dx) > 60) { dx < 0 ? nextSlide() : prevSlide(); }
    });

    // キーボード
    document.addEventListener("keydown", (e) => {
        if (Signage.sleeping) { exitSleep(); return; }
        if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); nextSlide(); }
        if (e.key === "ArrowLeft") { e.preventDefault(); prevSlide(); }
    });

    // 設定パネルの開閉
    const cfgBtn = document.getElementById("btn-signage-cfg");
    const cfgPanel = document.getElementById("signage-cfg-panel");
    const cfgApplyBtn = document.getElementById("cfg-apply-btn");

    // リモートアクセス判定（localhost以外なら管理者キー欄を表示）
    const isRemote = !["localhost", "127.0.0.1", "::1"].includes(location.hostname);
    const adminKeyRow = document.getElementById("cfg-admin-key-row");
    if (isRemote && adminKeyRow) adminKeyRow.style.display = "flex";

    if (cfgBtn && cfgPanel) {
        cfgBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const isOpen = cfgPanel.classList.toggle("open");
            if (isOpen) {
                // パネルを開いたとき現在の設定値を反映
                const secEl = document.getElementById("cfg-display-sec");
                const startEl = document.getElementById("cfg-sleep-start");
                const endEl = document.getElementById("cfg-sleep-end");
                const folderEl = document.getElementById("cfg-folder-path");
                const statusEl = document.getElementById("cfg-save-status");
                if (secEl) secEl.value = Math.round(Signage.config.displayMs / 1000);
                if (startEl) startEl.value = Signage.config.sleepStart;
                if (endEl) endEl.value = Signage.config.sleepEnd;
                if (folderEl) folderEl.value = Signage.config.folderPath || "";

                // Web設定反映
                const webPages = Signage.config.webPages || [];
                [1, 2].forEach(i => {
                    const labelEl = document.getElementById(`cfg-web${i}-label`);
                    const urlEl = document.getElementById(`cfg-web${i}-url`);
                    const page = webPages[i - 1] || {};
                    if (labelEl) labelEl.value = page.label || "";
                    if (urlEl) urlEl.value = page.url || "";
                });
                const idleEl = document.getElementById("cfg-idle-sec");
                if (idleEl) idleEl.value = Signage.config.idleReturnSeconds || 60;
                const newsEl = document.getElementById("cfg-news-speed");
                if (newsEl) newsEl.value = Signage.config.newsSpeed || 100;
                const stayEl = document.getElementById("cfg-web-max-stay");
                if (stayEl) stayEl.value = Signage.config.webMaxStaySeconds || 300;

                // 文書掲示の設定を反映
                const dc = Signage.config.documentCategories
                    || { button_count: 3, categories: [] };
                const dcCountEl = document.getElementById("cfg-doc-btn-count");
                if (dcCountEl) dcCountEl.value = dc.button_count || 3;
                for (let i = 0; i < 5; i++) {
                    const cat = (dc.categories || [])[i] || { label: "", folder: "" };
                    const labelEl = document.getElementById("cfg-doc-label-" + i);
                    const docFolderEl = document.getElementById("cfg-doc-folder-" + i);
                    if (labelEl) labelEl.value = cat.label || "";
                    if (docFolderEl) docFolderEl.value = cat.folder || "";
                }

                if (statusEl) statusEl.style.display = "none";
            }
        });

        // パネル外クリックで閉じる
        document.addEventListener("click", (e) => {
            if (!cfgPanel.contains(e.target) && e.target !== cfgBtn) {
                cfgPanel.classList.remove("open");
            }
        });
    }

    if (cfgApplyBtn) {
        cfgApplyBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const secs = Math.max(3, parseInt(document.getElementById("cfg-display-sec")?.value) || 10);
            const sleepStart = document.getElementById("cfg-sleep-start")?.value || "18:00";
            const sleepEnd = document.getElementById("cfg-sleep-end")?.value || "08:00";
            const folderPath = document.getElementById("cfg-folder-path")?.value.trim() || "";
            const webPages = [
                {
                    label: document.getElementById("cfg-web1-label")?.value.trim() || "Web1",
                    url: document.getElementById("cfg-web1-url")?.value.trim() || ""
                },
                {
                    label: document.getElementById("cfg-web2-label")?.value.trim() || "Web2",
                    url: document.getElementById("cfg-web2-url")?.value.trim() || ""
                }
            ];
            const idleSec = parseInt(document.getElementById("cfg-idle-sec")?.value) || 60;
            const newsSpeed = Math.max(20, parseInt(document.getElementById("cfg-news-speed")?.value) || 100);
            const webMaxStay = Math.max(60, parseInt(document.getElementById("cfg-web-max-stay")?.value) || 300);
            const documentCategories = {
                button_count: Math.min(5, Math.max(1,
                    parseInt(document.getElementById("cfg-doc-btn-count")?.value) || 3)),
                categories: [0, 1, 2, 3, 4].map(i => ({
                    label: document.getElementById("cfg-doc-label-" + i)?.value.trim() || "",
                    folder: document.getElementById("cfg-doc-folder-" + i)?.value.trim() || "",
                })),
            };

            // メモリ上の設定を更新
            Signage.config.displayMs = secs * 1000;
            Signage.config.sleepStart = sleepStart;
            Signage.config.sleepEnd = sleepEnd;
            Signage.config.folderPath = folderPath;
            Signage.config.webPages = webPages;
            Signage.config.idleReturnSeconds = idleSec;
            Signage.config.newsSpeed = newsSpeed;
            Signage.config.webMaxStaySeconds = webMaxStay;
            Signage.config.documentCategories = documentCategories;

            // サーバーにも保存
            const statusEl = document.getElementById("cfg-save-status");
            try {
                const cfgRes = await fetch("/api/config");
                if (cfgRes.ok) {
                    const fullCfg = await cfgRes.json();
                    if (!fullCfg.signage) fullCfg.signage = {};
                    fullCfg.signage.display_seconds = secs;
                    fullCfg.signage.sleep_start = sleepStart;
                    fullCfg.signage.sleep_end = sleepEnd;
                    fullCfg.signage.folder_path = folderPath;
                    fullCfg.signage.idle_return_seconds = idleSec;
                    fullCfg.signage.news_speed = newsSpeed;
                    fullCfg.signage.web_max_stay_seconds = webMaxStay;
                    fullCfg.web_pages = webPages;
                    fullCfg.document_categories = documentCategories;

                    const postHeaders = { "Content-Type": "application/json" };
                    const adminKey = document.getElementById("cfg-admin-key")?.value.trim();
                    if (adminKey) postHeaders["X-Admin-Key"] = adminKey;

                    const saveRes = await fetch("/api/config", {
                        method: "POST",
                        headers: postHeaders,
                        body: JSON.stringify(fullCfg)
                    });
                    if (!saveRes.ok) {
                        const err = await saveRes.json().catch(() => ({}));
                        const msg = err.error || "保存に失敗しました";
                        if (statusEl) {
                            statusEl.textContent = "⚠ " + msg;
                            statusEl.style.color = "#ff6b6b";
                            statusEl.style.display = "block";
                        }
                        return;
                    }
                }
            } catch (_) {
                if (statusEl) {
                    statusEl.textContent = "⚠ 通信エラー";
                    statusEl.style.color = "#ff6b6b";
                    statusEl.style.display = "block";
                }
                return;
            }

            if (statusEl) statusEl.style.display = "none";
            cfgPanel.classList.remove("open");
            updateNavButtons();
            // ニュース速度の変更を反映
            startMarquee();
            // タイマーと表示をリセット
            Signage.slideStartTime = Date.now();
            scheduleNextSlide();
        });
    }

    // ユーザー操作でスリープ復帰タイマーをリセット（3分延長）
    ["click", "touchstart", "keydown"].forEach(ev => {
        document.addEventListener(ev, extendWake, { passive: true });
    });

    // タブ表示/非表示
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && !Signage.sleeping) {
            // タブがアクティブになったとき: タイマーリセット
            Signage.slideStartTime = Date.now();
            scheduleNextSlide();
        }
    });

    // リサイズ時に再レンダリング
    let resizeTimer = null;
    window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (Signage.pdfDoc && !Signage.sleeping && !Signage.rendering) {
                renderPage(Signage.currentPage).catch(console.error);
            }
            // 横幅が変わるとスクロール距離が変わるため、テロップも作り直す
            startMarquee();
        }, 300);
    });
}

// ============================================================
// エントリーポイント
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
    initSignage().catch(e => {
        console.error("サイネージ初期化エラー:", e);
        showNoPdfMsg("初期化エラーが発生しました: " + e.message);
    });
});
