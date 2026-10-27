"""サンプル一式（様式・サイネージ・文書・点検記録）を作り直すスクリプト。

すべて架空の「サンプル工業 第一工場」の見本で、絵・文章・罫線はここで描いている。
アプリと同じ部品（reportlab・Pillow）だけを使う。

使い方（アプリのフォルダで）:
    .venv\\Scripts\\python.exe samples\\make_samples.py

点検記録は data/ の点検項目マスタを使い、アプリの保存APIを通して作る。
本物の config.json・results/ には触らない（一時フォルダで作ってからコピーする）。
"""
import json
import math
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import jpholiday
from PIL import Image, ImageDraw
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

SAMPLES = Path(__file__).resolve().parent
APP_DIR = SAMPLES.parent

FONT = "HeiseiKakuGo-W5"   # アプリと同じ。PDFに埋め込まない方式なのでフォントを配布しない
pdfmetrics.registerFont(UnicodeCIDFont(FONT))

COMPANY = "サンプル工業 第一工場"
NOTE = "これは「設備点検システム」の動作確認用の見本です。実在の会社・人物・手順とは関係ありません。"

NAVY = HexColor("#1f3a5f")
ORANGE = HexColor("#e8772e")
GREEN = HexColor("#2e8b57")
LIGHT = HexColor("#f4f6f9")
GRAY = HexColor("#6b7280")
LINE = HexColor("#333333")

CRANES = ["天井クレーン1号機", "天井クレーン2号機"]
CRANE_ITEMS = ["巻過防止装置は正常に働くか", "ブレーキは正常に効くか", "フックの外れ止めに損傷はないか",
               "ワイヤロープに素線切れ・キンクはないか", "押しボタンスイッチは正常に働くか",
               "走行・横行時に異音はないか"]
FORKLIFT = "フォークリフト1号車"
FL_DAILY = ["ブレーキの効き", "タイヤの損傷・空気圧", "ホーン・警報の作動", "前照灯・後退灯の点灯",
            "フォーク・チェーンの損傷", "油漏れはないか"]
FL_MONTHLY = ["油漏れはないか", "バッテリー液の量", "作動油の量", "マストへの給油", "アワーメーター"]
COMPRESSOR = "エアコンプレッサー1号機"
CP_ITEMS = ["吐出圧力", "安全弁は正常に働くか", "ドレンを排出したか", "吸込フィルターの汚れ",
            "異音・振動はないか", "運転時間"]
CP_LABELS = {"吐出圧力": "吐出圧力（MPa）", "運転時間": "運転時間（h）"}


# ========== PDFの共通部品 ==========

def new_canvas(path: Path, size, title: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=size)
    c.setTitle(title)
    c.setAuthor(COMPANY)
    c.setCreator("samples/make_samples.py")
    return c


def text(c, x, y, s, size, color=LINE, align="left"):
    c.setFont(FONT, size)
    c.setFillColor(color)
    if align == "center":
        c.drawCentredString(x, y, s)
    elif align == "right":
        c.drawRightString(x, y, s)
    else:
        c.drawString(x, y, s)


def width(s, size):
    return pdfmetrics.stringWidth(s, FONT, size)


def box(c, x, y, w, h, fill=None, stroke=LINE, lw=0.8, radius=0):
    c.setLineWidth(lw)
    if stroke is not None:
        c.setStrokeColor(stroke)
    if fill is not None:
        c.setFillColor(fill)
    if radius:
        c.roundRect(x, y, w, h, radius, stroke=1 if stroke else 0, fill=1 if fill is not None else 0)
    else:
        c.rect(x, y, w, h, stroke=1 if stroke else 0, fill=1 if fill is not None else 0)


def hline(c, x1, x2, y, lw=0.6):
    c.setLineWidth(lw)
    c.setStrokeColor(LINE)
    c.line(x1, y, x2, y)


def vline(c, x, y1, y2, lw=0.6):
    c.setLineWidth(lw)
    c.setStrokeColor(LINE)
    c.line(x, y1, x, y2)


def stamp_boxes(c, right, top, labels, w=52, h=52):
    """確認印の欄（右上から左へ並べる）"""
    x = right - w * len(labels)
    for i, label in enumerate(labels):
        bx = x + w * i
        box(c, bx, top - h, w, h)
        hline(c, bx, bx + w, top - 14)
        text(c, bx + w / 2, top - 11, label, 8, align="center")


def footer(c, page_w, size=7):
    text(c, page_w / 2, 14, NOTE, size, GRAY, align="center")


def baseline(row_bottom, row_h, size):
    """マスの縦中央に文字が来るベースライン"""
    return row_bottom + (row_h - size * 0.72) / 2


# ========== 様式PDF ==========

def make_form_01(form_dir: Path):
    """月1枚：天井クレーン2台の作業開始前点検表（使用前）"""
    W, H = 842, 595
    c = new_canvas(form_dir / "form.pdf", (W, H), "天井クレーン 作業開始前点検表")
    text(c, 20, 556, "天井クレーン 作業開始前点検表", 17, NAVY)
    text(c, 20, 538, f"事業所：{COMPANY}", 9, GRAY)
    # 年・月の記入欄。数字はアプリが印字する
    text(c, 330, 556, "年", 12)
    text(c, 380, 556, "月度", 12)
    hline(c, 285, 328, 553)
    hline(c, 345, 378, 553)
    stamp_boxes(c, 822, 578, ["管理者", "係長", "担当"], w=48, h=48)

    x0, label_w, cw, n = 20, 200, 19.5, 31
    gx = x0 + label_w
    gx_end = gx + cw * n
    rows = [("month", 14), ("day", 18), ("weekday", 14)]
    rows += [("target:" + m, 18) for m in CRANES]
    rows += [("item:" + i, 18) for i in CRANE_ITEMS]
    rows += [("unused", 16), ("inspector", 48)]
    top = 520
    y = top
    ys = {}
    for key, h in rows:
        ys[key] = (y - h, h)
        y -= h
    bottom = y

    box(c, x0, bottom, gx_end - x0, top - bottom, lw=1.2)
    for key, (yb, h) in ys.items():
        hline(c, x0, gx_end, yb)
    # 見出しの区切り（対象機器・点検項目のまとまりで太線）
    hline(c, x0, gx_end, ys["target:" + CRANES[0]][0] + 18, lw=1.2)
    hline(c, x0, gx_end, ys["item:" + CRANE_ITEMS[0]][0] + 18, lw=1.2)
    hline(c, x0, gx_end, ys["unused"][0] + 16, lw=1.2)
    for i in range(n + 1):
        vline(c, gx + cw * i, bottom, top, lw=1.2 if i == 0 else 0.4)

    # 左の見出し
    yb, h = ys["month"]
    text(c, x0 + 6, baseline(yb, h, 8), "月", 8)
    text(c, x0 + label_w / 2, baseline(ys["day"][0], 18, 10), "日", 10, align="center")
    text(c, x0 + label_w / 2, baseline(ys["weekday"][0], 14, 8), "曜日", 8, align="center")
    t_top = ys["target:" + CRANES[0]][0] + 18
    t_bot = ys["target:" + CRANES[-1]][0]
    i_top = ys["item:" + CRANE_ITEMS[0]][0] + 18
    i_bot = ys["item:" + CRANE_ITEMS[-1]][0]
    vline(c, x0 + 46, i_bot, t_top)
    text(c, x0 + 23, (t_top + t_bot) / 2 - 3, "対象機器", 7.5, align="center")
    for k, ch in enumerate("点検項目"):
        text(c, x0 + 23, (i_top + i_bot) / 2 + 22 - 14 * k, ch, 10, align="center")
    for m in CRANES:
        yb, h = ys["target:" + m]
        text(c, x0 + 52, baseline(yb, h, 9), m, 9)
    for item in CRANE_ITEMS:
        yb, h = ys["item:" + item]
        text(c, x0 + 52, baseline(yb, h, 7.5), item, 7.5)
    yb, h = ys["unused"]
    text(c, x0 + label_w / 2, baseline(yb, h, 9), "使用せず", 9, align="center")
    yb, h = ys["inspector"]
    text(c, x0 + label_w / 2, baseline(yb, h, 10), "点検者", 10, align="center")

    # 凡例・備考
    legend = "記号：✓ 良　A 要調整　△ 修理　× 要取替　ー 対象外　／ 対象機器欄の✓はその日に点検した機器"
    text(c, x0, bottom - 16, legend, 8)
    text(c, x0, bottom - 34, "2台の結果は1マスにまとめ、悪いほうを記入する。食い違いの内容は備考に書く。", 8, GRAY)
    box(c, x0, 30, gx_end - x0, bottom - 70)
    text(c, x0 + 6, bottom - 54, "備考", 9)
    footer(c, W)
    c.showPage()
    c.save()

    def center_x(n_):
        return gx + cw * (n_ - 1) + cw / 2

    def left_x(s, size):
        return round(gx + (cw - width(s, size)) / 2, 1)

    fields = []
    yb, h = ys["month"]
    fields.append({"source": "meta.month_prev", "page": 0, "x": round(gx + 1.5, 1),
                   "y": round(baseline(yb, h, 7), 1), "on_axis": True, "font_size": 7})
    fields.append({"source": "meta.month_start", "page": 0, "x": round(gx + 1.5, 1),
                   "y": round(baseline(yb, h, 7), 1), "on_axis": True, "font_size": 7})
    yb, h = ys["day"]
    fields.append({"source": "meta.day", "page": 0, "x": round(center_x(1), 1),
                   "y": round(yb + h / 2, 1), "on_axis": True, "font_size": 8, "circle_radius": 7.5})
    yb, h = ys["weekday"]
    fields.append({"source": "meta.weekday", "page": 0, "x": round(center_x(1), 1),
                   "y": round(yb + h / 2, 1), "on_axis": True, "font_size": 7.5})
    for m in CRANES:
        yb, h = ys["target:" + m]
        fields.append({"source": f"target:{m}", "page": 0, "x": left_x("✓", 9),
                       "y": round(baseline(yb, h, 9), 1), "on_axis": True, "font_size": 9})
    for item in CRANE_ITEMS:
        yb, h = ys["item:" + item]
        fields.append({"source": f"item:*|{item}", "page": 0, "x": left_x("✓", 9),
                       "y": round(baseline(yb, h, 9), 1), "on_axis": True, "font_size": 9})
    yb, h = ys["unused"]
    fields.append({"source": "meta.unused", "page": 0, "x": left_x("✓", 9),
                   "y": round(baseline(yb, h, 9), 1), "on_axis": True, "font_size": 9})
    yb, h = ys["inspector"]
    fields.append({"source": "meta.inspector", "page": 0, "x": left_x("点", 8),
                   "y": round(yb + h - 10, 1), "on_axis": True, "font_size": 8, "vertical": True})
    fields.append({"source": "meta.year", "page": 0, "x": 290, "y": 556, "font_size": 12})
    fields.append({"source": "meta.month", "page": 0, "x": 352, "y": 556, "font_size": 12})

    write_layout(form_dir, {
        "form_name": "天井クレーン 作業開始前点検表",
        "period": "month",
        "inspection_type": "使用前",
        "targets": CRANES,
        "axis": {"count": n, "step_x": cw, "step_y": 0},
        "default_font_size": 9,
        "fields": fields,
    })


def make_form_02(form_dir: Path):
    """年1枚：エアコンプレッサーの月例点検表（12か月分）"""
    W, H = 842, 595
    c = new_canvas(form_dir / "form.pdf", (W, H), "エアコンプレッサー 月例点検表")
    text(c, 20, 556, "エアコンプレッサー 月例点検表", 17, NAVY)
    text(c, 20, 538, f"事業所：{COMPANY}　　機器：{COMPRESSOR}", 9, GRAY)
    text(c, 345, 556, "年", 12)
    hline(c, 295, 343, 553)
    stamp_boxes(c, 822, 578, ["管理者", "係長", "担当"], w=48, h=48)

    x0, label_w, cw, n = 20, 200, 50, 12
    gx = x0 + label_w
    gx_end = gx + cw * n
    rows = [("head", 20), ("date", 22)] + [("item:" + i, 26) for i in CP_ITEMS] + [("inspector", 26)]
    top = 515
    ys, y = {}, top
    for key, h in rows:
        ys[key] = (y - h, h)
        y -= h
    bottom = y
    box(c, x0, bottom, gx_end - x0, top - bottom, lw=1.2)
    for key, (yb, h) in ys.items():
        hline(c, x0, gx_end, yb, lw=1.2 if key in ("head", "date", "item:" + CP_ITEMS[-1]) else 0.6)
    for i in range(n + 1):
        vline(c, gx + cw * i, bottom, top, lw=1.2 if i == 0 else 0.5)
    yb, h = ys["head"]
    text(c, x0 + label_w / 2, baseline(yb, h, 9), "点検項目　／　月", 9, align="center")
    for m in range(1, 13):
        text(c, gx + cw * (m - 1) + cw / 2, baseline(yb, h, 9), f"{m}月", 9, align="center")
    yb, h = ys["date"]
    text(c, x0 + 8, baseline(yb, h, 9), "点検日", 9)
    for item in CP_ITEMS:
        yb, h = ys["item:" + item]
        text(c, x0 + 8, baseline(yb, h, 9), CP_LABELS.get(item, item), 9)
    yb, h = ys["inspector"]
    text(c, x0 + 8, baseline(yb, h, 9), "点検者", 9)

    text(c, x0, bottom - 18, "記号：✓ 良　A 要調整　△ 修理　× 要取替　ー 対象外", 8)
    text(c, x0, bottom - 34, "吐出圧力の目安：0.65〜0.75 MPa（見本の値です）", 8, GRAY)
    box(c, x0, 30, gx_end - x0, bottom - 74)
    text(c, x0 + 6, bottom - 58, "備考", 9)
    footer(c, W)
    c.showPage()
    c.save()

    def left_x(s, size):
        return round(gx + (cw - width(s, size)) / 2, 1)

    fields = []
    yb, h = ys["date"]
    fields.append({"source": "meta.inspection_date", "page": 0, "x": left_x("2026-01-10", 6.5),
                   "y": round(baseline(yb, h, 6.5), 1), "on_axis": True, "font_size": 6.5})
    for item in CP_ITEMS:
        yb, h = ys["item:" + item]
        sample = "0.70" if item == "吐出圧力" else ("1360" if item == "運転時間" else "✓")
        fields.append({"source": f"item:{COMPRESSOR}|{item}", "page": 0, "x": left_x(sample, 10),
                       "y": round(baseline(yb, h, 10), 1), "on_axis": True, "font_size": 10})
    yb, h = ys["inspector"]
    fields.append({"source": "meta.inspector", "page": 0, "x": left_x("点検 一郎", 7.5),
                   "y": round(baseline(yb, h, 7.5), 1), "on_axis": True, "font_size": 7.5})
    fields.append({"source": "meta.year", "page": 0, "x": 302, "y": 556, "font_size": 12})

    write_layout(form_dir, {
        "form_name": "エアコンプレッサー 月例点検表",
        "period": "year",
        "inspection_type": "月例",
        "targets": [COMPRESSOR],
        "axis": {"count": n, "step_x": cw, "step_y": 0},
        "default_font_size": 10,
        "fields": fields,
    })


def make_form_03(form_dir: Path):
    """1回1枚：フォークリフトの月例点検記録"""
    W, H = 595, 842
    c = new_canvas(form_dir / "form.pdf", (W, H), "フォークリフト 月例点検記録")
    text(c, 40, 790, "フォークリフト 月例点検記録", 18, NAVY)
    text(c, 40, 770, f"事業所：{COMPANY}", 9, GRAY)
    stamp_boxes(c, 555, 812, ["管理者", "担当"], w=50, h=50)

    # 上の記入欄
    x0, x1 = 40, 555
    top = 740
    heads = [("機器", FORKLIFT), ("点検日", ""), ("点検者", ""), ("部署", "")]
    rh = 26
    box(c, x0, top - rh * 2, x1 - x0, rh * 2, lw=1.2)
    hline(c, x0, x1, top - rh)
    mid = (x0 + x1) / 2
    vline(c, mid, top - rh * 2, top)
    for k, (label, value) in enumerate(heads):
        col, row = k % 2, k // 2
        bx = x0 if col == 0 else mid
        yb = top - rh * (row + 1)
        vline(c, bx + 60, yb, yb + rh)
        text(c, bx + 30, baseline(yb, rh, 10), label, 10, align="center")
        if value:
            text(c, bx + 68, baseline(yb, rh, 10), value, 10)
    head_pos = {}
    for k, (label, _v) in enumerate(heads):
        col, row = k % 2, k // 2
        head_pos[label] = ((x0 if col == 0 else mid) + 68, round(baseline(top - rh * (row + 1), rh, 10), 1))

    # 点検項目の表
    t_top = top - rh * 2 - 30
    col_item, col_res, col_rem = x0, x0 + 230, x0 + 300
    rh2 = 34
    box(c, x0, t_top - 22 - rh2 * len(FL_MONTHLY), x1 - x0, 22 + rh2 * len(FL_MONTHLY), lw=1.2)
    hline(c, x0, x1, t_top - 22, lw=1.2)
    vline(c, col_res, t_top - 22 - rh2 * len(FL_MONTHLY), t_top)
    vline(c, col_rem, t_top - 22 - rh2 * len(FL_MONTHLY), t_top)
    text(c, (col_item + col_res) / 2, baseline(t_top - 22, 22, 10), "点検項目", 10, align="center")
    text(c, (col_res + col_rem) / 2, baseline(t_top - 22, 22, 10), "結果", 10, align="center")
    text(c, (col_rem + x1) / 2, baseline(t_top - 22, 22, 10), "備考", 10, align="center")
    item_y = {}
    for k, item in enumerate(FL_MONTHLY):
        yb = t_top - 22 - rh2 * (k + 1)
        if k:
            hline(c, x0, x1, yb + rh2)
        label = "アワーメーター（h）" if item == "アワーメーター" else item
        text(c, col_item + 10, baseline(yb, rh2, 10), label, 10)
        item_y[item] = yb
    t_bottom = t_top - 22 - rh2 * len(FL_MONTHLY)

    # 総合所見
    g_top = t_bottom - 26
    text(c, x0, g_top + 6, "総合所見", 10)
    box(c, x0, g_top - 90, x1 - x0, 90)
    text(c, x0, g_top - 110, "記号：✓ 良　A 要調整　△ 修理　× 要取替　ー 対象外", 8)
    text(c, x0, g_top - 124, "A・△・× を付けた項目は、備考に内容を書き、設備保全課へ連絡する。", 8, GRAY)
    footer(c, W)
    c.showPage()
    c.save()

    fields = [
        {"source": "meta.inspection_date", "page": 0, "x": head_pos["点検日"][0],
         "y": head_pos["点検日"][1], "font_size": 10},
        {"source": "meta.inspector", "page": 0, "x": head_pos["点検者"][0],
         "y": head_pos["点検者"][1], "font_size": 10},
        {"source": "meta.department", "page": 0, "x": head_pos["部署"][0],
         "y": head_pos["部署"][1], "font_size": 10},
    ]
    for item in FL_MONTHLY:
        yb = item_y[item]
        fields.append({"source": f"item:{FORKLIFT}|{item}", "page": 0,
                       "x": round(col_res + 20, 1), "y": round(baseline(yb, rh2, 11), 1),
                       "font_size": 11})
        fields.append({"source": f"remark:{FORKLIFT}|{item}", "page": 0,
                       "x": round(col_rem + 8, 1), "y": round(baseline(yb, rh2, 9), 1),
                       "font_size": 9})
    fields.append({"source": "meta.general_remark", "page": 0, "x": x0 + 8,
                   "y": round(g_top - 22, 1), "font_size": 10})

    write_layout(form_dir, {
        "form_name": "フォークリフト 月例点検記録",
        "period": "single",
        "inspection_type": "月例",
        "targets": [FORKLIFT],
        "default_font_size": 10,
        "fields": fields,
    })


def write_layout(form_dir: Path, layout: dict):
    with open(form_dir / "layout.json", "w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)


# ========== サイネージ ==========

SIGN = (960, 540)   # 16:9


def sign_header(c, title, color=NAVY):
    W, H = SIGN
    c.setFillColor(LIGHT)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(color)
    c.rect(0, H - 84, W, 84, stroke=0, fill=1)
    text(c, 40, H - 56, title, 32, white)
    text(c, W - 40, H - 52, COMPANY, 14, white, align="right")
    text(c, W / 2, 16, NOTE, 9, GRAY, align="center")


def make_signage(out: Path):
    W, H = SIGN
    c = new_canvas(out / "01_safety_goal.pdf", SIGN, "今月の安全目標")
    sign_header(c, "今月の安全目標")
    text(c, W / 2, 330, "合図・確認・声かけ", 64, NAVY, align="center")
    points = ["吊り荷の下に入らない", "始業前点検を必ず行う", "異常はすぐに報告する"]
    cw_, gap = 270, 25
    x = (W - cw_ * 3 - gap * 2) / 2
    for k, p in enumerate(points):
        bx = x + (cw_ + gap) * k
        box(c, bx, 90, cw_, 150, fill=white, stroke=ORANGE, lw=3, radius=12)
        text(c, bx + cw_ / 2, 190, f"{k + 1}", 40, ORANGE, align="center")
        text(c, bx + cw_ / 2, 130, p, 20, LINE, align="center")
    c.showPage()
    c.save()

    c = new_canvas(out / "02_inspection_notice.pdf", SIGN, "点検のお知らせ")
    sign_header(c, "点検のお知らせ（1/3）　点検の予定")
    rows = [("毎日 始業前", "天井クレーン1号機・2号機", "使用前点検"),
            ("毎日 始業前", "フォークリフト1号車", "使用前点検"),
            ("毎月10日ごろ", "エアコンプレッサー1号機", "月例点検"),
            ("毎月15日ごろ", "フォークリフト1号車", "月例点検")]
    tx, ty, widths = 80, 400, [200, 380, 220]
    heads = ["いつ", "機器", "点検"]
    box(c, tx, ty - 60 * len(rows) - 50, sum(widths), 60 * len(rows) + 50, fill=white, lw=1.5)
    c.setFillColor(NAVY)
    c.rect(tx, ty - 50, sum(widths), 50, stroke=0, fill=1)
    cx = tx
    for w_, h_ in zip(widths, heads):
        text(c, cx + w_ / 2, ty - 33, h_, 20, white, align="center")
        cx += w_
    for r, row in enumerate(rows):
        yb = ty - 50 - 60 * (r + 1)
        hline(c, tx, tx + sum(widths), yb + 60)
        cx = tx
        for w_, s in zip(widths, row):
            text(c, cx + w_ / 2, yb + 22, s, 20, align="center")
            cx += w_
    c.showPage()

    sign_header(c, "点検のお知らせ（2/3）　点検はタブレットで", GREEN)
    steps = [("1", "点検画面を開く", "サイネージの右下の\n「点検システム」を押します"),
             ("2", "機器を選ぶ", "上のタブで機器を\n選びます"),
             ("3", "結果を選ぶ", "✓ 良　A 要調整　△ 修理\n× 要取替　ー 対象外"),
             ("4", "名前を選んで保存", "点検者を選び\n「保存」を押します")]
    sw, gap = 200, 20
    x = (W - sw * 4 - gap * 3) / 2
    for k, (num, title, body) in enumerate(steps):
        bx = x + (sw + gap) * k
        box(c, bx, 110, sw, 290, fill=white, stroke=GREEN, lw=3, radius=12)
        c.setFillColor(GREEN)
        c.circle(bx + sw / 2, 345, 32, stroke=0, fill=1)
        text(c, bx + sw / 2, 333, num, 34, white, align="center")
        text(c, bx + sw / 2, 260, title, 20, LINE, align="center")
        for li, line in enumerate(body.split("\n")):
            text(c, bx + sw / 2, 205 - 26 * li, line, 14, GRAY, align="center")
    c.showPage()

    sign_header(c, "点検のお知らせ（3/3）　異常を見つけたら", ORANGE)
    steps = ["機器を止める", "「使用禁止」の札を掛ける", "設備保全課（内線 0000）へ連絡", "点検画面の備考に内容を書く"]
    for k, s in enumerate(steps):
        yb = 360 - 75 * k
        c.setFillColor(ORANGE)
        c.circle(140, yb + 18, 26, stroke=0, fill=1)
        text(c, 140, yb + 7, str(k + 1), 30, white, align="center")
        text(c, 190, yb + 6, s, 30, LINE)
    c.showPage()
    c.save()

    c = new_canvas(out / "03_5s.pdf", SIGN, "5S運動")
    sign_header(c, "5S運動　きれいな職場は安全な職場")
    five = [("整理", "いらない物を\n処分する", HexColor("#2563eb")),
            ("整頓", "決めた場所に\n置く", HexColor("#16a34a")),
            ("清掃", "すぐ使えるよう\nきれいにする", HexColor("#ca8a04")),
            ("清潔", "きれいな状態を\n保つ", HexColor("#ea580c")),
            ("しつけ", "決めたことを\n守る習慣", HexColor("#9333ea"))]
    bw, gap = 164, 16
    x = (W - bw * 5 - gap * 4) / 2
    for k, (word, body, color) in enumerate(five):
        bx = x + (bw + gap) * k
        box(c, bx, 80, bw, 330, fill=color, stroke=None, radius=14)
        text(c, bx + bw / 2, 320, word, 40 if len(word) == 2 else 32, white, align="center")
        for li, line in enumerate(body.split("\n")):
            text(c, bx + bw / 2, 210 - 30 * li, line, 18, white, align="center")
    c.showPage()
    c.save()

    make_factory_png(out / "04_factory.png")
    make_crane_gif(out / "05_crane.gif")

    news = ["【お知らせ】今月の安全目標は「合図・確認・声かけ」です",
            "天井クレーン2号機のブレーキ調整が終わりました",
            "エアコンプレッサー1号機の月例点検は毎月10日ごろに行います",
            "使用前点検の結果は点検画面から保存してください",
            "このニュースは見本です。news.txt を書き換えると内容が変わります"]
    (out / "news.txt").write_text("\n".join(news) + "\n", encoding="utf-8-sig")


def draw_factory(d: ImageDraw.ImageDraw, w: int, h: int, scale: float = 1.0):
    """文字を使わない工場の絵（空・建物・煙突・地面）"""
    for y in range(int(h * 0.75)):
        t = y / (h * 0.75)
        d.line([(0, y), (w, y)], fill=(int(120 + 100 * t), int(170 + 60 * t), 235))
    d.rectangle([0, int(h * 0.75), w, h], fill=(96, 160, 96))
    s = scale
    base = int(h * 0.75)
    # のこぎり屋根の工場
    x0, x1 = int(180 * s), int(1250 * s)
    d.rectangle([x0, base - int(300 * s), x1, base], fill=(205, 210, 220))
    teeth = 6
    tw = (x1 - x0) / teeth
    for k in range(teeth):
        a = x0 + tw * k
        d.polygon([(a, base - 300 * s), (a + tw, base - 300 * s), (a + tw, base - 400 * s)],
                  fill=(150, 160, 175))
        d.rectangle([a + tw - 18 * s, base - 395 * s, a + tw - 6 * s, base - 305 * s], fill=(170, 210, 240))
    for k in range(5):
        wx = x0 + 60 * s + k * 200 * s
        d.rectangle([wx, base - 220 * s, wx + 120 * s, base - 140 * s], fill=(170, 210, 240))
    d.rectangle([x0 + 420 * s, base - 120 * s, x0 + 640 * s, base], fill=(90, 100, 120))
    # 煙突
    d.rectangle([1320 * s, base - 520 * s, 1390 * s, base], fill=(180, 80, 70))
    for k in range(5):
        d.rectangle([1320 * s, base - 500 * s + k * 90 * s, 1390 * s, base - 470 * s + k * 90 * s],
                    fill=(240, 240, 240))
    # 倉庫
    d.rectangle([1460 * s, base - 200 * s, 1780 * s, base], fill=(225, 200, 150))
    d.polygon([(1440 * s, base - 200 * s), (1620 * s, base - 300 * s), (1800 * s, base - 200 * s)],
              fill=(190, 120, 70))
    d.rectangle([1560 * s, base - 140 * s, 1680 * s, base], fill=(120, 90, 60))


def make_factory_png(path: Path):
    w, h = 1920, 1080
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    draw_factory(d, w, h)
    # 太陽
    cx, cy, r = 1700, 180, 90
    for k in range(12):
        a = math.pi * 2 * k / 12
        d.line([(cx + math.cos(a) * 110, cy + math.sin(a) * 110),
                (cx + math.cos(a) * 150, cy + math.sin(a) * 150)], fill=(255, 210, 60), width=12)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 200, 40))
    img.save(path, optimize=True)


def make_crane_gif(path: Path):
    """天井クレーンが荷を運ぶ動き（文字なし）。動画の代わりの見本"""
    w, h = 960, 540
    frames = []
    count = 48
    for f in range(count):
        img = Image.new("RGB", (w, h), (236, 240, 245))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 470, w, h], fill=(150, 150, 150))
        # 柱と走行レール
        d.rectangle([40, 90, 70, 470], fill=(80, 90, 110))
        d.rectangle([w - 70, 90, w - 40, 470], fill=(80, 90, 110))
        d.rectangle([30, 80, w - 30, 110], fill=(230, 160, 40))
        for k in range(30):
            x = 40 + k * 30
            d.line([(x, 110), (x + 15, 80)], fill=(180, 120, 20), width=2)
        # 往復運動
        t = (1 - math.cos(2 * math.pi * f / count)) / 2
        tx = int(150 + (w - 300) * t)
        lift = int(60 * math.sin(math.pi * t))
        d.rectangle([tx - 40, 110, tx + 40, 140], fill=(60, 70, 90))
        rope_end = 330 - lift
        d.line([(tx - 8, 140), (tx - 8, rope_end)], fill=(40, 40, 40), width=3)
        d.line([(tx + 8, 140), (tx + 8, rope_end)], fill=(40, 40, 40), width=3)
        d.rectangle([tx - 18, rope_end, tx + 18, rope_end + 20], fill=(200, 60, 50))
        d.arc([tx - 14, rope_end + 14, tx + 14, rope_end + 44], 0, 270, fill=(40, 40, 40), width=4)
        d.rectangle([tx - 60, rope_end + 44, tx + 60, rope_end + 104], fill=(60, 120, 180))
        frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=32))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=80, loop=0, optimize=True)


# ========== 文書閲覧 ==========

def doc_page(c, title, sections):
    """A4縦の手順書。sections は (見出し, [行...]) の並び"""
    W, H = 595, 842
    c.setFillColor(NAVY)
    c.rect(0, H - 70, W, 70, stroke=0, fill=1)
    text(c, 40, H - 45, title, 20, white)
    text(c, W - 40, H - 45, COMPANY, 10, white, align="right")
    y = H - 110
    for head, lines in sections:
        c.setFillColor(ORANGE)
        c.rect(40, y - 4, 5, 18, stroke=0, fill=1)
        text(c, 52, y, head, 13, NAVY)
        y -= 24
        for line in lines:
            text(c, 56, y, line, 10.5)
            y -= 18
        y -= 12
    footer(c, W, 8)
    return y


def check_table(c, title, rows, top):
    """点検の見どころの表（点検項目／見るところ／よい状態）"""
    W = 595
    x0, widths = 40, [170, 175, 170]
    text(c, x0, top + 14, title, 13, NAVY)
    rh = 30
    total = sum(widths)
    box(c, x0, top - rh * (len(rows) + 1), total, rh * (len(rows) + 1), lw=1)
    c.setFillColor(LIGHT)
    c.rect(x0, top - rh, total, rh, stroke=0, fill=1)
    heads = ["点検項目", "見るところ", "よい状態"]
    cx = x0
    for w_, h_ in zip(widths, heads):
        text(c, cx + 8, top - rh + 11, h_, 10, NAVY)
        cx += w_
    for r, row in enumerate(rows):
        yb = top - rh * (r + 2)
        hline(c, x0, x0 + total, yb + rh)
        cx = x0
        for w_, s in zip(widths, row):
            text(c, cx + 8, yb + 11, s, 9)
            cx += w_
    cx = x0
    for w_ in widths[:-1]:
        cx += w_
        vline(c, cx, top - rh * (len(rows) + 1), top)
    return top - rh * (len(rows) + 1)


def make_documents(out: Path):
    W, H = 595, 842
    path = out / "作業手順書" / "天井クレーン 作業開始前点検の手順.pdf"
    c = new_canvas(path, (W, H), "天井クレーン 作業開始前点検の手順")
    y = doc_page(c, "天井クレーン 作業開始前点検の手順", [
        ("目的", ["その日の作業を始める前に、クレーンが安全に動くかを確かめる。"]),
        ("対象", ["天井クレーン1号機・2号機"]),
        ("準備", ["・作業範囲に人や物がないことを確かめる",
                  "・点検はクレーンに荷を吊っていない状態で行う"]),
        ("手順", ["1. 押しボタンスイッチで、巻上げ・巻下げ・走行・横行を少しずつ動かす",
                  "2. 巻上げを続け、巻過防止装置で止まることを確かめる",
                  "3. 動かして止めたとき、すぐに止まるか（ブレーキ）を確かめる",
                  "4. フック・外れ止め・ワイヤロープを目で見て確かめる",
                  "5. 結果を点検画面に入力し、点検者を選んで保存する"]),
        ("異常があったら", ["・その日はクレーンを使わず、「使用禁止」の札を掛ける",
                          "・設備保全課（内線 0000）へ連絡し、点検画面の備考に内容を書く"]),
    ])
    check_table(c, "点検の見どころ", [
        ("巻過防止装置", "巻き上げたとき", "決まった位置で止まる"),
        ("ブレーキ", "止めたとき", "すぐ止まり、ずれない"),
        ("フックの外れ止め", "外れ止めの金具", "変形・割れがない"),
        ("ワイヤロープ", "ロープ全体", "素線切れ・キンクがない"),
        ("押しボタンスイッチ", "各ボタン・非常停止", "押した通りに動く"),
        ("走行・横行", "動かしたときの音", "異音・引っかかりがない"),
    ], top=y - 20)
    c.showPage()
    c.save()

    path = out / "作業手順書" / "フォークリフト 始業点検の手順.pdf"
    c = new_canvas(path, (W, H), "フォークリフト 始業点検の手順")
    y = doc_page(c, "フォークリフト 始業点検の手順", [
        ("目的", ["運転を始める前に、フォークリフトの安全な状態を確かめる。"]),
        ("対象", ["フォークリフト1号車"]),
        ("手順", ["1. 車体のまわりを一周し、タイヤ・フォーク・チェーン・油漏れを見る",
                  "2. 運転席に座り、ブレーキと駐車ブレーキの効きを確かめる",
                  "3. ホーン・警報・前照灯・後退灯が働くかを確かめる",
                  "4. 結果を点検画面に入力し、点検者を選んで保存する"]),
        ("月例点検", ["毎月15日ごろに、バッテリー液・作動油・マストの給油を確かめ、",
                     "アワーメーターの値を記録する（月例点検記録の様式に印字されます）。"]),
    ])
    check_table(c, "点検の見どころ", [
        ("ブレーキ", "踏んだとき", "まっすぐ確実に止まる"),
        ("タイヤ", "4本とも", "傷・空気圧不足がない"),
        ("ホーン・警報", "鳴らしたとき", "はっきり聞こえる"),
        ("灯火", "前照灯・後退灯", "すべて点灯する"),
        ("フォーク・チェーン", "根元と全体", "曲がり・ゆるみがない"),
        ("油漏れ", "車体の下", "床に油の跡がない"),
    ], top=y - 20)
    c.showPage()
    c.save()

    path = out / "機器の取扱い" / "エアコンプレッサー 取扱いの要点.pdf"
    c = new_canvas(path, (W, H), "エアコンプレッサー 取扱いの要点")
    doc_page(c, "エアコンプレッサー 取扱いの要点", [
        ("対象", ["エアコンプレッサー1号機"]),
        ("運転の前", ["・吸込フィルターに汚れや詰まりがないか見る",
                     "・まわりに物を置かず、風通しを確保する"]),
        ("運転中", ["・吐出圧力が目安（0.65〜0.75 MPa ※見本の値）に入っているか見る",
                   "・いつもと違う音や振動がないか注意する"]),
        ("停止したあと", ["・タンクのドレン（たまった水）を排出する"]),
        ("月例点検で記録する値", ["・吐出圧力（MPa）",
                              "・運転時間（h）：本体の積算計の値をそのまま書く",
                              "記録は「エアコンプレッサー 月例点検表」（1年分の様式）に印字されます。"]),
    ])
    c.showPage()
    c.save()

    path = out / "緊急連絡体制" / "緊急連絡体制表.pdf"
    c = new_canvas(path, (W, H), "緊急連絡体制表")
    c.setFillColor(HexColor("#b91c1c"))
    c.rect(0, H - 70, W, 70, stroke=0, fill=1)
    text(c, 40, H - 45, "緊急連絡体制表", 20, white)
    text(c, W - 40, H - 45, COMPANY, 10, white, align="right")
    chain = [("発見した人", "まず周りに知らせ、機器を止める"),
             ("職場の責任者", "内線 0000"),
             ("設備保全課", "内線 0000（夜間・休日 000-0000-0000）"),
             ("安全衛生課", "内線 0000")]
    y = 690
    for k, (who, how) in enumerate(chain):
        box(c, 130, y - 60, 335, 60, fill=white, stroke=NAVY, lw=2, radius=8)
        text(c, 297, y - 26, who, 16, NAVY, align="center")
        text(c, 297, y - 47, how, 10, GRAY, align="center")
        if k < len(chain) - 1:
            c.setStrokeColor(NAVY)
            c.setLineWidth(2)
            c.line(297, y - 62, 297, y - 88)
            c.setFillColor(NAVY)
            p = c.beginPath()
            p.moveTo(289, y - 82)
            p.lineTo(305, y - 82)
            p.lineTo(297, y - 92)
            p.close()
            c.drawPath(p, stroke=0, fill=1)
        y -= 95
    text(c, 40, y - 10, "外部への通報", 13, NAVY)
    rows = [("火災・救急", "119"), ("事件・事故", "110")]
    for k, (what, num) in enumerate(rows):
        yb = y - 50 - 34 * k
        box(c, 40, yb, 515, 30)
        text(c, 52, yb + 10, what, 12)
        text(c, 540, yb + 10, num, 14, HexColor("#b91c1c"), align="right")
    text(c, 40, y - 140, "※ 内線番号・電話番号は見本です（0000 は実在しない番号として書いています）。", 9, GRAY)
    footer(c, W, 8)
    c.showPage()
    c.save()


# ========== 点検記録（1か月分の見本） ==========

def business_days(start: date, end: date, holidays: set) -> list:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5 and not jpholiday.is_holiday(d) and d.isoformat() not in holidays:
            days.append(d)
        d += timedelta(days=1)
    return days


def make_results(out: Path):
    """2026年10月度（9/24〜10/23）の記録と、コンプレッサーの1〜10月の月例記録を作る"""
    sys.path.insert(0, str(APP_DIR))
    import app as app_module

    work = Path(tempfile.mkdtemp(prefix="samples_"))
    save_dir = work / "results"
    config = {
        "save_directory": str(save_dir),
        "building_info": {"building_name": COMPANY, "managers": []},
        "cycle_start_day": 24,
    }
    config_path = work / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    app_module.CONFIG_PATH = config_path
    client = app_module.app.test_client()

    def post(payload):
        res = client.post("/api/results", json=payload)
        if res.status_code != 200:
            raise RuntimeError(f"保存に失敗: {res.status_code} {res.get_data(as_text=True)}")

    def rows(major, items, results=None, remarks=None):
        results, remarks = results or {}, remarks or {}
        return [{"equipment_name": major, "inspection_item": i,
                 "result": results.get(i, "✓"), "remark": remarks.get(i, "")} for i in items]

    holidays = {"2026-10-09"}
    days = business_days(date(2026, 9, 24), date(2026, 10, 23), holidays)
    staff = ["点検 一郎", "保全 花子", "整備 次郎"]
    crane2_off = {"2026-10-01", "2026-10-15"}   # 2号機を使わなかった日
    for k, d in enumerate(days):
        ds = d.isoformat()
        for m in CRANES:
            if m == CRANES[1] and ds in crane2_off:
                continue
            results, remarks, general = {}, {}, ""
            if m == CRANES[1] and ds == "2026-10-07":
                results = {"ブレーキは正常に効くか": "A"}
                remarks = {"ブレーキは正常に効くか": "止まるまでが少し長い"}
                general = "2号機のブレーキ調整を設備保全課へ依頼した"
            if m == CRANES[1] and ds == "2026-10-08":
                general = "2号機のブレーキ調整済み。動作に問題なし"
            if m == CRANES[0] and ds == "2026-10-16":
                results = {"押しボタンスイッチは正常に働くか": "△"}
                remarks = {"押しボタンスイッチは正常に働くか": "非常停止ボタンのカバーが割れている"}
                general = "1号機の非常停止ボタンのカバー交換を手配した"
            post({"inspection_date": ds, "inspection_type": "使用前",
                  "category_major": "天井クレーン", "category_minor": m,
                  "inspector_name": staff[k % 3], "department": "設備保全課",
                  "general_remark": general,
                  "results": rows("天井クレーン", CRANE_ITEMS, results, remarks)})
        results, remarks, general = {}, {}, ""
        if ds == "2026-10-13":
            results = {"タイヤの損傷・空気圧": "A"}
            remarks = {"タイヤの損傷・空気圧": "右前輪の空気圧が低め"}
            general = "右前輪に空気を補充した"
        post({"inspection_date": ds, "inspection_type": "使用前",
              "category_major": "フォークリフト", "category_minor": FORKLIFT,
              "inspector_name": "運搬 三郎", "department": "物流課",
              "general_remark": general,
              "results": rows("フォークリフト", FL_DAILY, results, remarks)})

    for month in range(1, 11):
        values = {"吐出圧力": f"{0.68 + 0.01 * (month % 4):.2f}", "運転時間": str(1200 + 160 * month)}
        remarks, general = {}, ""
        if month == 6:
            values["吸込フィルターの汚れ"] = "A"
            remarks = {"吸込フィルターの汚れ": "汚れあり。清掃した"}
            general = "吸込フィルターを清掃した"
        post({"inspection_date": f"2026-{month:02d}-10", "inspection_type": "月例",
              "display_year": 2026, "display_month": month,
              "category_major": "コンプレッサー", "category_minor": COMPRESSOR,
              "inspector_name": "整備 次郎", "department": "設備保全課",
              "general_remark": general,
              "results": rows("コンプレッサー", CP_ITEMS, values, remarks)})

    for month, hours in ((9, "3420"), (10, "3510")):
        post({"inspection_date": f"2026-{month:02d}-15", "inspection_type": "月例",
              "display_year": 2026, "display_month": month,
              "category_major": "フォークリフト", "category_minor": FORKLIFT,
              "inspector_name": "運搬 三郎", "department": "物流課",
              "general_remark": "",
              "results": rows("フォークリフト", FL_MONTHLY, {"アワーメーター": hours})})

    # 保存APIが作るバックアップ・ロックファイルは持っていかない
    for month_dir in sorted(p for p in save_dir.iterdir() if p.is_dir()):
        for f in month_dir.glob("*.json"):
            dest = out / month_dir.name / f.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
    print("一時フォルダ（不要なら手で消してください）:", work)


def main():
    for name, func in (("form_01", make_form_01), ("form_02", make_form_02), ("form_03", make_form_03)):
        d = SAMPLES / "forms" / name
        d.mkdir(parents=True, exist_ok=True)
        func(d)
    make_signage(SAMPLES / "signage")
    make_documents(SAMPLES / "documents")
    make_results(SAMPLES / "results")
    print("作成しました:", SAMPLES)


if __name__ == "__main__":
    main()
