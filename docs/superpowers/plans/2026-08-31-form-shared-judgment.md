# 様式PDF「全機器まとめ」と「対象機器欄」 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 同じ点検項目を持つ複数の機器の点検結果を、判定1マス＋対象機器欄という形で1枚の様式PDFに収める。

**Architecture:** `layout.json` の `fields[].source` に2つの書き方を足す。`item:*|<項目名>` はその日に記録がある機器の判定のうち最も悪いものを印字し、`target:<機器名>` はその機器の記録があればチェックを印字する。そのために印字用スロットへ「その日に点検した機器のリスト」を持たせる。画面側は左の一覧に2グループを足し、置き忘れの数え方を合わせる。

**Tech Stack:** Python 3 / Flask / reportlab / pypdf / pytest / 素のES Module（ビルドなし）

**設計書:** `docs/superpowers/specs/2026-08-31-form-shared-judgment-design.md`

**ブランチ:** `feature/layout-ui`（すでにこのブランチにいる。新しく切らない）

**着手前の基準値:** `.venv/Scripts/python.exe -m pytest tests/ -q` が **296 passed**（2026-08-31 実測）。

---

## 前提知識（この計画を実行する人へ）

このアプリを触るうえで、知らないと事故になることだけを挙げる。

- **PDFの座標は左下が原点で、上に行くほどYが大きい。** 画面と上下が逆。
- **点検項目名は機器をまたいで重複する。**「点検項目C-1」は5機器に存在する。項目を特定するときは必ず機器名とセットで扱う。
- **判定の記号は ✓（良）/ A（要調整）/ △（修理）/ ×（要取替）/ ー（対象外）。** 旧仕様の「○」で保存された記録が残っているので、比べる前に `normalize_judgment()` を通す。
- **点検サイクルは暦月ではなく締め日区切り**（既定24日始まり）。1サイクルは28〜31日で変わる。2026年3月分は 2/24〜3/23 の28日。
- **`static/` のJSはビルドしない。** ブラウザのキャッシュを切るために `?v=` の版数を上げる必要があり、**版数は4か所ある**（Task 7 で扱う）。
- テストの実行は `.venv/Scripts/python.exe -m pytest tests/ -q`。

---

## ファイル構成

| ファイル | この計画での役割 |
|---|---|
| `forms_layout.py` | 判定の悪さを比べる純粋な関数（`worst_judgment`）と定数 `ALL_TARGETS` を置く。ここは画面もPDFも参照する土台 |
| `pdf_forms.py` | スロットに `machines` を持たせ、`_field_value` に2つの分岐を足す。試し刷り用の `*` 展開もここ |
| `static/layout.js` | 左の一覧に2グループを足す。置いた項目の数え方を1か所にまとめる |
| `static/layout-preview.js` | `target:` の見本文字を返す分岐を1つ足す |
| `static/layout.html` | 版数を上げるだけ |
| `tests/test_app.py` | 全タスクのテストを追記する（このリポジトリはテストが1ファイル） |

---

### Task 1: 判定の悪さを比べる関数（`forms_layout.py`）

**Files:**
- Modify: `forms_layout.py`（`normalize_judgment()` の直後、42行目付近に追記）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_app.py` の末尾に追記する。

```python
# ========== 全機器まとめ（いちばん悪い判定） ==========

def test_all_targets_constant():
    """機器名の位置に入る印が * であること"""
    import forms_layout
    assert forms_layout.ALL_TARGETS == "*"


def test_worst_judgment_picks_replace_over_ok():
    """✓ と × が混ざったら × を返すこと"""
    import forms_layout
    assert forms_layout.worst_judgment(["✓", "×"]) == "×"


def test_worst_judgment_severity_order():
    """悪い順が × ＞ △ ＞ A ＞ ✓ ＞ ー であること"""
    import forms_layout
    assert forms_layout.worst_judgment(["✓", "A"]) == "A"
    assert forms_layout.worst_judgment(["A", "△"]) == "△"
    assert forms_layout.worst_judgment(["△", "×"]) == "×"
    assert forms_layout.worst_judgment(["ー", "✓"]) == "✓"


def test_worst_judgment_order_does_not_matter():
    """並べる順を変えても結果が同じであること"""
    import forms_layout
    assert forms_layout.worst_judgment(["×", "✓"]) == "×"
    assert forms_layout.worst_judgment(["✓", "×"]) == "×"


def test_worst_judgment_ignores_empty():
    """記録が無い機器（空文字）は比べる対象にしないこと"""
    import forms_layout
    assert forms_layout.worst_judgment(["", "✓", ""]) == "✓"
    assert forms_layout.worst_judgment(["", ""]) == ""
    assert forms_layout.worst_judgment([]) == ""


def test_worst_judgment_normalizes_legacy_mark():
    """旧仕様の「○」を✓として比べること"""
    import forms_layout
    assert forms_layout.worst_judgment(["○", "ー"]) == "✓"


def test_worst_judgment_falls_back_to_last_for_numbers():
    """数値のように比べられない値しか無ければ、最後の値を返すこと"""
    import forms_layout
    assert forms_layout.worst_judgment(["12.3", "11.8"]) == "11.8"


def test_worst_judgment_prefers_known_mark_over_number():
    """知っている判定記号があれば、そちらを優先すること"""
    import forms_layout
    assert forms_layout.worst_judgment(["12.3", "✓"]) == "✓"
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k worst_judgment`
Expected: FAIL（`AttributeError: module 'forms_layout' has no attribute 'worst_judgment'`）

- [ ] **Step 3: 実装する**

`forms_layout.py` の `normalize_judgment()` の直後（`item_input_type()` の前）に追記する。
`NOT_APPLICABLE_MARK` と `MARK_*` はこれより上ですでに定義されている。

```python
ALL_TARGETS = "*"   # item:*|<項目名> の、機器名の位置に入る印


# 判定の悪さ。数が大きいほど悪い。ここに無い値（数値など）は比べない。
_SEVERITY = {
    NOT_APPLICABLE_MARK: 1,   # ー 対象外
    MARK_OK: 2,               # ✓ 良
    MARK_ADJUST: 3,           # A 要調整
    MARK_REPAIR: 4,           # △ 修理
    MARK_REPLACE: 5,          # × 要取替
}


def worst_judgment(values) -> str:
    """判定を並べて、いちばん悪いものを返す。

    複数の機器の点検結果を1つのマスに印字するために使う。
    知っている判定記号が1つも無ければ（数値項目など）最後の値を返す。
    """
    worst, rank, fallback = "", 0, ""
    for value in values:
        value = normalize_judgment(value)
        if not value:
            continue
        fallback = value
        r = _SEVERITY.get(value, 0)
        if r > rank:
            worst, rank = value, r
    return worst or fallback
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（304 passed）

- [ ] **Step 5: コミット**

```bash
git add forms_layout.py tests/test_app.py
git commit -m "feat: add worst_judgment for merging judgments across equipment"
```

---

### Task 2: スロットに「その日に点検した機器」と、まとめた備考を持たせる（`pdf_forms.py`）

同じ日に2機器を保存すると、いまは備考が上書きされて片方が消える。機器のリストと合わせてここで直す。

**Files:**
- Modify: `pdf_forms.py`（`_empty_slot()` / `_attach()` / `build_slots()` の docstring / `_index()` / `build_form_writer()` の single 分岐）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 対象機器と備考のまとめ ==========

def _two_machine_records():
    """同じ日にクレーン1（✓）とクレーン2（×）を点検した記録を返す"""
    return [
        {"inspection_date": "2026-03-02", "category_minor": "クレーン1",
         "submitted_at": "2026-03-02T09:00:00", "general_remark": "",
         "results": [{"inspection_item": "C-1", "result": "✓", "remark": ""}]},
        {"inspection_date": "2026-03-02", "category_minor": "クレーン2",
         "submitted_at": "2026-03-02T10:00:00", "general_remark": "",
         "results": [{"inspection_item": "C-1", "result": "×", "remark": ""}]},
    ]


def test_index_by_date_lists_machines_in_save_order():
    """その日に点検した機器が、保存した順で並ぶこと"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(_two_machine_records(),
                                      ["クレーン1", "クレーン2"])
    assert indexed["2026-03-02"]["machines"] == ["クレーン1", "クレーン2"]


def test_index_by_date_machines_has_no_duplicates():
    """同じ機器を2回保存しても、機器名が重複しないこと"""
    import pdf_forms
    records = _two_machine_records()
    again = dict(records[0])
    again["submitted_at"] = "2026-03-02T11:00:00"
    indexed = pdf_forms.index_by_date(records + [again],
                                      ["クレーン1", "クレーン2"])
    assert indexed["2026-03-02"]["machines"] == ["クレーン1", "クレーン2"]


def test_index_by_date_skips_machines_not_in_targets():
    """様式に載っていない機器を machines に入れないこと"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(_two_machine_records(), ["クレーン1"])
    assert indexed["2026-03-02"]["machines"] == ["クレーン1"]


def test_index_by_date_merges_remarks_of_two_machines():
    """2機器とも備考を書いたら、機器名を付けてつなぐこと"""
    import pdf_forms
    records = _two_machine_records()
    records[0]["general_remark"] = "異音あり"
    records[1]["general_remark"] = "要取替"
    indexed = pdf_forms.index_by_date(records, ["クレーン1", "クレーン2"])
    assert (indexed["2026-03-02"]["meta"]["general_remark"]
            == "クレーン1：異音あり／クレーン2：要取替")


def test_index_by_date_single_remark_is_unchanged():
    """備考を書いた機器が1つだけなら、機器名を付けないこと"""
    import pdf_forms
    records = _two_machine_records()
    records[1]["general_remark"] = "要取替"
    indexed = pdf_forms.index_by_date(records, ["クレーン1", "クレーン2"])
    assert indexed["2026-03-02"]["meta"]["general_remark"] == "要取替"


def test_index_by_date_no_remark_is_empty():
    """どちらも備考を書いていなければ空文字であること"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(_two_machine_records(),
                                      ["クレーン1", "クレーン2"])
    assert indexed["2026-03-02"]["meta"]["general_remark"] == ""


def test_build_slots_carries_machines():
    """スロットに、その日に点検した機器が入ること"""
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    indexed = pdf_forms.index_by_date(_two_machine_records(),
                                      ["クレーン1", "クレーン2"])
    slots = pdf_forms.build_slots(layout, 2026, 3, _march_2026_cycle(),
                                  indexed, {})
    # サイクルは 2/24 始まりなので 3/2 は 7 マス目
    assert slots[7]["date"].isoformat() == "2026-03-02"
    assert slots[7]["machines"] == ["クレーン1", "クレーン2"]


def test_build_slots_machines_empty_without_record():
    """記録が無い日の machines が空のリストであること"""
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    slots = pdf_forms.build_slots(layout, 2026, 3, _march_2026_cycle(), {}, {})
    assert slots[7]["machines"] == []
    assert slots[31]["machines"] == []
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k "machines or remarks_of_two or single_remark or no_remark"`
Expected: FAIL（`KeyError: 'machines'`）

- [ ] **Step 3: 実装する**

**3-a.** `_empty_slot()` に `machines` を足す。

```python
def _empty_slot() -> dict:
    """1欄分の空のデータを作る"""
    return {"date": None, "month": None, "exists": False, "mark": "",
            "index": 0, "has_record": False, "unused": False,
            "values": {}, "remarks": {}, "meta": {}, "machines": []}
```

**3-b.** `_attach()` に1行足す。

```python
def _attach(slot: dict, record):
    """欄に点検記録を入れる（記録が無ければ何もしない）"""
    if not record:
        return
    slot["values"] = record.get("values", {})
    slot["remarks"] = record.get("remarks", {})
    slot["meta"] = record.get("meta", {})
    slot["machines"] = record.get("machines", [])
    slot["has_record"] = True
```

**3-c.** `build_slots()` の docstring の `remarks…` の行の下に1行足す。

```
      machines… その欄に記録がある機器名（保存順）
```

**3-d.** `_record_payload()` の直後、`_index()` の前に `_merge_remark()` を足す。

```python
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
```

**3-e.** `_index()` の本体を差し替える。docstring も1文足す。

```python
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
```

**3-f.** `build_form_writer()` の single 分岐で手組みしているスロットに `machines` を足す。
**これを忘れると、1枚1点検日の様式で対象欄と全機器まとめが黙って空になる。**

```python
        slot = {"date": None, "month": None, "exists": True, "mark": "",
                "values": payload.get("values", {}),
                "remarks": payload.get("remarks", {}),
                "meta": payload.get("meta", {}),
                "machines": payload.get("machines", [])}
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（312 passed）

- [ ] **Step 5: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: track inspected equipment per slot and merge their remarks"
```

---

### Task 3: 印字の分岐を足す（`pdf_forms._field_value`）

**Files:**
- Modify: `pdf_forms.py`（`_field_value()` の `item:` の分岐を書き換え、`target:` の分岐を足す）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 全機器まとめ・対象機器欄の印字 ==========

def _slot_with(values, machines):
    """_field_value を試すための最小のスロット"""
    return {"exists": True, "values": values, "machines": machines,
            "remarks": {}, "meta": {}, "date": None, "index": 1}


def test_field_value_all_targets_picks_worst():
    """全機器まとめが、いちばん悪い判定を返すこと"""
    import pdf_forms
    slot = _slot_with({"クレーン1|C-1": "✓", "クレーン2|C-1": "×"},
                      ["クレーン1", "クレーン2"])
    assert pdf_forms._field_value({"source": "item:*|C-1"}, slot, {}) == "×"


def test_field_value_all_targets_uses_only_recorded_machines():
    """その日に記録が無い機器の判定を混ぜないこと"""
    import pdf_forms
    slot = _slot_with({"クレーン1|C-1": "✓", "クレーン2|C-1": "×"},
                      ["クレーン1"])
    assert pdf_forms._field_value({"source": "item:*|C-1"}, slot, {}) == "✓"


def test_field_value_all_targets_empty_without_record():
    """記録が1件も無ければ空文字を返すこと"""
    import pdf_forms
    slot = _slot_with({}, [])
    assert pdf_forms._field_value({"source": "item:*|C-1"}, slot, {}) == ""


def test_field_value_all_targets_applies_mark_override():
    """様式ごとの記号の上書きが効くこと"""
    import pdf_forms
    slot = _slot_with({"クレーン1|C-1": "✓"}, ["クレーン1"])
    field = {"source": "item:*|C-1", "mark_ok": "○"}
    assert pdf_forms._field_value(field, slot, {}) == "○"


def test_field_value_target_marks_recorded_machine():
    """対象機器欄が、記録のある機器にだけチェックを入れること"""
    import pdf_forms
    slot = _slot_with({}, ["クレーン1"])
    assert pdf_forms._field_value({"source": "target:クレーン1"}, slot, {}) == "✓"
    assert pdf_forms._field_value({"source": "target:クレーン2"}, slot, {}) == ""


def test_field_value_target_uses_mark_override():
    """対象機器欄のチェック文字を上書きできること"""
    import pdf_forms
    slot = _slot_with({}, ["クレーン1"])
    field = {"source": "target:クレーン1", "mark_target": "レ"}
    assert pdf_forms._field_value(field, slot, {}) == "レ"


def test_field_value_single_machine_item_unchanged():
    """今までの item:機器|項目 の動きが変わらないこと"""
    import pdf_forms
    slot = _slot_with({"クレーン1|C-1": "×"}, ["クレーン1"])
    assert (pdf_forms._field_value({"source": "item:クレーン1|C-1"}, slot, {})
            == "×")


def test_form_pdf_prints_worst_judgment_and_targets(tmp_path):
    """PDFに、悪いほうの判定と対象機器のチェックが出ること"""
    from datetime import date
    import pdf_forms
    _make_form_pdf(tmp_path / "form.pdf")
    layout = {
        "period": "month", "inspection_type": "使用前",
        "targets": ["クレーン1", "クレーン2"], "default_font_size": 9,
        "axis": {"step_x": 20.0, "step_y": 0.0, "count": 31},
        "fields": [
            {"source": "item:*|C-1", "page": 0, "x": 50, "y": 700,
             "on_axis": True},
            {"source": "target:クレーン1", "page": 0, "x": 50, "y": 650,
             "on_axis": True, "mark_target": "甲"},
            {"source": "target:クレーン2", "page": 0, "x": 50, "y": 600,
             "on_axis": True, "mark_target": "乙"},
        ],
    }
    writer = pdf_forms.build_form_writer(
        tmp_path, layout, _two_machine_records(), 2026, 3,
        _march_2026_cycle(), {}, today=date(2026, 4, 1))
    out = tmp_path / "out.pdf"
    _write_out(writer, out)
    text = _read_text(out) or ""
    # 3/2 は1日だけ。クレーン1=✓・クレーン2=× なので × が1つ出る
    assert text.count("×") == 1
    assert text.count("甲") == 1
    assert text.count("乙") == 1
    # 28日サイクルなので、余りマス3つには「ー」が入る（対象欄は空欄のまま）
    assert text.count("ー") == 3


def test_form_pdf_single_period_prints_targets(tmp_path):
    """1枚1点検日の様式でも、対象機器欄と全機器まとめが出ること"""
    from datetime import date
    import pdf_forms
    _make_form_pdf(tmp_path / "form.pdf")
    layout = {
        "period": "single", "inspection_type": "使用前",
        "targets": ["クレーン1", "クレーン2"], "default_font_size": 9,
        "fields": [
            {"source": "item:*|C-1", "page": 0, "x": 50, "y": 700},
            {"source": "target:クレーン2", "page": 0, "x": 50, "y": 650,
             "mark_target": "乙"},
        ],
    }
    writer = pdf_forms.build_form_writer(
        tmp_path, layout, _two_machine_records(), 2026, 3,
        _march_2026_cycle(), {}, today=date(2026, 4, 1))
    out = tmp_path / "out.pdf"
    _write_out(writer, out)
    text = _read_text(out) or ""
    # single 型のスロットは build_form_writer が手で組み立てている。
    # machines を入れ忘れるとここが空になる。
    assert "×" in text
    assert "乙" in text

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k "all_targets or field_value_target or prints_worst"`
Expected: FAIL（`item:*|C-1` が空文字になり `assert "" == "×"` で落ちる）

- [ ] **Step 3: 実装する**

`pdf_forms.py` の `_field_value()` の先頭2分岐を、次のように書き換える。
`target:` は **`meta.` の分岐より前**に置くこと。

```python
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
```

余りマスの扱いは変えない。`_draw_slot_field()` が `source.startswith("item:")` で
「ー」を入れているので、`item:*|` はそのまま「ー」になり、`target:` は空欄になる。

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（321 passed）

- [ ] **Step 5: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: print merged judgment and target-equipment marks on form PDFs"
```

---

### Task 4: 試し刷りで「全機器まとめ」の欄を埋める（`pdf_forms.layout_item_names`）

`layout_item_names()` は `item:*|C-1` の機器名を `*` として返すため、`build_sample_records()` の
`equip == name` に一致せず、**試し刷りだと全機器まとめの欄だけ空になる。**

**Files:**
- Modify: `pdf_forms.py`（`layout_item_names()`）
- Test: `tests/test_app.py`（ファイル末尾に追記）

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_layout_item_names_expands_all_targets():
    """item:*|項目 が、様式の全機器に展開されること"""
    import pdf_forms
    layout = {"targets": ["クレーン1", "クレーン2"],
              "fields": [{"source": "item:*|C-1"}]}
    assert pdf_forms.layout_item_names(layout) == [
        ("クレーン1", "C-1"), ("クレーン2", "C-1")]


def test_layout_item_names_all_targets_no_duplicates():
    """機器ごとの指定と重なっても、同じ組を2回返さないこと"""
    import pdf_forms
    layout = {"targets": ["クレーン1", "クレーン2"],
              "fields": [{"source": "item:クレーン1|C-1"},
                         {"source": "item:*|C-1"}]}
    assert pdf_forms.layout_item_names(layout) == [
        ("クレーン1", "C-1"), ("クレーン2", "C-1")]


def test_layout_item_names_keeps_named_equipment():
    """機器名を書いた指定はこれまでどおり返すこと"""
    import pdf_forms
    layout = {"targets": ["クレーン1"],
              "fields": [{"source": "item:クレーン1|C-1"},
                         {"source": "remark:クレーン1|C-2"}]}
    assert pdf_forms.layout_item_names(layout) == [
        ("クレーン1", "C-1"), ("クレーン1", "C-2")]


def test_sample_records_fill_all_targets_item(tmp_path):
    """試し刷り用のダミー記録に、全機器まとめの項目が入ること"""
    import pdf_forms
    layout = {"period": "month", "targets": ["クレーン1", "クレーン2"],
              "fields": [{"source": "item:*|C-1"}]}
    records = pdf_forms.build_sample_records(
        layout, _march_2026_cycle(), 2026, set())
    machines = {r["category_minor"] for r in records}
    assert machines == {"クレーン1", "クレーン2"}
    items = {row["inspection_item"]
             for r in records for row in r["results"]}
    assert items == {"C-1"}
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q -k "layout_item_names or sample_records_fill"`
Expected: FAIL（`[('*', 'C-1')] != [('クレーン1', 'C-1'), ('クレーン2', 'C-1')]`）

- [ ] **Step 3: 実装する**

`layout_item_names()` を差し替える。

```python
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
```

`ALL_TARGETS` は `forms_layout` にある。`pdf_forms.py` の冒頭で
`NOT_APPLICABLE_MARK = forms_layout.NOT_APPLICABLE_MARK` と書いているのと同じ形で、
その並びに `ALL_TARGETS = forms_layout.ALL_TARGETS` を足してから使う。

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（325 passed）

- [ ] **Step 5: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: expand all-targets item into every equipment for sample prints"
```

---

### Task 5: 左の一覧に「全機器まとめ」「対象機器」を出す（`static/layout.js`）

ここからブラウザ側。**このリポジトリにJSの自動テストは無いので、Task 8 の実機確認が検証になる。**
サーバー側のテストは全件通ったままであること。

**Files:**
- Modify: `static/layout.js`（冒頭の import の下に定数、`collectItems()` に追記）

- [ ] **Step 1: 定数を足す**

`static/layout.js` の import 文（3〜5行目）の直後に足す。

```javascript
// 機器名の位置に入る印。サーバー側 forms_layout.ALL_TARGETS と同じ値にすること。
// 片方だけ変えると、画面で置いた項目がPDFに出なくなる。
const ALL_TARGETS = "*";
```

- [ ] **Step 2: `collectItems()` にグループを2つ足す**

`collectItems()` の中の `const targets = (state.layout && state.layout.targets) || [];` の
**直後**、`for (const name of targets) {` の**前**に挿入する。

```javascript
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
```

- [ ] **Step 3: サーバー側のテストが壊れていないことを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（325 passed。JSは触っていないので数は変わらない）

- [ ] **Step 4: コミット**

```bash
git add static/layout.js
git commit -m "feat: list merged-judgment and target-equipment items in the layout panel"
```

---

### Task 6: 「置き忘れ」の数え方を1か所にまとめる（`static/layout.js`）

`item:*|C-1` を置いても、機器ごとの `item:クレーン1|C-1` が未配置として残り、
**正しく作っても「まだ置いていない項目があります」が消えない。**

**Files:**
- Modify: `static/layout.js`（`renderItemList()` 354行目付近 / `countUnplaced()` 658行目付近 / `renderProgress()` 696行目付近）

- [ ] **Step 1: 共通の関数を足す**

`renderItemList()` の**すぐ上**に置く。

```javascript
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
```

- [ ] **Step 2: 3か所を置き換える**

次の2行が3か所にある。**3か所すべて**を `const placed = placedSourceSet();` の1行にする。

```javascript
    const placed = new Set(((state.layout && state.layout.fields) || [])
        .map(f => f.source));
```

置き換える関数は `renderItemList()` / `countUnplaced()` / `renderProgress()` の3つ。
`grep -n "f => f.source" static/layout.js` で残りが1件（403行目の
`f.source === state.selectedItem` の行）だけになることを確認する。
**403行目は別物なので触らない。**

- [ ] **Step 3: サーバー側のテストが壊れていないことを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（325 passed）

- [ ] **Step 4: コミット**

```bash
git add static/layout.js
git commit -m "fix: count merged-judgment placement as covering every equipment"
```

---

### Task 7: プレビューに対象機器欄を出し、版数を上げる

**Files:**
- Modify: `static/layout-preview.js`（`sampleValue()`）
- Modify: `static/layout.html`（8行目・92行目の `?v=15`）
- Modify: `static/layout.js`（4行目・5行目の `?v=15`）

- [ ] **Step 1: プレビューに分岐を足す**

`static/layout-preview.js` の `sampleValue()` の中、`if (source.startsWith("remark:"))` の
**すぐ上**に足す。

```javascript
    if (source.startsWith("target:")) {
        // 対象機器欄。プレビューは全機器を点検した前提の見本なので常に出す。
        return markOr(field, "mark_target", SAMPLE.judgment);
    }
```

**`item:*|項目名` の分岐は足さない。**既存の `item:` の分岐は縦棒より後ろ（点検項目名）
しか見ていないので、機器名の位置が `*` でもそのまま正しく動く。余りマスの「ー」も
`source.startsWith("item:")` で判定しているので効く。`target:` は `item:` で始まらないため、
余りマスは何も描かれず空欄になる（サーバー側と同じ）。

- [ ] **Step 2: 版数を4か所とも上げる**

`?v=15` → `?v=16`。**1つでも上げ忘れると、利用者のブラウザが古いファイルを使い続ける。**

| ファイル | 行 |
|---|---|
| `static/layout.html` | 8行目 `/layout.css?v=15` |
| `static/layout.html` | 92行目 `/layout.js?v=15` |
| `static/layout.js` | 4行目 `/layout-wizard.js?v=15` |
| `static/layout.js` | 5行目 `/layout-preview.js?v=15` |

- [ ] **Step 3: 上げ忘れが無いことを確認する**

Run: `grep -rn "?v=" static/layout.html static/layout.js`
Expected: 4行すべてが `?v=16`。`v=15` が1つも残っていないこと。

- [ ] **Step 4: サーバー側のテストが壊れていないことを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（325 passed）

- [ ] **Step 5: コミット**

```bash
git add static/layout-preview.js static/layout.html static/layout.js
git commit -m "feat: preview target-equipment marks and bump asset version"
```

---

### Task 8: 実機で確かめる

**テストだけでは足りない。**過去に、テストが全部通っているのにテンキーが枠からはみ出して
「確定」が押せない不具合を見逃している。**画面を開き、PDFを実際に開いて目で見る。**

**Files:** なし（確認のみ）

- [ ] **Step 1: 全テストが通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS（325 passed）

- [ ] **Step 2: サーバーを起動して `/layout` を開く**

Run: `.venv/Scripts/python.exe app.py`
ブラウザで `http://localhost:5000/layout` を開く（管理者キーが要る）。

- [ ] **Step 3: 2機器の様式を作る**

「様式を追加」から、機器の選択で **クレーン1 と クレーン2 の両方**にチェックを入れて作る。
確認すること:

- 左の一覧に **「全機器まとめ」**（点検項目C-1／C-2／C-3）が出ている
- 左の一覧に **「対象機器」**（クレーン1／クレーン2）が出ている
- 「全機器まとめ」に数値項目が入っていない

- [ ] **Step 4: 置いて、プレビューと置き忘れ表示を見る**

「全機器まとめ／点検項目C-1」を紙の上に置き、「マスの数だけ繰り返す」を入れる。
「対象機器／クレーン1」「対象機器／クレーン2」も置く。確認すること:

- 薄い文字（プレビュー）が **マスの数だけ横に並ぶ**
- 3月表示にすると、**余りマス3つは「全機器まとめ」だけ「ー」**になり、対象欄は空欄
- 「全機器まとめ／C-1」を置くと、**左の一覧のクレーン1／クレーン2のC-1にも ✓ が付く**
- 上の「置いた数／残り」の残り数が、まとめた分だけ減る

- [ ] **Step 5: 試し刷りのPDFを開いて目で見る**

「試し刷り」を押してPDFを開き、確認すること:

- 全機器まとめの欄に判定が入っている（**空欄になっていないこと**。Task 4 が効いている証拠）
- 対象機器の欄にチェックが入っている
- 位置が紙のマスと合っている

- [ ] **Step 6: 本番のPDFで、悪いほうが出ることを確かめる**

点検画面から、**同じ日に** クレーン1 を全部 ✓ で、クレーン2 の C-1 を **×** で保存する。
クレーン2の備考に「テスト」と書く。そのうえでPDFを出力して確認すること:

- C-1 のマスに **×** が出ている（✓ ではない）
- C-2・C-3 のマスは ✓
- 対象機器の欄は **クレーン1・クレーン2の両方**にチェック
- 備考に「クレーン2：テスト」と出ている

- [ ] **Step 7: 既存の様式が変わっていないことを確かめる**

1機器だけの既存様式（`sample_daily` など）を開き、PDFを出力して**今までと同じ見た目**であることを確認する。

- [ ] **Step 8: 結果を報告する**

Step 3〜7 で見たことを、**確認できた／できなかった**を分けて報告する。
できなかったものがあれば、そこで止めて報告する（「動くはずです」は書かない）。

---

## 完了の条件

- `.venv/Scripts/python.exe -m pytest tests/ -q` が全件通る（325 passed の見込み）
- Task 8 の Step 3〜7 をすべて実機で確認した
- `?v=16` が4か所そろっている
- 既存の1機器様式の出力が変わっていない
