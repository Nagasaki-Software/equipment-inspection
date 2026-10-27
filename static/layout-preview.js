/** 印字プレビュー。
 *
 *  PDFの上に「実際に印字される文字」を重ねて表示する。
 *  on_axis の項目は欄の数だけ描かれるので、これがそのまま
 *  「並び方が正しいか」を確かめるゴースト表示になる。
 *
 *  このモジュールは layout.js の状態を見ない。必要な材料は ctx で受け取る。
 */

const SAMPLE = {
    inspector: "見本 太郎",
    department: "見本部",
    remark: "見本",
    number: "0.00",
    judgment: "✓",
};

// 備考は、実際の試し刷りでは空欄になる。ただし画面のプレビューでは
// 位置を確かめられるよう、あえて見本の文字を出す。

/** layout.json の上書き指定を取り出す。
 *
 *  空文字での上書き（＝何も印字しない）も指定として尊重する。
 *  `||` で書くと空文字が既定値に戻ってしまい、サーバーの挙動と食い違う。
 */
function markOr(field, key, fallback) {
    const v = field[key];
    return (v === undefined || v === null) ? fallback : v;
}

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

function pad(n) { return String(n).padStart(2, "0"); }

/** n 番目の欄に印字される見本の文字を返す。空文字なら描かない。 */
export function sampleValue(field, n, ctx) {
    const source = String(field.source || "");
    if (source === "meta.month") return String(ctx.month);
    if (source === "meta.year") return String(ctx.year);
    if (source === "meta.day") {
        const d = ctx.dates[n - 1];
        return d ? String(d.getDate()) : "";
    }
    if (source === "meta.weekday") {
        // JavaScript の getDay() は日曜が0。Python の weekday()（月曜が0）に
        // 合わせないと、画面とPDFで曜日が1つずれる。
        const d = ctx.dates[n - 1];
        return d ? "月火水木金土日"[(d.getDay() + 6) % 7] : "";
    }
    if (source === "meta.month_start") {
        // 締め日区切りなので、1日のマスは月によって位置が変わる
        const d = ctx.dates[n - 1];
        return (d && d.getDate() === 1) ? `${d.getMonth() + 1}月` : "";
    }
    if (source === "meta.month_prev") {
        const d = ctx.dates[n - 1];
        return (d && n === 1) ? `${d.getMonth() + 1}月` : "";
    }
    if (source === "meta.unused") {
        return ctx.dates[n - 1] ? markOr(field, "mark_unused", SAMPLE.judgment) : "";
    }
    if (source === "meta.inspection_date") {
        // year 型は n が月番号（1〜12）。日ごとの日付とは意味が違う。
        if (ctx.layout && ctx.layout.period === "year") {
            return `${ctx.year}-${pad(n)}-01`;
        }
        const d = ctx.dates[n - 1];
        return d ? dateKey(d) : `${ctx.year}-${pad(ctx.month)}-01`;
    }
    if (source === "meta.inspector") return SAMPLE.inspector;
    if (source === "meta.department") return SAMPLE.department;
    if (source === "meta.building_name") return ctx.buildingName || "見本ビル";
    if (source === "meta.general_remark") return SAMPLE.remark;
    if (source.startsWith("target:")) {
        // 対象機器欄。プレビューは全機器を点検した前提の見本なので常に出す。
        return markOr(field, "mark_target", SAMPLE.judgment);
    }
    if (source.startsWith("remark:")) return SAMPLE.remark;
    if (source.startsWith("item:")) {
        const body = source.slice(5);
        const sep = body.indexOf("|");
        if (sep < 0) return markOr(field, "mark_ok", SAMPLE.judgment);
        const item = body.slice(sep + 1);
        // 様式によっては「良」を✓以外の字で書く。印字と同じ字を出す。
        return ctx.numberItems.has(item) ? SAMPLE.number
                                         : markOr(field, "mark_ok", SAMPLE.judgment);
    }
    return "";
}

/** 日にちの色。平日は空文字（丸を描かない）。 */
export function dayColor(dateStr, holidays) {
    const h = (holidays || {})[dateStr];
    if (!h) return "";
    if (h.is_sunday || h.is_holiday || h.is_custom_holiday) return COLOR_HOLIDAY;
    if (h.is_saturday) return COLOR_SATURDAY;
    return "";
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

/** container の中身をプレビューで描き直す。
 *
 *  ctx = { layout, viewport, pageIndex, selectedField, defaultFontSize,
 *          year, month, dates, holidays, buildingName, numberItems }
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
            // その欄が実在するか。month 型はサイクルの日数を超えると余りマスになる。
            // year 型と single 型に余りマスは無い。
            const exists = layout.period === "month" ? (n <= ctx.dates.length) : true;
            let text;
            if (exists) {
                text = sampleValue(field, n, ctx);
            } else if (String(field.source || "").startsWith("item:")) {
                // 余りマスは item だけ「ー」を入れて、記入漏れの空欄と見分けられるようにする
                // （サーバー側 pdf_forms._draw_slot_field と同じ規則）
                text = markOr(field, "mark_na", "ー");
            } else {
                text = "";
            }
            if (!text) continue;
            const [px, py] = axisPosition(field, axis, n);
            const [vx, vy] = ctx.viewport.convertToViewportPoint(px, py);
            const isDay = field.source === "meta.day";
            // 曜日も1文字を中央に置く。ただし丸は描かない。
            const isCentred = isDay || field.source === "meta.weekday";
            const el = document.createElement("div");
            el.className = "pf " + (n === 1 ? "pf-anchor" : "pf-ghost");
            if (n === 1) el.dataset.index = String(index);
            if (n === 1 && index === ctx.selectedField) el.classList.add("pf-selected");
            el.style.fontSize = `${size}px`;
            el.textContent = text;

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
        }
    });
}
