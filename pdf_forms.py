"""様式PDFへの点検結果の重ね書き。

軸の各欄に入るデータを組み立てる build_slots と、
それを reportlab で描いて pypdf で様式に重ねる処理からなる。
"""
import io
import logging
from datetime import date

import jpholiday
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas as rl_canvas

import forms_layout

logger = logging.getLogger("equipment_inspection")

MARK_SATURDAY = "saturday"
MARK_HOLIDAY = "holiday"


def _day_mark(target_date, custom_holidays: dict) -> str:
    """その日が土曜なら saturday、日曜・祝日・会社休業日なら holiday を返す。

    土曜かつ祝日のような重なりは holiday（赤）を優先する。
    """
    date_str = target_date.strftime("%Y-%m-%d")
    if (target_date.weekday() == 6
            or jpholiday.is_holiday(target_date)
            or date_str in custom_holidays):
        return MARK_HOLIDAY
    if target_date.weekday() == 5:
        return MARK_SATURDAY
    return ""


def _empty_slot() -> dict:
    """1欄分の空のデータを作る"""
    return {"date": None, "month": None, "exists": False, "mark": "",
            "index": 0, "has_record": False, "unused": False,
            "values": {}, "remarks": {}, "meta": {}, "machines": []}


def _attach(slot: dict, record):
    """欄に点検記録を入れる（記録が無ければ何もしない）"""
    if not record:
        return
    slot["values"] = record.get("values", {})
    slot["remarks"] = record.get("remarks", {})
    slot["meta"] = record.get("meta", {})
    slot["machines"] = record.get("machines", [])
    slot["has_record"] = True


def build_slots(layout: dict, display_year: int, display_month: int,
                cycle_dates: list, results_by_key: dict,
                custom_holidays: dict, today=None, sample: bool = False) -> dict:
    """軸の各欄（n: 1始まり）に入るデータを組み立てる。

    戻り値の各欄は次のキーを持つ。
      date   … その欄の日付（year 型は None）
      month  … その欄の月（month 型は None）
      exists … その欄が実在するか（余りマスは False）
      mark   … "" / "saturday" / "holiday"
      index  … その欄の番号（1始まり）
      has_record … その欄に点検記録があるか
      unused … 使用前点検で、24時を過ぎたのに記録が無い日か（＝使用せず）
      values … {"<機器名>|<点検項目名>": 結果} の辞書
      remarks… {"<機器名>|<点検項目名>": 備考} の辞書
      machines… その欄に記録がある機器名（保存順）
      meta   … 点検者名などの共通項目

    results_by_key のキーは、month 型なら "YYYY-MM-DD"、year 型なら月(1〜12)。
    today は「使用せず」の判定に使う。省略時は今日。
    sample=True は試し刷り用で、位置合わせのため全欄を使用せず扱いにする。
    """
    period = layout.get("period", "")
    count = forms_layout.axis_count(layout)
    # 「使用せず」は使用前点検（日ごと）だけの概念。月例には出さない。
    is_daily = layout.get("inspection_type", "使用前") == "使用前"
    if today is None:
        today = date.today()
    slots = {}
    for n in range(1, count + 1):
        slot = _empty_slot()
        slot["index"] = n      # 前月の表示は「1マス目かどうか」で決まる
        if period == "month":
            if n <= len(cycle_dates):
                d = cycle_dates[n - 1]
                slot["date"] = d
                slot["exists"] = True
                slot["mark"] = _day_mark(d, custom_holidays)
                _attach(slot, results_by_key.get(d.strftime("%Y-%m-%d")))
                # その日の24時を過ぎた（＝今日より前の日）のに記録が無ければ使用せず。
                # 当日と未来の日は、まだ点検されうるので空欄のままにする。
                slot["unused"] = is_daily and (
                    sample or (not slot["has_record"] and d < today))
        elif period == "year":
            slot["month"] = n
            slot["exists"] = True
            _attach(slot, results_by_key.get(n))
        slots[n] = slot
    return slots


def _record_payload(record: dict) -> dict:
    """1件の点検記録を values / remarks / meta に分解する。

    キーの機器名には category_minor を使う。results の中の equipment_name には
    大分類（category_major）が入っており、様式の targets と一致しないため。
    """
    equipment = record.get("category_minor", "")
    values, remarks = {}, {}
    rows = record.get("results", [])
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = f"{equipment}|{row.get('inspection_item', '')}"
            values[key] = row.get("result", "")
            remarks[key] = row.get("remark", "")
    meta = {
        "inspection_date": record.get("inspection_date", ""),
        "inspector": record.get("inspector_name", ""),
        "department": record.get("department", ""),
        "building_name": record.get("building_name", ""),
        "general_remark": record.get("general_remark", ""),
    }
    return {"values": values, "remarks": remarks, "meta": meta}


def _merge_remark(notes) -> str:
    """機器ごとの備考をまとめる。

    notes は [(機器名, 備考), ...] を保存順で受け取る。
    備考を書いた機器が1つだけなら、機器名を付けずにそのまま返す
    （1機器だけの様式の見た目を変えないため）。
    """
    written = [(name, text) for name, text in notes if text]
    if not written:
        return ""
    if len(written) == 1:
        return written[0][1]
    return "／".join(f"{name}：{text}" for name, text in written)


def _index(records: list, targets: list, key_func) -> dict:
    """点検記録を「欄のキー → 欄データ」に変換する。

    1つの様式に複数の機器が載る場合、同じ日でも機器ごとに別々の記録になる。
    values / remarks は機器名で名前空間が分かれているので統合できる。
    submitted_at の昇順に処理するので、同じキーは新しい記録が上書きする。
    備考は欄に1つしか出せないため、機器ごとの記入を _merge_remark でまとめ直す。
    """
    targets = set(targets)
    store = {}
    for record in sorted(records, key=lambda r: str(r.get("submitted_at", ""))):
        equipment = record.get("category_minor")
        if equipment not in targets:
            continue
        key = key_func(record)
        if key is None:
            continue
        payload = _record_payload(record)
        slot = store.setdefault(key, {"values": {}, "remarks": {}, "meta": {},
                                      "machines": [], "notes": {}})
        slot["values"].update(payload["values"])
        slot["remarks"].update(payload["remarks"])
        slot["meta"] = payload["meta"]
        if equipment not in slot["machines"]:
            slot["machines"].append(equipment)
        slot["notes"][equipment] = payload["meta"].get("general_remark", "")
    for slot in store.values():
        # _record_payload が返した辞書をそのまま書き換えないよう複製する
        slot["meta"] = dict(slot["meta"])
        slot["meta"]["general_remark"] = _merge_remark(
            [(name, slot["notes"].get(name, "")) for name in slot["machines"]])
    return store


def index_by_date(records: list, targets: list) -> dict:
    """点検記録を「日付文字列 → 欄データ」に変換する（month 型で使う）"""
    return _index(records, targets,
                  lambda r: r.get("inspection_date") or None)


def index_by_month(records: list, targets: list) -> dict:
    """点検記録を「月(1〜12) → 欄データ」に変換する（year 型で使う）"""
    def month_of(record):
        parts = str(record.get("inspection_date", "")).split("-")
        if len(parts) < 2:
            return None
        try:
            month = int(parts[1])
        except ValueError:
            return None
        return month if 1 <= month <= 12 else None

    return _index(records, targets, month_of)


FONT_NAME = "HeiseiKakuGo-W5"
DEFAULT_FONT_SIZE = 11
NOT_APPLICABLE_MARK = forms_layout.NOT_APPLICABLE_MARK
ALL_TARGETS = forms_layout.ALL_TARGETS
COLOR_SATURDAY = "#0000ff"
COLOR_HOLIDAY = "#ff0000"
WEEKDAY_NAMES = "月火水木金土日"   # date.weekday() は月曜が0
CIRCLE_RATIO = 0.9

_font_registered = False


def _ensure_font():
    """日本語フォントを登録する（初回のみ）"""
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))
        _font_registered = True


def _apply_marks(field: dict, raw: str) -> str:
    """判定結果を様式ごとの印字文字に置き換える。

    様式によっては「良」を✓ではなく別の字で書くことがあるため、
    layout.json 側で mark_ok / mark_adjust / mark_repair / mark_ng / mark_na を
    指定できる。要取替のキーが mark_ng なのは、既存の layout.json との互換のため。
    """
    raw = forms_layout.normalize_judgment(raw)
    if raw == forms_layout.MARK_OK:
        return field.get("mark_ok", forms_layout.MARK_OK)
    if raw == forms_layout.MARK_ADJUST:
        return field.get("mark_adjust", forms_layout.MARK_ADJUST)
    if raw == forms_layout.MARK_REPAIR:
        return field.get("mark_repair", forms_layout.MARK_REPAIR)
    if raw == forms_layout.MARK_REPLACE:
        return field.get("mark_ng", forms_layout.MARK_REPLACE)
    if raw == NOT_APPLICABLE_MARK:
        return field.get("mark_na", NOT_APPLICABLE_MARK)
    return raw


def _field_value(field: dict, slot, meta: dict) -> str:
    """フィールドの source に対応する印字文字列を返す。空文字なら印字しない。"""
    source = field.get("source", "")
    slot = slot or {}
    if source.startswith("item:"):
        body = source[5:]
        equip, _, item = body.partition("|")
        if equip == forms_layout.ALL_TARGETS:
            # その日に記録がある機器の判定を集めて、いちばん悪いものを印字する。
            # 機器ごとに結果が違うときの説明は備考に書く運用。
            values = [slot.get("values", {}).get(f"{m}|{item}", "")
                      for m in slot.get("machines", [])]
            return _apply_marks(field, forms_layout.worst_judgment(values))
        return _apply_marks(field, slot.get("values", {}).get(body, ""))
    if source.startswith("target:"):
        # 対象機器欄。その日にその機器の記録があればチェックを入れる。
        if source[7:] not in slot.get("machines", []):
            return ""
        return field.get("mark_target", forms_layout.MARK_OK)
    if source.startswith("remark:"):
        return slot.get("remarks", {}).get(source[7:], "")
    if source == "meta.day":
        d = slot.get("date")
        return str(d.day) if d else ""
    if source == "meta.year":
        return str(meta.get("year", ""))
    if source == "meta.month":
        return str(meta.get("month", ""))
    if source == "meta.month_start":
        # 締め日区切りなので、月の変わり目は月によって違うマスに来る。
        # 「日にちが1のマス」でだけ出せば、位置は自動で追従する。
        d = slot.get("date")
        return f"{d.month}月" if d and d.day == 1 else ""
    if source == "meta.month_prev":
        d = slot.get("date")
        return f"{d.month}月" if d and slot.get("index") == 1 else ""
    if source == "meta.unused":
        # 使用せず欄。該当しない日は何も書かない。
        if not slot.get("unused"):
            return ""
        return field.get("mark_unused", forms_layout.MARK_OK)
    if source.startswith("meta."):
        key = source[5:]
        return str(slot.get("meta", {}).get(key, meta.get(key, "")))
    logger.warning("未知の source を飛ばしました: %s", source)
    return ""


def _draw_field(c, field: dict, x: float, y: float, text: str, default_size: int):
    """1つのフィールドを描く。空文字なら何もしない。"""
    if not text:
        return
    size = float(field.get("font_size", default_size))
    c.setFont(FONT_NAME, size)
    c.setFillColor(HexColor(field.get("color", "#000000")))
    if field.get("vertical"):
        # 1文字ずつ下に積む。PDFのYは上が正なので、下へは減らす。
        # クリック位置の意味は横書きと同じ（1文字目の左下）。
        for i, ch in enumerate(text):
            c.drawString(x, y - size * i, ch)
        return
    c.drawString(x, y, text)


def _circle_color(mark: str) -> str:
    """欄の印から丸の色を返す。平日は空文字（丸を描かない）。"""
    if mark == MARK_SATURDAY:
        return COLOR_SATURDAY
    if mark == MARK_HOLIDAY:
        return COLOR_HOLIDAY
    return ""


def _circle_radius(field: dict, font_size: float) -> float:
    """丸の半径。省略時は文字サイズ×0.9。"""
    value = field.get("circle_radius")
    if value is None:
        return font_size * CIRCLE_RATIO
    try:
        return float(value)
    except (TypeError, ValueError):
        return font_size * CIRCLE_RATIO


def _draw_day_field(c, field: dict, x: float, y: float, slot: dict,
                    default_size: int):
    """日にちを丸の中心に描き、土日祝は丸で囲む。

    x, y は丸の中心を指す（他のフィールドは文字の左下基準）。
    """
    d = slot.get("date")
    if not d:
        return
    size = float(field.get("font_size", default_size))
    circle_color = _circle_color(slot.get("mark", ""))
    color = circle_color or field.get("color", "#000000")
    c.setFont(FONT_NAME, size)
    c.setFillColor(HexColor(color))
    # drawCentredString の y は文字の下端なので、中心に来るよう少し下げる
    c.drawCentredString(x, y - size * 0.35, str(d.day))
    if circle_color:
        # 生の16進文字列のまま渡す（HexColor化するとテストの色比較が
        # Color(...) の repr 同士の比較になり、意図した検証ができないため）。
        # reportlab の Canvas.setStrokeColor は文字列を toColor() で解釈するので
        # 実描画結果は HexColor(circle_color) を渡した場合と同一になる。
        c.setStrokeColor(circle_color)
        c.setLineWidth(1.0)
        c.circle(x, y, _circle_radius(field, size), stroke=1, fill=0)


def _draw_weekday_field(c, field: dict, x: float, y: float, slot: dict,
                        default_size: int):
    """曜日を1文字、日にちと同じ中央基準で描く。

    色の規則は日にちと同じ（_circle_color を使い回す）。別に判定を書くと、
    祝日の扱いを変えたときに日にちと曜日で色が食い違う。
    丸は描かない（丸は日にちだけ）。
    x, y は文字の中央を指す。
    """
    d = slot.get("date")
    if not d:
        return
    size = float(field.get("font_size", default_size))
    color = _circle_color(slot.get("mark", "")) or field.get("color", "#000000")
    c.setFont(FONT_NAME, size)
    c.setFillColor(HexColor(color))
    # drawCentredString の y は文字の下端なので、中心に来るよう少し下げる
    c.drawCentredString(x, y - size * 0.35, WEEKDAY_NAMES[d.weekday()])


def _draw_slot_field(c, field: dict, x: float, y: float, slot, meta: dict,
                     default_size: int):
    """軸の1欄分を描く"""
    slot = slot or {}
    source = field.get("source", "")
    if not slot.get("exists", False):
        # 余りマス（その月に存在しない日）。item だけ「ー」を入れて
        # 「記入漏れの空欄」と見分けられるようにする。
        if source.startswith("item:"):
            _draw_field(c, field, x, y,
                        field.get("mark_na", NOT_APPLICABLE_MARK), default_size)
        return
    if source == "meta.day":
        _draw_day_field(c, field, x, y, slot, default_size)
        return
    if source == "meta.weekday":
        _draw_weekday_field(c, field, x, y, slot, default_size)
        return
    _draw_field(c, field, x, y, _field_value(field, slot, meta), default_size)


def build_form_pdf(form_pdf_path, layout: dict, slots: dict, meta: dict) -> PdfWriter:
    """様式PDFに文字を重ねた PdfWriter を返す。様式PDF自体は書き換えない。"""
    _ensure_font()
    reader = PdfReader(str(form_pdf_path))
    if not reader.pages:
        # ページを持たないPDFを黙って処理すると「様式が出ないのに
        # エラーも出ない」状態になり、原因にたどり着けない。
        raise ValueError(f"様式PDFにページがありません: {form_pdf_path}")
    writer = PdfWriter()
    default_size = int(layout.get("default_font_size", DEFAULT_FONT_SIZE))
    axis = layout.get("axis") or {}
    page_count = len(reader.pages)

    # ページごとにフィールドを振り分ける。範囲外の page は1回だけ警告する。
    by_page = {}
    for field in layout.get("fields", []):
        page = field.get("page", 0)
        if not isinstance(page, int) or not (0 <= page < page_count):
            logger.warning("様式のページ範囲外の配置を飛ばしました: source=%s page=%s",
                           field.get("source"), page)
            continue
        by_page.setdefault(page, []).append(field)

    for page_index, page in enumerate(reader.pages):
        fields = by_page.get(page_index, [])
        if not fields:
            writer.add_page(page)
            continue
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(width, height))
        for field in fields:
            if field.get("on_axis"):
                for n in sorted(slots):
                    x, y = forms_layout.axis_position(field, axis, n)
                    _draw_slot_field(c, field, x, y, slots[n], meta, default_size)
            else:
                x, y = forms_layout.axis_position(field, axis, 1)
                _draw_field(c, field, x, y,
                            _field_value(field, slots.get(1), meta), default_size)
        # 何も描かないまま save() すると0ページのPDFになり、次行の pages[0] で
        # 落ちる。1件も記録が無い月や、使用せず欄だけのページで実際に起きる。
        c.showPage()
        c.save()
        buf.seek(0)
        writer.add_page(page)
        writer.pages[-1].merge_page(PdfReader(buf).pages[0])
    return writer


def build_form_writer(form_dir, layout: dict, records: list, display_year: int,
                      display_month: int, cycle_dates: list,
                      custom_holidays: dict, today=None, sample: bool = False):
    """1つの様式について、印字済みページを持つ PdfWriter を返す。

    single 型は点検日ごとに様式を複製する。点検日が1日も無ければ None を返す
    （白紙を何枚出すか決められないため）。
    today は「使用せず」の判定に使う。省略時は今日。
    sample=True は試し刷り用（全欄を使用せず扱いにする）。
    """
    from pathlib import Path
    form_pdf = Path(form_dir) / forms_layout.FORM_PDF_FILENAME
    if not form_pdf.exists():
        raise FileNotFoundError(f"様式PDFがありません: {form_pdf}")

    period = layout.get("period")
    targets = layout.get("targets", [])
    meta = {"year": display_year, "month": display_month}

    if period == "month":
        indexed = index_by_date(records, targets)
        slots = build_slots(layout, display_year, display_month,
                            cycle_dates, indexed, custom_holidays, today, sample)
        return build_form_pdf(form_pdf, layout, slots, meta)

    if period == "year":
        indexed = index_by_month(records, targets)
        slots = build_slots(layout, display_year, display_month,
                            cycle_dates, indexed, custom_holidays, today, sample)
        return build_form_pdf(form_pdf, layout, slots, meta)

    # single: 点検日ごとに1枚
    indexed = index_by_date(records, targets)
    if not indexed:
        return None
    writer = PdfWriter()
    for date_str in sorted(indexed):
        payload = indexed[date_str]
        slot = {"date": None, "month": None, "exists": True, "mark": "",
                "values": payload.get("values", {}),
                "remarks": payload.get("remarks", {}),
                "meta": payload.get("meta", {}),
                "machines": payload.get("machines", [])}
        one = build_form_pdf(form_pdf, layout, {1: slot}, meta)
        for page in one.pages:
            writer.add_page(page)
    return writer


SAMPLE_INSPECTOR = "見本 太郎"
SAMPLE_DEPARTMENT = "見本部"
SAMPLE_BUILDING = "見本ビル"
SAMPLE_NUMBER = "0.00"
SAMPLE_JUDGMENT = forms_layout.MARK_OK


def layout_item_names(layout: dict) -> list:
    """layout.json の fields から (機器名, 点検項目名) の一覧を取り出す。

    item: と remark: の両方を見るが、同じ組は1回だけ返す。
    item:*|項目 は「全機器まとめ」なので、targets の全機器に展開する。
    """
    targets = layout.get("targets", [])
    seen, names = set(), []
    for field in layout.get("fields", []):
        source = field.get("source", "")
        for prefix in ("item:", "remark:"):
            if not source.startswith(prefix):
                continue
            body = source[len(prefix):]
            if "|" not in body:
                continue
            equip, item = body.split("|", 1)
            equips = targets if equip == ALL_TARGETS else [equip]
            for e in equips:
                if (e, item) in seen:
                    continue
                seen.add((e, item))
                names.append((e, item))
    return names


def build_sample_records(layout: dict, cycle_dates: list, display_year: int,
                         number_items: set) -> list:
    """試し刷り用のダミー記録を作る。全欄が埋まるように日付を網羅する。"""
    targets = layout.get("targets", [])
    item_names = layout_item_names(layout)
    if layout.get("period") == "year":
        dates = [f"{display_year}-{m:02d}-01" for m in range(1, 13)]
    else:
        dates = [d.strftime("%Y-%m-%d") for d in cycle_dates]
    if not dates:
        dates = [f"{display_year}-01-01"]

    records = []
    for name in targets:
        rows = [(equip, item) for (equip, item) in item_names if equip == name]
        for date_str in dates:
            results = [
                {"equipment_name": name, "inspection_item": item,
                 "result": SAMPLE_NUMBER if item in number_items
                           else SAMPLE_JUDGMENT,
                 "remark": ""}
                for (_equip, item) in rows
            ]
            records.append({
                "inspection_date": date_str,
                "inspection_type": layout.get("inspection_type", "使用前"),
                "category_major": "",
                "category_minor": name,
                "inspector_name": SAMPLE_INSPECTOR,
                "department": SAMPLE_DEPARTMENT,
                "general_remark": "",
                "building_name": SAMPLE_BUILDING,
                "results": results,
                "submitted_at": f"{date_str}T09:00:00",
            })
    return records
