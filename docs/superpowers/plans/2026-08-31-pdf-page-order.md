# 点検結果PDF 特記事項ページと様式の並び順 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 点検結果PDFの1枚目に特記事項をまとめたページを出し、続く様式PDFの順番を設定画面から指定できるようにする。

**Architecture:** 特記事項ページは既存の表出力とは別のPDFとして作り、合成のときに先頭へ足す（表出力のコードには触らない）。様式の並びは `config.json` の `form_order` で決め、`_build_form_writers` が一覧を並べ替える。設定画面には ▲▼ で入れ替える一覧を足す。

**Tech Stack:** Python 3 / Flask / reportlab / pypdf / pytest / 素のJavaScript（ビルドなし）

**設計書:** `docs/superpowers/specs/2026-08-31-pdf-page-order-design.md`

**ブランチ:** `feature/layout-ui`（すでにこのブランチにいる。新しく切らない）

**着手前の基準値:** `.venv/Scripts/python.exe -m pytest tests/ -q` が **325 passed**（2026-08-31 実測）。

---

## 前提知識（この計画を実行する人へ）

- **点検サイクルは暦月ではなく締め日区切り**（既定24日始まり）。2026年3月分は 2/24〜3/23 の28日。`get_cycle_range(年, 月)` が開始日と終了日を返す。
- **使用前点検の記録は月ごとのファイルに入っており、サイクル外の日も同じファイルに混ざる。**日付で絞らないと前月・翌月の記録を拾う。
- **機器名として使うのは `category_minor`。** 記録の中の `equipment_name` には大分類が入っていて別物。
- **`_generate_pdf`（表出力）には手を入れない。**既存の出力が1バイトも変わらないことが、この変更の絶対条件。
- テストは1ファイル `tests/test_app.py`。実行は `.venv/Scripts/python.exe -m pytest tests/ -q`。
- テストの `client` フィクスチャは `(テストクライアント, tmp_path)` を返す。保存先を分けるには
  `monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)` を使う（既存テストと同じ）。

---

## ファイル構成

| ファイル | この計画での役割 |
|---|---|
| `app.py` | 特記事項を集める・描く関数を新設。様式の並べ替え。設定APIの検証。PDFの合成順 |
| `static/inspection.html` | 設定モーダルに「様式の並び順」の枠を足す。`app.js?v=` を上げる |
| `static/app.js` | 並び順の一覧を描く・▲▼で入れ替える・保存時に送る |
| `tests/test_app.py` | 全タスクのテストを追記する |

---

### Task 1: 特記事項を集める（`app.py`）

**Files:**
- Modify: `app.py`（`_get_pdf_styles()` の直前に3つの関数を追加）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_app.py` の末尾に追記する。

```python
# ========== 特記事項ページ：記録の集め方 ==========

def _write_results(tmp_path, itype, year, month, records):
    """点検結果のJSONを直接置く（保存APIを通さない）"""
    import app as flask_app
    fp = flask_app.get_result_file_path(itype, year, month)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def _remark_record(date_str, minor, text, major="クレーン"):
    """特記事項つきの点検記録を1件作る"""
    return {"inspection_date": date_str, "category_major": major,
            "category_minor": minor, "inspector_name": "見本 太郎",
            "department": "見本部", "general_remark": text,
            "results": [], "submitted_at": f"{date_str}T09:00:00"}


def test_collect_remarks_picks_up_daily(client, monkeypatch, tmp_path):
    """使用前点検の特記事項を拾うこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3,
                   [_remark_record("2026-03-02", "クレーン1", "異音あり")])
    rows = flask_app._collect_remarks(2026, 3)
    assert len(rows) == 1
    assert rows[0]["machine"] == "クレーン1"
    assert rows[0]["type"] == "使用前"
    assert rows[0]["text"] == "異音あり"


def test_collect_remarks_skips_outside_cycle(client, monkeypatch, tmp_path):
    """サイクル外の日の記録を拾わないこと（3月分は 2/24〜3/23）"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3, [
        _remark_record("2026-03-02", "クレーン1", "サイクル内"),
        _remark_record("2026-03-25", "クレーン1", "サイクル外"),
    ])
    rows = flask_app._collect_remarks(2026, 3)
    assert [r["text"] for r in rows] == ["サイクル内"]


def test_collect_remarks_skips_empty(client, monkeypatch, tmp_path):
    """特記事項が空・空白だけの記録は行を作らないこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3, [
        _remark_record("2026-03-02", "クレーン1", ""),
        _remark_record("2026-03-03", "クレーン1", "   "),
        _remark_record("2026-03-04", "クレーン1", "あり"),
    ])
    rows = flask_app._collect_remarks(2026, 3)
    assert [r["text"] for r in rows] == ["あり"]


def test_collect_remarks_includes_monthly(client, monkeypatch, tmp_path):
    """月例点検の特記事項も拾い、種別で見分けられること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3,
                   [_remark_record("2026-03-02", "クレーン1", "日次のほう")])
    _write_results(tmp_path, "月例", 2026, 3,
                   [_remark_record("2026-03-10", "クレーン1", "月例のほう")])
    rows = flask_app._collect_remarks(2026, 3)
    assert {(r["type"], r["text"]) for r in rows} == {
        ("使用前", "日次のほう"), ("月例", "月例のほう")}


def test_collect_remarks_sorts_by_master_then_date(client, monkeypatch, tmp_path):
    """機器は点検項目マスタの順、機器の中は日付順に並ぶこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3, [
        _remark_record("2026-03-05", "クレーン2", "2番機の5日"),
        _remark_record("2026-03-03", "クレーン1", "1番機の3日"),
        _remark_record("2026-03-02", "クレーン1", "1番機の2日"),
    ])
    rows = flask_app._collect_remarks(2026, 3)
    # マスタでの登場順を実際に読んで、その順になっていることを確かめる
    master = [r.get("category_minor", "")
              for r in flask_app.read_csv_as_list(flask_app.EQUIPMENT_CSV)]
    pos = {m: i for i, m in enumerate(dict.fromkeys(master))}
    assert pos["クレーン1"] < pos["クレーン2"], "前提：マスタでクレーン1が先"
    assert [r["text"] for r in rows] == ["1番機の2日", "1番機の3日", "2番機の5日"]


def test_collect_remarks_unknown_machine_goes_last(client, monkeypatch, tmp_path):
    """マスタに無い機器は末尾に回ること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3, [
        _remark_record("2026-03-02", "存在しない機器", "知らない子"),
        _remark_record("2026-03-03", "クレーン1", "マスタにいる"),
    ])
    rows = flask_app._collect_remarks(2026, 3)
    assert [r["machine"] for r in rows] == ["クレーン1", "存在しない機器"]


def test_collect_remarks_daily_before_monthly(client, monkeypatch, tmp_path):
    """同じ機器・同じ日なら 使用前 → 月例 の順になること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3,
                   [_remark_record("2026-03-02", "クレーン1", "日次")])
    _write_results(tmp_path, "月例", 2026, 3,
                   [_remark_record("2026-03-02", "クレーン1", "月例")])
    rows = flask_app._collect_remarks(2026, 3)
    assert [r["text"] for r in rows] == ["日次", "月例"]


def test_collect_remarks_empty_month(client, monkeypatch, tmp_path):
    """記録が1件も無ければ空のリストを返すこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    assert flask_app._collect_remarks(2026, 3) == []
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k collect_remarks`
Expected: FAIL（`AttributeError: module 'app' has no attribute '_collect_remarks'`）

- [ ] **Step 3: 実装する**

`app.py` の `_get_pdf_styles()` の**直前**に追加する。

```python
def _parse_result_date(value):
    """点検日の文字列を date にする。読めなければ None を返す。"""
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _remark_row(record: dict, d, inspection_type: str):
    """1件の点検記録から特記事項の行を作る。書かれていなければ None。"""
    text = record.get("general_remark", "")
    if not isinstance(text, str) or not text.strip():
        return None
    # 機器名は category_minor。results の equipment_name は大分類なので使わない。
    return {"machine": record.get("category_minor", ""), "date": d,
            "type": inspection_type, "text": text.strip()}


def _collect_remarks(display_year: int, display_month: int) -> list:
    """その月の特記事項を、機器ごと・日付順に並べて返す。

    機器の並びは点検項目マスタの登場順（表出力と食い違わせないため）。
    マスタに無い機器は末尾に回す。記録が消えるより並びが崩れるほうがましなため。
    使用前はサイクル（締め日区切り）の範囲だけを拾う。月例は表示月のファイル全部。
    """
    start_date, end_date = get_cycle_range(display_year, display_month)

    order = {}
    for row in read_csv_as_list(EQUIPMENT_CSV):
        name = row.get("category_minor", "")
        if name and name not in order:
            order[name] = len(order)

    rows = []
    daily = (_read_json_safe(get_result_file_path(
                 "使用前", start_date.year, start_date.month))
             + _read_json_safe(get_result_file_path(
                 "使用前", display_year, display_month)))
    for record in daily:
        d = _parse_result_date(record.get("inspection_date", ""))
        # サイクル外の日も同じ月のファイルに入っている。ここで落とさないと混じる。
        if d is None or not (start_date <= d <= end_date):
            continue
        row = _remark_row(record, d, "使用前")
        if row:
            rows.append(row)

    for record in _read_json_safe(get_result_file_path(
            "月例", display_year, display_month)):
        d = _parse_result_date(record.get("inspection_date", ""))
        if d is None:
            continue
        row = _remark_row(record, d, "月例")
        if row:
            rows.append(row)

    unknown = len(order)
    type_rank = {"使用前": 0, "月例": 1}
    rows.sort(key=lambda r: (
        order.get(r["machine"], unknown),
        r["machine"] if r["machine"] not in order else "",
        r["date"],
        type_rank.get(r["type"], 9)))
    return rows
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（333 passed）

- [ ] **Step 5: コミット**

```bash
git add app.py tests/test_app.py
git commit -m "feat: collect monthly remarks grouped by equipment"
```

---

### Task 2: 特記事項のページを描く（`app.py`）

**Files:**
- Modify: `app.py`（`_collect_remarks()` の直後に `_build_remark_page()` を追加）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 特記事項ページ：描画 ==========

def _remark_page_text(year, month):
    """特記事項ページのPDFから文字を取り出す"""
    import app as flask_app
    from pypdf import PdfReader
    buf = flask_app._build_remark_page(year, month)
    return "".join((p.extract_text() or "")
                   for p in PdfReader(buf).pages)


def test_remark_page_has_title(client, monkeypatch, tmp_path):
    """建物名と年月と「特記事項」が入ること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    text = "".join(_remark_page_text(2026, 3).split())
    assert "テスト" in text        # client フィクスチャの建物名
    assert "2026年3月" in text
    assert "特記事項" in text


def test_remark_page_says_none_when_empty(client, monkeypatch, tmp_path):
    """記録が無い月は「特記事項なし」と出て、ページは1枚できること"""
    import app as flask_app
    from pypdf import PdfReader
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    buf = flask_app._build_remark_page(2026, 3)
    reader = PdfReader(buf)
    assert len(reader.pages) == 1
    text = "".join((reader.pages[0].extract_text() or "").split())
    assert "特記事項なし" in text


def test_remark_page_lists_rows(client, monkeypatch, tmp_path):
    """機器・点検日・種別・内容が印字されること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3,
                   [_remark_record("2026-03-02", "クレーン1", "異音あり")])
    text = "".join(_remark_page_text(2026, 3).split())
    assert "クレーン1" in text
    assert "2026/3/2" in text
    assert "使用前" in text
    assert "異音あり" in text


def test_remark_page_repeats_machine_only_once(client, monkeypatch, tmp_path):
    """同じ機器が続く行では、機器名を1回だけ出すこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3, [
        _remark_record("2026-03-02", "クレーン1", "1件目"),
        _remark_record("2026-03-03", "クレーン1", "2件目"),
    ])
    text = _remark_page_text(2026, 3)
    assert text.count("クレーン1") == 1
    assert "1件目" in text and "2件目" in text


def test_remark_page_survives_long_text(client, monkeypatch, tmp_path):
    """長い特記事項でも例外にならず、ページができること"""
    import app as flask_app
    from pypdf import PdfReader
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3,
                   [_remark_record("2026-03-02", "クレーン1", "長い内容。" * 200)])
    buf = flask_app._build_remark_page(2026, 3)
    assert len(PdfReader(buf).pages) >= 1
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k remark_page`
Expected: FAIL（`AttributeError: module 'app' has no attribute '_build_remark_page'`）

- [ ] **Step 3: 実装する**

`app.py` の `_collect_remarks()` の**直後**に追加する。
`SimpleDocTemplate` / `Table` / `TableStyle` / `Paragraph` / `Spacer` / `colors` /
`landscape` / `A4` は、このファイルの冒頭ですでに import されている。

```python
def _build_remark_page(display_year: int, display_month: int) -> io.BytesIO:
    """特記事項の1枚を作って返す。記録が無くてもページは作る。

    表出力（_generate_pdf）とは別のPDFにする。合成のときに先頭へ足すため、
    また既存の出力を1バイトも変えないため。
    """
    styles = _get_pdf_styles()
    building_name = load_config().get("building_info", {}).get("building_name", "")
    rows = _collect_remarks(display_year, display_month)

    story = [
        Paragraph(f"{building_name}　{display_year}年{display_month}月　特記事項",
                  styles["title"]),
        Spacer(1, 12),
    ]
    if not rows:
        story.append(Paragraph("特記事項なし", styles["jp"]))
    else:
        data = [[Paragraph(t, styles["jp"])
                 for t in ("機器", "点検日", "種別", "内容")]]
        for i, r in enumerate(rows):
            first = (i == 0 or rows[i - 1]["machine"] != r["machine"])
            d = r["date"]
            data.append([
                Paragraph(r["machine"] if first else "", styles["jp"]),
                Paragraph(f"{d.year}/{d.month}/{d.day}", styles["jp"]),
                Paragraph(r["type"], styles["jp"]),
                Paragraph(r["text"], styles["remark"]),
            ])
        # 同じ機器が続く行は、機器名の欄を縦につなぐ。
        # 表の行番号は「並びの番号 + 1」（0行目が見出し）。
        spans, begin = [], 0
        for i in range(1, len(rows) + 1):
            if i == len(rows) or rows[i]["machine"] != rows[begin]["machine"]:
                if i - begin > 1:
                    spans.append(("SPAN", (0, begin + 1), (0, i)))
                begin = i
        usable = landscape(A4)[0] - 56
        table = Table(data, colWidths=[110, 70, 50, usable - 230],
                      repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.92, 0.94, 0.96)),
        ] + spans))
        story.append(table)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            rightMargin=28, leftMargin=28,
                            topMargin=57, bottomMargin=14)
    doc.build(story)
    buf.seek(0)
    return buf
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（338 passed）

- [ ] **Step 5: コミット**

```bash
git add app.py tests/test_app.py
git commit -m "feat: render the monthly remark page"
```

---

### Task 3: 様式の並び順（`app.py`）

**Files:**
- Modify: `app.py`（`_build_form_writers()` の直前に `_ordered_form_entries()` を追加し、`_build_form_writers()` のループを差し替え）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 様式の並び順 ==========

def _entries(*ids):
    """並べ替えの試験用に、様式一覧の形だけを作る"""
    return [{"id": i} for i in ids]


def test_ordered_form_entries_default_is_unchanged():
    """並び順が未設定なら、元の順（フォルダ名順）のままであること"""
    import app as flask_app
    got = flask_app._ordered_form_entries(_entries("a", "b", "c"), [])
    assert [e["id"] for e in got] == ["a", "b", "c"]
    got = flask_app._ordered_form_entries(_entries("a", "b", "c"), None)
    assert [e["id"] for e in got] == ["a", "b", "c"]


def test_ordered_form_entries_follows_order():
    """指定した順に並ぶこと"""
    import app as flask_app
    got = flask_app._ordered_form_entries(_entries("a", "b", "c"), ["c", "a", "b"])
    assert [e["id"] for e in got] == ["c", "a", "b"]


def test_ordered_form_entries_appends_unlisted():
    """指定に無い様式は、指定した様式のあとに元の順で続くこと"""
    import app as flask_app
    got = flask_app._ordered_form_entries(_entries("a", "b", "c"), ["c"])
    assert [e["id"] for e in got] == ["c", "a", "b"]


def test_ordered_form_entries_ignores_missing():
    """実在しない様式IDが混じっていても落ちないこと"""
    import app as flask_app
    got = flask_app._ordered_form_entries(_entries("a", "b"), ["zzz", "b"])
    assert [e["id"] for e in got] == ["b", "a"]


def test_ordered_form_entries_ignores_duplicates():
    """同じIDが2回あっても、その様式は1回だけ出ること"""
    import app as flask_app
    got = flask_app._ordered_form_entries(_entries("a", "b"), ["b", "b", "a"])
    assert [e["id"] for e in got] == ["b", "a"]
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k ordered_form_entries`
Expected: FAIL（`AttributeError: module 'app' has no attribute '_ordered_form_entries'`）

- [ ] **Step 3: 実装する**

**3-a.** `_build_form_writers()` の**直前**に追加する。

```python
def _ordered_form_entries(entries: list, form_order) -> list:
    """様式の一覧を、設定した並び順に並べ替える。

    設定に無い様式は、指定した様式のあとに元の順（フォルダ名順）で続ける。
    設定にあるが実在しない様式IDは無視する。同じIDが2回あっても1回だけ出す。
    """
    by_id = {e["id"]: e for e in entries}
    used, result = set(), []
    for form_id in (form_order or []):
        entry = by_id.get(form_id)
        if entry is None or form_id in used:
            continue
        used.add(form_id)
        result.append(entry)
    for entry in entries:
        if entry["id"] not in used:
            result.append(entry)
    return result
```

**3-b.** `_build_form_writers()` の中の

```python
    for entry in forms_layout.list_forms(forms_dir):
```

を、次の2行に差し替える。

```python
    form_order = load_config().get("form_order", [])
    for entry in _ordered_form_entries(forms_layout.list_forms(forms_dir),
                                       form_order):
```

`forms_dir` を作っている行より**あと**に置くこと。表出力に落ちた様式（`fallbacks`）の扱いは変えない。

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（343 passed）

- [ ] **Step 5: コミット**

```bash
git add app.py tests/test_app.py
git commit -m "feat: order form PDFs by the configured sequence"
```

---

### Task 4: 設定APIで並び順を受け取る（`app.py`）

このAPIはキーごとに検証して取り込む作りなので、分岐を足さないと**画面から保存しても無視される。**

**Files:**
- Modify: `app.py`（`api_post_config()` の `forms_directory` の分岐の直後）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_api_post_config_saves_form_order(client):
    """form_order を保存できること"""
    c, _ = client
    res = c.post("/api/config",
                 data=json.dumps({"form_order": ["form_02", "form_01"]}),
                 content_type="application/json")
    assert res.status_code == 200
    assert c.get("/api/config").get_json()["form_order"] == ["form_02", "form_01"]


def test_api_post_config_form_order_must_be_list(client):
    """form_order が配列でなければ400になること"""
    c, _ = client
    res = c.post("/api/config", data=json.dumps({"form_order": "form_01"}),
                 content_type="application/json")
    assert res.status_code == 400


def test_api_post_config_form_order_items_must_be_strings(client):
    """form_order の中身が文字列でなければ400になること"""
    c, _ = client
    res = c.post("/api/config", data=json.dumps({"form_order": ["form_01", 3]}),
                 content_type="application/json")
    assert res.status_code == 400


def test_api_post_config_form_order_length_limit(client):
    """form_order が長すぎれば400になること"""
    c, _ = client
    res = c.post("/api/config",
                 data=json.dumps({"form_order": [f"f{i}" for i in range(201)]}),
                 content_type="application/json")
    assert res.status_code == 400
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k form_order`
Expected: FAIL（保存されず `KeyError`、また不正な値でも 200 が返る）

- [ ] **Step 3: 実装する**

`api_post_config()` の中、`forms_directory` の分岐の**直後**に追加する。

```python
    if "form_order" in data:
        fo = data["form_order"]
        if not isinstance(fo, list):
            return jsonify({"error": "form_order は配列で指定してください"}), 400
        if len(fo) > 200:
            return jsonify({"error": "form_order が長すぎます"}), 400
        for name in fo:
            if not isinstance(name, str):
                return jsonify({"error": "form_order は様式IDの配列で指定してください"}), 400
        config["form_order"] = fo
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（347 passed）

- [ ] **Step 5: コミット**

```bash
git add app.py tests/test_app.py
git commit -m "feat: accept form_order in the config API"
```

---

### Task 5: PDFの合成順を変える（`app.py`）

**Files:**
- Modify: `app.py`（`api_get_pdf()` の `try:` の中）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== PDF全体の並び ==========

def _pdf_first_page_text(res):
    """レスポンスのPDFの1枚目から文字を取り出す"""
    from pypdf import PdfReader
    import io as _io
    return "".join((PdfReader(_io.BytesIO(res.data)).pages[0]
                    .extract_text() or "").split())


def test_api_pdf_first_page_is_remarks_without_forms(client, monkeypatch, tmp_path):
    """様式が1つも無くても、1枚目が特記事項になること"""
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert "特記事項" in _pdf_first_page_text(res)


def test_api_pdf_first_page_is_remarks_with_forms(client, monkeypatch, tmp_path):
    """様式があっても、1枚目が特記事項になること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert "特記事項" in _pdf_first_page_text(res)


def test_api_pdf_shows_saved_remark(client, monkeypatch, tmp_path):
    """保存した特記事項が1枚目に出ること"""
    import app as flask_app
    c, _ = client
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _empty_forms_dir(tmp_path, monkeypatch)
    _write_results(tmp_path, "使用前", 2026, 3,
                   [_remark_record("2026-03-02", "クレーン1", "ここが1枚目に出る")])
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert "ここが1枚目に出る" in _pdf_first_page_text(res)


def test_api_pdf_page_count_is_table_plus_one(client, monkeypatch, tmp_path):
    """様式が無いとき、ページ数が「表出力 ＋ 特記事項1枚」になること。

    表出力そのものに手を入れていないことの裏取りでもある。
    """
    from pypdf import PdfReader
    import io as _io
    import app as flask_app
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    merged = len(PdfReader(_io.BytesIO(res.data)).pages)

    table_res = flask_app._generate_pdf(2026, 3)
    table_res.direct_passthrough = False
    table = len(PdfReader(_io.BytesIO(table_res.get_data())).pages)

    assert merged == table + 1
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k "first_page_is_remarks or shows_saved_remark"`
Expected: FAIL（1枚目が表出力のままで「特記事項」が入っていない）

- [ ] **Step 3: 実装する**

`api_get_pdf()` の `try:` の中を、次の内容に差し替える。
**「様式が無ければ表出力をそのまま返す」早期returnは無くす。**
残したままにすると、様式を作っていない環境で特記事項ページが出ない。

```python
        table_response = _generate_pdf(display_year, display_month)
        form_writers, fallbacks = _build_form_writers(display_year, display_month)

        merged = PdfWriter()
        # 1枚目は特記事項。様式が1つも無くても必ず先頭に付ける。
        for page in PdfReader(_build_remark_page(display_year,
                                                 display_month)).pages:
            merged.add_page(page)
        for writer in form_writers:
            for page in writer.pages:
                merged.add_page(page)
        table_response.direct_passthrough = False
        for page in PdfReader(io.BytesIO(table_response.get_data())).pages:
            merged.add_page(page)

        buf = io.BytesIO()
        merged.write(buf)
        buf.seek(0)
        response = make_response(buf.read())
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = (
            f'inline; filename="inspection_{display_year}{display_month:02d}.pdf"')
        if fallbacks:
            response.headers["X-Form-Fallback"] = ",".join(fallbacks)
        return response
```

**この差し替えで、様式が無いときの `Content-Disposition` が `attachment` から `inline` に変わる**（これまで様式がある場合はすでに `inline` だった）。ブラウザが保存ではなくその場で開くようになる。意図した統一で、テストは `Content-Disposition` を見ていない。

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（351 passed）

既存の `test_api_pdf_unchanged_without_forms` は「ページ数が1以上」を見ているだけなので通る。
もし落ちるテストがあれば、**テストを弱めずに**内容を報告して止まること。

- [ ] **Step 5: コミット**

```bash
git add app.py tests/test_app.py
git commit -m "feat: put the remark page first in the inspection PDF"
```

---

### Task 6: 設定画面に「様式の並び順」を足す

**Files:**
- Modify: `static/inspection.html`（設定モーダルの「様式の割り当て」の下、および `app.js?v=`）
- Modify: `static/app.js`（一覧の描画・▲▼・保存）

このリポジトリにJSの自動テストは無い。Task 7 の実機確認が検証になる。

- [ ] **Step 1: 置き場所を作る**

`static/inspection.html` の「様式の割り当て」の `</div>` を含むブロック（`id="cfg-form-assignments"` の div を閉じたあと）の**直後**に、次を追加する。

```html
                <div class="form-row">
                    <label>様式の並び順</label>
                    <div id="cfg-form-order" style="font-size:12px; line-height:1.7; max-height:180px; overflow-y:auto; border:1px solid #d5dbe0; border-radius:4px; padding:8px; background:#fafbfc;"></div>
                    <small style="color:#667;">上から順にPDFに綴じられます。特記事項は常に1枚目、表出力は常に最後です。</small>
                </div>
```

- [ ] **Step 2: 一覧を描く処理を足す**

`static/app.js` の `renderFormAssignments()` の**直後**に追加する。

```javascript
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
    const saved = (state.config && state.config.form_order) || [];
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

/** 画面に出ている順の様式IDを返す */
function currentFormOrder() {
    const el = document.getElementById("cfg-form-order");
    if (!el) return [];
    return [...el.querySelectorAll(".form-order-row")].map(r => r.dataset.id);
}
```

- [ ] **Step 3: 設定を開いたときに描く**

`static/app.js` の 1233行目付近、設定モーダルを開くときに走る次の行の**直後**に `renderFormOrder();` を足す。

```javascript
    renderFormAssignments();
    renderFormOrder();
```

呼び出しは1か所だけ（`grep -n "renderFormAssignments();" static/app.js` で確認できる）。

- [ ] **Step 4: 保存に含める**

`handleSettingsSave()` の `payload` に1行足す。

```javascript
        cycle_start_day:
            Number(document.getElementById("cfg-cycle-start-day").value) || 24,
        form_order: currentFormOrder(),
```

- [ ] **Step 5: 版数を上げる**

`static/inspection.html` の `<script src="/app.js?v=4"></script>` を `?v=5` にする。
**上げ忘れると、利用者のブラウザが古い設定画面を使い続ける。**

確認：`grep -n "app.js?v=" static/inspection.html` が `?v=5` の1行だけになること。

- [ ] **Step 6: 構文とテストを確認する**

```
node --check static/app.js
.venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: `node --check` は出力なし。pytest は `351 passed`（Pythonは触っていないので変わらない）。

- [ ] **Step 7: コミット**

```bash
git add static/inspection.html static/app.js
git commit -m "feat: let the settings screen reorder form PDFs"
```

---

### Task 7: 実機で確かめる

**テストだけでは足りない。**画面を開き、PDFを実際に開いて目で見る。

**Files:** なし（確認のみ）

- [ ] **Step 1: 全テストが通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: `351 passed`

- [ ] **Step 2: サーバーを起動する**

Run: `.venv/Scripts/python.exe app.py`
ブラウザで `http://localhost:5000/inspection` を開く。

- [ ] **Step 3: 設定画面を見る**

⚙ 設定を開き、確認すること:

- 「様式の割り当て」の下に **「様式の並び順」** が出ている
- 様式名が縦に並び、各行に ▲▼ がある
- **いちばん上の行の ▲ と、いちばん下の行の ▼ が押せない**

- [ ] **Step 4: 並べ替えて保存する**

いちばん下の様式を ▲ で先頭まで上げ、「設定を保存」を押す。そのあと設定を開き直し、
**並びが保たれている**ことを確認する。

- [ ] **Step 5: PDFを開いて目で見る**

点検画面からPDFを出力し、確認すること:

- **1枚目が特記事項**になっている（タイトルに建物名・年月・「特記事項」）
- **2枚目以降の様式が、設定した順**になっている
- 表出力が最後に付いている
- 特記事項を書いた月なら、機器ごとにまとまって出ている

- [ ] **Step 6: 特記事項が無い月を確かめる**

記録の無い月を選んでPDFを出し、**1枚目に「特記事項なし」**と出ること、
エラーにならないことを確認する。

- [ ] **Step 7: 結果を報告する**

Step 3〜6 で見たことを、**確認できた／できなかった**を分けて報告する。
できなかったものがあれば、そこで止めて報告する（「動くはずです」は書かない）。

---

## 完了の条件

- `.venv/Scripts/python.exe -m pytest tests/ -q` が全件通る（351 passed の見込み）
- Task 7 の Step 3〜6 をすべて実機で確認した
- `app.js?v=5` になっている
- 表出力（`_generate_pdf`）に手を入れていない（`git diff` で確認できる）
