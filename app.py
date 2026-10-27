"""
設備点検システム ver5 - セキュリティ・安定性改善版
"""

import calendar
import copy
import os
import io
import html
import tempfile
import json
import csv
import re
import sys
import secrets
import shutil
import socket
import logging
import mimetypes
import threading
import functools
from datetime import datetime, date, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory, make_response
from filelock import FileLock, Timeout
import jpholiday
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer, PageBreak)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from pypdf import PdfReader, PdfWriter

import forms_layout
import pdf_forms


# ========== ベースディレクトリ ==========

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
    static_folder = Path(sys._MEIPASS) / "static" if hasattr(sys, '_MEIPASS') else BASE_DIR / "static"
else:
    BASE_DIR = Path(__file__).parent
    static_folder = BASE_DIR / "static"

APP_VERSION = "0.10.1"   # 画面と /api/health に出す。版数の出どころはここだけ

app = Flask(__name__, static_folder=str(static_folder), static_url_path="")
# 様式PDF（上限50MB）を受け取れるようにする。他のAPIはJSONのみで小さい。
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB上限（DoS対策）
# JS・CSSをブラウザに貯め込ませない。毎回「変わったか」を聞かせ、変わって
# いなければ中身を送らない（304）。以前はURLに ?v=17 のような数字を手で付けて
# 更新を知らせていたが、4か所を揃える必要があり、1つでも上げ忘れると利用者の
# ブラウザだけが古いファイルを使い続けた。社内LANの1台構成なので通信量は問題ない。
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "config.json"
ADMIN_KEY_PATH = BASE_DIR / "admin_key.txt"
EQUIPMENT_CSV = DATA_DIR / "equipment_master.csv"
INSPECTORS_CSV = DATA_DIR / "inspectors.csv"
CUSTOM_HOLIDAYS_CSV = DATA_DIR / "custom_holidays.csv"


# ========== ログ設定 ==========

def _setup_logging() -> logging.Logger:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    handler = RotatingFileHandler(
        str(log_dir / "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    _logger = logging.getLogger("equipment_inspection")
    _logger.setLevel(logging.INFO)
    if not _logger.handlers:
        _logger.addHandler(handler)
    return _logger

logger = _setup_logging()


# ========== 管理者認証 ==========

def _get_admin_key() -> str:
    """管理者キーを取得。初回起動時に自動生成する"""
    if ADMIN_KEY_PATH.exists():
        return ADMIN_KEY_PATH.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(16)
    ADMIN_KEY_PATH.write_text(key, encoding="utf-8")
    logger.info("管理者キーを新規生成しました")
    return key


def _is_localhost(addr: str) -> bool:
    """アドレスがローカルホストかどうか判定する（IPv4-mapped IPv6対応）"""
    # ::ffff:127.0.0.1 のような形式にも対応
    normalized = addr.replace("::ffff:", "")
    return normalized in ("127.0.0.1", "::1", "")


def require_admin(f):
    """管理者認証デコレータ。ローカルホストからのアクセスは許可する"""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        remote = request.remote_addr or ""
        logger.debug("管理者認証チェック: remote_addr=%s, path=%s", remote, request.path)
        if _is_localhost(remote):
            return f(*args, **kwargs)
        key = request.headers.get("X-Admin-Key", "")
        if key != _get_admin_key():
            logger.warning("認証失敗: remote_addr=%s, path=%s", remote, request.path)
            return jsonify({"error": "管理者認証が必要です"}), 401
        return f(*args, **kwargs)
    return wrapper


# ========== バックアップ ==========

_MAX_BACKUPS = 10


def _backup_file(filepath: Path):
    """ファイル書き込み前にバックアップを作成する"""
    if not filepath.exists():
        return
    backup_dir = filepath.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"{filepath.stem}_{ts}{filepath.suffix}"
    try:
        shutil.copy2(str(filepath), str(dest))
        backups = sorted(backup_dir.glob(f"{filepath.stem}_*{filepath.suffix}"))
        for old in backups[:-_MAX_BACKUPS]:
            old.unlink()
    except Exception as e:
        logger.error("バックアップ失敗 %s: %s", filepath.name, e)


# ========== 設定管理（キャッシュ・排他制御付き） ==========

_config_cache: dict = {"data": None, "mtime": 0.0}
_config_cache_lock = threading.Lock()  # キャッシュ読み書きのスレッドセーフ化


def _default_config() -> dict:
    return {
        "save_directory": "",
        "cycle_start_day": 24,
        "forms_directory": "",
        "server": {"host": "127.0.0.1", "port": 5000},
        "signage": {
            "folder_path": "", "display_seconds": 5,
            "sleep_start": "18:00", "sleep_end": "08:00",
            "idle_return_seconds": 30, "news_speed": 100,
            "web_max_stay_seconds": 300
        },
        "web_pages": [
            {"label": "Web1", "url": ""},
            {"label": "Web2", "url": ""}
        ],
        "building_info": {
            "building_name": "仮ビル 本館",
            "managers": [
                {"title": "施設長", "name": "管理 太郎",
                 "phone_int": "1234", "phone_ext": "011-000-0001"},
                {"title": "副施設長", "name": "副管理 次郎",
                 "phone_int": "1235", "phone_ext": "011-000-0002"},
                {"title": "担当者", "name": "担当 花子",
                 "phone_int": "1236", "phone_ext": "011-000-0003"}
            ]
        },
        "document_categories": {"button_count": 3, "categories": []}
    }


def load_config() -> dict:
    """設定ファイルを読み込む（キャッシュ・排他制御付き、deepcopyで参照共有を防止）"""
    if not CONFIG_PATH.exists():
        return _default_config()
    try:
        mtime = CONFIG_PATH.stat().st_mtime
        with _config_cache_lock:
            if _config_cache["data"] is not None and _config_cache["mtime"] == mtime:
                return copy.deepcopy(_config_cache["data"])
        lock_path = str(CONFIG_PATH) + ".lock"
        with FileLock(lock_path, timeout=5):
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            # TOCTOU対策: FileLock取得後にmtimeを再取得する
            mtime = CONFIG_PATH.stat().st_mtime
        with _config_cache_lock:
            _config_cache["data"] = data
            _config_cache["mtime"] = mtime
        return copy.deepcopy(data)
    except Exception as e:
        logger.error("設定読み込みエラー: %s", e)
        with _config_cache_lock:
            if _config_cache["data"] is not None:
                return copy.deepcopy(_config_cache["data"])
        return _default_config()


def save_config(config: dict):
    """設定ファイルを保存する（バックアップ・排他制御付き）"""
    _backup_file(CONFIG_PATH)
    lock_path = str(CONFIG_PATH) + ".lock"
    tmp = str(CONFIG_PATH) + ".tmp"
    with FileLock(lock_path, timeout=5):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    with _config_cache_lock:
        _config_cache["data"] = copy.deepcopy(config)
        _config_cache["mtime"] = CONFIG_PATH.stat().st_mtime
    logger.info("設定ファイルを保存しました")


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


# ========== ヘルパー ==========

def get_save_directory() -> Path:
    save_dir = load_config().get("save_directory", "").strip()
    return Path(save_dir) if save_dir else BASE_DIR / "results"


def get_forms_directory() -> Path:
    """様式フォルダのパスを返す（空欄ならアプリ内の forms）"""
    forms_dir = load_config().get("forms_directory", "").strip()
    return Path(forms_dir) if forms_dir else BASE_DIR / "forms"


def get_result_file_path(inspection_type: str, year: int, month: int) -> Path:
    save_dir = get_save_directory()
    month_dir = save_dir / f"{year:04d}-{month:02d}"
    month_dir.mkdir(parents=True, exist_ok=True)
    label = "daily" if inspection_type == "使用前" else "monthly"
    return month_dir / f"inspection_{label}_{year:04d}{month:02d}.json"


def _read_json_safe(filepath: Path) -> list:
    """JSONファイルを安全に読み込む（排他制御・エラーハンドリング付き）"""
    if not filepath.exists():
        return []
    lock_path = str(filepath) + ".lock"
    try:
        with FileLock(lock_path, timeout=10):
            with open(filepath, encoding="utf-8") as f:
                return json.load(f)
    except json.JSONDecodeError as e:
        logger.error("JSONパースエラー %s: %s", filepath.name, e)
        return []
    except Timeout:
        logger.error("ファイルロックタイムアウト: %s", filepath.name)
        return []
    except Exception as e:
        logger.error("ファイル読み込みエラー %s: %s", filepath.name, e)
        return []


def read_csv_as_list(csv_path: Path) -> list:
    if not csv_path.exists():
        return []
    with open(csv_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _load_custom_holidays() -> dict:
    """独自休日CSVを {日付: 名前} で読み込む（列欠落・空行に耐性あり）"""
    rows = read_csv_as_list(CUSTOM_HOLIDAYS_CSV)
    return {r["date"]: r.get("name", "") for r in rows if r.get("date")}


def get_holiday_info(target_date: date, custom_holidays: dict) -> dict:
    info = {
        "is_saturday": target_date.weekday() == 5,
        "is_sunday": target_date.weekday() == 6,
        "is_holiday": False, "holiday_name": "",
        "is_custom_holiday": False, "custom_holiday_name": ""
    }
    name = jpholiday.is_holiday_name(target_date)
    if name:
        info["is_holiday"] = True
        info["holiday_name"] = name
    date_str = target_date.strftime("%Y-%m-%d")
    if date_str in custom_holidays:
        info["is_custom_holiday"] = True
        info["custom_holiday_name"] = custom_holidays[date_str]
    return info


_font_registered = False


def register_jp_font():
    """日本語フォントを登録する（初回のみ実行）"""
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        _font_registered = True


_jp_style_cache: dict = {}


def get_jp_style(size=9):
    """日本語スタイルを取得する（サイズごとにキャッシュ）"""
    if size in _jp_style_cache:
        return _jp_style_cache[size]
    styles = getSampleStyleSheet()
    style = ParagraphStyle(f"JP_{size}", parent=styles["Normal"],
                           fontName="HeiseiKakuGo-W5", fontSize=size, leading=size + 3)
    _jp_style_cache[size] = style
    return style


# ========== 入力バリデーション ==========

_VALID_TYPES = {"使用前", "月例"}
_DATE_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")
_MAX_STR = 500


# ========== 数値の正規化 ==========
# 日本語入力がONのまま打つと「０．５２」と全角で入る。画面側でも直すが、
# 保存される値の正しさはここで担保する。

# 長音「ー」は変換しない。数値項目でも「点検対象外」の記録に使うため。
_FULLWIDTH_MAP = str.maketrans(
    "０１２３４５６７８９．－−",
    "0123456789.--"
)


def _normalize_number(value) -> str:
    """全角数字・全角ピリオド・全角マイナスを半角に直し、前後の空白を落とす。

    JSONの数値型で送られてきた場合も文字列に直す。
    「ー」（点検対象外）はそのまま返す。
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return value
    if value.strip() == forms_layout.NOT_APPLICABLE_MARK:
        return forms_layout.NOT_APPLICABLE_MARK
    return value.translate(_FULLWIDTH_MAP).replace("　", " ").strip()


_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")


def _is_number_like(value: str) -> bool:
    """点検値として妥当な数値かどうかを返す。

    float() を使うと inf / nan / 1e5 / 1_000 まで通ってしまうため、
    符号つきの十進数だけを受け付ける。
    """
    if not isinstance(value, str):
        return False
    return bool(_NUMBER_RE.match(value.strip()))


def _number_item_keys(category_major: str, category_minor: str) -> set:
    """マスタで「数値」と指定されている項目のキー集合を、機器で絞り込んで返す"""
    keys = set()
    try:
        for row in read_csv_as_list(EQUIPMENT_CSV):
            if row.get("category_major", "") != category_major:
                continue
            if row.get("category_minor", "") != category_minor:
                continue
            if forms_layout.item_input_type(row) == forms_layout.INPUT_TYPE_NUMBER:
                keys.add(row.get("inspection_item", ""))
        return keys
    except Exception as e:
        logger.warning("点検項目マスタが読めないため数値検証を省略します: %s", e)
        return set()


def _validate_results(data: dict, number_keys: set = None) -> list:
    errors = []
    itype = data.get("inspection_type", "")
    if itype not in _VALID_TYPES:
        errors.append(f"不正な点検種別: {itype}")
    idate = data.get("inspection_date", "")
    if not _DATE_RE.match(idate):
        errors.append(f"不正な日付形式: {idate}")
    else:
        try:
            datetime.strptime(idate, "%Y-%m-%d")
        except ValueError:
            errors.append(f"無効な日付: {idate}")
    results = data.get("results", [])
    if not isinstance(results, list):
        errors.append("results は配列で指定してください")
    elif len(results) > 500:
        errors.append("results の件数が多すぎます（最大500件）")
    if isinstance(results, list):
        if number_keys is None:
            number_keys = _number_item_keys(
                data.get("category_major", ""), data.get("category_minor", ""))
        for r in results:
            if not isinstance(r, dict):
                continue
            item = r.get("inspection_item", "")
            if item not in number_keys:
                continue
            value = _normalize_number(r.get("result", ""))
            if value == forms_layout.NOT_APPLICABLE_MARK:
                continue          # 点検対象外はそのまま通す
            if value and not _is_number_like(value):
                shown = str(r.get("result"))[:50]
                errors.append(f"{item} は数値で入力してください: {shown}")
    for key in ("category_major", "category_minor", "inspector_name",
                "department", "general_remark"):
        val = data.get(key, "")
        if isinstance(val, str) and len(val) > _MAX_STR:
            errors.append(f"{key} が長すぎます（最大{_MAX_STR}文字）")
    return errors


# ========== ドキュメントカテゴリ ヘルパー ==========

def _get_category_folder(category_id: int):
    """カテゴリIDから設定済みフォルダパスを取得する"""
    config = load_config()
    cats = config.get("document_categories", {}).get("categories", [])
    if 0 <= category_id < len(cats):
        folder = cats[category_id].get("folder", "").strip()
        if folder:
            p = Path(folder)
            if p.exists() and p.is_dir():
                return p
    return None


# ========== PDF配信ヘルパー（キャッシュヘッダー付き） ==========

def _send_pdf_cached(folder_path: Path, filename: str):
    """PDFを配信する。ETag・304・Range(206)の処理は werkzeug 標準に任せる。

    注意: ETagを手動で上書きすると If-Range 照合が常に不一致になり、
    大きいPDFの分割取得(Range)が毎回200の全体転送に落ちる。
    LAN経由のクライアントで描画が白抜けした不具合の原因のため、
    ここでは Cache-Control の付与のみ行うこと。
    """
    file_path = folder_path / filename
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"error": "Not found"}), 404
    try:
        response = make_response(
            send_from_directory(str(folder_path), filename, mimetype="application/pdf")
        )
        response.headers["Cache-Control"] = "public, max-age=300"
        return response
    except Exception as e:
        logger.error("PDF配信エラー %s: %s", filename, e)
        return jsonify({"error": "ファイル読み込みエラー"}), 500


# ========== API: 静的ページ ==========

@app.route("/")
def index():
    return send_from_directory(str(static_folder), "signage.html")

@app.route("/inspection")
def inspection():
    return send_from_directory(str(static_folder), "inspection.html")

@app.route("/documents")
def documents():
    return send_from_directory(str(static_folder), "documents.html")

@app.route("/documents/list")
def documents_list():
    return send_from_directory(str(static_folder), "documents-list.html")

@app.route("/documents/viewer")
def documents_viewer():
    return send_from_directory(str(static_folder), "documents-viewer.html")

@app.route("/layout")
@require_admin
def layout_editor():
    return send_from_directory(str(static_folder), "layout.html")

@app.route("/webview")
def webview():
    return send_from_directory(str(static_folder), "webview.html")


# ========== API: 設定（管理者認証付き） ==========

@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(load_config())

@app.route("/api/config", methods=["POST"])
@require_admin
def api_post_config():
    data = request.get_json()
    if not data:
        return jsonify({"error": "データ不正"}), 400
    config = load_config()
    if "save_directory" in data:
        sd = data["save_directory"]
        if not isinstance(sd, str):
            return jsonify({"error": "save_directory は文字列で指定してください"}), 400
        if len(sd) > 500:
            return jsonify({"error": "save_directory が長すぎます"}), 400
        config["save_directory"] = sd
    if "cycle_start_day" in data:
        try:
            day = int(data["cycle_start_day"])
        except (TypeError, ValueError):
            return jsonify({"error": "cycle_start_day は数値で指定してください"}), 400
        if not (1 <= day <= 31):
            return jsonify({"error": "cycle_start_day は1〜31の範囲で指定してください"}), 400
        config["cycle_start_day"] = day
    if "forms_directory" in data:
        fd = data["forms_directory"]
        if not isinstance(fd, str):
            return jsonify({"error": "forms_directory は文字列で指定してください"}), 400
        if len(fd) > 500:
            return jsonify({"error": "forms_directory が長すぎます"}), 400
        config["forms_directory"] = fd
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
    if "building_info" in data:
        bi = data["building_info"]
        if not isinstance(bi, dict):
            return jsonify({"error": "building_info はオブジェクトで指定してください"}), 400
        if "building_info" not in config:
            config["building_info"] = {}
        config["building_info"].update(bi)
    if "signage" in data:
        sg = data["signage"]
        if not isinstance(sg, dict):
            return jsonify({"error": "signage はオブジェクトで指定してください"}), 400
        if "folder_path" in sg and not isinstance(sg.get("folder_path", ""), str):
            return jsonify({"error": "signage.folder_path は文字列で指定してください"}), 400
        if "signage" not in config:
            config["signage"] = {}
        config["signage"].update(sg)
    if "document_categories" in data:
        config["document_categories"] = data["document_categories"]
    if "web_pages" in data:
        web_pages = data["web_pages"]
        # 型バリデーション：リストであり、各要素が label と url を持つ辞書か確認する
        if not isinstance(web_pages, list):
            return jsonify({"error": "web_pages は配列で指定してください"}), 400
        for page in web_pages:
            if not isinstance(page, dict) or "label" not in page or "url" not in page:
                return jsonify({"error": "web_pages の各要素に label と url が必要です"}), 400
            if not isinstance(page["label"], str) or not isinstance(page["url"], str):
                return jsonify({"error": "web_pages の label と url は文字列で指定してください"}), 400
        config["web_pages"] = web_pages
    if "server" in data:
        srv = data["server"]
        if not isinstance(srv, dict):
            return jsonify({"error": "server はオブジェクトで指定してください"}), 400
        if "port" in srv:
            try:
                port_val = int(srv["port"])
                if not (1 <= port_val <= 65535):
                    return jsonify({"error": "server.port は1〜65535の範囲で指定してください"}), 400
            except (ValueError, TypeError):
                return jsonify({"error": "server.port は数値で指定してください"}), 400
        if "server" not in config:
            config["server"] = {}
        config["server"].update(srv)
    save_config(config)
    return jsonify({"status": "ok"})


# ========== API: マスタデータ ==========

@app.route("/api/equipment", methods=["GET"])
def api_get_equipment():
    return jsonify(read_csv_as_list(EQUIPMENT_CSV))

@app.route("/api/inspectors", methods=["GET"])
def api_get_inspectors():
    return jsonify(read_csv_as_list(INSPECTORS_CSV))


# ========== API: 休日 ==========

@app.route("/api/holidays", methods=["GET"])
def api_get_holidays():
    start_str = request.args.get("start")
    end_str = request.args.get("end")
    if not start_str or not end_str:
        return jsonify({"error": "start と end が必要です"}), 400
    try:
        start_d = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "日付形式が不正です"}), 400
    if (end_d - start_d).days > 366:
        return jsonify({"error": "期間が長すぎます"}), 400

    custom_holidays = _load_custom_holidays()
    result = []
    cur = start_d
    while cur <= end_d:
        info = get_holiday_info(cur, custom_holidays)
        info["date"] = cur.strftime("%Y-%m-%d")
        info["weekday"] = cur.weekday()
        result.append(info)
        cur += timedelta(days=1)
    return jsonify(result)


# ========== API: 点検結果（バリデーション付き） ==========

@app.route("/api/results", methods=["GET"])
def api_get_results():
    inspection_type = request.args.get("type", "使用前")
    try:
        year = int(request.args.get("year", datetime.now().year))
        month = int(request.args.get("month", datetime.now().month))
    except (ValueError, TypeError):
        return jsonify({"error": "year/month が不正です"}), 400
    fp = get_result_file_path(inspection_type, year, month)
    return jsonify(_read_json_safe(fp))


PREVIOUS_LOOKBACK_MONTHS = 3


@app.route("/api/results/previous")
def api_get_previous_values():
    """指定日より前の、直近の点検結果を返す（数値項目の前回値表示に使う）。

    戻り値は {"点検項目名": "値"} の辞書。
    """
    inspection_type = request.args.get("type", "使用前")
    category_major = request.args.get("category_major", "")
    category_minor = request.args.get("category_minor", "")
    before_str = request.args.get("before", "")
    if not _DATE_RE.match(before_str):
        return jsonify({"error": "before の日付形式が不正です"}), 400
    try:
        before = datetime.strptime(before_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "before が無効な日付です"}), 400

    # 指定日の属する月から、最大3か月前まで遡って探す
    records = []
    year, month = before.year, before.month
    for _ in range(PREVIOUS_LOOKBACK_MONTHS + 1):
        records.extend(_read_json_safe(
            get_result_file_path(inspection_type, year, month)))
        month -= 1
        if month == 0:
            month, year = 12, year - 1

    candidates = [r for r in records
                  if r.get("category_major") == category_major
                  and r.get("category_minor") == category_minor
                  and r.get("inspection_date", "") < before_str]
    if not candidates:
        return jsonify({})
    latest = max(candidates, key=lambda r: (r.get("inspection_date", ""),
                                            r.get("submitted_at", "")))
    values = {}
    for row in latest.get("results", []):
        if not isinstance(row, dict):
            continue
        item = row.get("inspection_item", "")
        if item:
            values[item] = row.get("result", "")
    return jsonify(values)


@app.route("/api/results", methods=["POST"])
def api_post_results():
    data = request.get_json()
    if not data:
        return jsonify({"error": "データ不正"}), 400

    number_keys = _number_item_keys(
        data.get("category_major", ""), data.get("category_minor", ""))
    if isinstance(data.get("results"), list):
        for r in data["results"]:
            if isinstance(r, dict) and r.get("inspection_item") in number_keys:
                r["result"] = _normalize_number(r.get("result", ""))

    errors = _validate_results(data, number_keys=number_keys)
    if errors:
        logger.warning("点検結果バリデーションエラー: %s", errors)
        return jsonify({"error": "入力エラー", "details": errors}), 400

    inspection_type = data.get("inspection_type", "使用前")
    inspection_date = data.get("inspection_date", datetime.now().strftime("%Y-%m-%d"))
    dt = datetime.strptime(inspection_date, "%Y-%m-%d")

    display_year = data.get("display_year")
    display_month = data.get("display_month")
    if inspection_type != "使用前" and display_year and display_month:
        try:
            fp = get_result_file_path(inspection_type, int(display_year), int(display_month))
        except (ValueError, TypeError):
            return jsonify({"error": "display_year/display_month が不正です"}), 400
    else:
        fp = get_result_file_path(inspection_type, dt.year, dt.month)

    lock_path = str(fp) + ".lock"
    try:
        with FileLock(lock_path, timeout=10):
            existing = []
            if fp.exists():
                try:
                    with open(fp, encoding="utf-8") as f:
                        existing = json.load(f)
                except json.JSONDecodeError:
                    logger.warning("破損した結果ファイルを検出: %s", fp.name)
                    _backup_file(fp)
                    existing = []

            category_major = data.get("category_major", "")
            category_minor = data.get("category_minor", "")
            new_rec = {
                "inspection_date": inspection_date,
                "inspection_type": inspection_type,
                "category_major": category_major,
                "category_minor": category_minor,
                "inspector_name": data.get("inspector_name", ""),
                "department": data.get("department", ""),
                "general_remark": data.get("general_remark", ""),
                "building_name": load_config().get("building_info", {}).get("building_name", ""),
                "results": data.get("results", []),
                "submitted_at": datetime.now().isoformat()
            }

            updated = False
            for rec in existing:
                if (rec.get("inspection_date") == inspection_date and
                        rec.get("category_major") == category_major and
                        rec.get("category_minor") == category_minor):
                    existing_items = {
                        f"{r.get('equipment_name')}|{r.get('inspection_item')}": r
                        for r in rec.get("results", [])
                    }
                    for new_r in data.get("results", []):
                        existing_items[
                            f"{new_r.get('equipment_name')}|{new_r.get('inspection_item')}"
                        ] = new_r
                    rec["results"] = list(existing_items.values())
                    rec["inspector_name"] = data.get("inspector_name", rec.get("inspector_name"))
                    rec["department"] = data.get("department", rec.get("department"))
                    rec["general_remark"] = data.get("general_remark", rec.get("general_remark", ""))
                    rec["submitted_at"] = datetime.now().isoformat()
                    updated = True
                    break
            if not updated:
                existing.append(new_rec)

            _backup_file(fp)
            tmp = str(fp) + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
                os.replace(tmp, fp)
            except BaseException:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise

    except Timeout:
        logger.error("ファイルロックタイムアウト: %s", fp)
        return jsonify({"error": "ファイルがロック中です。再試行してください。"}), 503

    logger.info("点検結果保存: %s %s %s/%s",
                inspection_type, inspection_date, category_major, category_minor)
    return jsonify({"status": "ok", "file": str(fp)})


# ========== API: PDF生成（排他制御・エラーハンドリング付き） ==========

_pdf_lock = threading.Lock()

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
    except Exception as e:
        logger.error("PDF生成エラー: %s", e, exc_info=True)
        return jsonify({"error": "PDF生成中にエラーが発生しました"}), 500
    finally:
        _pdf_lock.release()


def _ordered_form_entries(entries: list, form_order) -> list:
    """様式の一覧を、設定した並び順に並べ替える。

    設定に無い様式は、指定した様式のあとに元の順（フォルダ名順）で続ける。
    設定にあるが実在しない様式IDは無視する。同じIDが2回あっても1回だけ出す。
    config.json は手で編集できるので、壊れた指定は例外にせず読み飛ばす。
    """
    if not isinstance(form_order, list):
        # 配列でなければ指定なしとして扱う。文字列だと1文字ずつ回って
        # 静かに違う並びになるため、ここで落とす。
        form_order = []
    by_id = {e["id"]: e for e in entries}
    used, result = set(), []
    for form_id in form_order:
        if not isinstance(form_id, str):
            continue
        entry = by_id.get(form_id)
        if entry is None or form_id in used:
            continue
        used.add(form_id)
        result.append(entry)
    for entry in entries:
        if entry["id"] not in used:
            result.append(entry)
    return result


def _build_form_writers(display_year: int, display_month: int):
    """様式ごとの PdfWriter と、表出力に落ちた様式IDの一覧を返す"""
    forms_dir = get_forms_directory()
    writers, fallbacks = [], []
    cycle_dates = get_cycle_dates(display_year, display_month)
    custom_holidays = _load_custom_holidays()
    form_order = load_config().get("form_order", [])
    for entry in _ordered_form_entries(forms_layout.list_forms(forms_dir),
                                       form_order):
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
            if writer is not None and len(writer.pages) > 0:
                writers.append(writer)
            elif writer is not None:
                logger.warning("様式のページが作られませんでした（表出力に切り替えます）: %s",
                               entry["id"])
                fallbacks.append(entry["id"])
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
    # month / single はサイクルが前月にまたがるので2か月分を読む
    start, end = get_cycle_range(display_year, display_month)
    records.extend(_read_json_safe(
        get_result_file_path(itype, start.year, start.month)))
    if (start.year, start.month) != (display_year, display_month):
        records.extend(_read_json_safe(
            get_result_file_path(itype, display_year, display_month)))
    # 2か月分のファイルにはサイクル外の日も入っている。single 型は点検日ごとに
    # 1枚出すので、絞らないと前月の点検日まで印字される。
    first, last = start.isoformat(), end.isoformat()
    return [r for r in records
            if first <= str(r.get("inspection_date", "")) <= last]


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
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "データ不正"}), 400
    try:
        forms_layout.save_layout(form_dir, data)
    except forms_layout.LayoutError as e:
        return jsonify({"error": str(e)}), 400
    except Timeout:
        return jsonify({"error": "ファイルがロック中です。再試行してください。"}), 503
    except OSError as e:
        logger.error("様式レイアウトの保存に失敗 %s: %s", form_dir.name, e)
        return jsonify({"error": "保存に失敗しました"}), 500
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


MAX_FORM_PDF_BYTES = 50 * 1024 * 1024


@app.route("/api/forms", methods=["POST"])
@require_admin
def api_create_form():
    form_id = request.form.get("form_id", "")
    if not forms_layout.is_valid_form_id(form_id):
        return jsonify({
            "error": "様式IDはそのままフォルダ名になります。"
                     "半角英数字とアンダースコア（_）だけを使い、64文字以内にしてください。"
                     "日本語・空白・ハイフン（-）・フォルダのパス（¥ や /）は使えません。"
                     "例: crane_daily"
        }), 400

    forms_dir = get_forms_directory()
    form_dir = forms_dir / form_id
    if form_dir.exists():
        return jsonify({"error": "同じ様式IDが既にあります"}), 400

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "様式PDFを選んでください"}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDFファイルを選んでください"}), 400
    content = upload.read()
    if len(content) > MAX_FORM_PDF_BYTES:
        return jsonify({"error": "様式PDFが大きすぎます（上限50MB）"}), 400
    if content[:5] != b"%PDF-":
        return jsonify({"error": "PDFファイルではありません"}), 400
    try:
        page_count = len(PdfReader(io.BytesIO(content)).pages)
    except Exception as e:
        logger.warning("様式PDFを読めません: %s", e)
        return jsonify({"error": "PDFを読み込めませんでした"}), 400
    if page_count < 1:
        return jsonify({"error": "この様式PDFにはページがありません"}), 400

    try:
        targets = json.loads(request.form.get("targets", "[]"))
    except json.JSONDecodeError:
        return jsonify({"error": "targets の形式が不正です"}), 400

    period = request.form.get("period", "month")
    layout = {
        "form_name": request.form.get("form_name") or form_id,
        "period": period,
        "inspection_type": request.form.get("inspection_type", "使用前"),
        "targets": targets,
        "default_font_size": 11,
        "fields": [],
    }
    if period in forms_layout.DEFAULT_AXIS_COUNT:
        layout["axis"] = {"step_x": 0.0, "step_y": 0.0,
                          "count": forms_layout.DEFAULT_AXIS_COUNT[period]}

    try:
        form_dir.mkdir(parents=True)
    except FileExistsError:
        # exists() の確認直後に別の操作で作られた場合
        return jsonify({"error": "同じ様式IDが既にあります"}), 400
    try:
        # save_layout が内容を検証する。不正なら中途半端なフォルダを残さず消す。
        forms_layout.save_layout(form_dir, layout)
    except forms_layout.LayoutError as e:
        _remove_empty_form_dir(form_dir)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("様式の作成に失敗 %s: %s", form_id, e)
        _remove_empty_form_dir(form_dir)
        return jsonify({"error": "様式の作成に失敗しました"}), 500

    (form_dir / forms_layout.FORM_PDF_FILENAME).write_bytes(content)
    logger.info("様式を新規作成: %s（%dページ）", form_id, page_count)
    return jsonify({"status": "ok", "id": form_id})


def _safe_form_dir_for_delete(form_id):
    """削除対象のフォルダを返す。名前が安全でなければ None。存在の有無は問わない。

    開けない様式（フォルダ名が様式IDの規則から外れているもの）を消せることが
    主目的なので、is_valid_form_id は使わない。パス区切りとゴミ箱だけを弾く。
    """
    if not isinstance(form_id, str) or not form_id:
        return None
    if "/" in form_id or "\\" in form_id:
        return None
    if form_id.startswith("."):     # "." ".." ".trash" をまとめて弾く
        return None
    forms_dir = get_forms_directory()
    candidate = forms_dir / form_id
    try:
        # シンボリックリンクなどで様式フォルダの外へ出ていないか確かめる
        if candidate.resolve().parent != forms_dir.resolve():
            return None
    except OSError:
        return None
    return candidate


@app.route("/api/forms/<form_id>", methods=["DELETE"])
@require_admin
def api_delete_form(form_id):
    """様式をゴミ箱（.trash）へ移す。

    完全には消さない。様式PDFは紙を取り込んだ唯一の控えであることがあり、
    このアプリの他の書き込みもすべてバックアップを残す作りになっているため。
    """
    form_dir = _safe_form_dir_for_delete(form_id)
    if form_dir is None:
        return jsonify({"error": "この名前の様式は削除できません"}), 400
    if not form_dir.is_dir():
        return jsonify({"error": "Not found"}), 404

    trash = get_forms_directory() / forms_layout.TRASH_DIRNAME
    dest = trash / f"{form_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        trash.mkdir(parents=True, exist_ok=True)
        form_dir.rename(dest)
    except OSError as e:
        logger.error("様式を削除できません %s: %s", form_id, e)
        return jsonify({
            "error": "削除できませんでした（ファイルが開かれているかもしれません）"
        }), 500
    logger.info("様式をゴミ箱へ移しました: %s -> %s", form_id, dest)
    return jsonify({"status": "ok", "moved_to": str(dest)})


def _number_items_for_targets(targets) -> set:
    """様式の対象機器について、数値と指定されている点検項目名の集合を返す"""
    names = set()
    wanted = set(targets or [])
    if not wanted:
        return names
    try:
        rows = read_csv_as_list(EQUIPMENT_CSV)
    except Exception as e:
        logger.warning("点検項目マスタが読めないため数値項目を判別できません: %s", e)
        return names
    for row in rows:
        if row.get("category_minor") not in wanted:
            continue
        if forms_layout.item_input_type(row) == forms_layout.INPUT_TYPE_NUMBER:
            names.add(row.get("inspection_item", ""))
    return names


@app.route("/api/forms/<form_id>/preview")
@require_admin
def api_form_preview(form_id):
    form_dir = _resolve_form_dir(form_id)
    if form_dir is None:
        return jsonify({"error": "Not found"}), 404
    try:
        display_year = int(request.args.get("display_year", datetime.now().year))
        display_month = int(request.args.get("display_month", datetime.now().month))
    except (ValueError, TypeError):
        return jsonify({"error": "パラメータが不正です"}), 400
    if not (1 <= display_month <= 12):
        return jsonify({"error": "月は1〜12で指定してください"}), 400
    try:
        layout = forms_layout.load_layout(form_dir)
    except forms_layout.LayoutError as e:
        return jsonify({"error": str(e)}), 400

    cycle_dates = get_cycle_dates(display_year, display_month)
    records = pdf_forms.build_sample_records(
        layout, cycle_dates, display_year,
        _number_items_for_targets(layout.get("targets")))
    try:
        # sample=True … 位置合わせ用なので、使用せず欄も全欄に印字する
        writer = pdf_forms.build_form_writer(
            form_dir, layout, records, display_year, display_month,
            cycle_dates, _load_custom_holidays(), sample=True)
    except FileNotFoundError:
        return jsonify({"error": "様式PDFがありません"}), 404
    except Exception as e:
        logger.error("試し刷りの生成に失敗 %s: %s", form_dir.name, e, exc_info=True)
        return jsonify({"error": "試し刷りの生成に失敗しました"}), 500
    if writer is None or not writer.pages:
        return jsonify({"error": "試し刷りするページを作れませんでした"}), 400

    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    response = make_response(buf.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'inline; filename="preview_{form_dir.name}.pdf"')
    return response


def _remove_empty_form_dir(form_dir: Path):
    """作りかけの様式フォルダを片付ける（中身があるときは触らない）"""
    try:
        if form_dir.is_dir() and not any(form_dir.iterdir()):
            form_dir.rmdir()
    except OSError as e:
        logger.warning("作りかけの様式フォルダを片付けられませんでした %s: %s",
                       form_dir, e)


_pdf_styles_cache = None


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
    # 手編集された記録では category_minor が None や数値のことがある。
    # ここで文字列に揃えないと、並べ替えのタプル比較で落ちる。
    machine = str(record.get("category_minor") or "")
    return {"machine": machine, "date": d,
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


def _remark_machine_spans(rows: list) -> list:
    """同じ機器が続く行を縦につなぐ指定を返す。

    表の行番号は「並びの番号 + 1」（0行目が見出し）。
    """
    spans, begin = [], 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i]["machine"] != rows[begin]["machine"]:
            if i - begin > 1:
                spans.append(("SPAN", (0, begin + 1), (0, i)))
            begin = i
    return spans


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
                Paragraph(html.escape(r["machine"], quote=False)
                          if first else "", styles["jp"]),
                Paragraph(f"{d.year}/{d.month}/{d.day}", styles["jp"]),
                Paragraph(r["type"], styles["jp"]),
                Paragraph(html.escape(r["text"], quote=False), styles["remark"]),
            ])
        # 同じ機器が続く行は、機器名の欄を縦につなぐ
        spans = _remark_machine_spans(rows)
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


def _get_pdf_styles():
    """PDF生成用スタイルを取得する（初回のみ生成、以降キャッシュ）"""
    global _pdf_styles_cache
    if _pdf_styles_cache is not None:
        return _pdf_styles_cache
    register_jp_font()
    _pdf_styles_cache = {
        "jp": get_jp_style(9),
        "title": ParagraphStyle("JpTitle_cached", fontName="HeiseiKakuGo-W5",
                                fontSize=17, leading=21, alignment=1),
        "date": ParagraphStyle("JpDate_cached", fontName="HeiseiKakuGo-W5",
                               fontSize=9, leading=11, alignment=1, wordWrap=None),
        "result": ParagraphStyle("JpResult_cached", fontName="HeiseiKakuGo-W5",
                                 fontSize=9, leading=11, alignment=1),
        "insp_vert": ParagraphStyle("JpInspVert_cached", fontName="HeiseiKakuGo-W5",
                                    fontSize=9, leading=10, alignment=1),
        "month_header": ParagraphStyle("JpMonthHdr_cached", fontName="HeiseiKakuGo-W5",
                                       fontSize=10, leading=13, alignment=1),
        "remark": ParagraphStyle("JpRemark_cached", fontName="HeiseiKakuGo-W5",
                                 fontSize=9, leading=12, alignment=0),
        "monthly_jp": get_jp_style(10),
        "monthly_center": ParagraphStyle("JpMonthlyCenter_cached", fontName="HeiseiKakuGo-W5",
                                         fontSize=10, leading=14, alignment=1),
        "monthly_remark": ParagraphStyle("JpMonthlyRemark_cached", fontName="HeiseiKakuGo-W5",
                                         fontSize=10, leading=14, alignment=0),
    }
    return _pdf_styles_cache


def _generate_pdf(display_year: int, display_month: int):
    start_date, end_date = get_cycle_range(display_year, display_month)
    start_year, start_month = start_date.year, start_date.month

    config = load_config()
    building_name = config.get("building_info", {}).get("building_name", "")

    # キャッシュ済みスタイルを取得する
    styles = _get_pdf_styles()
    jp_style = styles["jp"]
    title_style = styles["title"]

    all_equip = read_csv_as_list(EQUIPMENT_CSV)
    custom_holidays = _load_custom_holidays()
    today = date.today()   # 「使用せず」の判定に使う

    dates = []
    cur = start_date
    while cur <= end_date:
        dates.append(cur)
        cur += timedelta(days=1)
    if not dates:
        dates = [start_date]

    _usable_w = landscape(A4)[0] - 56
    _item_col_w = 160
    _date_col_w = (_usable_w - _item_col_w) / len(dates)
    date_style = styles["date"]
    result_style = styles["result"]
    insp_vert_style = styles["insp_vert"]

    holiday_map = {}
    for d in dates:
        holiday_map[d.strftime("%Y-%m-%d")] = get_holiday_info(d, custom_holidays)

    fp1 = get_result_file_path("使用前", start_year, start_month)
    fp2 = get_result_file_path("使用前", display_year, display_month)
    all_daily = _read_json_safe(fp1) + _read_json_safe(fp2)

    result_by_date = {}
    for rec in all_daily:
        d = rec.get("inspection_date", "")
        maj = rec.get("category_major", "")
        min_ = rec.get("category_minor", "")
        result_by_date[(d, maj, min_)] = {
            "inspector": rec.get("inspector_name", ""),
            "general_remark": rec.get("general_remark", ""),
            "by_item": {r.get("inspection_item", ""): r.get("result", "")
                        for r in rec.get("results", [])}
        }

    categories = {}
    for row in all_equip:
        maj = row.get("category_major", "")
        min_ = row.get("category_minor", "")
        if maj not in categories:
            categories[maj] = {}
        if min_ not in categories[maj]:
            categories[maj][min_] = []
        categories[maj][min_].append(row)

    story = []

    # ---- 使用前点検（カレンダー形式） ----
    for maj, minors in categories.items():
        for min_, items in minors.items():
            daily_items = [r for r in items
                           if r.get("inspection_type", "") in ("使用前", "両方")]
            if not daily_items:
                continue

            title = (f"{building_name}　{display_year}年{display_month}月"
                     f"　{maj}　{min_}　使用前点検結果")
            story.append(Paragraph(title, title_style))
            story.append(Spacer(1, 6))

            month_spans = {}
            for d in dates:
                key = (d.year, d.month)
                month_spans[key] = month_spans.get(key, 0) + 1

            month_header_style = styles["month_header"]
            header1 = [Paragraph("点検項目", jp_style)]
            for (yr, mo), cnt in month_spans.items():
                header1.append(Paragraph(f"{mo}月", month_header_style))
                for _ in range(cnt - 1):
                    header1.append("")

            header2 = [Paragraph("", jp_style)]
            date_col_w = round(_date_col_w, 2)
            col_widths = [_item_col_w]
            for d in dates:
                header2.append(Paragraph(str(d.day), date_style))
                col_widths.append(date_col_w)

            table_data = [header1, header2]
            span_cmds = []
            col_idx = 1
            for (yr, mo), cnt in month_spans.items():
                if cnt > 1:
                    span_cmds.append(("SPAN", (col_idx, 0), (col_idx + cnt - 1, 0)))
                col_idx += cnt
            span_cmds.append(("SPAN", (0, 0), (0, 1)))

            for item in daily_items:
                iname = item.get("inspection_item", "")
                row_data = [Paragraph(iname, jp_style)]
                for d in dates:
                    ds = d.strftime("%Y-%m-%d")
                    result = (result_by_date.get((ds, maj, min_), {})
                              .get("by_item", {}).get(iname, ""))
                    row_data.append(Paragraph(
                        forms_layout.normalize_judgment(result), result_style))
                table_data.append(row_data)

            # 使用せず行：その日の24時を過ぎた（＝今日より前の）のに記録が無ければ✓。
            # 当日と未来の日は、まだ点検されうるので空欄のままにする。
            unused_row = [Paragraph("使用せず", jp_style)]
            for d in dates:
                ds = d.strftime("%Y-%m-%d")
                has_record = (ds, maj, min_) in result_by_date
                mark = forms_layout.MARK_OK if (not has_record and d < today) else ""
                unused_row.append(Paragraph(mark, result_style))
            table_data.append(unused_row)

            insp_row = [Paragraph("点検者", jp_style)]
            for d in dates:
                ds = d.strftime("%Y-%m-%d")
                inspector = result_by_date.get((ds, maj, min_), {}).get("inspector", "")
                vertical = "<br/>".join(list(inspector)) if inspector else ""
                insp_row.append(Paragraph(vertical, insp_vert_style))
            table_data.append(insp_row)

            remark_texts = []
            for d in dates:
                ds = d.strftime("%Y-%m-%d")
                gr = result_by_date.get((ds, maj, min_), {}).get("general_remark", "")
                if isinstance(gr, str) and gr.strip():
                    remark_texts.append(f"{d.year}/{d.month}/{d.day}　{gr}")
            remark_content = "<br/>".join(remark_texts) if remark_texts else "特記事項なし"
            remark_style_obj = styles["remark"]
            remark_row = [Paragraph("備考", jp_style),
                          Paragraph(remark_content, remark_style_obj)]
            remark_row += [""] * (len(dates) - 1)
            table_data.append(remark_row)
            remark_row_idx = len(table_data) - 1
            span_cmds.append(("SPAN", (1, remark_row_idx), (-1, remark_row_idx)))

            style_cmds = [
                ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
                ("BACKGROUND", (0, 0), (-1, 1), colors.lightgrey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, -1), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("VALIGN", (1, -2), (-1, -2), "TOP"),
                ("VALIGN", (0, -1), (-1, -1), "TOP"),
                ("ROWHEIGHT", (0, -2), (-1, -2), 50),
                ("ROWHEIGHT", (0, -1), (-1, -1), 200),
                ("LEFTPADDING", (1, 0), (-1, -1), 0),
                ("RIGHTPADDING", (1, 0), (-1, -1), 0),
                ("LEFTPADDING", (1, -1), (-1, -1), 6),
                ("RIGHTPADDING", (1, -1), (-1, -1), 6),
            ] + span_cmds

            for ci, d in enumerate(dates, start=1):
                ds = d.strftime("%Y-%m-%d")
                h = holiday_map.get(ds, {})
                bg = None
                if h.get("is_saturday"):
                    bg = HexColor("#cce5ff")
                elif h.get("is_sunday") or h.get("is_holiday"):
                    bg = HexColor("#ffccd9")
                elif h.get("is_custom_holiday"):
                    bg = HexColor("#fff2cc")
                if bg:
                    for ri in range(1, len(table_data) - 1):
                        style_cmds.append(("BACKGROUND", (ci, ri), (ci, ri), bg))

            tbl = Table(table_data, colWidths=col_widths, repeatRows=2)
            tbl.setStyle(TableStyle(style_cmds))
            story.append(tbl)
            story.append(PageBreak())

    # ---- 月例点検（リスト形式） ----
    monthly_jp_style = styles["monthly_jp"]
    monthly_jp_center_style = styles["monthly_center"]
    monthly_remark_style = styles["monthly_remark"]
    fp_monthly = get_result_file_path("月例", display_year, display_month)
    monthly_rec = _read_json_safe(fp_monthly)

    monthly_by_major = {}
    for rec in monthly_rec:
        maj = rec.get("category_major", "")
        if maj not in monthly_by_major:
            monthly_by_major[maj] = []
        monthly_by_major[maj].append(rec)

    usable_width = landscape(A4)[0] - 56

    for maj, recs in monthly_by_major.items():
        title = (f"{building_name}　{display_year}年{display_month}月"
                 f"　{maj}　月例点検結果")
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 6))

        tbl_data = [[
            Paragraph("設備名", monthly_jp_style),
            Paragraph("点検項目", monthly_jp_style),
            Paragraph("結果", monthly_jp_center_style),
            Paragraph("点検日", monthly_jp_style),
            Paragraph("点検者", monthly_jp_style),
        ]]
        span_cmds = []
        data_row_idx = 1

        for rec in recs:
            cat_minor = rec.get("category_minor", "")
            insp_name = rec.get("inspector_name", "")
            insp_date = rec.get("inspection_date", "")
            items = rec.get("results", [])
            n = len(items)
            start_row = data_row_idx
            for item in items:
                tbl_data.append([
                    Paragraph(cat_minor, monthly_jp_style),
                    Paragraph(item.get("inspection_item", ""), monthly_jp_style),
                    Paragraph(forms_layout.normalize_judgment(item.get("result", "")),
                              monthly_jp_center_style),
                    Paragraph(insp_date, monthly_jp_style),
                    Paragraph(insp_name, monthly_jp_style),
                ])
                data_row_idx += 1
            end_row = data_row_idx - 1
            if n > 1:
                span_cmds.append(("SPAN", (0, start_row), (0, end_row)))
                span_cmds.append(("SPAN", (3, start_row), (3, end_row)))
                span_cmds.append(("SPAN", (4, start_row), (4, end_row)))

        remark_parts = []
        for rec in recs:
            gr = rec.get("general_remark", "")
            if isinstance(gr, str) and gr.strip():
                remark_parts.append(f"{rec.get('category_minor', '')}　{gr}")
        remark_display = "<br/>".join(remark_parts) if remark_parts else "特記事項なし"

        tbl_data.append([
            Paragraph("特記事項", monthly_jp_style),
            Paragraph(remark_display, monthly_remark_style),
            "", "", "",
        ])
        remark_row_idx = len(tbl_data) - 1

        col_w = [usable_width * 0.13, usable_width * 0.47, usable_width * 0.08,
                 usable_width * 0.15, usable_width * 0.17]
        tbl = Table(tbl_data, colWidths=col_w)
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("VALIGN", (0, -1), (-1, -1), "TOP"),
            ("SPAN", (1, remark_row_idx), (-1, remark_row_idx)),
            ("ALIGN", (1, remark_row_idx), (-1, remark_row_idx), "LEFT"),
            ("ROWHEIGHT", (0, remark_row_idx), (-1, remark_row_idx), 60),
        ] + span_cmds))
        story.append(tbl)
        story.append(PageBreak())

    if not story:
        story.append(Paragraph("点検結果がありません", jp_style))

    # 一時ファイルにPDFを生成し、storyオブジェクトのメモリを先に解放する
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)
    try:
        doc = SimpleDocTemplate(tmp_path, pagesize=landscape(A4),
                                rightMargin=28, leftMargin=28,
                                topMargin=57, bottomMargin=14)
        doc.build(story)
        del story  # ReportLabオブジェクトのメモリを即座に解放する

        buffer = io.BytesIO()
        with open(tmp_path, "rb") as f:
            shutil.copyfileobj(f, buffer)
        buffer.seek(0)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    filename = f"inspection_{display_year:04d}{display_month:02d}.pdf"
    return send_file(buffer, mimetype="application/pdf",
                     as_attachment=True, download_name=filename)


# ========== API: ヘルスチェック ==========

@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "version": APP_VERSION,
                    "timestamp": datetime.now().isoformat()})


# ========== API: サイネージ ==========

def _get_signage_folder() -> Path:
    config = load_config()
    folder = config.get("signage", {}).get("folder_path", "").strip()
    return Path(folder) if folder else BASE_DIR / "signage_pdfs"


def _read_text_file(path: Path) -> str:
    """テキストファイルを読み込む（UTF-8/Shift-JIS自動判定）"""
    try:
        data = path.read_bytes()
    except OSError as e:
        logger.error("テキスト読み込みエラー %s: %s", path.name, e)
        return ""
    for enc in ("utf-8-sig", "cp932"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# サイネージで表示できる拡張子。txt はニューステロップ用なので含めない。
_SIGNAGE_MEDIA_EXTS = {".mp4", ".webm", ".gif", ".png", ".jpg", ".jpeg"}
_SIGNAGE_ALL_EXTS = {".pdf"} | _SIGNAGE_MEDIA_EXTS


@app.route("/api/signage/files")
def api_signage_files():
    folder_path = _get_signage_folder()
    if not folder_path.exists():
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return jsonify([])
    files = sorted(f.name for f in folder_path.iterdir()
                   if f.suffix.lower() in _SIGNAGE_ALL_EXTS and f.is_file())
    return jsonify(files)


@app.route("/api/signage/news")
def api_signage_news():
    """サイネージフォルダ内のtxtファイルから、ニューステロップの項目一覧を返す"""
    folder_path = _get_signage_folder()
    items = []
    if folder_path.exists() and folder_path.is_dir():
        for f in sorted(folder_path.iterdir()):
            if f.suffix.lower() == ".txt" and f.is_file():
                for line in _read_text_file(f).splitlines():
                    line = line.strip()
                    if line:
                        items.append(line)
    return jsonify(items)

@app.route("/api/signage/pdf/<filename>")
def api_signage_pdf(filename):
    folder_path = _get_signage_folder()
    safe_name = Path(filename).name
    if not safe_name.lower().endswith(".pdf"):
        return jsonify({"error": "Not found"}), 404
    return _send_pdf_cached(folder_path, safe_name)


_SIGNAGE_VIDEO_EXTS = {".mp4", ".webm"}
_VIDEO_CHUNK = 2 * 1024 * 1024
# Range要求1回で返す上限。ブラウザは続きを自分で取りに来る。
# 上限が無いと、先読みで受信を止めたブラウザ1台につき waitress の作業スレッドが
# 再生終了まで1本ふさがる（送り待ちが outbuf_high_watermark=16MB を超えると止まるため）。
# 16MB より小さくしておけば、応答を書き終えた時点でスレッドが空く。
_VIDEO_RESPONSE_MAX = 8 * 1024 * 1024


def _iter_video_chunks(path: Path, start: int, end: int, signature):
    """start〜end（endを含む）を少しずつ返す。

    Windows では開いたままのファイルは削除も名前変更もできない。ブラウザは動画を
    先読みすると受け取りを止めるため、開きっぱなしで送ると再生中ずっと差し替えられない。
    そこで読むたびに開いて閉じる。途中で差し替え・削除されたら、新旧を混ぜずに打ち切る
    （ブラウザは読み込み失敗として扱い、サイネージは次のファイルへ進む）。
    """
    pos = start
    while pos <= end:
        try:
            st = path.stat()
            if (st.st_mtime_ns, st.st_size) != signature:
                logger.info("配信中に動画が差し替えられたため打ち切りました: %s", path.name)
                return
            with open(path, "rb") as f:
                f.seek(pos)
                data = f.read(min(_VIDEO_CHUNK, end - pos + 1))
        except OSError as e:
            logger.info("配信中に動画を読めなくなったため打ち切りました: %s (%s)", path.name, e)
            return
        if not data:
            return
        yield data
        pos += len(data)


def _send_video_chunked(file_path: Path):
    """動画を Range 要求に応じて送る（ETag / If-Range / If-None-Match 対応）"""
    st = file_path.stat()
    size = st.st_size
    signature = (st.st_mtime_ns, size)
    etag = f"{st.st_mtime_ns:x}-{size:x}"

    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=300",
        "ETag": f'"{etag}"',
    }
    if request.if_none_match.contains(etag):
        return Response(status=304, headers=headers)

    start, end, status = 0, size - 1, 200
    rng = request.range
    if_range = request.headers.get("If-Range")
    # If-Range が今のファイルと合わないときは、範囲を無視して全体を送る（HTTPの決まり）
    if rng is not None and (if_range is None or request.if_range.etag == etag):
        bounds = rng.range_for_length(size)
        if bounds is None:
            headers["Content-Range"] = f"bytes */{size}"
            return Response(status=416, headers=headers)
        start, end, status = bounds[0], bounds[1] - 1, 206
        end = min(end, start + _VIDEO_RESPONSE_MAX - 1)
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    headers["Content-Length"] = str(end - start + 1)
    mimetype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return Response(_iter_video_chunks(file_path, start, end, signature),
                    status=status, headers=headers, mimetype=mimetype,
                    direct_passthrough=True)


@app.route("/api/signage/media/<filename>")
def api_signage_media(filename):
    """動画・画像を配信する。

    PDFは実績のある /api/signage/pdf/ をそのまま使うため、ここでは扱わない。
    動画は _send_video_chunked で送る（再生中も削除・差し替えできるように）。
    画像の mimetype は werkzeug に判定させる。
    """
    folder_path = _get_signage_folder()
    safe_name = Path(filename).name
    if Path(safe_name).suffix.lower() not in _SIGNAGE_MEDIA_EXTS:
        return jsonify({"error": "Not found"}), 404
    file_path = folder_path / safe_name
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"error": "Not found"}), 404
    if file_path.suffix.lower() in _SIGNAGE_VIDEO_EXTS:
        return _send_video_chunked(file_path)
    try:
        response = make_response(send_from_directory(str(folder_path), safe_name))
        response.headers["Cache-Control"] = "public, max-age=300"
        return response
    except Exception as e:
        logger.error("メディア配信エラー %s: %s", safe_name, e)
        return jsonify({"error": "ファイル読み込みエラー"}), 500


# ========== API: 備考CSV ==========

@app.route("/api/remarks_csv", methods=["GET"])
def api_remarks_csv():
    try:
        display_year = int(request.args.get("display_year", datetime.now().year))
        display_month = int(request.args.get("display_month", datetime.now().month))
    except (ValueError, TypeError):
        return jsonify({"error": "パラメータが不正です"}), 400

    rows = []
    start_month = display_month - 1 if display_month > 1 else 12
    start_year = display_year if display_month > 1 else display_year - 1

    fp1 = get_result_file_path("使用前", start_year, start_month)
    fp2 = get_result_file_path("使用前", display_year, display_month)
    for rec in _read_json_safe(fp1) + _read_json_safe(fp2):
        remark = rec.get("general_remark", "")
        if isinstance(remark, str) and remark.strip():
            rows.append({"点検種別": "使用前",
                         "設備（大分類）": rec.get("category_major", ""),
                         "設備（小分類）": rec.get("category_minor", ""),
                         "点検日": rec.get("inspection_date", ""),
                         "点検者": rec.get("inspector_name", ""),
                         "特記事項": remark})

    fp_monthly = get_result_file_path("月例", display_year, display_month)
    for rec in _read_json_safe(fp_monthly):
        remark = rec.get("general_remark", "")
        if isinstance(remark, str) and remark.strip():
            rows.append({"点検種別": "月例",
                         "設備（大分類）": rec.get("category_major", ""),
                         "設備（小分類）": rec.get("category_minor", ""),
                         "点検日": rec.get("inspection_date", ""),
                         "点検者": rec.get("inspector_name", ""),
                         "特記事項": remark})

    buffer = io.StringIO()
    fieldnames = ["点検種別", "設備（大分類）", "設備（小分類）", "点検日", "点検者", "特記事項"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    if rows:
        writer.writerows(rows)
    else:
        writer.writerow({"点検種別": "", "設備（大分類）": "", "設備（小分類）": "",
                         "点検日": "", "点検者": "", "特記事項": "特記事項なし"})

    csv_bytes = io.BytesIO()
    csv_bytes.write(b"\xef\xbb\xbf")
    csv_bytes.write(buffer.getvalue().encode("utf-8"))
    csv_bytes.seek(0)
    filename = f"remarks_{display_year:04d}{display_month:02d}.csv"
    return send_file(csv_bytes, mimetype="text/csv",
                     as_attachment=True, download_name=filename)


# ========== API: ドキュメント（カテゴリIDベース） ==========

@app.route("/api/documents/categories")
def api_documents_categories():
    config = load_config()
    return jsonify(config.get("document_categories", {"button_count": 3, "categories": []}))

@app.route("/api/documents/files")
def api_documents_files():
    try:
        category_id = int(request.args.get("category_id", -1))
    except (ValueError, TypeError):
        return jsonify([])
    folder_path = _get_category_folder(category_id)
    if folder_path is None:
        return jsonify([])
    files = sorted(f.stem for f in folder_path.iterdir()
                   if f.suffix.lower() == ".pdf" and f.is_file())
    return jsonify(files)

@app.route("/api/documents/pdf/<filename>")
def api_documents_pdf(filename):
    try:
        category_id = int(request.args.get("category_id", -1))
    except (ValueError, TypeError):
        return jsonify({"error": "category_id が必要です"}), 400
    folder_path = _get_category_folder(category_id)
    if folder_path is None:
        return jsonify({"error": "無効なカテゴリです"}), 400
    safe_name = Path(filename).name
    if not safe_name.lower().endswith(".pdf"):
        safe_name = safe_name + ".pdf"
    return _send_pdf_cached(folder_path, safe_name)


# ========== 起動 ==========

def _resolve_port(server_cfg: dict, default: int = 5000) -> int:
    """設定からポート番号を取得する。不正値・欠落時は既定値にフォールバックする"""
    try:
        return int(server_cfg.get("port", default))
    except (ValueError, TypeError):
        return default


def _find_available_port(preferred: int, host: str, max_attempts: int = 10):
    for port in range(preferred, preferred + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host if host != "0.0.0.0" else "", port))
                return port
        except OSError:
            continue
    return None


if __name__ == "__main__":
    config = load_config()
    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    preferred_port = _resolve_port(server_cfg)

    port = _find_available_port(preferred_port, host)
    if port is None:
        msg = f"ポート {preferred_port}～{preferred_port + 9} が全て使用中です"
        print(f"エラー: {msg}")
        logger.error(msg)
        sys.exit(1)

    if port != preferred_port:
        msg = f"ポート {preferred_port} は使用中のため、ポート {port} で起動します"
        print(f"注意: {msg}")
        logger.warning(msg)

    admin_key = _get_admin_key()
    print("設備点検システムを起動します...")
    print(f"ブラウザで http://localhost:{port} を開いてください")
    if host != "127.0.0.1":
        print(f"管理者キー: {admin_key}")
        print("（リモートからの設定変更にはこのキーが必要です）")
    logger.info("サーバー起動: %s:%d", host, port)

    try:
        from waitress import serve
        print("（waitressサーバーで起動）")
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, debug=False)
