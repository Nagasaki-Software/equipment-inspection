"""様式レイアウト（layout.json）の読み書きと座標計算。

様式は forms/<様式ID>/ に form.pdf と layout.json を置くフォルダ単位で管理する。
"""
import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from filelock import FileLock

# json / os / re / Path / FileLock は Task 6 以降の layout.json 読み書きで使う。

logger = logging.getLogger("equipment_inspection")

INPUT_TYPE_JUDGMENT = "判定"
INPUT_TYPE_NUMBER = "数値"
NOT_APPLICABLE_MARK = "ー"   # 点検対象外。判定項目でも数値項目でも使う
_VALID_INPUT_TYPES = (INPUT_TYPE_JUDGMENT, INPUT_TYPE_NUMBER)

# 判定の記号。画面・様式PDF・表出力のすべてがここを見る。
MARK_OK = "✓"        # 良
MARK_ADJUST = "A"    # 要調整
MARK_REPAIR = "△"    # 修理
MARK_REPLACE = "×"   # 要取替
LEGACY_MARK_OK = "○"  # 旧仕様の「良」。保存済みの記録に残っている
NG_MARKS = (MARK_ADJUST, MARK_REPAIR, MARK_REPLACE)


def normalize_judgment(value) -> str:
    """保存済みの判定を今の記号に読み替える。記録そのものは書き換えない。

    旧仕様の「○」は「良」の意味なので MARK_OK として扱う。
    旧仕様の「×」は「不合格」としか記録されておらず3分類に振り分けられないため、
    そのまま（要取替）として扱う。
    """
    if not isinstance(value, str):
        return ""
    return MARK_OK if value == LEGACY_MARK_OK else value


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


LAYOUT_FILENAME = "layout.json"
FORM_PDF_FILENAME = "form.pdf"
VALID_PERIODS = ("year", "month", "single")
DEFAULT_AXIS_COUNT = {"year": 12, "month": 31}
MAX_AXIS_COUNT = 400   # 1年366日＋余裕。これを超える様式は現実に存在しない
LAYOUT_BACKUP_GENERATIONS = 10
TRASH_DIRNAME = ".trash"   # 削除した様式の置き場。ドットは様式IDに使えないので衝突しない
_FORM_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")
MAX_FORM_ID_LENGTH = 64

# Windows の予約デバイス名。フォルダ名にすると予期しない動きをする
# （NUL は mkdir が黙って何も作らない）。
_RESERVED_FORM_IDS = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)


class LayoutError(Exception):
    """layout.json が読めない・内容が不正なときに投げる"""


def is_valid_form_id(form_id) -> bool:
    """様式IDが安全か（パストラバーサル・Windows予約名の対策）"""
    if not isinstance(form_id, str) or not form_id:
        return False
    if len(form_id) > MAX_FORM_ID_LENGTH:
        return False
    # fullmatch にする。match だと末尾の改行を通してしまう。
    if not _FORM_ID_RE.fullmatch(form_id):
        return False
    return form_id.upper() not in _RESERVED_FORM_IDS


def _is_number(value) -> bool:
    """数値か（bool は int の派生型なので除外する）"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_layout(layout: dict):
    """layout.json の内容を検証する。問題があれば LayoutError を投げる。

    配列の中身まで見るのは、ここを通ったあとの描画処理が
    LayoutError 以外の例外で落ちないようにするため。
    """
    if not isinstance(layout, dict):
        raise LayoutError("layout.json の中身がオブジェクトではありません")

    period = layout.get("period")
    if period not in VALID_PERIODS:
        raise LayoutError(f"period が不正です: {period}")

    if "form_name" in layout and not isinstance(layout["form_name"], str):
        raise LayoutError("form_name は文字列で指定してください")

    targets = layout.get("targets")
    if not isinstance(targets, list):
        raise LayoutError("targets は配列で指定してください")
    for i, name in enumerate(targets):
        if not isinstance(name, str):
            raise LayoutError(f"targets[{i}] が文字列ではありません: {name!r}")

    fields = layout.get("fields")
    if not isinstance(fields, list):
        raise LayoutError("fields は配列で指定してください")
    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            raise LayoutError(f"fields[{i}] がオブジェクトではありません: {field!r}")
        if not isinstance(field.get("source", ""), str):
            raise LayoutError(f"fields[{i}].source は文字列で指定してください")
        page = field.get("page", 0)
        if not isinstance(page, int) or isinstance(page, bool) or page < 0:
            raise LayoutError(f"fields[{i}].page は0以上の整数で指定してください: {page!r}")
        for key in ("x", "y", "font_size", "circle_radius"):
            if key in field and field[key] is not None and not _is_number(field[key]):
                raise LayoutError(
                    f"fields[{i}].{key} は数値で指定してください: {field[key]!r}")

    if period in DEFAULT_AXIS_COUNT:
        axis = layout.get("axis")
        if not isinstance(axis, dict):
            raise LayoutError(f"period={period} には axis が必要です")
        for key in ("step_x", "step_y", "count"):
            if key in axis and axis[key] is not None and not _is_number(axis[key]):
                raise LayoutError(f"axis.{key} は数値で指定してください: {axis[key]!r}")


def load_layout(form_dir) -> dict:
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
        raise LayoutError(
            f"{LAYOUT_FILENAME} の文字コードが不正です（UTF-8で保存してください）: {e}") from e
    except OSError as e:
        raise LayoutError(f"{LAYOUT_FILENAME} が読めません: {e}") from e
    _validate_layout(layout)
    return layout


def _backup_layout(path: Path):
    """上書き前に layout.json を世代バックアップする（最大10世代）"""
    if not path.exists():
        return
    backup_dir = path.parent / "backups"
    try:
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, backup_dir / f"layout_{stamp}.json")
        old = sorted(backup_dir.glob("layout_*.json"))
        for f in old[:-LAYOUT_BACKUP_GENERATIONS]:
            f.unlink()
    except Exception as e:
        # バックアップに失敗しても保存そのものは続ける
        logger.warning("layout.json のバックアップに失敗: %s", e)


def save_layout(form_dir, layout: dict):
    """layout.json を保存する（排他制御・一時ファイル経由の原子的書き込み）"""
    _validate_layout(layout)
    form_dir = Path(form_dir)
    form_dir.mkdir(parents=True, exist_ok=True)
    path = form_dir / LAYOUT_FILENAME
    lock_path = str(path) + ".lock"
    with FileLock(lock_path, timeout=10):
        _backup_layout(path)
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


def list_forms(forms_dir) -> list:
    """様式フォルダ配下の様式を一覧する。壊れた様式は error 付きで返す。"""
    forms_dir = Path(forms_dir)
    if not forms_dir.is_dir():
        return []
    forms = []
    for d in sorted(p for p in forms_dir.iterdir() if p.is_dir()):
        # 先頭がドットのフォルダは様式ではない（.trash など）。
        # ドットは is_valid_form_id が通さない文字なので、正規の様式と衝突しない。
        if d.name.startswith("."):
            continue
        entry = {"id": d.name, "form_name": d.name, "period": "",
                 "targets": [], "has_pdf": (d / FORM_PDF_FILENAME).exists(),
                 "error": "", "editable": True, "warning": ""}
        # フォルダ名が様式IDの規則から外れていると、レイアウト画面から開けない
        # （URLに使えないため）。ただし出力そのものは動くので error にはしない。
        if not is_valid_form_id(d.name):
            entry["editable"] = False
            entry["warning"] = (
                f"フォルダ名「{d.name}」は様式IDの規則から外れているため、"
                "レイアウト画面では開けません（半角英数字とアンダースコアのみ、"
                "64文字以内）。フォルダ名を直すと編集できるようになります。")
        try:
            layout = load_layout(d)
            entry["form_name"] = layout.get("form_name", d.name)
            entry["period"] = layout.get("period", "")
            entry["targets"] = layout.get("targets", [])
        except LayoutError as e:
            entry["error"] = str(e)
            logger.warning("様式の設定エラー %s: %s", d.name, e)
        except Exception as e:
            # 想定外の壊れ方（極端に深いJSONなど）でも一覧全体を落とさない
            entry["error"] = f"設定を読めません: {e}"
            logger.warning("様式の読み込みに失敗 %s: %s", d.name, e)
        forms.append(entry)
    return forms


def axis_position(field: dict, axis, n: int):
    """軸の n 番目（1始まり）におけるフィールドの印字位置を返す。

    on_axis でないフィールドは軸の影響を受けず、そのままの座標を返す。
    PDF座標は左下が原点なので、下に並ぶ様式では step_y が負になる。
    """
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        # 0始まりで呼ぶと全項目が1欄ぶんずれる。静かに間違えるより落とす。
        raise ValueError(f"軸の番号は1以上の整数で指定してください: {n!r}")
    x = float(field.get("x", 0.0) or 0.0)
    y = float(field.get("y", 0.0) or 0.0)
    if not field.get("on_axis"):
        return (x, y)
    axis = axis or {}
    step_x = float(axis.get("step_x", 0.0) or 0.0)
    step_y = float(axis.get("step_y", 0.0) or 0.0)
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
    if count <= 0:
        return DEFAULT_AXIS_COUNT[period]
    return min(count, MAX_AXIS_COUNT)


def form_assignments(forms_dir) -> dict:
    """機器名 → その機器が載っている様式IDのリスト、を返す。

    設定が壊れている様式は除外する（表出力にフォールバックさせるため）。
    """
    assignments = {}
    for entry in list_forms(forms_dir):
        if entry["error"]:
            continue
        for name in entry["targets"]:
            ids = assignments.setdefault(name, [])
            if entry["id"] not in ids:
                ids.append(entry["id"])
    return assignments
