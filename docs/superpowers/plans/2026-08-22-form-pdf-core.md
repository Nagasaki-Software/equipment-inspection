# 様式PDF出力（中核） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 点検結果を既存の紙の様式PDFに座標指定で印字し、様式を紐づけていない機器は従来どおり表形式で出力する。

**Architecture:** 様式は `forms/<様式ID>/` に `form.pdf` と `layout.json` を置くフォルダ単位で管理する。`forms_layout.py` が設定の読み書きと座標計算を担い、`pdf_forms.py` が reportlab で作った文字レイヤーを pypdf で様式PDFに重ねる。`app.py` の `/api/pdf` は機器を「様式組」と「表組」に振り分け、両方を1つのPDFに結合して返す。

**Tech Stack:** Python 3 / Flask / reportlab（既存）/ pypdf（新規）/ pytest（既存）

**設計書:** `docs/superpowers/specs/2026-08-22-inspection-form-pdf-design.md`

**この計画の範囲:** 設計書の第0〜2段階。完了時点で、`layout.json` を手で用意すれば様式PDF出力が動く。レイアウト画面と入力画面の改善は `2026-08-22-form-pdf-ui.md` で扱う。

---

## ファイル構成

| ファイル | 新規/変更 | 責務 |
|---|---|---|
| `forms_layout.py` | 新規 | `layout.json` の読み書きと検証、様式一覧、機器と様式の紐づけ、軸の座標計算、マスタCSVの `input_type` / `unit` の読み取り |
| `pdf_forms.py` | 新規 | 軸の各欄へのデータ割り当て、様式PDFへの重ね書き、日にちと休日の丸の描画 |
| `app.py` | 変更 | 点検サイクルのヘルパー、締め日の設定化、数値の正規化と検証、`/api/pdf` の分岐、様式API |
| `static/app.js` | 変更 | 締め日を設定から読む、誤ったコメントの修正 |
| `tests/test_app.py` | 変更 | 全タスクのテストを追記 |
| `requirements.txt` | 変更 | pypdf を追加 |

`app.py` は現在1214行ある。今回追加するロジックは原則 `forms_layout.py` と `pdf_forms.py` に置き、`app.py` にはルートと最小限の接続コードだけを足す。

---

## Task 1: 点検サイクルのヘルパー

現在「前月24日〜当月23日」の計算が `app.py:687` と `static/app.js:69` に散らばっている。まず `app.py` に1本化する。

**Files:**
- Modify: `app.py`（`_default_config` の直前あたりに追加）
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_app.py` の末尾に追記する。

```python
# ========== 点検サイクル ==========

def test_cycle_range_default_start_day():
    """既定（24日）のサイクルは前月24日〜当月23日になること"""
    from datetime import date
    import app as flask_app
    start, end = flask_app.get_cycle_range(2026, 3, start_day=24)
    assert start == date(2026, 2, 24)
    assert end == date(2026, 3, 23)


def test_cycle_range_crosses_year():
    """1月分のサイクルが前年12月24日から始まること"""
    from datetime import date
    import app as flask_app
    start, end = flask_app.get_cycle_range(2026, 1, start_day=24)
    assert start == date(2025, 12, 24)
    assert end == date(2026, 1, 23)


def test_cycle_length_varies_by_month():
    """サイクルの日数が月によって28〜31日に変わること"""
    import app as flask_app
    assert len(flask_app.get_cycle_dates(2026, 3, start_day=24)) == 28
    assert len(flask_app.get_cycle_dates(2026, 5, start_day=24)) == 30
    assert len(flask_app.get_cycle_dates(2026, 9, start_day=24)) == 31


def test_cycle_length_leap_year():
    """うるう年の3月分が29日になること"""
    import app as flask_app
    assert len(flask_app.get_cycle_dates(2028, 3, start_day=24)) == 29


def test_cycle_range_other_start_day():
    """締め日を20日にすると範囲が追随すること"""
    from datetime import date
    import app as flask_app
    start, end = flask_app.get_cycle_range(2026, 3, start_day=20)
    assert start == date(2026, 2, 20)
    assert end == date(2026, 3, 19)


def test_cycle_range_clamps_missing_day():
    """31日締めで2月のように31日が無い月は月末に丸めること"""
    from datetime import date
    import app as flask_app
    start, end = flask_app.get_cycle_range(2026, 3, start_day=31)
    assert start == date(2026, 2, 28)
    assert end == date(2026, 3, 30)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k cycle -v`
Expected: FAIL（`AttributeError: module 'app' has no attribute 'get_cycle_range'`）

- [ ] **Step 3: 実装する**

`app.py` の先頭の import に `calendar` を追加する。

```python
import calendar
```

`def _default_config() -> dict:` の直前に次を追加する。

```python
# ========== 点検サイクル ==========
# 日常点検は締め日で区切る。既定では「前月24日 〜 当月23日」が1サイクル。

DEFAULT_CYCLE_START_DAY = 24


def get_cycle_start_day() -> int:
    """点検サイクルの締め日を設定から取得する（不正値は既定値に戻す）"""
    try:
        day = int(load_config().get("cycle_start_day", DEFAULT_CYCLE_START_DAY))
    except (TypeError, ValueError):
        return DEFAULT_CYCLE_START_DAY
    return day if 1 <= day <= 31 else DEFAULT_CYCLE_START_DAY


def _clamp_day(year: int, month: int, day: int) -> date:
    """その月に存在しない日（2月31日など）は月末に丸める"""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def get_cycle_range(display_year: int, display_month: int, start_day: int = None):
    """表示月の点検サイクルを (開始日, 終了日) で返す"""
    if start_day is None:
        start_day = get_cycle_start_day()
    prev_month = display_month - 1 if display_month > 1 else 12
    prev_year = display_year if display_month > 1 else display_year - 1
    start = _clamp_day(prev_year, prev_month, start_day)
    end = _clamp_day(display_year, display_month, start_day) - timedelta(days=1)
    return start, end


def get_cycle_dates(display_year: int, display_month: int, start_day: int = None) -> list:
    """サイクル内の日付を1日ずつ並べて返す"""
    start, end = get_cycle_range(display_year, display_month, start_day)
    days = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    return days
```

`date` と `timedelta` は既に `from datetime import ...` で読み込まれている。読み込まれていなければ import に追加する。

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k cycle -v`
Expected: 6 passed

- [ ] **Step 5: コミット**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add inspection cycle helpers with configurable start day"
```

---

## Task 2: 締め日を設定ファイルに出す

`app.py:687` の直書きの `24` を Task 1 のヘルパー経由にし、設定で変えられるようにする。**既存の表PDFの日付範囲が変わらないことが合格条件。**

**Files:**
- Modify: `app.py`（`_default_config`、`api_post_config`、`_generate_pdf`）
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_default_config_has_cycle_start_day():
    """既定設定に cycle_start_day が含まれ、値が24であること"""
    import app as flask_app
    assert flask_app._default_config()["cycle_start_day"] == 24


def test_api_post_config_cycle_start_day(client):
    """cycle_start_day を保存できること"""
    c, _ = client
    res = c.post("/api/config",
                 data=json.dumps({"cycle_start_day": 20}),
                 content_type="application/json")
    assert res.status_code == 200
    assert c.get("/api/config").get_json()["cycle_start_day"] == 20


def test_api_post_config_cycle_start_day_out_of_range(client):
    """範囲外の cycle_start_day は400になること"""
    c, _ = client
    res = c.post("/api/config",
                 data=json.dumps({"cycle_start_day": 40}),
                 content_type="application/json")
    assert res.status_code == 400


def test_get_cycle_start_day_reads_config(client, monkeypatch):
    """設定の cycle_start_day が読まれること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "load_config", lambda: {"cycle_start_day": 20})
    assert flask_app.get_cycle_start_day() == 20


def test_get_cycle_start_day_falls_back(client, monkeypatch):
    """不正な cycle_start_day は既定値24に戻ること"""
    import app as flask_app
    for bad in (0, 32, -5, None, "abc", [1], {}):
        monkeypatch.setattr(flask_app, "load_config", lambda v=bad: {"cycle_start_day": v})
        assert flask_app.get_cycle_start_day() == 24, f"{bad!r} で24に戻らなかった"


def test_get_cycle_start_day_missing_key(client, monkeypatch):
    """設定にキーが無ければ既定値24を使うこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "load_config", lambda: {})
    assert flask_app.get_cycle_start_day() == 24


def test_generate_pdf_uses_cycle_range(client, monkeypatch):
    """PDF生成が get_cycle_range の範囲を使っていること（回帰）"""
    from datetime import date
    import app as flask_app
    called = {}
    original = flask_app.get_cycle_range

    def spy(y, m, start_day=None):
        called["args"] = (y, m)
        return original(y, m, start_day)

    monkeypatch.setattr(flask_app, "get_cycle_range", spy)
    c, _ = client
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert called["args"] == (2026, 3)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "cycle_start_day or generate_pdf_uses" -v`
Expected: FAIL（`KeyError: 'cycle_start_day'` など）

- [ ] **Step 3: 実装する**

`_default_config()` の戻り値の辞書に1行加える。

```python
        "save_directory": "",
        "cycle_start_day": 24,
        "server": {"host": "127.0.0.1", "port": 5000},
```

`api_post_config()` の `if "save_directory" in data:` ブロックの直後に追加する。

```python
    if "cycle_start_day" in data:
        try:
            day = int(data["cycle_start_day"])
        except (TypeError, ValueError):
            return jsonify({"error": "cycle_start_day は数値で指定してください"}), 400
        if not (1 <= day <= 31):
            return jsonify({"error": "cycle_start_day は1〜31の範囲で指定してください"}), 400
        config["cycle_start_day"] = day
```

`_generate_pdf()` の冒頭4行を置き換える。

置き換え前:

```python
    start_month = display_month - 1 if display_month > 1 else 12
    start_year = display_year if display_month > 1 else display_year - 1
    start_date = date(start_year, start_month, 24)
    end_date = date(display_year, display_month, 23)
```

置き換え後:

```python
    start_date, end_date = get_cycle_range(display_year, display_month)
    start_year, start_month = start_date.year, start_date.month
```

`start_year` / `start_month` は後段の `get_result_file_path("使用前", start_year, start_month)` で使われているため、必ず残すこと。

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: 既存38件＋新規10件すべて passed

- [ ] **Step 5: コミット**

```bash
git add app.py tests/test_app.py
git commit -m "refactor: read inspection cycle start day from config"
```

---

## Task 3: 画面側の締め日とコメント修正

**Files:**
- Modify: `tests/test_app.py`（Task 2 のレビューで見つかった穴を塞ぐ）
- Modify: `static/app.js:44-72`（`getDefaultTargetMonth` と `getCalendarRange`）、`static/app.js:1062`（`initApp`）
- Modify: `static/inspection.html`（キャッシュ回避のクエリ更新）

画面側は pytest では検証できない。**ブラウザでの動作確認が合格条件。**

- [ ] **Step 0: 前月ファイルを読むことを検証するテストを追加する**

Task 2 のレビューで、`_generate_pdf` の `start_year` / `start_month` が「前月」であることを直接検証しているテストが無いことが分かった。ここを書き間違えても既存テストは全件パスし、症状は例外ではなく「前月分が白紙のPDFになる」という静かなデータ欠落になる。先に塞ぐ。

```python
def test_generate_pdf_reads_previous_month_file(client, monkeypatch):
    """日常点検の結果を「前月」のファイルから読んでいること（静かなデータ欠落の防止）"""
    import app as flask_app
    read_files = []
    original = flask_app.get_result_file_path

    def spy(inspection_type, year, month):
        path = original(inspection_type, year, month)
        read_files.append((inspection_type, year, month))
        return path

    monkeypatch.setattr(flask_app, "get_result_file_path", spy)
    c, _ = client
    assert c.get("/api/pdf?display_year=2026&display_month=3").status_code == 200
    assert ("使用前", 2026, 2) in read_files, f"前月を読んでいない: {read_files}"


def test_generate_pdf_reads_previous_year_file_in_january(client, monkeypatch):
    """1月分では前年12月のファイルを読むこと（年またぎ）"""
    import app as flask_app
    read_files = []
    original = flask_app.get_result_file_path

    def spy(inspection_type, year, month):
        path = original(inspection_type, year, month)
        read_files.append((inspection_type, year, month))
        return path

    monkeypatch.setattr(flask_app, "get_result_file_path", spy)
    c, _ = client
    assert c.get("/api/pdf?display_year=2026&display_month=1").status_code == 200
    assert ("使用前", 2025, 12) in read_files, f"前年12月を読んでいない: {read_files}"
```

このテストが**現在の実装で通ること**を確認してから、わざと `start_year, start_month = display_year, display_month` に書き換えて**失敗することも確認**する（確認後は必ず元に戻す）。テストが本当に穴を塞げているかを確かめるため。

- [ ] **Step 1: 締め日を変数にする**

`static/app.js` の `const state = {` の直前に追加する。

```js
// 点検サイクルの締め日。/api/config 読み込み後に上書きする。
let cycleStartDay = 24;
```

- [ ] **Step 2: 2つの関数を書き換える**

`getDefaultTargetMonth()` の中の `if (now.getDate() >= 24) {` を次に変える。

```js
    if (now.getDate() >= cycleStartDay) {
```

`getCalendarRange()` を丸ごと書き換える。**コメントの「27日」は実装（23日）に合わせて直す。**

置き換え前:

```js
/**
 * 表示月（displayYearMonth）から点検カレンダー範囲を計算する。
 * 範囲：前月24日 〜 表示月27日
 */
function getCalendarRange(displayYearMonth) {
    const [y, m] = displayYearMonth.split("-").map(Number);
    const prevM = m === 1 ? 12 : m - 1;
    const prevY = m === 1 ? y - 1 : y;
    const start = new Date(prevY, prevM - 1, 24);
    const end = new Date(y, m - 1, 23);
    return { start, end };
}
```

置き換え後:

```js
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
```

- [ ] **Step 3: 設定読み込み後に締め日を反映する**

`initApp()` の `state.config = config;` の直後に追加する。

```js
        const cfgDay = Number(state.config.cycle_start_day);
        if (Number.isInteger(cfgDay) && cfgDay >= 1 && cfgDay <= 31) {
            cycleStartDay = cfgDay;
            // 締め日が既定と違う場合は表示月を計算し直す
            state.targetYearMonth = getDefaultTargetMonth();
            document.getElementById("target-month").value = state.targetYearMonth;
        }
```

- [ ] **Step 4: キャッシュ回避のクエリを進める**

`static/inspection.html` の `app.js` を読み込む行のクエリ番号を1つ上げる（例: `?v=3` → `?v=4`）。クエリが無ければ `?v=1` を付ける。

- [ ] **Step 5: ブラウザで確認**

`起動.bat` からアプリを起動し、点検画面を開く。次の3点を目視で確認する。

1. 月例点検タブでカレンダーの範囲が「前月24日〜当月23日」になっている
2. 設定画面から保存しても表示が崩れない
3. ブラウザの開発者ツールのコンソールにエラーが出ていない

- [ ] **Step 6: コミット**

```bash
git add static/app.js static/inspection.html
git commit -m "refactor: read cycle start day from config in inspection screen"
```

---

## Task 4: マスタCSVの入力方式と単位

**Files:**
- Create: `forms_layout.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== マスタCSVの入力方式 ==========

def test_item_input_type_defaults_to_judgment():
    """input_type 列が無い行は判定になること"""
    import forms_layout
    row = {"category_minor": "A-1", "inspection_item": "傷はないか"}
    assert forms_layout.item_input_type(row) == "判定"


def test_item_input_type_empty_is_judgment():
    """input_type が空欄の行は判定になること"""
    import forms_layout
    assert forms_layout.item_input_type({"input_type": ""}) == "判定"
    assert forms_layout.item_input_type({"input_type": "  "}) == "判定"


def test_item_input_type_number():
    """input_type が数値の行は数値になること"""
    import forms_layout
    assert forms_layout.item_input_type({"input_type": "数値"}) == "数値"


def test_item_input_type_unknown_falls_back():
    """知らない値は判定として扱うこと"""
    import forms_layout
    assert forms_layout.item_input_type({"input_type": "なにか"}) == "判定"


def test_item_unit():
    """数値の行から単位が読めること"""
    import forms_layout
    assert forms_layout.item_unit({"input_type": "数値", "unit": "MPa"}) == "MPa"
    assert forms_layout.item_unit({"input_type": "判定", "unit": "MPa"}) == ""
    assert forms_layout.item_unit({"input_type": "数値"}) == ""
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "input_type or item_unit" -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'forms_layout'`）

- [ ] **Step 3: 実装する**

`forms_layout.py` を新規作成する。

```python
"""様式レイアウト（layout.json）の読み書きと座標計算。

様式は forms/<様式ID>/ に form.pdf と layout.json を置くフォルダ単位で管理する。
"""
import json
import logging
import os
import re
from pathlib import Path

from filelock import FileLock

logger = logging.getLogger("equipment_inspection")

INPUT_TYPE_JUDGMENT = "判定"
INPUT_TYPE_NUMBER = "数値"
_VALID_INPUT_TYPES = (INPUT_TYPE_JUDGMENT, INPUT_TYPE_NUMBER)


def item_input_type(row: dict) -> str:
    """点検項目マスタの1行から入力方式を返す。

    列が無い・空欄・知らない値はすべて「判定」として扱う（後方互換）。
    """
    value = (row.get("input_type") or "").strip()
    return value if value in _VALID_INPUT_TYPES else INPUT_TYPE_JUDGMENT


def item_unit(row: dict) -> str:
    """点検項目マスタの1行から単位を返す。数値項目以外は空文字を返す。"""
    if item_input_type(row) != INPUT_TYPE_NUMBER:
        return ""
    return (row.get("unit") or "").strip()
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "input_type or item_unit" -v`
Expected: 5 passed

- [ ] **Step 5: コミット**

```bash
git add forms_layout.py tests/test_app.py
git commit -m "feat: read input_type and unit columns from equipment master"
```

---

## Task 5: 数値の正規化とサーバ側検証

全角で入力された数値を半角に直してから保存し、数値として読めない値は 400 で拒否する。

**Files:**
- Modify: `app.py`（`_validate_results` の直前と `api_post_results`）
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 数値の正規化 ==========

def test_normalize_number_converts_fullwidth():
    """全角数字・全角ピリオド・全角マイナスが半角になること"""
    import app as flask_app
    assert flask_app._normalize_number("０．５２") == "0.52"
    assert flask_app._normalize_number("－１２") == "-12"
    assert flask_app._normalize_number("　1.5　") == "1.5"


def test_normalize_number_keeps_halfwidth():
    """半角の値はそのまま返すこと"""
    import app as flask_app
    assert flask_app._normalize_number("0.52") == "0.52"


def test_is_number_like():
    """数値として読める文字列を判定できること"""
    import app as flask_app
    assert flask_app._is_number_like("0.52") is True
    assert flask_app._is_number_like("-3") is True
    assert flask_app._is_number_like("") is False
    assert flask_app._is_number_like("あ") is False
    assert flask_app._is_number_like("1.2.3") is False


def test_post_results_normalizes_fullwidth_number(client, monkeypatch, tmp_path):
    """数値項目に全角で送ると半角に直して保存されること"""
    import app as flask_app
    master = tmp_path / "equipment_master.csv"
    master.write_text(
        "category_major,category_minor,inspection_item,inspection_type,input_type,unit\n"
        "設備A,A-1,油圧,使用前,数値,MPa\n",
        encoding="utf-8")
    monkeypatch.setattr(flask_app, "EQUIPMENT_CSV", master)
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "2026-03-02",
        "category_major": "設備A",
        "category_minor": "A-1",
        "inspector_name": "テスト",
        "department": "テスト部",
        "results": [{"equipment_name": "設備A", "inspection_item": "油圧",
                     "result": "０．５２", "remark": ""}],
    }
    res = c.post("/api/results", data=json.dumps(payload),
                 content_type="application/json")
    assert res.status_code == 200
    saved = json.loads(Path(res.get_json()["file"]).read_text(encoding="utf-8"))
    assert saved[0]["results"][0]["result"] == "0.52"


def test_post_results_rejects_non_numeric_for_number_item(client, monkeypatch, tmp_path):
    """数値項目に数値でない値を送ると400になること"""
    import app as flask_app
    master = tmp_path / "equipment_master.csv"
    master.write_text(
        "category_major,category_minor,inspection_item,inspection_type,input_type,unit\n"
        "設備A,A-1,油圧,使用前,数値,MPa\n",
        encoding="utf-8")
    monkeypatch.setattr(flask_app, "EQUIPMENT_CSV", master)
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "2026-03-02",
        "category_major": "設備A",
        "category_minor": "A-1",
        "inspector_name": "テスト",
        "department": "テスト部",
        "results": [{"equipment_name": "設備A", "inspection_item": "油圧",
                     "result": "こわれてる", "remark": ""}],
    }
    res = c.post("/api/results", data=json.dumps(payload),
                 content_type="application/json")
    assert res.status_code == 400


def test_post_results_judgment_item_not_normalized(client, monkeypatch, tmp_path):
    """判定項目の「ー」がそのまま保存されること"""
    import app as flask_app
    master = tmp_path / "equipment_master.csv"
    master.write_text(
        "category_major,category_minor,inspection_item,inspection_type,input_type,unit\n"
        "設備A,A-1,傷はないか,使用前,判定,\n",
        encoding="utf-8")
    monkeypatch.setattr(flask_app, "EQUIPMENT_CSV", master)
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "2026-03-02",
        "category_major": "設備A",
        "category_minor": "A-1",
        "inspector_name": "テスト",
        "department": "テスト部",
        "results": [{"equipment_name": "設備A", "inspection_item": "傷はないか",
                     "result": "ー", "remark": ""}],
    }
    res = c.post("/api/results", data=json.dumps(payload),
                 content_type="application/json")
    assert res.status_code == 200
    saved = json.loads(Path(res.get_json()["file"]).read_text(encoding="utf-8"))
    assert saved[0]["results"][0]["result"] == "ー"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "normalize_number or number_like or post_results_normalizes or post_results_rejects_non_numeric or judgment_item_not_normalized" -v`
Expected: FAIL（`AttributeError: module 'app' has no attribute '_normalize_number'`）

- [ ] **Step 3: 実装する**

`app.py` の `def _validate_results(data: dict) -> list:` の直前に追加する。

```python
# ========== 数値の正規化 ==========
# 日本語入力がONのまま打つと「０．５２」と全角で入る。画面側でも直すが、
# 保存される値の正しさはここで担保する。

_FULLWIDTH_MAP = str.maketrans(
    "０１２３４５６７８９．－−ー",
    "0123456789.---"
)


def _normalize_number(value: str) -> str:
    """全角数字・全角ピリオド・全角マイナスを半角に直し、前後の空白を落とす"""
    if not isinstance(value, str):
        return value
    return value.translate(_FULLWIDTH_MAP).replace("　", " ").strip()


def _is_number_like(value: str) -> bool:
    """数値として読める文字列かどうかを返す"""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def _number_item_keys() -> set:
    """マスタで「数値」と指定されている項目のキー集合を返す"""
    keys = set()
    for row in read_csv_as_list(EQUIPMENT_CSV):
        if forms_layout.item_input_type(row) == forms_layout.INPUT_TYPE_NUMBER:
            keys.add(row.get("inspection_item", ""))
    return keys
```

`_normalize_number` は判定項目の「ー」も半角ハイフンに変えてしまうため、**数値項目にだけ適用する**。

`app.py` の import に追加する。

```python
import forms_layout
```

`_validate_results(data)` の `results` のチェックの後（`for key in ("category_major", ...)` の直前）に追加する。

```python
    if isinstance(results, list):
        number_keys = _number_item_keys()
        for r in results:
            if not isinstance(r, dict):
                continue
            item = r.get("inspection_item", "")
            if item not in number_keys:
                continue
            value = _normalize_number(r.get("result", ""))
            if value and not _is_number_like(value):
                errors.append(f"{item} は数値で入力してください: {r.get('result')}")
```

`api_post_results()` の `errors = _validate_results(data)` の**直前**に正規化を挿入する。

```python
    number_keys = _number_item_keys()
    for r in data.get("results", []):
        if isinstance(r, dict) and r.get("inspection_item") in number_keys:
            r["result"] = _normalize_number(r.get("result", ""))

    errors = _validate_results(data)
```

**正規化してから検証する。** 全角で送られた正しい数値（`０．５２`）は半角に直されて検証を通り、正規化しても数値にならない値（`こわれてる`）だけが弾かれる。

`_validate_results` の中でも同じ正規化をしているが、これは関数単体で呼ばれたときのための保険であり、二重に走っても結果は変わらない（半角の値をもう一度正規化しても同じ値になる）。

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: すべて passed

- [ ] **Step 5: コミット**

```bash
git add app.py tests/test_app.py
git commit -m "feat: normalize and validate numeric inspection values"
```

---

## Task 6: layout.json の読み書き

**Files:**
- Modify: `forms_layout.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== layout.json の読み書き ==========

def _write_layout(tmp_path, form_id, layout):
    """テスト用に様式フォルダと layout.json を作る"""
    d = tmp_path / form_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "layout.json").write_text(
        json.dumps(layout, ensure_ascii=False), encoding="utf-8")
    return d


SAMPLE_LAYOUT = {
    "form_name": "吊具月例点検表",
    "period": "year",
    "inspection_type": "月例",
    "targets": ["吊具A", "吊具B"],
    "axis": {"step_x": 38.0, "step_y": 0.0, "count": 12},
    "default_font_size": 11,
    "fields": [
        {"source": "meta.month", "page": 0, "x": 90.0, "y": 780.0},
        {"source": "item:吊具A|傷はないか", "page": 0, "x": 120.0, "y": 660.0,
         "on_axis": True},
    ],
}


def test_load_layout(tmp_path):
    """layout.json を読めること"""
    import forms_layout
    d = _write_layout(tmp_path, "tsurigu", SAMPLE_LAYOUT)
    layout = forms_layout.load_layout(d)
    assert layout["form_name"] == "吊具月例点検表"
    assert layout["period"] == "year"
    assert len(layout["fields"]) == 2


def test_load_layout_broken_json_raises(tmp_path):
    """壊れた layout.json は LayoutError になること"""
    import forms_layout
    d = tmp_path / "broken"
    d.mkdir()
    (d / "layout.json").write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_load_layout_missing_period_raises(tmp_path):
    """period が無い layout.json は LayoutError になること"""
    import forms_layout
    bad = dict(SAMPLE_LAYOUT)
    del bad["period"]
    d = _write_layout(tmp_path, "nofield", bad)
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_save_layout_roundtrip(tmp_path):
    """保存した内容を読み戻せること"""
    import forms_layout
    d = tmp_path / "new"
    d.mkdir()
    forms_layout.save_layout(d, SAMPLE_LAYOUT)
    assert forms_layout.load_layout(d)["form_name"] == "吊具月例点検表"


def test_save_layout_leaves_no_tmp_file(tmp_path):
    """保存後に一時ファイルが残らないこと"""
    import forms_layout
    d = tmp_path / "atomic"
    d.mkdir()
    forms_layout.save_layout(d, SAMPLE_LAYOUT)
    assert not list(d.glob("*.tmp"))


def test_list_forms(tmp_path):
    """様式一覧を取得できること"""
    import forms_layout
    _write_layout(tmp_path, "tsurigu", SAMPLE_LAYOUT)
    forms = forms_layout.list_forms(tmp_path)
    assert len(forms) == 1
    assert forms[0]["id"] == "tsurigu"
    assert forms[0]["form_name"] == "吊具月例点検表"
    assert forms[0]["error"] == ""


def test_list_forms_reports_broken_layout(tmp_path):
    """壊れた様式は例外ではなく error 付きで返すこと"""
    import forms_layout
    d = tmp_path / "broken"
    d.mkdir()
    (d / "layout.json").write_text("{ oops", encoding="utf-8")
    forms = forms_layout.list_forms(tmp_path)
    assert len(forms) == 1
    assert forms[0]["error"] != ""


def test_valid_form_id():
    """様式IDは半角英数字とアンダースコアのみ許すこと"""
    import forms_layout
    assert forms_layout.is_valid_form_id("crane_1") is True
    assert forms_layout.is_valid_form_id("../etc") is False
    assert forms_layout.is_valid_form_id("吊具") is False
    assert forms_layout.is_valid_form_id("") is False
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "layout or list_forms or valid_form_id" -v`
Expected: FAIL（`AttributeError: module 'forms_layout' has no attribute 'load_layout'`）

- [ ] **Step 3: 実装する**

`forms_layout.py` の `item_unit` の後に追加する。

```python
LAYOUT_FILENAME = "layout.json"
FORM_PDF_FILENAME = "form.pdf"
VALID_PERIODS = ("year", "month", "single")
DEFAULT_AXIS_COUNT = {"year": 12, "month": 31}
_FORM_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")


class LayoutError(Exception):
    """layout.json が読めない・内容が不正なときに投げる"""


def is_valid_form_id(form_id: str) -> bool:
    """様式IDが安全か（パストラバーサル対策）"""
    if not isinstance(form_id, str) or not form_id:
        return False
    return bool(_FORM_ID_RE.match(form_id))


def _validate_layout(layout: dict):
    """layout.json の内容を検証する。問題があれば LayoutError を投げる。"""
    if not isinstance(layout, dict):
        raise LayoutError("layout.json の中身がオブジェクトではありません")
    period = layout.get("period")
    if period not in VALID_PERIODS:
        raise LayoutError(f"period が不正です: {period}")
    if not isinstance(layout.get("targets"), list):
        raise LayoutError("targets は配列で指定してください")
    if not isinstance(layout.get("fields"), list):
        raise LayoutError("fields は配列で指定してください")
    if period in DEFAULT_AXIS_COUNT and not isinstance(layout.get("axis"), dict):
        raise LayoutError(f"period={period} には axis が必要です")


def load_layout(form_dir: Path) -> dict:
    """様式フォルダから layout.json を読む"""
    path = Path(form_dir) / LAYOUT_FILENAME
    if not path.exists():
        raise LayoutError(f"{LAYOUT_FILENAME} がありません: {form_dir}")
    try:
        with open(path, encoding="utf-8-sig") as f:
            layout = json.load(f)
    except json.JSONDecodeError as e:
        raise LayoutError(f"{LAYOUT_FILENAME} が壊れています: {e}") from e
    except UnicodeDecodeError as e:
        # メモ帳などが cp932 で保存し直すことが実際に起こる。
        # ここで捕まえないとアプリ全体が落ちる。
        raise LayoutError(
            f"{LAYOUT_FILENAME} の文字コードが不正です（UTF-8で保存してください）: {e}") from e
    except OSError as e:
        raise LayoutError(f"{LAYOUT_FILENAME} が読めません: {e}") from e
    _validate_layout(layout)
    return layout


def save_layout(form_dir: Path, layout: dict):
    """layout.json を保存する（排他制御・一時ファイル経由の原子的書き込み）"""
    _validate_layout(layout)
    form_dir = Path(form_dir)
    form_dir.mkdir(parents=True, exist_ok=True)
    path = form_dir / LAYOUT_FILENAME
    lock_path = str(path) + ".lock"
    with FileLock(lock_path, timeout=10):
        tmp = str(path) + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(layout, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise


def list_forms(forms_dir: Path) -> list:
    """様式フォルダ配下の様式を一覧する。壊れた様式は error 付きで返す。"""
    forms_dir = Path(forms_dir)
    if not forms_dir.exists():
        return []
    forms = []
    for d in sorted(p for p in forms_dir.iterdir() if p.is_dir()):
        entry = {"id": d.name, "form_name": d.name, "period": "",
                 "targets": [], "has_pdf": (d / FORM_PDF_FILENAME).exists(),
                 "error": ""}
        try:
            layout = load_layout(d)
            entry["form_name"] = layout.get("form_name", d.name)
            entry["period"] = layout.get("period", "")
            entry["targets"] = layout.get("targets", [])
        except LayoutError as e:
            entry["error"] = str(e)
            logger.warning("様式の設定エラー %s: %s", d.name, e)
        forms.append(entry)
    return forms
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "layout or list_forms or valid_form_id" -v`
Expected: 8 passed

- [ ] **Step 5: コミット**

```bash
git add forms_layout.py tests/test_app.py
git commit -m "feat: add layout.json load, save and listing"
```

---

## Task 7: 軸の座標計算と機器の紐づけ

**Files:**
- Modify: `forms_layout.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 軸の座標計算 ==========

AXIS = {"step_x": 38.0, "step_y": 0.0, "count": 12}


def test_axis_position_first_slot():
    """1番目の欄はフィールドの座標そのものになること"""
    import forms_layout
    field = {"x": 120.0, "y": 660.0, "on_axis": True}
    assert forms_layout.axis_position(field, AXIS, 1) == (120.0, 660.0)


def test_axis_position_horizontal():
    """横並びの軸で n に応じて x がずれること"""
    import forms_layout
    field = {"x": 120.0, "y": 660.0, "on_axis": True}
    assert forms_layout.axis_position(field, AXIS, 6) == (310.0, 660.0)
    assert forms_layout.axis_position(field, AXIS, 12) == (538.0, 660.0)


def test_axis_position_vertical():
    """縦並びの軸で n に応じて y がずれること"""
    import forms_layout
    axis = {"step_x": 0.0, "step_y": -20.0, "count": 31}
    field = {"x": 100.0, "y": 700.0, "on_axis": True}
    assert forms_layout.axis_position(field, axis, 3) == (100.0, 660.0)


def test_axis_position_ignores_axis_when_not_on_axis():
    """on_axis でないフィールドは軸の影響を受けないこと"""
    import forms_layout
    field = {"x": 120.0, "y": 660.0}
    assert forms_layout.axis_position(field, AXIS, 9) == (120.0, 660.0)


def test_axis_count():
    """欄数は axis.count、無ければ period の既定値を使うこと"""
    import forms_layout
    assert forms_layout.axis_count({"period": "year", "axis": {"count": 6}}) == 6
    assert forms_layout.axis_count({"period": "year", "axis": {}}) == 12
    assert forms_layout.axis_count({"period": "month", "axis": {}}) == 31
    assert forms_layout.axis_count({"period": "single"}) == 0


# ========== 機器と様式の紐づけ ==========

def test_form_assignments(tmp_path):
    """機器名から様式IDを引けること"""
    import forms_layout
    _write_layout(tmp_path, "tsurigu", SAMPLE_LAYOUT)
    assignments = forms_layout.form_assignments(tmp_path)
    assert assignments["吊具A"] == ["tsurigu"]
    assert assignments["吊具B"] == ["tsurigu"]
    assert "クレーン1" not in assignments


def test_form_assignments_multiple_forms(tmp_path):
    """同じ機器が複数の様式に載っている場合は両方返すこと"""
    import forms_layout
    _write_layout(tmp_path, "form_a", SAMPLE_LAYOUT)
    other = dict(SAMPLE_LAYOUT)
    other["targets"] = ["吊具A"]
    _write_layout(tmp_path, "form_b", other)
    assignments = forms_layout.form_assignments(tmp_path)
    assert sorted(assignments["吊具A"]) == ["form_a", "form_b"]


def test_form_assignments_skips_broken(tmp_path):
    """壊れた様式は紐づけから除外されること"""
    import forms_layout
    d = tmp_path / "broken"
    d.mkdir()
    (d / "layout.json").write_text("{ oops", encoding="utf-8")
    assert forms_layout.form_assignments(tmp_path) == {}
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "axis_ or form_assignments" -v`
Expected: FAIL（`AttributeError: module 'forms_layout' has no attribute 'axis_position'`）

- [ ] **Step 3: 実装する**

`forms_layout.py` の末尾に追加する。

```python
def axis_position(field: dict, axis: dict, n: int):
    """軸の n 番目（1始まり）におけるフィールドの印字位置を返す。

    on_axis でないフィールドは軸の影響を受けず、そのままの座標を返す。
    """
    x = float(field.get("x", 0.0))
    y = float(field.get("y", 0.0))
    if not field.get("on_axis"):
        return (x, y)
    step_x = float((axis or {}).get("step_x", 0.0))
    step_y = float((axis or {}).get("step_y", 0.0))
    return (x + step_x * (n - 1), y + step_y * (n - 1))


def axis_count(layout: dict) -> int:
    """様式に用意されている欄の数を返す。single 型は 0。"""
    period = layout.get("period", "")
    if period not in DEFAULT_AXIS_COUNT:
        return 0
    axis = layout.get("axis") or {}
    try:
        count = int(axis.get("count", DEFAULT_AXIS_COUNT[period]))
    except (TypeError, ValueError):
        return DEFAULT_AXIS_COUNT[period]
    return count if count > 0 else DEFAULT_AXIS_COUNT[period]


def form_assignments(forms_dir: Path) -> dict:
    """機器名 → その機器が載っている様式IDのリスト、を返す。

    設定が壊れている様式は除外する（表出力にフォールバックさせるため）。
    """
    assignments = {}
    for entry in list_forms(forms_dir):
        if entry["error"]:
            continue
        for name in entry["targets"]:
            assignments.setdefault(name, []).append(entry["id"])
    return assignments
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "axis_ or form_assignments" -v`
Expected: 8 passed

- [ ] **Step 5: コミット**

```bash
git add forms_layout.py tests/test_app.py
git commit -m "feat: add axis position calculation and equipment-to-form mapping"
```

---

## Task 8: pypdf の導入

**このタスクはユーザーの承認が必要。承認を得るまで先に進まないこと。**

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: ユーザーに説明して承認を得る**

次の内容を伝えて承認を得る。

- パッケージ名: `pypdf`
- 目的: 既存の様式PDFに、点検結果の文字レイヤーを重ねるため。reportlab だけでは既存PDFを読み込めない
- 影響範囲: このアプリの `.venv` 内のみ（ローカルインストール）
- 素性: GitHubスター約9,000、活発に更新されている純Pythonライブラリ

- [ ] **Step 2: セキュリティスキャンを実行**

`package-security-scan` スキルで `pypdf` をスキャンし、結果をユーザーに報告する。問題が見つかった場合はここで停止する。

- [ ] **Step 3: requirements.txt に追加**

`requirements.txt` の `reportlab` の次の行に追加する。

```
pypdf
```

- [ ] **Step 4: インストールして動作確認**

Run: `.venv\Scripts\python.exe -m pip install pypdf`
Run: `.venv\Scripts\python.exe -c "import pypdf; print(pypdf.__version__)"`
Expected: バージョン番号が表示される

- [ ] **Step 5: 既存テストが壊れていないことを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: すべて passed

- [ ] **Step 6: コミット**

```bash
git add requirements.txt
git commit -m "chore: add pypdf for overlaying results onto form PDFs"
```

---

## Task 9: 軸の各欄へのデータ割り当て

様式の n 番目の欄に、どの日付のどの結果を入れるかを決める。**PDFを触らない純粋な計算なのでテストしやすい。**

**Files:**
- Create: `pdf_forms.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 軸の欄へのデータ割り当て ==========

def test_build_slots_month_maps_cycle_dates():
    """month 型で n=1 がサイクル開始日になること"""
    from datetime import date, timedelta
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    cycle_dates = [date(2026, 2, 24) + timedelta(days=i) for i in range(28)]
    slots = pdf_forms.build_slots(layout, 2026, 3, cycle_dates, {}, {})
    assert slots[1]["date"] == date(2026, 2, 24)
    assert slots[28]["date"] == date(2026, 3, 23)


def test_build_slots_month_marks_extra_slots():
    """28日サイクルで29〜31番目が「該当日なし」になること"""
    from datetime import date, timedelta
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    cycle_dates = [date(2026, 2, 24) + timedelta(days=i) for i in range(28)]
    slots = pdf_forms.build_slots(layout, 2026, 3, cycle_dates, {}, {})
    assert slots[28]["exists"] is True
    assert slots[29]["exists"] is False
    assert slots[31]["exists"] is False
    assert slots[29]["date"] is None


def test_build_slots_year_maps_months():
    """year 型で n が月に対応すること"""
    import pdf_forms
    layout = {"period": "year", "axis": {"count": 12}}
    slots = pdf_forms.build_slots(layout, 2026, 9, [], {}, {})
    assert slots[1]["month"] == 1
    assert slots[12]["month"] == 12
    assert all(slots[n]["exists"] for n in range(1, 13))


def test_build_slots_marks_saturday_sunday_holiday():
    """土曜・日曜・祝日・会社休業日の印がつくこと"""
    from datetime import date, timedelta
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    # 2026-02-28 は土曜、2026-03-01 は日曜
    cycle_dates = [date(2026, 2, 24) + timedelta(days=i) for i in range(28)]
    custom = {"2026-03-20": "創立記念日"}
    slots = pdf_forms.build_slots(layout, 2026, 3, cycle_dates, {}, custom)
    by_date = {s["date"]: s for s in slots.values() if s["date"]}
    assert by_date[date(2026, 2, 28)]["mark"] == "saturday"
    assert by_date[date(2026, 3, 1)]["mark"] == "holiday"
    assert by_date[date(2026, 3, 20)]["mark"] == "holiday"
    assert by_date[date(2026, 2, 25)]["mark"] == ""


def test_build_slots_saturday_holiday_prefers_holiday():
    """土曜かつ祝日の日は holiday（赤）になること"""
    from datetime import date, timedelta
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    cycle_dates = [date(2026, 2, 24) + timedelta(days=i) for i in range(28)]
    # 2026-02-28（土）を会社休業日に指定する
    slots = pdf_forms.build_slots(layout, 2026, 3, cycle_dates, {},
                                  {"2026-02-28": "臨時休業"})
    by_date = {s["date"]: s for s in slots.values() if s["date"]}
    assert by_date[date(2026, 2, 28)]["mark"] == "holiday"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k build_slots -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'pdf_forms'`）

- [ ] **Step 3: 実装する**

`pdf_forms.py` を新規作成する。

```python
"""様式PDFへの点検結果の重ね書き。

軸の各欄に入るデータを組み立てる build_slots と、
それを reportlab で描いて pypdf で様式に重ねる build_form_pdf からなる。
"""
import logging

import jpholiday

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


def build_slots(layout: dict, display_year: int, display_month: int,
                cycle_dates: list, results_by_key: dict,
                custom_holidays: dict) -> dict:
    """軸の各欄（n: 1始まり）に入るデータを組み立てる。

    戻り値の各欄は次のキーを持つ。
      date   … その欄の日付（year 型は None）
      month  … その欄の月（month 型は None）
      exists … その欄が実在するか（余りマスは False）
      mark   … "" / "saturday" / "holiday"
      values … {"<機器名>|<点検項目名>": 結果} の辞書
      remarks… {"<機器名>|<点検項目名>": 備考} の辞書
      meta   … 点検者名などの共通項目
    """
    period = layout.get("period", "")
    count = forms_layout.axis_count(layout)
    slots = {}
    for n in range(1, count + 1):
        slot = {"date": None, "month": None, "exists": False, "mark": "",
                "values": {}, "remarks": {}, "meta": {}}
        if period == "month":
            if n <= len(cycle_dates):
                d = cycle_dates[n - 1]
                slot["date"] = d
                slot["exists"] = True
                slot["mark"] = _day_mark(d, custom_holidays)
                record = results_by_key.get(d.strftime("%Y-%m-%d"))
                if record:
                    slot["values"] = record.get("values", {})
                    slot["remarks"] = record.get("remarks", {})
                    slot["meta"] = record.get("meta", {})
        elif period == "year":
            slot["month"] = n
            slot["exists"] = True
            record = results_by_key.get(n)
            if record:
                slot["values"] = record.get("values", {})
                slot["remarks"] = record.get("remarks", {})
                slot["meta"] = record.get("meta", {})
        slots[n] = slot
    return slots
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k build_slots -v`
Expected: 5 passed

- [ ] **Step 5: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: map inspection results onto form axis slots"
```

---

## Task 10: 結果ファイルから欄データへの変換

保存されている結果JSONを、Task 9 の `results_by_key` の形に変換する。

**Files:**
- Modify: `pdf_forms.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 結果ファイルの変換 ==========

RECORDS = [
    {
        "inspection_date": "2026-02-25",
        "inspection_type": "使用前",
        "category_minor": "吊具A",
        "inspector_name": "山田 太郎",
        "department": "施設管理部",
        "general_remark": "特になし",
        "building_name": "仮ビル 本館",
        "results": [
            {"equipment_name": "吊具A", "inspection_item": "傷はないか",
             "result": "○", "remark": ""},
            {"equipment_name": "吊具A", "inspection_item": "油圧",
             "result": "0.52", "remark": "やや低い"},
        ],
        "submitted_at": "2026-02-25T09:00:00",
    },
    {
        "inspection_date": "2026-02-25",
        "inspection_type": "使用前",
        "category_minor": "吊具A",
        "inspector_name": "鈴木 花子",
        "department": "設備管理課",
        "general_remark": "",
        "building_name": "仮ビル 本館",
        "results": [
            {"equipment_name": "吊具A", "inspection_item": "傷はないか",
             "result": "×", "remark": "要交換"},
        ],
        "submitted_at": "2026-02-25T15:00:00",
    },
]


def test_index_by_date_groups_results():
    """日付ごとに結果をまとめられること"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(RECORDS, ["吊具A"])
    assert "2026-02-25" in indexed
    assert indexed["2026-02-25"]["values"]["吊具A|油圧"] == "0.52"


def test_index_by_date_uses_latest_record():
    """同じ日に複数の記録があれば submitted_at が新しい方を使うこと"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(RECORDS, ["吊具A"])
    assert indexed["2026-02-25"]["values"]["吊具A|傷はないか"] == "×"
    assert indexed["2026-02-25"]["meta"]["inspector"] == "鈴木 花子"


def test_index_by_date_filters_by_target():
    """targets に無い機器の記録は無視すること"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(RECORDS, ["吊具B"])
    assert indexed == {}


def test_index_by_month_uses_latest_record():
    """月ごとに最新の記録を使えること"""
    import pdf_forms
    indexed = pdf_forms.index_by_month(RECORDS, ["吊具A"])
    assert 2 in indexed
    assert indexed[2]["values"]["吊具A|傷はないか"] == "×"


def test_index_by_date_keeps_remarks():
    """備考も取り出せること"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(RECORDS, ["吊具A"])
    assert indexed["2026-02-25"]["remarks"]["吊具A|傷はないか"] == "要交換"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k index_by -v`
Expected: FAIL（`AttributeError: module 'pdf_forms' has no attribute 'index_by_date'`）

- [ ] **Step 3: 実装する**

`pdf_forms.py` に追加する。

```python
def _record_payload(record: dict) -> dict:
    """1件の点検記録を values / remarks / meta に分解する"""
    values, remarks = {}, {}
    for r in record.get("results", []):
        key = f"{r.get('equipment_name', '')}|{r.get('inspection_item', '')}"
        values[key] = r.get("result", "")
        remarks[key] = r.get("remark", "")
    meta = {
        "inspection_date": record.get("inspection_date", ""),
        "inspector": record.get("inspector_name", ""),
        "department": record.get("department", ""),
        "building_name": record.get("building_name", ""),
        "general_remark": record.get("general_remark", ""),
    }
    return {"values": values, "remarks": remarks, "meta": meta}


def _merge_latest(store: dict, key, record: dict):
    """同じキーに複数の記録があれば submitted_at が新しい方で上書きする"""
    stamp = record.get("submitted_at", "")
    current = store.get(key)
    if current is not None and current["_stamp"] > stamp:
        return
    payload = _record_payload(record)
    payload["_stamp"] = stamp
    store[key] = payload


def index_by_date(records: list, targets: list) -> dict:
    """点検記録を「日付文字列 → 欄データ」に変換する（month 型で使う）"""
    targets = set(targets)
    store = {}
    for record in records:
        if record.get("category_minor") not in targets:
            continue
        _merge_latest(store, record.get("inspection_date", ""), record)
    return store


def index_by_month(records: list, targets: list) -> dict:
    """点検記録を「月(1〜12) → 欄データ」に変換する（year 型で使う）"""
    targets = set(targets)
    store = {}
    for record in records:
        if record.get("category_minor") not in targets:
            continue
        date_str = record.get("inspection_date", "")
        try:
            month = int(date_str.split("-")[1])
        except (IndexError, ValueError):
            continue
        _merge_latest(store, month, record)
    return store
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k index_by -v`
Expected: 5 passed

- [ ] **Step 5: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: index inspection records by date and month for forms"
```

---

## Task 11: 様式PDFへの重ね書き

**Files:**
- Modify: `pdf_forms.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 様式PDFへの重ね書き ==========

def _make_form_pdf(path, pages=1):
    """テスト用の白紙PDFを作る"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    c = canvas.Canvas(str(path), pagesize=A4)
    for _ in range(pages):
        c.showPage()
    c.save()
    return path


def test_build_form_pdf_keeps_page_count(tmp_path):
    """重ね書きしてもページ数が変わらないこと"""
    import pdf_forms
    from pypdf import PdfReader
    form = _make_form_pdf(tmp_path / "form.pdf", pages=2)
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "meta.inspector", "page": 0, "x": 100, "y": 700},
    ]}
    out = tmp_path / "out.pdf"
    writer = pdf_forms.build_form_pdf(
        form, layout, {}, {"inspector": "山田 太郎", "year": 2026, "month": 3})
    with open(out, "wb") as f:
        writer.write(f)
    assert len(PdfReader(str(out)).pages) == 2


def test_build_form_pdf_writes_text(tmp_path):
    """配置した文字がPDFに入っていること"""
    import pdf_forms
    from pypdf import PdfReader
    form = _make_form_pdf(tmp_path / "form.pdf")
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "meta.inspector", "page": 0, "x": 100, "y": 700},
    ]}
    out = tmp_path / "out.pdf"
    writer = pdf_forms.build_form_pdf(
        form, layout, {}, {"inspector": "ヤマダ", "year": 2026, "month": 3})
    with open(out, "wb") as f:
        writer.write(f)
    assert "ヤマダ" in PdfReader(str(out)).pages[0].extract_text()


def test_build_form_pdf_skips_out_of_range_page(tmp_path):
    """様式のページ数を超える page 指定は落ちずに飛ばすこと"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf", pages=1)
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "meta.inspector", "page": 5, "x": 100, "y": 700},
    ]}
    writer = pdf_forms.build_form_pdf(
        form, layout, {}, {"inspector": "ヤマダ", "year": 2026, "month": 3})
    assert len(writer.pages) == 1


def test_build_form_pdf_prints_month(tmp_path):
    """タイトルの月（meta.month）が印字されること"""
    import pdf_forms
    from pypdf import PdfReader
    form = _make_form_pdf(tmp_path / "form.pdf")
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "meta.month", "page": 0, "x": 100, "y": 780},
    ]}
    out = tmp_path / "out.pdf"
    writer = pdf_forms.build_form_pdf(form, layout, {}, {"year": 2026, "month": 8})
    with open(out, "wb") as f:
        writer.write(f)
    assert "8" in PdfReader(str(out)).pages[0].extract_text()
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k build_form_pdf -v`
Expected: FAIL（`AttributeError: module 'pdf_forms' has no attribute 'build_form_pdf'`）

- [ ] **Step 3: 実装する**

`pdf_forms.py` の import に追加する。

```python
import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas as rl_canvas
```

続けて末尾に追加する。

```python
FONT_NAME = "HeiseiKakuGo-W5"
DEFAULT_FONT_SIZE = 11
COLOR_SATURDAY = "#0000ff"
COLOR_HOLIDAY = "#ff0000"
CIRCLE_RATIO = 0.9

_font_registered = False


def _ensure_font():
    """日本語フォントを登録する（初回のみ）"""
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))
        _font_registered = True


def _field_value(field: dict, slot: dict, meta: dict) -> str:
    """フィールドの source に対応する印字文字列を返す。空文字なら印字しない。"""
    source = field.get("source", "")
    if source.startswith("item:"):
        key = source[len("item:"):]
        raw = (slot or {}).get("values", {}).get(key, "")
        return _apply_marks(field, raw)
    if source.startswith("remark:"):
        key = source[len("remark:"):]
        return (slot or {}).get("remarks", {}).get(key, "")
    if source == "meta.day":
        d = (slot or {}).get("date")
        return str(d.day) if d else ""
    if source == "meta.year":
        return str(meta.get("year", ""))
    if source == "meta.month":
        return str(meta.get("month", ""))
    if source.startswith("meta."):
        key = source[len("meta."):]
        slot_meta = (slot or {}).get("meta", {})
        return str(slot_meta.get(key, meta.get(key, "")))
    logger.warning("未知の source を飛ばしました: %s", source)
    return ""


def _apply_marks(field: dict, raw: str) -> str:
    """判定結果を mark_ok / mark_ng / mark_na に置き換える"""
    if raw == "○":
        return field.get("mark_ok", "○")
    if raw == "×":
        return field.get("mark_ng", "×")
    if raw == "ー":
        return field.get("mark_na", "ー")
    return raw


def _draw_field(c, field: dict, x: float, y: float, text: str, default_size: int):
    """1つのフィールドを描く"""
    if text == "":
        return
    size = float(field.get("font_size", default_size))
    c.setFont(FONT_NAME, size)
    c.setFillColor(HexColor(field.get("color", "#000000")))
    c.drawString(x, y, text)


def build_form_pdf(form_pdf_path, layout: dict, slots: dict, meta: dict) -> PdfWriter:
    """様式PDFに文字を重ねた PdfWriter を返す。様式PDF自体は書き換えない。"""
    _ensure_font()
    reader = PdfReader(str(form_pdf_path))
    writer = PdfWriter()
    default_size = int(layout.get("default_font_size", DEFAULT_FONT_SIZE))
    axis = layout.get("axis") or {}
    fields = layout.get("fields", [])

    for page_index, page in enumerate(reader.pages):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(width, height))
        for field in fields:
            try:
                target_page = int(field.get("page", 0))
            except (TypeError, ValueError):
                continue
            if target_page != page_index:
                if target_page >= len(reader.pages):
                    logger.warning("様式のページ数を超える page 指定を飛ばしました: %s",
                                   field.get("source"))
                continue
            if field.get("on_axis"):
                for n, slot in sorted(slots.items()):
                    x, y = forms_layout.axis_position(field, axis, n)
                    _draw_slot_field(c, field, x, y, slot, meta, default_size)
            else:
                x, y = forms_layout.axis_position(field, axis, 1)
                first_slot = slots.get(1) if slots else None
                _draw_field(c, field, x, y,
                            _field_value(field, first_slot, meta), default_size)
        c.save()
        buf.seek(0)
        overlay = PdfReader(buf).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)
    return writer
```

`_draw_slot_field` は次のタスクで日にちの丸を扱うため、いったん最小の実装を置く。

```python
def _draw_slot_field(c, field, x, y, slot, meta, default_size):
    """軸の1欄分を描く（日にちの丸は Task 12 で追加する）"""
    if not (slot or {}).get("exists", False):
        return
    _draw_field(c, field, x, y, _field_value(field, slot, meta), default_size)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k build_form_pdf -v`
Expected: 4 passed

- [ ] **Step 5: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: overlay inspection results onto form PDF pages"
```

---

## Task 12: 日にちの印字と休日の丸

**Files:**
- Modify: `pdf_forms.py`（`_draw_slot_field`）
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 日にちと休日の丸 ==========

def _slots_for_march_2026():
    """2026年3月分（2/24〜3/23、28日）の欄を作る"""
    from datetime import date, timedelta
    import pdf_forms
    cycle_dates = [date(2026, 2, 24) + timedelta(days=i) for i in range(28)]
    layout = {"period": "month", "axis": {"count": 31}}
    return pdf_forms.build_slots(layout, 2026, 3, cycle_dates, {}, {})


def test_draw_day_numbers_span_two_months(tmp_path):
    """日にちが 24…31, 1…23 の順で印字されること"""
    import pdf_forms
    from pypdf import PdfReader
    form = _make_form_pdf(tmp_path / "form.pdf")
    layout = {"period": "month", "targets": [],
              "axis": {"step_x": 15.0, "step_y": 0.0, "count": 31},
              "fields": [{"source": "meta.day", "page": 0, "x": 50, "y": 700,
                          "on_axis": True}]}
    out = tmp_path / "out.pdf"
    writer = pdf_forms.build_form_pdf(form, layout, _slots_for_march_2026(),
                                      {"year": 2026, "month": 3})
    with open(out, "wb") as f:
        writer.write(f)
    text = PdfReader(str(out)).pages[0].extract_text()
    assert "24" in text and "23" in text


def test_extra_slots_have_no_day(tmp_path):
    """余りマス（29〜31番目）には日にちを印字しないこと"""
    import pdf_forms
    slots = _slots_for_march_2026()
    drawn = []
    layout = {"period": "month", "targets": [],
              "axis": {"step_x": 15.0, "step_y": 0.0, "count": 31},
              "fields": [{"source": "meta.day", "page": 0, "x": 50, "y": 700,
                          "on_axis": True}]}
    for n, slot in slots.items():
        if pdf_forms._field_value(layout["fields"][0], slot, {}) and slot["exists"]:
            drawn.append(n)
    assert drawn == list(range(1, 29))


def test_circle_color_for_marks():
    """土曜は青、日曜・祝日・会社休業日は赤の丸になること"""
    import pdf_forms
    assert pdf_forms._circle_color(pdf_forms.MARK_SATURDAY) == pdf_forms.COLOR_SATURDAY
    assert pdf_forms._circle_color(pdf_forms.MARK_HOLIDAY) == pdf_forms.COLOR_HOLIDAY
    assert pdf_forms._circle_color("") == ""


def test_circle_radius_default():
    """circle_radius 省略時は文字サイズ×0.9 になること"""
    import pdf_forms
    assert pdf_forms._circle_radius({}, 10) == 9.0
    assert pdf_forms._circle_radius({"circle_radius": 12.5}, 10) == 12.5


def test_day_field_draws_circle_for_holiday(tmp_path):
    """休日の欄で丸を描く処理が呼ばれること"""
    import pdf_forms
    calls = []

    class FakeCanvas:
        def setFont(self, *a): pass
        def setFillColor(self, *a): pass
        def setStrokeColor(self, color): calls.append(("stroke", color))
        def setLineWidth(self, *a): pass
        def drawCentredString(self, *a): calls.append(("text", a[2]))
        def circle(self, *a, **kw): calls.append(("circle",))

    slot = {"exists": True, "mark": pdf_forms.MARK_HOLIDAY,
            "date": __import__("datetime").date(2026, 3, 1),
            "values": {}, "remarks": {}, "meta": {}}
    field = {"source": "meta.day", "x": 50, "y": 700, "on_axis": True}
    pdf_forms._draw_slot_field(FakeCanvas(), field, 50, 700, slot, {}, 11)
    assert ("circle",) in calls
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "day_number or extra_slots or circle" -v`
Expected: FAIL（`AttributeError: module 'pdf_forms' has no attribute '_circle_color'`）

- [ ] **Step 3: 実装する**

`pdf_forms.py` の `_draw_slot_field` を次で置き換える。

```python
def _circle_color(mark: str) -> str:
    """欄の印から丸の色を返す。平日は空文字（丸を描かない）。"""
    if mark == MARK_SATURDAY:
        return COLOR_SATURDAY
    if mark == MARK_HOLIDAY:
        return COLOR_HOLIDAY
    return ""


def _circle_radius(field: dict, font_size: float) -> float:
    """丸の半径。省略時は文字サイズ×0.9。"""
    try:
        return float(field["circle_radius"])
    except (KeyError, TypeError, ValueError):
        return font_size * CIRCLE_RATIO


def _draw_day_field(c, field, x, y, slot, default_size):
    """日にちを丸の中心に描き、土日祝は丸で囲む。

    x, y は丸の中心を指す（他のフィールドは左下基準）。
    """
    d = slot.get("date")
    if not d:
        return
    size = float(field.get("font_size", default_size))
    color = _circle_color(slot.get("mark", "")) or field.get("color", "#000000")
    c.setFont(FONT_NAME, size)
    c.setFillColor(HexColor(color))
    # drawCentredString の y は文字の下端なので、中心に来るよう半分ずらす
    c.drawCentredString(x, y - size * 0.35, str(d.day))
    if _circle_color(slot.get("mark", "")):
        c.setStrokeColor(HexColor(color))
        c.setLineWidth(1.0)
        c.circle(x, y, _circle_radius(field, size), stroke=1, fill=0)


def _draw_slot_field(c, field, x, y, slot, meta, default_size):
    """軸の1欄分を描く"""
    if not (slot or {}).get("exists", False):
        return
    if field.get("source") == "meta.day":
        _draw_day_field(c, field, x, y, slot, default_size)
        return
    _draw_field(c, field, x, y, _field_value(field, slot, meta), default_size)
```

余りマスへの「ー」は、`item:` のフィールドが `exists=False` の欄でも印字される必要がある。`_draw_slot_field` の先頭を次に変える。

```python
def _draw_slot_field(c, field, x, y, slot, meta, default_size):
    """軸の1欄分を描く"""
    slot = slot or {}
    source = field.get("source", "")
    if not slot.get("exists", False):
        # 余りマス（その月に存在しない日）。item だけ「ー」を入れる。
        if source.startswith("item:"):
            _draw_field(c, field, x, y, field.get("mark_na", "ー"), default_size)
        return
    if source == "meta.day":
        _draw_day_field(c, field, x, y, slot, default_size)
        return
    _draw_field(c, field, x, y, _field_value(field, slot, meta), default_size)
```

- [ ] **Step 4: 余りマスの「ー」のテストを追加して通す**

```python
def test_extra_slot_item_prints_dash():
    """余りマスの item に「ー」が入ること"""
    import pdf_forms
    calls = []

    class FakeCanvas:
        def setFont(self, *a): pass
        def setFillColor(self, *a): pass
        def drawString(self, x, y, text): calls.append(text)

    field = {"source": "item:吊具A|傷はないか", "x": 50, "y": 700, "on_axis": True}
    pdf_forms._draw_slot_field(FakeCanvas(), field, 50, 700,
                               {"exists": False}, {}, 11)
    assert calls == ["ー"]


def test_extra_slot_remark_prints_nothing():
    """余りマスの remark には何も印字しないこと"""
    import pdf_forms
    calls = []

    class FakeCanvas:
        def setFont(self, *a): pass
        def setFillColor(self, *a): pass
        def drawString(self, x, y, text): calls.append(text)

    field = {"source": "remark:吊具A|傷はないか", "x": 50, "y": 700, "on_axis": True}
    pdf_forms._draw_slot_field(FakeCanvas(), field, 50, 700,
                               {"exists": False}, {}, 11)
    assert calls == []
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "day_number or extra_slot or circle" -v`
Expected: すべて passed

- [ ] **Step 5: コミット**

```bash
git add pdf_forms.py tests/test_app.py
git commit -m "feat: print day numbers with weekend and holiday circles"
```

---

## Task 13: PDF出力の統合とフォールバック

`/api/pdf` を、様式組と表組の両方を1つのPDFに結合して返すようにする。

**Files:**
- Modify: `pdf_forms.py`（結合の入口）、`app.py`（`api_get_pdf`）
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== PDF出力の統合 ==========

def _setup_forms_dir(tmp_path, monkeypatch, layout, with_pdf=True):
    """様式フォルダを1つ用意して設定に反映する"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    form_dir = forms_dir / "tsurigu"
    form_dir.mkdir(parents=True)
    (form_dir / "layout.json").write_text(
        json.dumps(layout, ensure_ascii=False), encoding="utf-8")
    if with_pdf:
        _make_form_pdf(form_dir / "form.pdf")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    return forms_dir


MONTH_LAYOUT = {
    "form_name": "吊具日常点検表",
    "period": "month",
    "inspection_type": "使用前",
    "targets": ["A-1"],
    "axis": {"step_x": 15.0, "step_y": 0.0, "count": 31},
    "fields": [
        {"source": "meta.day", "page": 0, "x": 50, "y": 700, "on_axis": True},
        {"source": "item:設備A|傷はないか", "page": 0, "x": 50, "y": 660,
         "on_axis": True},
    ],
}


def test_api_pdf_includes_form_pages(client, monkeypatch, tmp_path):
    """様式に紐づく機器があるとページ数が表だけのときより増えること"""
    from pypdf import PdfReader
    import io as _io
    import app as flask_app
    c, _ = client
    # 開発機の forms/ を拾わないよう、まず空のフォルダを見るようにする
    empty_dir = tmp_path / "empty_forms"
    empty_dir.mkdir()
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: empty_dir)
    baseline = c.get("/api/pdf?display_year=2026&display_month=3")
    base_pages = len(PdfReader(_io.BytesIO(baseline.data)).pages)
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert len(PdfReader(_io.BytesIO(res.data)).pages) > base_pages


def test_api_pdf_falls_back_when_form_pdf_missing(client, monkeypatch, tmp_path):
    """様式PDFが無いときは表出力に落ちてヘッダーで知らせること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT, with_pdf=False)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert "tsurigu" in res.headers.get("X-Form-Fallback", "")


def test_api_pdf_falls_back_when_layout_broken(client, monkeypatch, tmp_path):
    """layout.json が壊れているときも表出力に落ちること"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    form_dir = forms_dir / "broken"
    form_dir.mkdir(parents=True)
    (form_dir / "layout.json").write_text("{ oops", encoding="utf-8")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200


def test_get_forms_directory_defaults_to_app_folder(client):
    """forms_directory が空欄ならアプリ内の forms を使うこと"""
    import app as flask_app
    assert flask_app.get_forms_directory().name == "forms"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k "api_pdf_includes or falls_back or forms_directory" -v`
Expected: FAIL（`AttributeError: module 'app' has no attribute 'get_forms_directory'`）

- [ ] **Step 3: 様式PDFの組み立て口を pdf_forms.py に足す**

```python
def build_form_writer(form_dir, layout, records, display_year, display_month,
                      cycle_dates, custom_holidays):
    """1つの様式について、印字済みページを持つ PdfWriter を返す。

    single 型は点検日ごとに様式を複製する。点検日が無ければ None を返す。
    """
    from pathlib import Path
    form_pdf = Path(form_dir) / forms_layout.FORM_PDF_FILENAME
    if not form_pdf.exists():
        raise FileNotFoundError(f"様式PDFがありません: {form_pdf}")
    period = layout.get("period")
    targets = layout.get("targets", [])
    meta = {"year": display_year, "month": display_month}

    if period == "month":
        # index_by_date のキーは "YYYY-MM-DD" で、build_slots が引く形と同じ
        indexed = index_by_date(records, targets)
        slots = build_slots(layout, display_year, display_month,
                            cycle_dates, indexed, custom_holidays)
        return build_form_pdf(form_pdf, layout, slots, meta)

    if period == "year":
        indexed = index_by_month(records, targets)
        slots = build_slots(layout, display_year, display_month,
                            cycle_dates, indexed, custom_holidays)
        return build_form_pdf(form_pdf, layout, slots, meta)

    # single: 点検日ごとに1枚
    indexed = index_by_date(records, targets)
    if not indexed:
        return None
    writer = PdfWriter()
    for date_str in sorted(indexed):
        payload = indexed[date_str]
        slot = dict(payload)
        slot["exists"] = True
        slot["date"] = None
        slot["mark"] = ""
        one = build_form_pdf(form_pdf, layout, {1: slot}, meta)
        for page in one.pages:
            writer.add_page(page)
    return writer
```

- [ ] **Step 4: app.py に様式フォルダと統合処理を足す**

`get_save_directory()` の直後に追加する。

```python
def get_forms_directory() -> Path:
    """様式フォルダのパスを返す（空欄ならアプリ内の forms）"""
    forms_dir = load_config().get("forms_directory", "").strip()
    return Path(forms_dir) if forms_dir else BASE_DIR / "forms"
```

`api_post_config()` の `cycle_start_day` のブロックの後に追加する。

```python
    if "forms_directory" in data:
        fd = data["forms_directory"]
        if not isinstance(fd, str):
            return jsonify({"error": "forms_directory は文字列で指定してください"}), 400
        if len(fd) > 500:
            return jsonify({"error": "forms_directory が長すぎます"}), 400
        config["forms_directory"] = fd
```

`_default_config()` に `"forms_directory": "",` を `"cycle_start_day": 24,` の次に追加する。

`api_get_pdf()` を次で置き換える。

```python
@app.route("/api/pdf", methods=["GET"])
def api_get_pdf():
    try:
        display_year = int(request.args.get("display_year", datetime.now().year))
        display_month = int(request.args.get("display_month", datetime.now().month))
    except (ValueError, TypeError):
        return jsonify({"error": "パラメータが不正です"}), 400

    acquired = _pdf_lock.acquire(timeout=60)
    if not acquired:
        return jsonify({"error": "PDF生成が進行中です。しばらくお待ちください。"}), 503
    try:
        table_response = _generate_pdf(display_year, display_month)
        form_writers, fallbacks = _build_form_writers(display_year, display_month)
        if not form_writers:
            if fallbacks:
                table_response.headers["X-Form-Fallback"] = ",".join(fallbacks)
            return table_response
        merged = PdfWriter()
        for writer in form_writers:
            for page in writer.pages:
                merged.add_page(page)
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
    except Exception as e:
        logger.error("PDF生成エラー: %s", e, exc_info=True)
        return jsonify({"error": "PDF生成中にエラーが発生しました"}), 500
    finally:
        _pdf_lock.release()


def _build_form_writers(display_year: int, display_month: int):
    """様式ごとの PdfWriter と、表出力に落ちた様式IDの一覧を返す"""
    forms_dir = get_forms_directory()
    writers, fallbacks = [], []
    cycle_dates = get_cycle_dates(display_year, display_month)
    custom_holidays = _load_custom_holidays()
    for entry in forms_layout.list_forms(forms_dir):
        if entry["error"]:
            fallbacks.append(entry["id"])
            continue
        form_dir = forms_dir / entry["id"]
        try:
            layout = forms_layout.load_layout(form_dir)
            records = _collect_records(layout, display_year, display_month)
            writer = pdf_forms.build_form_writer(
                form_dir, layout, records, display_year, display_month,
                cycle_dates, custom_holidays)
            if writer is not None:
                writers.append(writer)
        except Exception as e:
            logger.warning("様式の出力に失敗したため表出力に切り替えます %s: %s",
                           entry["id"], e)
            fallbacks.append(entry["id"])
    return writers, fallbacks


def _collect_records(layout: dict, display_year: int, display_month: int) -> list:
    """様式の型に応じて必要な期間の点検記録を集める"""
    itype = layout.get("inspection_type", "使用前")
    records = []
    if layout.get("period") == "year":
        for month in range(1, 13):
            records.extend(_read_json_safe(
                get_result_file_path(itype, display_year, month)))
        return records
    start, _ = get_cycle_range(display_year, display_month)
    records.extend(_read_json_safe(
        get_result_file_path(itype, start.year, start.month)))
    if (start.year, start.month) != (display_year, display_month):
        records.extend(_read_json_safe(
            get_result_file_path(itype, display_year, display_month)))
    return records
```

`app.py` の import に追加する。

```python
import io

from pypdf import PdfReader, PdfWriter

import pdf_forms
```

`make_response` は既に import 済み。無ければ `from flask import ..., make_response` に追加する。

- [ ] **Step 5: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: すべて passed

- [ ] **Step 6: コミット**

```bash
git add app.py pdf_forms.py tests/test_app.py
git commit -m "feat: merge form pages and table pages into one PDF"
```

---

## Task 14: 様式API

レイアウト画面（別計画）から使うAPIを先に用意する。

**Files:**
- Modify: `app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# ========== 様式API ==========

def test_api_forms_lists(client, monkeypatch, tmp_path):
    """様式一覧が取得できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms")
    assert res.status_code == 200
    data = res.get_json()
    assert data[0]["id"] == "tsurigu"
    assert data[0]["form_name"] == "吊具日常点検表"


def test_api_form_layout_get(client, monkeypatch, tmp_path):
    """layout.json の中身が取得できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/layout")
    assert res.status_code == 200
    assert res.get_json()["period"] == "month"


def test_api_form_layout_invalid_id(client, monkeypatch, tmp_path):
    """様式IDに危険な文字を含むと404になること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    assert c.get("/api/forms/..%2Fetc/layout").status_code == 404
    assert c.get("/api/forms/吊具/layout").status_code == 404


def test_api_form_layout_post(client, monkeypatch, tmp_path):
    """layout.json を保存できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    changed = dict(MONTH_LAYOUT)
    changed["form_name"] = "変更後"
    res = c.post("/api/forms/tsurigu/layout",
                 data=json.dumps(changed), content_type="application/json")
    assert res.status_code == 200
    assert c.get("/api/forms/tsurigu/layout").get_json()["form_name"] == "変更後"


def test_api_form_layout_post_invalid(client, monkeypatch, tmp_path):
    """period が不正な layout は400になること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    bad = dict(MONTH_LAYOUT)
    bad["period"] = "weekly"
    res = c.post("/api/forms/tsurigu/layout",
                 data=json.dumps(bad), content_type="application/json")
    assert res.status_code == 400


def test_api_form_pdf(client, monkeypatch, tmp_path):
    """様式PDF本体を取得できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/pdf")
    assert res.status_code == 200
    assert res.data[:5] == b"%PDF-"


def test_api_form_assignments(client, monkeypatch, tmp_path):
    """機器と様式の紐づけ一覧が取得できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/assignments")
    assert res.status_code == 200
    assert res.get_json()["A-1"] == ["tsurigu"]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -k api_form -v`
Expected: FAIL（404）

- [ ] **Step 3: 実装する**

`app.py` の `api_get_pdf` の後に追加する。

```python
# ========== API: 様式 ==========

def _resolve_form_dir(form_id: str):
    """様式IDから安全にフォルダを解決する。不正なら None を返す。"""
    safe = Path(form_id).name
    if not forms_layout.is_valid_form_id(safe):
        return None
    form_dir = get_forms_directory() / safe
    return form_dir if form_dir.is_dir() else None


@app.route("/api/forms")
def api_forms():
    return jsonify(forms_layout.list_forms(get_forms_directory()))


@app.route("/api/forms/assignments")
def api_form_assignments():
    return jsonify(forms_layout.form_assignments(get_forms_directory()))


@app.route("/api/forms/<form_id>/layout", methods=["GET"])
def api_get_form_layout(form_id):
    form_dir = _resolve_form_dir(form_id)
    if form_dir is None:
        return jsonify({"error": "Not found"}), 404
    try:
        return jsonify(forms_layout.load_layout(form_dir))
    except forms_layout.LayoutError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/forms/<form_id>/layout", methods=["POST"])
@require_admin
def api_post_form_layout(form_id):
    form_dir = _resolve_form_dir(form_id)
    if form_dir is None:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json()
    if not data:
        return jsonify({"error": "データ不正"}), 400
    try:
        forms_layout.save_layout(form_dir, data)
    except forms_layout.LayoutError as e:
        return jsonify({"error": str(e)}), 400
    except Timeout:
        return jsonify({"error": "ファイルがロック中です。再試行してください。"}), 503
    logger.info("様式レイアウト保存: %s", form_dir.name)
    return jsonify({"status": "ok"})


@app.route("/api/forms/<form_id>/pdf")
def api_get_form_pdf(form_id):
    form_dir = _resolve_form_dir(form_id)
    if form_dir is None:
        return jsonify({"error": "Not found"}), 404
    if not (form_dir / forms_layout.FORM_PDF_FILENAME).exists():
        return jsonify({"error": "Not found"}), 404
    return _send_pdf_cached(form_dir, forms_layout.FORM_PDF_FILENAME)
```

`/api/forms/assignments` は `/api/forms/<form_id>/layout` より**先に**定義すること。Flask は登録順ではなくルールの具体度で解決するため実害はないが、読む人が迷わないようにする。

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: すべて passed

- [ ] **Step 5: コミット**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add form listing, layout and PDF APIs"
```

---

## Task 15: 実機での通し確認

自動テストでは分からない「実際に紙に出したときの見え方」を確認する。

**Files:**
- Create: `forms/sample_daily/layout.json`（確認用。コミットしない）

- [ ] **Step 1: 確認用の様式を用意する**

手元の日常点検の様式PDFを1つ `forms/sample_daily/form.pdf` に置く。無ければA4縦の白紙PDFで代用する。

`forms/sample_daily/layout.json` を作る。座標は仮の値でよい。

```json
{
  "form_name": "確認用 日常点検表",
  "period": "month",
  "inspection_type": "使用前",
  "targets": ["A-1"],
  "axis": {"step_x": 16.0, "step_y": 0.0, "count": 31},
  "default_font_size": 9,
  "fields": [
    {"source": "meta.month", "page": 0, "x": 90.0, "y": 800.0, "font_size": 14},
    {"source": "meta.day", "page": 0, "x": 120.0, "y": 760.0, "on_axis": true},
    {"source": "item:設備A|変形していないか", "page": 0, "x": 120.0, "y": 730.0,
     "on_axis": true},
    {"source": "item:設備A|オイルは漏れていないか", "page": 0, "x": 120.0, "y": 710.0,
     "on_axis": true}
  ]
}
```

- [ ] **Step 2: アプリを起動して出力する**

`起動.bat` からアプリを起動し、点検画面で **2026年3月**（28日サイクル）を選んで「PDF出力」を押す。

- [ ] **Step 3: 出力を確認する**

次の6点を目で確認する。

1. 様式のページが表のページより前に出ている
2. 日にちが 24, 25 … 31, 1, 2 … 23 の順に並んでいる
3. 29〜31番目の欄に日にちが無く、点検項目の欄に「ー」が入っている
4. 土曜の日にちが青い丸、日曜・祝日・会社の休業日が赤い丸で囲まれている
5. タイトルの月の位置に「3」が入っている
6. 様式を紐づけていない機器が、これまでどおり表のページに出ている

- [ ] **Step 4: 31日サイクルでも確認する**

**2026年9月**（31日サイクル）を選んで出力し、余りマスが無い（すべての欄に日にちが入る）ことを確認する。

- [ ] **Step 5: 確認用ファイルを片付ける**

`forms/sample_daily/` は確認用なのでコミットしない。`.gitignore` に次を追加する。

```
forms/
```

様式は現場ごとに違い、実データを含むため、リポジトリには入れない。

- [ ] **Step 6: コミット**

```bash
git add .gitignore
git commit -m "chore: ignore forms directory holding site-specific form PDFs"
```

---

## この計画の完了条件

- `pytest tests/test_app.py` が全件パスする（既存38件＋新規約60件）
- 様式を1つも置いていない状態で、PDF出力が従来とまったく同じ結果になる
- `layout.json` を手で用意すれば、様式PDFに点検結果・日にち・休日の丸が印字される
- 様式PDFや `layout.json` が壊れていても、アプリは落ちずに表出力へ切り替わる

## 次の計画

`docs/superpowers/plans/2026-08-22-form-pdf-ui.md`（レイアウト画面と入力画面の改善）
