/**
 * 文書・Web表示ページ用非アクティブタイマー
 * - config.signage.idle_return_seconds 秒間操作がなければ / に戻る
 * - iframe埋め込みページ（Web表示）では、中の操作をセキュリティ上外から
 *   直接検知できないため、次の3段構えで判定する:
 *     1. 透明のセンサー線（格子）をまたぐポインタの動きを検知して延長
 *     2. 埋め込みページへのクリック/タップをフォーカス移動として検知して延長
 *     3. 保険として web_max_stay_seconds で必ず / に戻る（滞在上限）
 */
(async function () {
    "use strict";
    let timeoutMs = 60000;
    let maxStayMs = 300000;
    try {
        const res = await fetch("/api/config");
        if (res.ok) {
            const cfg = await res.json();
            const sg = cfg.signage || {};
            const secs = parseInt(sg.idle_return_seconds) || 60;
            timeoutMs = Math.max(10, secs) * 1000;
            const cap = parseInt(sg.web_max_stay_seconds) || 300;
            maxStayMs = Math.max(60, cap) * 1000;
        }
    } catch (_) {}

    let timer;

    // 動作確認・現場診断用（ブラウザのコンソールから参照できる）
    window.__idleState = { lastReset: 0, maxStayAt: 0 };

    function reset() {
        window.__idleState.lastReset = Date.now();
        clearTimeout(timer);
        timer = setTimeout(function () {
            window.location.href = "/";
        }, timeoutMs);
    }

    ["mousemove", "mousedown", "keydown", "touchstart", "click", "scroll"].forEach(function (ev) {
        document.addEventListener(ev, reset, { passive: true });
    });

    const iframe = document.querySelector("iframe");
    if (iframe) {
        // 埋め込みページへのクリック/タップは、ウィンドウのフォーカスが
        // iframeへ移ることで検知できる
        window.addEventListener("blur", function () {
            if (document.activeElement && document.activeElement.tagName === "IFRAME") {
                reset();
            }
        });

        // 透明のセンサー線（2px幅・5%間隔の格子）。ポインタが線をまたぐと
        // 親ページの mousemove 等が発火し、上のリスナーが延長する。
        // 線の上はクリックが埋め込みページへ届かないため、細さ優先。
        const grid = document.createElement("div");
        grid.id = "idle-sensor-grid";
        grid.style.cssText =
            "position:fixed;inset:0;z-index:500;pointer-events:none;";
        for (let p = 5; p < 100; p += 5) {
            const v = document.createElement("div");
            v.style.cssText =
                "position:absolute;top:0;bottom:0;width:2px;left:" + p + "%;pointer-events:auto;";
            grid.appendChild(v);
            const h = document.createElement("div");
            h.style.cssText =
                "position:absolute;left:0;right:0;height:2px;top:" + p + "%;pointer-events:auto;";
            grid.appendChild(h);
        }
        document.body.appendChild(grid);

        // 滞在上限: どれだけ操作していても必ずサイネージへ戻る
        window.__idleState.maxStayAt = Date.now() + maxStayMs;
        setTimeout(function () {
            window.location.href = "/";
        }, maxStayMs);
    }

    reset();
}());
