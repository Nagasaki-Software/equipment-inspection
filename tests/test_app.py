"""設備点検システム ver5 テストスイート"""
import json
import os
from pathlib import Path

import pytest


# ========== 静的ページテスト ==========

def test_root_returns_200(client):
    c, _ = client
    res = c.get("/")
    assert res.status_code == 200


def test_inspection_returns_200(client):
    c, _ = client
    res = c.get("/inspection")
    assert res.status_code == 200


def test_documents_returns_200(client):
    c, _ = client
    res = c.get("/documents")
    assert res.status_code == 200


# ========== 設定APIテスト ==========

def test_api_get_config(client):
    c, _ = client
    res = c.get("/api/config")
    assert res.status_code == 200
    data = res.get_json()
    assert "building_info" in data


def test_api_post_config_document_categories(client):
    c, _ = client
    payload = {
        "document_categories": {
            "button_count": 3,
            "categories": [{"label": "A", "folder": "/tmp"}],
        }
    }
    res = c.post(
        "/api/config",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 200
    cfg_res = c.get("/api/config")
    cfg = cfg_res.get_json()
    assert cfg["document_categories"]["button_count"] == 3


def test_api_post_config_invalid_save_directory(client):
    """save_directoryに文字列以外を送ると400エラーになること"""
    c, _ = client
    res = c.post(
        "/api/config",
        data=json.dumps({"save_directory": 12345}),
        content_type="application/json",
    )
    assert res.status_code == 400


def test_api_post_config_invalid_server_port(client):
    """server.portに不正値を送ると400エラーになること"""
    c, _ = client
    res = c.post(
        "/api/config",
        data=json.dumps({"server": {"port": 99999}}),
        content_type="application/json",
    )
    assert res.status_code == 400


def test_api_post_config_invalid_signage_type(client):
    """signageに辞書以外を送ると400エラーになること"""
    c, _ = client
    res = c.post(
        "/api/config",
        data=json.dumps({"signage": "invalid"}),
        content_type="application/json",
    )
    assert res.status_code == 400


# ========== ドキュメントAPIテスト（category_idベース） ==========

def test_api_documents_categories(client):
    c, _ = client
    res = c.get("/api/documents/categories")
    assert res.status_code == 200
    data = res.get_json()
    assert "button_count" in data
    assert "categories" in data


def test_api_documents_files_valid_category(client):
    """有効なカテゴリIDで、PDFファイルが一覧取得できること"""
    c, tmp_path = client
    (tmp_path / "テスト資料.pdf").write_bytes(b"%PDF-1.4")
    res = c.get("/api/documents/files?category_id=0")
    assert res.status_code == 200
    files = res.get_json()
    assert "テスト資料" in files


def test_api_documents_files_invalid_category(client):
    """無効なカテゴリIDでは空リストが返ること"""
    c, _ = client
    res = c.get("/api/documents/files?category_id=999")
    assert res.status_code == 200
    assert res.get_json() == []


def test_api_documents_pdf_found(client):
    """存在するPDFファイルが取得できること"""
    c, tmp_path = client
    (tmp_path / "資料.pdf").write_bytes(b"%PDF-1.4 test")
    res = c.get(
        "/api/documents/pdf/%E8%B3%87%E6%96%99.pdf?category_id=0"
    )
    assert res.status_code == 200
    assert res.content_type == "application/pdf"


def test_api_documents_pdf_not_found(client):
    """存在しないPDFファイルで404が返ること"""
    c, _ = client
    res = c.get("/api/documents/pdf/notexist.pdf?category_id=0")
    assert res.status_code == 404


# ========== 点検結果APIテスト ==========

def test_api_get_results(client):
    """結果取得APIが正常に応答すること"""
    c, _ = client
    res = c.get("/api/results?type=使用前&year=2026&month=5")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


def test_api_post_results_success(client):
    """正常な点検結果のPOSTが成功すること"""
    c, _ = client
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "2026-05-17",
        "inspector_name": "テスト太郎",
        "department": "テスト部",
        "category_major": "電気",
        "category_minor": "照明",
        "general_remark": "",
        "results": [
            {"equipment_name": "電気", "inspection_item": "通電確認", "result": "○", "remark": ""}
        ]
    }
    res = c.post(
        "/api/results",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"


def test_api_post_results_invalid_type(client):
    """不正な点検種別でバリデーションエラーになること"""
    c, _ = client
    payload = {
        "inspection_type": "不正値",
        "inspection_date": "2026-05-17",
        "results": []
    }
    res = c.post(
        "/api/results",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 400


def test_api_post_results_invalid_date(client):
    """不正な日付形式でバリデーションエラーになること"""
    c, _ = client
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "20260517",
        "results": []
    }
    res = c.post(
        "/api/results",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 400


def test_api_post_results_too_many_results(client):
    """resultsが500件を超えるとバリデーションエラーになること"""
    c, _ = client
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "2026-05-17",
        "results": [{"equipment_name": "X", "inspection_item": f"item{i}", "result": "○"} for i in range(501)]
    }
    res = c.post(
        "/api/results",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 400
    data = res.get_json()
    assert "500" in str(data)


def test_api_post_results_string_too_long(client):
    """文字列フィールドが500文字を超えるとバリデーションエラーになること"""
    c, _ = client
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "2026-05-17",
        "inspector_name": "A" * 501,
        "results": []
    }
    res = c.post(
        "/api/results",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 400


# ========== サイネージ ニューステロップ ==========

def _set_signage_folder(c, folder):
    """設定のサイネージフォルダを指定する（テスト用ヘルパー）"""
    res = c.post(
        "/api/config",
        data=json.dumps({"signage": {"folder_path": str(folder)}}),
        content_type="application/json",
    )
    assert res.status_code == 200


def test_api_signage_news_lists_lines(client):
    """txtファイル内の各行がニュース項目として返ること"""
    c, tmp_path = client
    news_dir = tmp_path / "news"
    news_dir.mkdir()
    (news_dir / "topics.txt").write_text("お知らせ1\nお知らせ2\n", encoding="utf-8")
    _set_signage_folder(c, news_dir)
    res = c.get("/api/signage/news")
    assert res.status_code == 200
    data = res.get_json()
    assert data == ["お知らせ1", "お知らせ2"]


def test_api_signage_news_multiple_files_sorted(client):
    """複数txtファイルがファイル名順に連結されること"""
    c, tmp_path = client
    news_dir = tmp_path / "news2"
    news_dir.mkdir()
    (news_dir / "b.txt").write_text("Bのお知らせ\n", encoding="utf-8")
    (news_dir / "a.txt").write_text("Aのお知らせ\n", encoding="utf-8")
    _set_signage_folder(c, news_dir)
    res = c.get("/api/signage/news")
    assert res.get_json() == ["Aのお知らせ", "Bのお知らせ"]


def test_api_signage_news_empty_returns_empty_list(client):
    """txtファイルが無い場合は空リストを返すこと（表示文言はフロント側）"""
    c, tmp_path = client
    empty_dir = tmp_path / "empty_news"
    empty_dir.mkdir()
    _set_signage_folder(c, empty_dir)
    res = c.get("/api/signage/news")
    assert res.status_code == 200
    assert res.get_json() == []


def test_api_signage_news_shift_jis(client):
    """Shift-JISのtxtファイルも文字化けせず読めること"""
    c, tmp_path = client
    sjis_dir = tmp_path / "sjis_news"
    sjis_dir.mkdir()
    (sjis_dir / "s.txt").write_bytes("緊急連絡".encode("cp932") + b"\r\n")
    _set_signage_folder(c, sjis_dir)
    res = c.get("/api/signage/news")
    assert res.get_json() == ["緊急連絡"]


def test_api_signage_pdf_range_with_if_range(client):
    """大きいPDFの分割取得: If-Range付きRange要求にも206が返ること。

    ETagを手動で上書きすると werkzeug の If-Range 照合が壊れ、
    分割取得が毎回200(全体転送)に落ちる回帰を防ぐ。
    （LANクライアントでPDFの絵が白抜けした不具合の根本原因）
    """
    c, tmp_path = client
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "big.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 200000)
    res = c.post(
        "/api/config",
        data=json.dumps({"signage": {"folder_path": str(pdf_dir)}}),
        content_type="application/json",
    )
    assert res.status_code == 200

    # 1回目: Rangeのみ → 206（部分応答）
    r1 = c.get("/api/signage/pdf/big.pdf", headers={"Range": "bytes=0-999"})
    assert r1.status_code == 206
    etag = r1.headers.get("ETag")
    assert etag

    # 2回目: ブラウザと同様に If-Range を付ける → 206 のままであること
    r2 = c.get("/api/signage/pdf/big.pdf",
               headers={"Range": "bytes=1000-1999", "If-Range": etag})
    assert r2.status_code == 206
    assert int(r2.headers.get("Content-Length", "0")) == 1000


# ========== サイネージ 動画・画像 ==========

def test_api_signage_files_lists_media(client):
    """動画・画像もPDFと一緒に一覧へ出ること（名前順）"""
    c, tmp_path = client
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    for name in ("01_資料.pdf", "02_説明.mp4", "03_案内.gif",
                 "04_写真.png", "05_写真.jpg", "06_動画.webm"):
        (media_dir / name).write_bytes(b"dummy")
    (media_dir / "メモ.txt").write_text("ニュース", encoding="utf-8")
    (media_dir / "設定.exe").write_bytes(b"dummy")
    _set_signage_folder(c, media_dir)
    res = c.get("/api/signage/files")
    assert res.status_code == 200
    assert res.get_json() == ["01_資料.pdf", "02_説明.mp4", "03_案内.gif",
                             "04_写真.png", "05_写真.jpg", "06_動画.webm"]


def test_api_signage_media_serves_mp4(client):
    """MP4が動画として配信されること"""
    c, tmp_path = client
    media_dir = tmp_path / "media2"
    media_dir.mkdir()
    (media_dir / "説明.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 500)
    _set_signage_folder(c, media_dir)
    res = c.get("/api/signage/media/%E8%AA%AC%E6%98%8E.mp4")
    assert res.status_code == 200
    assert res.content_type.startswith("video/mp4")


def test_api_signage_media_supports_range(client):
    """動画の途中再生・シークのため、Range要求に206を返すこと"""
    c, tmp_path = client
    media_dir = tmp_path / "media3"
    media_dir.mkdir()
    (media_dir / "long.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 200000)
    _set_signage_folder(c, media_dir)
    r1 = c.get("/api/signage/media/long.mp4", headers={"Range": "bytes=0-999"})
    assert r1.status_code == 206
    etag = r1.headers.get("ETag")
    assert etag
    r2 = c.get("/api/signage/media/long.mp4",
               headers={"Range": "bytes=1000-1999", "If-Range": etag})
    assert r2.status_code == 206
    assert int(r2.headers.get("Content-Length", "0")) == 1000


def _make_big_video(c, tmp_path, dirname):
    """2MBの区切りをまたぐ大きさの動画もどきを作る"""
    media_dir = tmp_path / dirname
    media_dir.mkdir()
    data = bytes(range(256)) * (5 * 1024 * 1024 // 256 + 123)   # 約5MB
    path = media_dir / "big.mp4"
    path.write_bytes(data)
    _set_signage_folder(c, media_dir)
    return path, data


def test_api_signage_media_video_full_and_seek(client):
    """大きな動画でも全体・途中からの両方を正しい中身で返すこと"""
    c, tmp_path = client
    path, data = _make_big_video(c, tmp_path, "media_big1")
    r = c.get("/api/signage/media/big.mp4")
    assert r.status_code == 200
    assert r.data == data
    assert r.headers.get("Accept-Ranges") == "bytes"

    start = 3 * 1024 * 1024 + 7
    r2 = c.get("/api/signage/media/big.mp4", headers={"Range": f"bytes={start}-"})
    assert r2.status_code == 206
    assert r2.headers["Content-Range"] == f"bytes {start}-{len(data) - 1}/{len(data)}"
    assert r2.data == data[start:]


def test_api_signage_media_video_range_out_of_bounds(client):
    """ファイルより後ろを指定されたら416を返すこと"""
    c, tmp_path = client
    path, data = _make_big_video(c, tmp_path, "media_big2")
    r = c.get("/api/signage/media/big.mp4", headers={"Range": f"bytes={len(data) + 10}-"})
    assert r.status_code == 416
    assert r.headers["Content-Range"] == f"bytes */{len(data)}"


def test_api_signage_media_video_not_locked_while_streaming(client):
    """送っている途中でも、動画の名前変更（＝削除・差し替え）ができること。
    Windowsでは開いたままのファイルは消せないため、読むたびに閉じる。"""
    c, tmp_path = client
    path, data = _make_big_video(c, tmp_path, "media_big3")
    r = c.get("/api/signage/media/big.mp4", headers={"Range": "bytes=0-"},
              buffered=False)
    try:
        it = iter(r.response)
        first = next(it)
        assert first == data[:len(first)]
        moved = path.with_name("moved.mp4")
        os.rename(path, moved)          # 開いたままなら PermissionError になる
        os.rename(moved, path)
    finally:
        r.close()


def test_api_signage_media_video_range_response_is_capped(client, monkeypatch):
    """終わりを指定しないRange要求には上限の長さだけ返し、続きはブラウザに取りに来させること
    （大きな動画で waitress のスレッドを再生中ずっとふさがないため）"""
    import app as flask_app
    c, tmp_path = client
    path, data = _make_big_video(c, tmp_path, "media_big5")
    monkeypatch.setattr(flask_app, "_VIDEO_RESPONSE_MAX", 1024 * 1024)
    r = c.get("/api/signage/media/big.mp4", headers={"Range": "bytes=100-"})
    assert r.status_code == 206
    assert r.headers["Content-Range"] == f"bytes 100-{100 + 1024 * 1024 - 1}/{len(data)}"
    assert r.data == data[100:100 + 1024 * 1024]


def test_api_signage_media_video_stops_when_replaced(client):
    """送っている途中で差し替えられたら、新旧を混ぜずに打ち切ること"""
    c, tmp_path = client
    path, data = _make_big_video(c, tmp_path, "media_big4")
    r = c.get("/api/signage/media/big.mp4", buffered=False)
    it = iter(r.response)
    received = next(it)
    path.write_bytes(b"\xff" * (len(data) + 1000))   # 別の動画に差し替え
    for chunk in it:
        received += chunk
    r.close()
    assert len(received) < len(data)
    assert received == data[:len(received)]


def test_api_signage_media_rejects_other_extensions(client):
    """許可していない拡張子は配信しないこと"""
    c, tmp_path = client
    media_dir = tmp_path / "media4"
    media_dir.mkdir()
    (media_dir / "危険.exe").write_bytes(b"dummy")
    _set_signage_folder(c, media_dir)
    res = c.get("/api/signage/media/%E5%8D%B1%E9%99%BA.exe")
    assert res.status_code == 404


def test_api_signage_media_not_found(client):
    """存在しないファイルで404が返ること"""
    c, tmp_path = client
    media_dir = tmp_path / "media5"
    media_dir.mkdir()
    _set_signage_folder(c, media_dir)
    res = c.get("/api/signage/media/notexist.mp4")
    assert res.status_code == 404


def test_api_documents_files_still_pdf_only(client):
    """文書掲示はPDF閲覧専用のまま（サイネージ側の拡張が波及していないこと）"""
    c, tmp_path = client
    (tmp_path / "資料.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "動画.mp4").write_bytes(b"dummy")
    res = c.get("/api/documents/files?category_id=0")
    assert res.status_code == 200
    assert res.get_json() == ["資料"]


# ========== ヘルスチェック ==========

def test_api_health(client):
    c, _ = client
    res = c.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"


# ========== 点検結果ファイルのアトミック書き込み ==========

_RESULT_PAYLOAD = {
    "inspection_type": "使用前",
    "inspection_date": "2026-05-17",
    "inspector_name": "テスト太郎",
    "category_major": "電気",
    "category_minor": "照明",
    "results": [
        {"equipment_name": "電気", "inspection_item": "通電確認", "result": "○"}
    ],
}


def test_post_results_leaves_no_tmp_file(client, monkeypatch):
    """保存成功後に .tmp 一時ファイルが残らないこと"""
    import app as flask_app
    c, tmp_path = client
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    res = c.post("/api/results", data=json.dumps(_RESULT_PAYLOAD),
                 content_type="application/json")
    assert res.status_code == 200
    assert list(tmp_path.glob("**/*.tmp")) == []


def test_post_results_keeps_original_on_write_failure(client, monkeypatch):
    """書き込み失敗時に既存の結果ファイルが壊れないこと（アトミック性）"""
    import app as flask_app
    c, tmp_path = client
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    # 1回目: 正常に保存
    res = c.post("/api/results", data=json.dumps(_RESULT_PAYLOAD),
                 content_type="application/json")
    assert res.status_code == 200
    fp = flask_app.get_result_file_path("使用前", 2026, 5)
    original = fp.read_text(encoding="utf-8")
    # 2回目: 置換を失敗させる（TESTINGモードのFlaskは例外をそのまま送出する）
    def boom(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(flask_app.os, "replace", boom)
    payload2 = dict(_RESULT_PAYLOAD, inspector_name="別の人",
                    results=[{"equipment_name": "電気",
                              "inspection_item": "通電確認", "result": "×"}])
    with pytest.raises(OSError):
        c.post("/api/results", data=json.dumps(payload2),
               content_type="application/json")
    # 元ファイルは無傷で、一時ファイルも残っていない
    assert fp.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("**/*.tmp")) == []


# ========== 設定ファイルのアトミック書き込み ==========

def test_save_config_leaves_no_tmp_file(client):
    """設定保存成功後に .tmp 一時ファイルが残らないこと"""
    import app as flask_app
    c, tmp_path = client
    res = c.post("/api/config", data=json.dumps({"save_directory": "/tmp/x"}),
                 content_type="application/json")
    assert res.status_code == 200
    assert list(tmp_path.glob("**/*.tmp")) == []


def test_save_config_keeps_original_on_write_failure(client, monkeypatch):
    """設定書き込み失敗時に既存の設定ファイルが壊れないこと（アトミック性）"""
    import app as flask_app
    c, tmp_path = client
    config_path = flask_app.CONFIG_PATH
    original = config_path.read_text(encoding="utf-8")

    def boom(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(flask_app.os, "replace", boom)
    with pytest.raises(OSError):
        c.post("/api/config", data=json.dumps({"save_directory": "/tmp/y"}),
               content_type="application/json")
    # 元ファイルは無傷で、一時ファイルも残っていない
    assert config_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("**/*.tmp")) == []


# ========== 祝日CSV読み込みの堅牢化 ==========

def test_holidays_endpoint_tolerates_malformed_csv(client, monkeypatch):
    """custom_holidays.csv の列が欠けてもクラッシュせず200を返すこと"""
    import app as flask_app
    c, tmp_path = client
    bad = tmp_path / "custom_holidays.csv"
    # "name" 列が無く、日付の無い空行も混在
    bad.write_text("date,note\n2026-05-01,メモ\n,空行\n", encoding="utf-8")
    monkeypatch.setattr(flask_app, "CUSTOM_HOLIDAYS_CSV", bad)
    res = c.get("/api/holidays?start=2026-05-01&end=2026-05-03")
    assert res.status_code == 200
    days = res.get_json()
    by_date = {d["date"]: d for d in days}
    # 日付のある行は独自休日として扱われ、名前列が無くても空文字で安全に処理される
    assert by_date["2026-05-01"]["is_custom_holiday"] is True
    assert by_date["2026-05-01"]["custom_holiday_name"] == ""


# ========== 起動時ポート値のフォールバック ==========

def test_resolve_port_valid():
    """正常なポート値はそのまま整数で返ること"""
    import app as flask_app
    assert flask_app._resolve_port({"port": 5050}) == 5050
    assert flask_app._resolve_port({"port": "5050"}) == 5050


def test_resolve_port_invalid_falls_back():
    """不正なポート値や欠落時は既定値5000にフォールバックすること"""
    import app as flask_app
    assert flask_app._resolve_port({"port": "abc"}) == 5000
    assert flask_app._resolve_port({"port": None}) == 5000
    assert flask_app._resolve_port({}) == 5000


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


# ========== 数値項目の機器識別（レビューで見つかった不具合） ==========

def _write_master(tmp_path, rows):
    """テスト用の点検項目マスタCSVを作る"""
    master = tmp_path / "equipment_master.csv"
    header = ("category_major,category_minor,inspection_item,"
              "inspection_type,input_type,unit\n")
    master.write_text(header + "".join(rows), encoding="utf-8")
    return master


def _post_one(c, major, minor, item, value):
    """点検結果を1件だけPOSTする"""
    payload = {
        "inspection_type": "使用前",
        "inspection_date": "2026-03-02",
        "category_major": major,
        "category_minor": minor,
        "inspector_name": "テスト",
        "department": "テスト部",
        "results": [{"equipment_name": major, "inspection_item": item,
                     "result": value, "remark": ""}],
    }
    return c.post("/api/results", data=json.dumps(payload),
                  content_type="application/json")


def test_number_item_does_not_leak_to_other_equipment(client, monkeypatch, tmp_path):
    """同じ項目名でも、別の機器の判定項目が数値扱いされないこと"""
    import app as flask_app
    master = _write_master(tmp_path, [
        "クレーン,クレーン1,点検項目C-1,使用前,数値,MPa\n",
        "設備C,シャッター1,点検項目C-1,使用前,判定,\n",
    ])
    monkeypatch.setattr(flask_app, "EQUIPMENT_CSV", master)
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    # 判定項目の機器に ○ と ー を送っても通ること
    assert _post_one(c, "設備C", "シャッター1", "点検項目C-1", "○").status_code == 200
    assert _post_one(c, "設備C", "シャッター1", "点検項目C-1", "ー").status_code == 200
    # 数値項目の機器には数値が求められること
    assert _post_one(c, "クレーン", "クレーン1", "点検項目C-1", "0.52").status_code == 200
    assert _post_one(c, "クレーン", "クレーン1", "点検項目C-1", "こわれてる").status_code == 400


def test_number_item_accepts_not_applicable_mark(client, monkeypatch, tmp_path):
    """数値項目でも「ー」（点検対象外）を記録できること"""
    import app as flask_app
    master = _write_master(tmp_path, ["設備A,A-1,油圧,使用前,数値,MPa\n"])
    monkeypatch.setattr(flask_app, "EQUIPMENT_CSV", master)
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    res = _post_one(c, "設備A", "A-1", "油圧", "ー")
    assert res.status_code == 200
    saved = json.loads(Path(res.get_json()["file"]).read_text(encoding="utf-8"))
    assert saved[0]["results"][0]["result"] == "ー"


def test_number_item_keys_filters_by_equipment(monkeypatch, tmp_path):
    """_number_item_keys が機器で絞り込むこと"""
    import app as flask_app
    master = _write_master(tmp_path, [
        "クレーン,クレーン1,点検項目C-1,使用前,数値,MPa\n",
        "設備C,シャッター1,点検項目C-1,使用前,判定,\n",
    ])
    monkeypatch.setattr(flask_app, "EQUIPMENT_CSV", master)
    assert flask_app._number_item_keys("クレーン", "クレーン1") == {"点検項目C-1"}
    assert flask_app._number_item_keys("設備C", "シャッター1") == set()
    assert flask_app._number_item_keys("存在しない", "機器") == set()


def test_number_item_keys_survives_broken_master(monkeypatch, tmp_path):
    """マスタCSVが読めなくても空集合を返して落ちないこと"""
    import app as flask_app
    master = tmp_path / "broken_master.csv"
    # cp932 で保存された日本語CSVは utf-8 として読めない
    master.write_bytes("category_major,inspection_item\nクレーン,傷\n".encode("cp932"))
    monkeypatch.setattr(flask_app, "EQUIPMENT_CSV", master)
    assert flask_app._number_item_keys("クレーン", "クレーン1") == set()


def test_post_results_survives_broken_master(client, monkeypatch, tmp_path):
    """マスタCSVが壊れていても点検結果は保存できること"""
    import app as flask_app
    master = tmp_path / "broken_master.csv"
    master.write_bytes("category_major,inspection_item\nクレーン,傷\n".encode("cp932"))
    monkeypatch.setattr(flask_app, "EQUIPMENT_CSV", master)
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    assert _post_one(c, "設備A", "A-1", "傷はないか", "○").status_code == 200


def test_is_number_like_rejects_special_values():
    """inf / nan / 指数表記 / アンダースコア区切りを弾くこと"""
    import app as flask_app
    for bad in ("inf", "-inf", "nan", "NaN", "1e5", "1_000", "０x10"):
        assert flask_app._is_number_like(bad) is False, f"{bad!r} を通してしまった"
    for good in ("0.52", "-3", "+5", ".5", "5.", "100"):
        assert flask_app._is_number_like(good) is True, f"{good!r} を弾いてしまった"


def test_normalize_number_accepts_json_number():
    """JSONの数値型で送られても文字列に直すこと"""
    import app as flask_app
    assert flask_app._normalize_number(0.52) == "0.52"
    assert flask_app._normalize_number(12) == "12"


def test_normalize_number_keeps_not_applicable():
    """「ー」はそのまま返すこと（半角ハイフンに変えない）"""
    import app as flask_app
    assert flask_app._normalize_number("ー") == "ー"
    assert flask_app._normalize_number("　ー　") == "ー"


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


def test_load_layout_missing_file_raises(tmp_path):
    """layout.json が無いフォルダは LayoutError になること"""
    import forms_layout
    d = tmp_path / "empty"
    d.mkdir()
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


def test_load_layout_year_requires_axis(tmp_path):
    """year 型で axis が無ければ LayoutError になること"""
    import forms_layout
    bad = dict(SAMPLE_LAYOUT)
    del bad["axis"]
    d = _write_layout(tmp_path, "noaxis", bad)
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_load_layout_single_needs_no_axis(tmp_path):
    """single 型は axis が無くても読めること"""
    import forms_layout
    single = dict(SAMPLE_LAYOUT)
    single["period"] = "single"
    del single["axis"]
    d = _write_layout(tmp_path, "single", single)
    assert forms_layout.load_layout(d)["period"] == "single"


def test_save_layout_roundtrip(tmp_path):
    """保存した内容を読み戻せること"""
    import forms_layout
    d = tmp_path / "new"
    d.mkdir()
    forms_layout.save_layout(d, SAMPLE_LAYOUT)
    assert forms_layout.load_layout(d)["form_name"] == "吊具月例点検表"


def test_save_layout_creates_folder(tmp_path):
    """フォルダが無ければ作ること"""
    import forms_layout
    d = tmp_path / "notyet"
    forms_layout.save_layout(d, SAMPLE_LAYOUT)
    assert (d / "layout.json").exists()


def test_save_layout_rejects_invalid(tmp_path):
    """不正な内容は保存せず LayoutError になること"""
    import forms_layout
    d = tmp_path / "bad"
    d.mkdir()
    bad = dict(SAMPLE_LAYOUT)
    bad["period"] = "weekly"
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.save_layout(d, bad)
    assert not (d / "layout.json").exists()


def test_save_layout_leaves_no_tmp_file(tmp_path):
    """保存後に一時ファイルが残らないこと"""
    import forms_layout
    d = tmp_path / "atomic"
    d.mkdir()
    forms_layout.save_layout(d, SAMPLE_LAYOUT)
    assert not list(d.glob("*.tmp"))


def test_save_layout_keeps_japanese_readable(tmp_path):
    """日本語がエスケープされずそのまま書かれること"""
    import forms_layout
    d = tmp_path / "jp"
    d.mkdir()
    forms_layout.save_layout(d, SAMPLE_LAYOUT)
    text = (d / "layout.json").read_text(encoding="utf-8")
    assert "吊具月例点検表" in text


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


def test_list_forms_missing_directory(tmp_path):
    """様式フォルダが存在しなくても空リストを返すこと"""
    import forms_layout
    assert forms_layout.list_forms(tmp_path / "nothing") == []


def test_list_forms_sorted(tmp_path):
    """様式が名前順に並ぶこと"""
    import forms_layout
    _write_layout(tmp_path, "zebra", SAMPLE_LAYOUT)
    _write_layout(tmp_path, "alpha", SAMPLE_LAYOUT)
    assert [f["id"] for f in forms_layout.list_forms(tmp_path)] == ["alpha", "zebra"]


def test_valid_form_id():
    """様式IDは半角英数字とアンダースコアのみ許すこと"""
    import forms_layout
    assert forms_layout.is_valid_form_id("crane_1") is True
    assert forms_layout.is_valid_form_id("../etc") is False
    assert forms_layout.is_valid_form_id("吊具") is False
    assert forms_layout.is_valid_form_id("") is False
    assert forms_layout.is_valid_form_id("a b") is False
    assert forms_layout.is_valid_form_id(None) is False


def test_load_layout_wrong_encoding_raises_layout_error(tmp_path):
    """cp932 で保存された layout.json は LayoutError になること（落ちないこと）"""
    import forms_layout
    d = tmp_path / "cp932"
    d.mkdir()
    body = json.dumps(SAMPLE_LAYOUT, ensure_ascii=False)
    (d / "layout.json").write_bytes(body.encode("cp932"))
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_list_forms_survives_wrong_encoding(tmp_path):
    """cp932 の様式が混ざっていても list_forms が落ちず error 付きで返すこと"""
    import forms_layout
    ok = _write_layout(tmp_path, "good", SAMPLE_LAYOUT)
    bad = tmp_path / "cp932"
    bad.mkdir()
    body = json.dumps(SAMPLE_LAYOUT, ensure_ascii=False)
    (bad / "layout.json").write_bytes(body.encode("cp932"))
    forms = forms_layout.list_forms(tmp_path)
    assert len(forms) == 2
    by_id = {f["id"]: f for f in forms}
    assert by_id["cp932"]["error"] != ""
    assert by_id["good"]["error"] == ""


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
    """縦並びの軸で n に応じて y がずれること（PDF座標は上が正）"""
    import forms_layout
    axis = {"step_x": 0.0, "step_y": -20.0, "count": 31}
    field = {"x": 100.0, "y": 700.0, "on_axis": True}
    assert forms_layout.axis_position(field, axis, 3) == (100.0, 660.0)


def test_axis_position_ignores_axis_when_not_on_axis():
    """on_axis でないフィールドは軸の影響を受けないこと"""
    import forms_layout
    field = {"x": 120.0, "y": 660.0}
    assert forms_layout.axis_position(field, AXIS, 9) == (120.0, 660.0)


def test_axis_position_without_axis():
    """axis が None や空でも落ちないこと"""
    import forms_layout
    field = {"x": 120.0, "y": 660.0, "on_axis": True}
    assert forms_layout.axis_position(field, None, 5) == (120.0, 660.0)
    assert forms_layout.axis_position(field, {}, 5) == (120.0, 660.0)


def test_axis_position_missing_coordinates():
    """x / y が無いフィールドは 0 として扱うこと"""
    import forms_layout
    assert forms_layout.axis_position({"on_axis": True}, AXIS, 2) == (38.0, 0.0)


def test_axis_count():
    """欄数は axis.count、無ければ period の既定値を使うこと"""
    import forms_layout
    assert forms_layout.axis_count({"period": "year", "axis": {"count": 6}}) == 6
    assert forms_layout.axis_count({"period": "year", "axis": {}}) == 12
    assert forms_layout.axis_count({"period": "month", "axis": {}}) == 31
    assert forms_layout.axis_count({"period": "single"}) == 0


def test_axis_count_invalid_value():
    """count が不正なら period の既定値に戻ること"""
    import forms_layout
    assert forms_layout.axis_count({"period": "year", "axis": {"count": 0}}) == 12
    assert forms_layout.axis_count({"period": "year", "axis": {"count": -3}}) == 12
    assert forms_layout.axis_count({"period": "month", "axis": {"count": "abc"}}) == 31
    assert forms_layout.axis_count({"period": "month", "axis": {"count": None}}) == 31


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
    """壊れた様式は紐づけから除外されること（表出力にフォールバックさせるため）"""
    import forms_layout
    d = tmp_path / "broken"
    d.mkdir()
    (d / "layout.json").write_text("{ oops", encoding="utf-8")
    assert forms_layout.form_assignments(tmp_path) == {}


def test_form_assignments_empty_directory(tmp_path):
    """様式が1つも無ければ空の辞書を返すこと"""
    import forms_layout
    assert forms_layout.form_assignments(tmp_path) == {}
    assert forms_layout.form_assignments(tmp_path / "nothing") == {}


# ========== forms_layout の堅牢化（レビューで見つかった穴） ==========

def test_validate_rejects_non_dict_field(tmp_path):
    """fields に辞書でない要素が混ざったら LayoutError になること"""
    import forms_layout
    bad = dict(SAMPLE_LAYOUT)
    bad["fields"] = [{"source": "meta.month", "page": 0, "x": 1.0, "y": 2.0}, 123]
    d = _write_layout(tmp_path, "badfield", bad)
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_validate_rejects_non_string_target(tmp_path):
    """targets に文字列でない要素が混ざったら LayoutError になること"""
    import forms_layout
    bad = dict(SAMPLE_LAYOUT)
    bad["targets"] = ["吊具A", ["吊具B"]]
    d = _write_layout(tmp_path, "badtarget", bad)
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_validate_rejects_non_numeric_axis(tmp_path):
    """axis.step_x が数値でなければ LayoutError になること"""
    import forms_layout
    bad = dict(SAMPLE_LAYOUT)
    bad["axis"] = {"step_x": "38,0", "step_y": 0.0, "count": 12}
    d = _write_layout(tmp_path, "badaxis", bad)
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_validate_rejects_non_numeric_coordinate(tmp_path):
    """フィールドの x が数値でなければ LayoutError になること"""
    import forms_layout
    bad = dict(SAMPLE_LAYOUT)
    bad["fields"] = [{"source": "meta.month", "page": 0, "x": "abc", "y": 2.0}]
    d = _write_layout(tmp_path, "badcoord", bad)
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_validate_rejects_negative_page(tmp_path):
    """page が負なら LayoutError になること"""
    import forms_layout
    bad = dict(SAMPLE_LAYOUT)
    bad["fields"] = [{"source": "meta.month", "page": -1, "x": 1.0, "y": 2.0}]
    d = _write_layout(tmp_path, "badpage", bad)
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_validate_rejects_non_string_form_name(tmp_path):
    """form_name が文字列でなければ LayoutError になること"""
    import forms_layout
    bad = dict(SAMPLE_LAYOUT)
    bad["form_name"] = {"a": 1}
    d = _write_layout(tmp_path, "badname", bad)
    with pytest.raises(forms_layout.LayoutError):
        forms_layout.load_layout(d)


def test_list_forms_survives_unexpected_error(tmp_path):
    """想定外の壊れ方でも一覧全体が落ちず、他の様式が残ること"""
    import forms_layout
    _write_layout(tmp_path, "good_a", SAMPLE_LAYOUT)
    _write_layout(tmp_path, "good_b", SAMPLE_LAYOUT)
    deep = tmp_path / "deep"
    deep.mkdir()
    # 極端に深いネストは json.load が RecursionError を投げる
    (deep / "layout.json").write_text("[" * 20000 + "]" * 20000, encoding="utf-8")
    forms = forms_layout.list_forms(tmp_path)
    assert len(forms) == 3
    by_id = {f["id"]: f for f in forms}
    assert by_id["deep"]["error"] != ""
    assert by_id["good_a"]["error"] == ""
    assert by_id["good_b"]["error"] == ""


def test_valid_form_id_rejects_trailing_newline():
    """末尾の改行を通さないこと"""
    import forms_layout
    assert forms_layout.is_valid_form_id("form\n") is False
    assert forms_layout.is_valid_form_id("form\r\n") is False


def test_valid_form_id_rejects_windows_reserved_names():
    """Windows の予約デバイス名を通さないこと"""
    import forms_layout
    for name in ("CON", "con", "PRN", "AUX", "NUL", "nul",
                 "COM1", "COM9", "LPT1", "lpt9"):
        assert forms_layout.is_valid_form_id(name) is False, f"{name} を通した"
    # 予約名を含むだけの ID は通ること
    assert forms_layout.is_valid_form_id("CONTROL") is True
    assert forms_layout.is_valid_form_id("form_con") is True


def test_valid_form_id_rejects_too_long():
    """長すぎる様式IDを通さないこと"""
    import forms_layout
    assert forms_layout.is_valid_form_id("a" * 64) is True
    assert forms_layout.is_valid_form_id("a" * 65) is False
    assert forms_layout.is_valid_form_id("a" * 400) is False


def test_axis_position_rejects_invalid_n():
    """0始まりや負の番号は例外にすること（静かにずれるのを防ぐ）"""
    import forms_layout
    field = {"x": 120.0, "y": 660.0, "on_axis": True}
    for bad in (0, -1, "3", None, 2.5, True):
        with pytest.raises((ValueError, TypeError)):
            forms_layout.axis_position(field, AXIS, bad)


def test_axis_count_upper_bound():
    """欄数に上限があること"""
    import forms_layout
    assert forms_layout.axis_count(
        {"period": "month", "axis": {"count": 10 ** 9}}) == forms_layout.MAX_AXIS_COUNT
    assert forms_layout.axis_count({"period": "month", "axis": {"count": 31}}) == 31


def test_list_forms_with_file_path(tmp_path):
    """フォルダでないパスを渡しても落ちず空リストを返すこと"""
    import forms_layout
    f = tmp_path / "notafolder.txt"
    f.write_text("hello", encoding="utf-8")
    assert forms_layout.list_forms(f) == []


def test_form_assignments_deduplicates(tmp_path):
    """targets に同じ機器が2回書かれても様式IDは1回だけ返すこと"""
    import forms_layout
    dup = dict(SAMPLE_LAYOUT)
    dup["targets"] = ["吊具A", "吊具A"]
    _write_layout(tmp_path, "dup", dup)
    assert forms_layout.form_assignments(tmp_path) == {"吊具A": ["dup"]}


def test_save_layout_backs_up_previous(tmp_path):
    """上書き前に世代バックアップを取ること"""
    import forms_layout
    d = tmp_path / "bk"
    d.mkdir()
    first = dict(SAMPLE_LAYOUT)
    first["form_name"] = "1回目"
    forms_layout.save_layout(d, first)
    second = dict(SAMPLE_LAYOUT)
    second["form_name"] = "2回目"
    forms_layout.save_layout(d, second)
    backups = list((d / "backups").glob("layout_*.json"))
    assert len(backups) == 1
    assert "1回目" in backups[0].read_text(encoding="utf-8")
    assert forms_layout.load_layout(d)["form_name"] == "2回目"


def test_save_layout_first_time_makes_no_backup(tmp_path):
    """初回保存ではバックアップを作らないこと"""
    import forms_layout
    d = tmp_path / "first"
    d.mkdir()
    forms_layout.save_layout(d, SAMPLE_LAYOUT)
    assert not (d / "backups").exists() or not list((d / "backups").glob("*.json"))


# ========== 軸の欄へのデータ割り当て ==========

def _march_2026_cycle():
    """2026年3月分のサイクル（2/24〜3/23、28日）の日付を並べて返す"""
    from datetime import date, timedelta
    return [date(2026, 2, 24) + timedelta(days=i) for i in range(28)]


def test_build_slots_month_maps_cycle_dates():
    """month 型で n=1 がサイクル開始日になること"""
    from datetime import date
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    slots = pdf_forms.build_slots(layout, 2026, 3, _march_2026_cycle(), {}, {})
    assert slots[1]["date"] == date(2026, 2, 24)
    assert slots[28]["date"] == date(2026, 3, 23)


def test_build_slots_month_marks_extra_slots():
    """28日サイクルで29〜31番目が「該当日なし」になること"""
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    slots = pdf_forms.build_slots(layout, 2026, 3, _march_2026_cycle(), {}, {})
    assert slots[28]["exists"] is True
    assert slots[29]["exists"] is False
    assert slots[31]["exists"] is False
    assert slots[29]["date"] is None
    assert len(slots) == 31


def test_build_slots_year_maps_months():
    """year 型で n が月に対応すること"""
    import pdf_forms
    layout = {"period": "year", "axis": {"count": 12}}
    slots = pdf_forms.build_slots(layout, 2026, 9, [], {}, {})
    assert slots[1]["month"] == 1
    assert slots[12]["month"] == 12
    assert all(slots[n]["exists"] for n in range(1, 13))
    assert len(slots) == 12


def test_build_slots_single_has_no_slots():
    """single 型は軸が無いので欄も作らないこと"""
    import pdf_forms
    assert pdf_forms.build_slots({"period": "single"}, 2026, 3, [], {}, {}) == {}


def test_build_slots_marks_saturday_sunday_holiday():
    """土曜・日曜・祝日・会社休業日の印がつくこと"""
    from datetime import date
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    # 2026-02-28 は土曜、2026-03-01 は日曜
    custom = {"2026-03-20": "創立記念日"}
    slots = pdf_forms.build_slots(layout, 2026, 3, _march_2026_cycle(), {}, custom)
    by_date = {s["date"]: s for s in slots.values() if s["date"]}
    assert by_date[date(2026, 2, 28)]["mark"] == pdf_forms.MARK_SATURDAY
    assert by_date[date(2026, 3, 1)]["mark"] == pdf_forms.MARK_HOLIDAY
    assert by_date[date(2026, 3, 20)]["mark"] == pdf_forms.MARK_HOLIDAY
    assert by_date[date(2026, 2, 25)]["mark"] == ""


def test_build_slots_saturday_holiday_prefers_holiday():
    """土曜かつ会社休業日の日は holiday（赤）になること"""
    from datetime import date
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    # 2026-02-28（土）を会社休業日に指定する
    slots = pdf_forms.build_slots(layout, 2026, 3, _march_2026_cycle(), {},
                                  {"2026-02-28": "臨時休業"})
    by_date = {s["date"]: s for s in slots.values() if s["date"]}
    assert by_date[date(2026, 2, 28)]["mark"] == pdf_forms.MARK_HOLIDAY


def test_build_slots_national_holiday_detected():
    """jpholiday の祝日が holiday になること（2026-03-20 は春分の日）"""
    from datetime import date
    import jpholiday
    import pdf_forms
    assert jpholiday.is_holiday(date(2026, 3, 20))
    layout = {"period": "month", "axis": {"count": 31}}
    slots = pdf_forms.build_slots(layout, 2026, 3, _march_2026_cycle(), {}, {})
    by_date = {s["date"]: s for s in slots.values() if s["date"]}
    assert by_date[date(2026, 3, 20)]["mark"] == pdf_forms.MARK_HOLIDAY


def test_build_slots_attaches_results_by_date():
    """month 型で日付に対応する結果が欄に入ること"""
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 31}}
    records = {"2026-02-25": {"values": {"吊具A|傷はないか": "○"},
                              "remarks": {"吊具A|傷はないか": "軽微"},
                              "meta": {"inspector": "山田 太郎"}}}
    slots = pdf_forms.build_slots(layout, 2026, 3, _march_2026_cycle(), records, {})
    assert slots[2]["values"]["吊具A|傷はないか"] == "○"
    assert slots[2]["remarks"]["吊具A|傷はないか"] == "軽微"
    assert slots[2]["meta"]["inspector"] == "山田 太郎"
    # 記録の無い日は空のまま
    assert slots[3]["values"] == {}


def test_build_slots_attaches_results_by_month():
    """year 型で月に対応する結果が欄に入ること"""
    import pdf_forms
    layout = {"period": "year", "axis": {"count": 12}}
    records = {5: {"values": {"吊具A|傷はないか": "×"}, "remarks": {},
                   "meta": {"inspector": "鈴木 花子"}}}
    slots = pdf_forms.build_slots(layout, 2026, 9, [], records, {})
    assert slots[5]["values"]["吊具A|傷はないか"] == "×"
    assert slots[5]["meta"]["inspector"] == "鈴木 花子"
    assert slots[6]["values"] == {}


def test_build_slots_respects_axis_count():
    """欄数より多い日数があっても欄数までしか作らないこと"""
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 10}}
    slots = pdf_forms.build_slots(layout, 2026, 3, _march_2026_cycle(), {}, {})
    assert len(slots) == 10
    assert 11 not in slots


# ========== 結果ファイルの変換 ==========

# 吊具A（2回保存）と 吊具B（1回）が同じ日に点検されている想定。
# equipment_name には大分類が入る点に注意（機器は category_minor）。
INDEX_RECORDS = [
    {
        "inspection_date": "2026-02-25",
        "inspection_type": "使用前",
        "category_major": "吊具",
        "category_minor": "吊具A",
        "inspector_name": "山田 太郎",
        "department": "施設管理部",
        "general_remark": "特になし",
        "building_name": "仮ビル 本館",
        "results": [
            {"equipment_name": "吊具", "inspection_item": "傷はないか",
             "result": "○", "remark": ""},
            {"equipment_name": "吊具", "inspection_item": "油圧",
             "result": "0.52", "remark": "やや低い"},
        ],
        "submitted_at": "2026-02-25T09:00:00",
    },
    {
        "inspection_date": "2026-02-25",
        "inspection_type": "使用前",
        "category_major": "吊具",
        "category_minor": "吊具A",
        "inspector_name": "鈴木 花子",
        "department": "設備管理課",
        "general_remark": "",
        "building_name": "仮ビル 本館",
        "results": [
            {"equipment_name": "吊具", "inspection_item": "傷はないか",
             "result": "×", "remark": "要交換"},
        ],
        "submitted_at": "2026-02-25T15:00:00",
    },
    {
        "inspection_date": "2026-02-25",
        "inspection_type": "使用前",
        "category_major": "吊具",
        "category_minor": "吊具B",
        "inspector_name": "田中 一郎",
        "department": "営繕課",
        "general_remark": "",
        "building_name": "仮ビル 本館",
        "results": [
            {"equipment_name": "吊具", "inspection_item": "傷はないか",
             "result": "○", "remark": ""},
        ],
        "submitted_at": "2026-02-25T10:00:00",
    },
]


def test_index_by_date_uses_category_minor_as_equipment():
    """キーが category_minor（機器）で作られること。equipment_name は大分類なので使わない"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(INDEX_RECORDS, ["吊具A"])
    values = indexed["2026-02-25"]["values"]
    assert "吊具A|油圧" in values
    assert "吊具|油圧" not in values


def test_index_by_date_merges_multiple_equipment():
    """1枚に複数機器が載る様式で、同じ日の機器ごとの記録が統合されること"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(INDEX_RECORDS, ["吊具A", "吊具B"])
    values = indexed["2026-02-25"]["values"]
    assert values["吊具B|傷はないか"] == "○"
    assert values["吊具A|油圧"] == "0.52"


def test_index_by_date_latest_wins_for_same_item():
    """同じ機器・同じ項目は submitted_at が新しい記録が勝つこと"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(INDEX_RECORDS, ["吊具A"])
    values = indexed["2026-02-25"]["values"]
    # 09:00 の ○ ではなく 15:00 の × が残る
    assert values["吊具A|傷はないか"] == "×"
    # 15:00 の記録に無い項目は 09:00 の値が残る
    assert values["吊具A|油圧"] == "0.52"


def test_index_by_date_meta_from_latest():
    """meta は最も新しい記録のものを使うこと"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(INDEX_RECORDS, ["吊具A", "吊具B"])
    assert indexed["2026-02-25"]["meta"]["inspector"] == "鈴木 花子"


def test_index_by_date_keeps_remarks():
    """備考も取り出せること"""
    import pdf_forms
    indexed = pdf_forms.index_by_date(INDEX_RECORDS, ["吊具A"])
    remarks = indexed["2026-02-25"]["remarks"]
    assert remarks["吊具A|傷はないか"] == "要交換"
    assert remarks["吊具A|油圧"] == "やや低い"


def test_index_by_date_filters_by_target():
    """targets に無い機器の記録は無視すること"""
    import pdf_forms
    assert pdf_forms.index_by_date(INDEX_RECORDS, ["吊具C"]) == {}
    assert pdf_forms.index_by_date(INDEX_RECORDS, []) == {}


def test_index_by_date_meta_fields():
    """meta に必要な項目が揃っていること"""
    import pdf_forms
    meta = pdf_forms.index_by_date(INDEX_RECORDS, ["吊具B"])["2026-02-25"]["meta"]
    assert meta["inspection_date"] == "2026-02-25"
    assert meta["inspector"] == "田中 一郎"
    assert meta["department"] == "営繕課"
    assert meta["building_name"] == "仮ビル 本館"
    assert "general_remark" in meta


def test_index_by_month_groups_by_month():
    """year 型用に月ごとにまとめられること"""
    import pdf_forms
    indexed = pdf_forms.index_by_month(INDEX_RECORDS, ["吊具A"])
    assert 2 in indexed
    assert indexed[2]["values"]["吊具A|傷はないか"] == "×"


def test_index_by_month_separates_months():
    """別の月の記録が混ざらないこと"""
    import pdf_forms
    extra = dict(INDEX_RECORDS[0])
    extra["inspection_date"] = "2026-05-10"
    extra["submitted_at"] = "2026-05-10T09:00:00"
    indexed = pdf_forms.index_by_month(INDEX_RECORDS + [extra], ["吊具A"])
    assert sorted(indexed.keys()) == [2, 5]


def test_index_by_month_ignores_bad_date():
    """日付が壊れた記録は飛ばして落ちないこと"""
    import pdf_forms
    broken = dict(INDEX_RECORDS[0])
    broken["inspection_date"] = "こわれた"
    indexed = pdf_forms.index_by_month([broken], ["吊具A"])
    assert indexed == {}


def test_index_handles_empty_records():
    """記録が無くても空の辞書を返すこと"""
    import pdf_forms
    assert pdf_forms.index_by_date([], ["吊具A"]) == {}
    assert pdf_forms.index_by_month([], ["吊具A"]) == {}


def test_index_survives_malformed_record():
    """results が無い・型がおかしい記録でも落ちないこと"""
    import pdf_forms
    bad = [
        {"inspection_date": "2026-02-25", "category_minor": "吊具A"},
        {"inspection_date": "2026-02-25", "category_minor": "吊具A",
         "results": "こわれてる"},
        {"inspection_date": "2026-02-25", "category_minor": "吊具A",
         "results": [123, "abc", None]},
    ]
    indexed = pdf_forms.index_by_date(bad, ["吊具A"])
    assert indexed["2026-02-25"]["values"] == {}


# ========== 様式PDFへの重ね書き ==========

def _make_form_pdf(path, pages=1, pagesize=None):
    """テスト用の白紙PDFを作る"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    c = canvas.Canvas(str(path), pagesize=pagesize or A4)
    for _ in range(pages):
        c.showPage()
    c.save()
    return path


def _read_text(path, page=0):
    """PDFの指定ページからテキストを取り出す"""
    from pypdf import PdfReader
    return PdfReader(str(path)).pages[page].extract_text()


def _write_out(writer, path):
    """PdfWriter をファイルに書き出す"""
    with open(path, "wb") as f:
        writer.write(f)
    return path


SINGLE_SLOT = {"date": None, "month": None, "exists": True, "mark": "",
               "values": {"吊具A|傷はないか": "○", "吊具A|油圧": "0.52"},
               "remarks": {"吊具A|傷はないか": "軽微"},
               "meta": {"inspector": "ヤマダ", "inspection_date": "2026-03-02",
                        "department": "シセツ", "building_name": "ホンカン",
                        "general_remark": "トクニナシ"}}


def test_build_form_pdf_keeps_page_count(tmp_path):
    """重ね書きしてもページ数が変わらないこと"""
    from pypdf import PdfReader
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf", pages=2)
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "meta.inspector", "page": 0, "x": 100, "y": 700},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert len(PdfReader(str(out)).pages) == 2


def test_build_form_pdf_writes_meta(tmp_path):
    """meta の値がPDFに入っていること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "meta.inspector", "page": 0, "x": 100, "y": 700},
        {"source": "meta.building_name", "page": 0, "x": 100, "y": 680},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    text = _read_text(out)
    assert "ヤマダ" in text
    assert "ホンカン" in text


def test_build_form_pdf_writes_item_result(tmp_path):
    """点検結果（判定・数値）がPDFに入っていること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "item:吊具A|傷はないか", "page": 0, "x": 100, "y": 700},
        {"source": "item:吊具A|油圧", "page": 0, "x": 100, "y": 680},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    text = _read_text(out)
    # 保存されている「○」は旧仕様の「良」。今の記号（✓）で印字される
    assert "✓" in text
    assert "0.52" in text


def test_build_form_pdf_writes_remark(tmp_path):
    """備考がPDFに入っていること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "remark:吊具A|傷はないか", "page": 0, "x": 100, "y": 700},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert "軽微" in _read_text(out)


def test_build_form_pdf_writes_year_and_month(tmp_path):
    """タイトルの年・月がPDFに入っていること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    layout = {"period": "single", "targets": [], "fields": [
        {"source": "meta.month", "page": 0, "x": 100, "y": 780},
        {"source": "meta.year", "page": 0, "x": 200, "y": 780},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 8}),
        tmp_path / "out.pdf")
    text = _read_text(out)
    assert "8" in text
    assert "2026" in text


def test_build_form_pdf_applies_mark_overrides(tmp_path):
    """mark_ok で ✓ の代わりの文字を印字できること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "item:吊具A|傷はないか", "page": 0, "x": 100, "y": 700,
         "mark_ok": "V"},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    text = _read_text(out)
    assert "V" in text
    assert "✓" not in text


def test_build_form_pdf_skips_out_of_range_page(tmp_path):
    """様式のページ数を超える page 指定は落ちずに飛ばすこと"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf", pages=1)
    layout = {"period": "single", "targets": [], "fields": [
        {"source": "meta.inspector", "page": 5, "x": 100, "y": 700},
    ]}
    writer = pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3})
    assert len(writer.pages) == 1


def test_build_form_pdf_places_on_correct_page(tmp_path):
    """page 指定どおりのページに印字されること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf", pages=2)
    layout = {"period": "single", "targets": [], "fields": [
        {"source": "meta.inspector", "page": 1, "x": 100, "y": 700},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert "ヤマダ" not in (_read_text(out, 0) or "")
    assert "ヤマダ" in _read_text(out, 1)


def test_build_form_pdf_on_axis_repeats(tmp_path):
    """on_axis のフィールドが欄の数だけ繰り返されること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slots = {n: {"date": None, "month": n, "exists": True, "mark": "",
                 "values": {"吊具A|傷はないか": str(n)}, "remarks": {}, "meta": {}}
             for n in range(1, 4)}
    layout = {"period": "year", "targets": ["吊具A"],
              "axis": {"step_x": 40.0, "step_y": 0.0, "count": 3},
              "fields": [{"source": "item:吊具A|傷はないか", "page": 0,
                          "x": 100, "y": 700, "on_axis": True}]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, slots, {"year": 2026, "month": 3}), tmp_path / "out.pdf")
    text = _read_text(out)
    for expected in ("1", "2", "3"):
        assert expected in text


def test_build_form_pdf_extra_slot_prints_dash(tmp_path):
    """余りマス（その月に存在しない日）の項目に「ー」が入ること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slots = {
        1: {"date": None, "month": 1, "exists": True, "mark": "",
            "values": {"吊具A|傷はないか": "○"}, "remarks": {}, "meta": {}},
        2: {"date": None, "month": None, "exists": False, "mark": "",
            "values": {}, "remarks": {}, "meta": {}},
    }
    layout = {"period": "month", "targets": ["吊具A"],
              "axis": {"step_x": 40.0, "step_y": 0.0, "count": 2},
              "fields": [{"source": "item:吊具A|傷はないか", "page": 0,
                          "x": 100, "y": 700, "on_axis": True}]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, slots, {"year": 2026, "month": 3}), tmp_path / "out.pdf")
    text = _read_text(out)
    assert "✓" in text
    assert "ー" in text


def test_build_form_pdf_extra_slot_remark_stays_empty(tmp_path):
    """余りマスの備考には何も印字しないこと"""
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


def test_build_form_pdf_does_not_modify_source(tmp_path):
    """様式PDFそのものは書き換えないこと"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    before = form.read_bytes()
    layout = {"period": "single", "targets": [], "fields": [
        {"source": "meta.inspector", "page": 0, "x": 100, "y": 700},
    ]}
    _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert form.read_bytes() == before


def test_build_form_pdf_unknown_source_is_skipped(tmp_path):
    """知らない source は落ちずに飛ばすこと"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    layout = {"period": "single", "targets": [], "fields": [
        {"source": "なぞの指定", "page": 0, "x": 100, "y": 700},
        {"source": "meta.inspector", "page": 0, "x": 100, "y": 680},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert "ヤマダ" in _read_text(out)


def test_build_form_pdf_missing_value_prints_nothing(tmp_path):
    """記録の無い項目には何も印字しないこと（空欄のまま）"""
    import pdf_forms
    calls = []

    class FakeCanvas:
        def setFont(self, *a): pass
        def setFillColor(self, *a): pass
        def drawString(self, x, y, text): calls.append(text)

    field = {"source": "item:吊具A|存在しない項目", "x": 50, "y": 700}
    pdf_forms._draw_slot_field(FakeCanvas(), field, 50, 700, SINGLE_SLOT, {}, 11)
    assert calls == []


def test_build_form_pdf_a4_landscape(tmp_path):
    """A4横向きの様式でもページサイズが保たれること"""
    from reportlab.lib.pagesizes import A4, landscape
    from pypdf import PdfReader
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf", pagesize=landscape(A4))
    layout = {"period": "single", "targets": [], "fields": [
        {"source": "meta.inspector", "page": 0, "x": 100, "y": 500},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    page = PdfReader(str(out)).pages[0]
    assert float(page.mediabox.width) > float(page.mediabox.height)
    assert "ヤマダ" in _read_text(out)


# ========== 日にちと休日の丸 ==========

def _day_slots(marks):
    """marks（"" / "saturday" / "holiday" のリスト）から欄データを作る。

    1番目から順に 24日、25日…と割り当てる。marks が None の欄は余りマス。
    """
    from datetime import date, timedelta
    slots = {}
    for i, mark in enumerate(marks):
        n = i + 1
        if mark is None:
            slots[n] = {"date": None, "month": None, "exists": False, "mark": "",
                        "values": {}, "remarks": {}, "meta": {}}
            continue
        slots[n] = {"date": date(2026, 2, 24) + timedelta(days=i), "month": None,
                    "exists": True, "mark": mark,
                    "values": {}, "remarks": {}, "meta": {}}
    return slots


DAY_LAYOUT = {
    "period": "month", "targets": [],
    "axis": {"step_x": 20.0, "step_y": 0.0, "count": 5},
    "fields": [{"source": "meta.day", "page": 0, "x": 100, "y": 700,
                "on_axis": True}],
}


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
    assert pdf_forms._circle_radius({"circle_radius": None}, 10) == 9.0


def test_day_numbers_span_two_months(tmp_path):
    """日にちが 24, 25, 26… と印字されること"""
    import pdf_forms
    slots = _day_slots(["", "", "", "", ""])
    form = _make_form_pdf(tmp_path / "form.pdf")
    out = _write_out(pdf_forms.build_form_pdf(
        form, DAY_LAYOUT, slots, {"year": 2026, "month": 3}), tmp_path / "out.pdf")
    text = _read_text(out)
    for expected in ("24", "25", "26", "27", "28"):
        assert expected in text, f"{expected} が印字されていない"


def test_day_numbers_cross_month_boundary(tmp_path):
    """月をまたいで 31 の次が 1 になること"""
    from datetime import date
    import pdf_forms
    # 2026-02-28, 03-01, 03-02 の3日分
    slots = {
        1: {"date": date(2026, 2, 28), "month": None, "exists": True,
            "mark": "", "values": {}, "remarks": {}, "meta": {}},
        2: {"date": date(2026, 3, 1), "month": None, "exists": True,
            "mark": "", "values": {}, "remarks": {}, "meta": {}},
        3: {"date": date(2026, 3, 2), "month": None, "exists": True,
            "mark": "", "values": {}, "remarks": {}, "meta": {}},
    }
    layout = dict(DAY_LAYOUT)
    layout["axis"] = {"step_x": 30.0, "step_y": 0.0, "count": 3}
    form = _make_form_pdf(tmp_path / "form.pdf")
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, slots, {"year": 2026, "month": 3}), tmp_path / "out.pdf")
    text = _read_text(out)
    assert "28" in text and "1" in text and "2" in text


def test_extra_slot_has_no_day(tmp_path):
    """余りマスには日にちを印字しないこと"""
    import pdf_forms
    drawn = []

    class FakeCanvas:
        def setFont(self, *a): pass
        def setFillColor(self, *a): pass
        def setStrokeColor(self, *a): pass
        def setLineWidth(self, *a): pass
        def drawCentredString(self, x, y, text): drawn.append(text)
        def drawString(self, x, y, text): drawn.append(text)
        def circle(self, *a, **kw): drawn.append("CIRCLE")

    field = {"source": "meta.day", "x": 100, "y": 700, "on_axis": True}
    slot = {"date": None, "month": None, "exists": False, "mark": "",
            "values": {}, "remarks": {}, "meta": {}}
    pdf_forms._draw_slot_field(FakeCanvas(), field, 100, 700, slot, {}, 11)
    assert drawn == []


def _capture_day_draw(mark, field=None):
    """1欄分の meta.day を描いたときの呼び出しを記録する"""
    from datetime import date
    import pdf_forms
    calls = []

    class FakeCanvas:
        def setFont(self, name, size): calls.append(("font", size))
        def setFillColor(self, color): calls.append(("fill", str(color)))
        def setStrokeColor(self, color): calls.append(("stroke", str(color)))
        def setLineWidth(self, w): calls.append(("width", w))
        def drawCentredString(self, x, y, text): calls.append(("text", text))
        def circle(self, x, y, r, **kw): calls.append(("circle", r))

    slot = {"date": date(2026, 2, 28), "month": None, "exists": True,
            "mark": mark, "values": {}, "remarks": {}, "meta": {}}
    f = field or {"source": "meta.day", "x": 100, "y": 700, "on_axis": True}
    pdf_forms._draw_slot_field(FakeCanvas(), f, 100, 700, slot, {}, 11)
    return calls


def test_weekday_has_no_circle():
    """平日は丸を描かないこと"""
    calls = _capture_day_draw("")
    assert ("text", "28") in calls
    assert not any(c[0] == "circle" for c in calls)


def test_saturday_draws_blue_circle():
    """土曜は青い丸を描くこと"""
    import pdf_forms
    calls = _capture_day_draw(pdf_forms.MARK_SATURDAY)
    assert ("text", "28") in calls
    assert any(c[0] == "circle" for c in calls)
    assert any(c[0] == "stroke" and "0000ff" in c[1].lower().replace("#", "")
               or c[0] == "stroke" and c[1] == pdf_forms.COLOR_SATURDAY
               for c in calls)


def test_holiday_draws_red_circle():
    """日曜・祝日・会社休業日は赤い丸を描くこと"""
    import pdf_forms
    calls = _capture_day_draw(pdf_forms.MARK_HOLIDAY)
    assert ("text", "28") in calls
    assert any(c[0] == "circle" for c in calls)


def test_circle_radius_used():
    """circle_radius の指定が丸の半径に使われること"""
    import pdf_forms
    field = {"source": "meta.day", "x": 100, "y": 700, "on_axis": True,
             "circle_radius": 15.0}
    calls = _capture_day_draw(pdf_forms.MARK_HOLIDAY, field)
    assert ("circle", 15.0) in calls


def test_day_uses_centred_string():
    """日にちは中央揃えで描くこと（丸の中心に合わせるため）"""
    calls = _capture_day_draw("")
    assert any(c[0] == "text" for c in calls)


def test_other_fields_still_left_aligned():
    """meta.day 以外は従来どおり左下基準で描くこと"""
    import pdf_forms
    calls = []

    class FakeCanvas:
        def setFont(self, *a): pass
        def setFillColor(self, *a): pass
        def drawString(self, x, y, text): calls.append(("left", text))
        def drawCentredString(self, x, y, text): calls.append(("center", text))

    slot = {"date": None, "month": None, "exists": True, "mark": "",
            "values": {"吊具A|傷はないか": "○"}, "remarks": {}, "meta": {}}
    field = {"source": "item:吊具A|傷はないか", "x": 100, "y": 700}
    pdf_forms._draw_slot_field(FakeCanvas(), field, 100, 700, slot, {}, 11)
    assert calls == [("left", "✓")]


def test_build_form_pdf_no_pypdf_deprecation_warning(tmp_path, recwarn):
    """pypdf の非推奨APIを使っていないこと"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slots = _day_slots(["", "saturday", "holiday", "", None])
    pdf_forms.build_form_pdf(form, DAY_LAYOUT, slots, {"year": 2026, "month": 3})
    messages = [str(w.message) for w in recwarn
                if issubclass(w.category, DeprecationWarning)]
    pypdf_warnings = [m for m in messages if "replace_contents" in m]
    assert pypdf_warnings == [], f"pypdf の非推奨警告が残っている: {pypdf_warnings}"


# ========== PDF出力の統合 ==========

MONTH_LAYOUT = {
    "form_name": "吊具日常点検表",
    "period": "month",
    "inspection_type": "使用前",
    "targets": ["A-1"],
    "axis": {"step_x": 15.0, "step_y": 0.0, "count": 31},
    "fields": [
        {"source": "meta.day", "page": 0, "x": 50, "y": 700, "on_axis": True},
        {"source": "item:A-1|傷はないか", "page": 0, "x": 50, "y": 660,
         "on_axis": True},
    ],
}


def _setup_forms_dir(tmp_path, monkeypatch, layout, form_id="tsurigu",
                     with_pdf=True):
    """様式フォルダを1つ用意して設定に反映する"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    form_dir = forms_dir / form_id
    form_dir.mkdir(parents=True, exist_ok=True)
    (form_dir / "layout.json").write_text(
        json.dumps(layout, ensure_ascii=False), encoding="utf-8")
    if with_pdf:
        _make_form_pdf(form_dir / "form.pdf")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    return forms_dir


def _empty_forms_dir(tmp_path, monkeypatch):
    """様式が1つも無い状態にする"""
    import app as flask_app
    empty = tmp_path / "no_forms"
    empty.mkdir(exist_ok=True)
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: empty)
    return empty


def test_get_forms_directory_defaults_to_app_folder(client):
    """forms_directory が空欄ならアプリ内の forms を使うこと"""
    import app as flask_app
    assert flask_app.get_forms_directory().name == "forms"


def test_default_config_has_forms_directory():
    """既定設定に forms_directory があること"""
    import app as flask_app
    assert flask_app._default_config()["forms_directory"] == ""


def test_api_post_config_forms_directory(client):
    """forms_directory を保存できること"""
    c, _ = client
    res = c.post("/api/config",
                 data=json.dumps({"forms_directory": "\\\\server\\forms"}),
                 content_type="application/json")
    assert res.status_code == 200
    assert c.get("/api/config").get_json()["forms_directory"] == "\\\\server\\forms"


def test_api_post_config_forms_directory_type_check(client):
    """forms_directory が文字列でなければ400になること"""
    c, _ = client
    res = c.post("/api/config", data=json.dumps({"forms_directory": 123}),
                 content_type="application/json")
    assert res.status_code == 400


def test_api_pdf_unchanged_without_forms(client, monkeypatch, tmp_path):
    """様式が1つも無ければ出力がこれまでどおりであること（絶対条件）"""
    from pypdf import PdfReader
    import io as _io
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert res.data[:5] == b"%PDF-"
    assert "X-Form-Fallback" not in res.headers
    assert len(PdfReader(_io.BytesIO(res.data)).pages) >= 1


def test_api_pdf_includes_form_pages(client, monkeypatch, tmp_path):
    """様式に紐づく機器があるとページ数が表だけのときより増えること"""
    from pypdf import PdfReader
    import io as _io
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    baseline = c.get("/api/pdf?display_year=2026&display_month=3")
    base_pages = len(PdfReader(_io.BytesIO(baseline.data)).pages)
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert len(PdfReader(_io.BytesIO(res.data)).pages) == base_pages + 1


def test_api_pdf_form_pages_come_first(client, monkeypatch, tmp_path):
    """様式のページが表のページより前に来ること（1枚目は特記事項）"""
    from pypdf import PdfReader
    import io as _io
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    first = PdfReader(_io.BytesIO(res.data)).pages[1].extract_text() or ""
    # 様式は白紙に日にちだけ印字されるので「24」が入る。表には見出しが入る。
    assert "24" in first


def test_api_pdf_falls_back_when_form_pdf_missing(client, monkeypatch, tmp_path):
    """様式PDFが無いときは表出力に落ちてヘッダーで知らせること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT, with_pdf=False)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert res.data[:5] == b"%PDF-"
    assert "tsurigu" in res.headers.get("X-Form-Fallback", "")


def test_api_pdf_falls_back_when_layout_broken(client, monkeypatch, tmp_path):
    """layout.json が壊れているときも落ちずに表出力になること"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    form_dir = forms_dir / "broken"
    form_dir.mkdir(parents=True)
    (form_dir / "layout.json").write_text("{ oops", encoding="utf-8")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert "broken" in res.headers.get("X-Form-Fallback", "")


def test_api_pdf_year_form(client, monkeypatch, tmp_path):
    """year 型の様式でも出力できること"""
    from pypdf import PdfReader
    import io as _io
    year_layout = dict(MONTH_LAYOUT)
    year_layout["period"] = "year"
    year_layout["inspection_type"] = "月例"
    year_layout["axis"] = {"step_x": 40.0, "step_y": 0.0, "count": 12}
    year_layout["fields"] = [
        {"source": "meta.year", "page": 0, "x": 60, "y": 780},
        {"source": "item:A-1|傷はないか", "page": 0, "x": 60, "y": 700,
         "on_axis": True},
    ]
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, year_layout)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert "2026" in (PdfReader(_io.BytesIO(res.data)).pages[0].extract_text() or "")


def test_api_pdf_single_form_no_records(client, monkeypatch, tmp_path):
    """single 型で点検日が1日も無ければその様式は出力しないこと"""
    from pypdf import PdfReader
    import io as _io
    single = dict(MONTH_LAYOUT)
    single["period"] = "single"
    single.pop("axis", None)
    single["fields"] = [{"source": "meta.inspector", "page": 0, "x": 60, "y": 700}]
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    base = len(PdfReader(_io.BytesIO(
        c.get("/api/pdf?display_year=2026&display_month=3").data)).pages)
    _setup_forms_dir(tmp_path, monkeypatch, single)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert len(PdfReader(_io.BytesIO(res.data)).pages) == base


def test_api_pdf_single_form_one_page_per_day(client, monkeypatch, tmp_path):
    """single 型は点検日ごとに1枚ずつ出ること"""
    from pypdf import PdfReader
    import io as _io
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    single = dict(MONTH_LAYOUT)
    single["period"] = "single"
    single.pop("axis", None)
    single["fields"] = [{"source": "meta.inspector", "page": 0, "x": 60, "y": 700}]
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    base = len(PdfReader(_io.BytesIO(
        c.get("/api/pdf?display_year=2026&display_month=3").data)).pages)
    # サイクル内の2日分を保存する（2026年3月分は 2/24〜3/23）
    for day in ("2026-02-25", "2026-03-02"):
        c.post("/api/results", data=json.dumps({
            "inspection_type": "使用前", "inspection_date": day,
            "category_major": "設備A", "category_minor": "A-1",
            "inspector_name": "テスト", "department": "テスト部",
            "results": [{"equipment_name": "設備A", "inspection_item": "傷はないか",
                         "result": "○", "remark": ""}],
        }), content_type="application/json")
    _setup_forms_dir(tmp_path, monkeypatch, single)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert len(PdfReader(_io.BytesIO(res.data)).pages) == base + 2


def test_api_pdf_single_form_skips_outside_cycle(client, monkeypatch, tmp_path):
    """single 型はサイクル外の日の記録を出さないこと（2026年3月分は 2/24〜3/23）。
    前月のファイルを丸ごと読むため、絞らないと前月の点検日まで1枚ずつ出てしまう。"""
    from pypdf import PdfReader
    import io as _io
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    single = dict(MONTH_LAYOUT)
    single["period"] = "single"
    single.pop("axis", None)
    single["fields"] = [{"source": "meta.inspector", "page": 0, "x": 60, "y": 700}]
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    base = len(PdfReader(_io.BytesIO(
        c.get("/api/pdf?display_year=2026&display_month=3").data)).pages)
    for day in ("2026-02-10", "2026-03-02", "2026-03-25"):
        c.post("/api/results", data=json.dumps({
            "inspection_type": "使用前", "inspection_date": day,
            "category_major": "設備A", "category_minor": "A-1",
            "inspector_name": "テスト", "department": "テスト部",
            "results": [{"equipment_name": "設備A", "inspection_item": "傷はないか",
                         "result": "✓", "remark": ""}],
        }), content_type="application/json")
    _setup_forms_dir(tmp_path, monkeypatch, single)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert len(PdfReader(_io.BytesIO(res.data)).pages) == base + 1


def test_api_pdf_prints_saved_result(client, monkeypatch, tmp_path):
    """保存した点検結果が様式に印字されること（1枚目は特記事項）"""
    from pypdf import PdfReader
    import io as _io
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    c.post("/api/results", data=json.dumps({
        "inspection_type": "使用前", "inspection_date": "2026-02-25",
        "category_major": "設備A", "category_minor": "A-1",
        "inspector_name": "テスト", "department": "テスト部",
        "results": [{"equipment_name": "設備A", "inspection_item": "傷はないか",
                     "result": "○", "remark": ""}],
    }), content_type="application/json")
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert "✓" in (PdfReader(_io.BytesIO(res.data)).pages[1].extract_text() or "")


def test_api_pdf_still_locks(client, monkeypatch, tmp_path):
    """排他制御が効いていること（同時実行で503が返る）

    threading.Lock はCの組み込み型でインスタンス属性の差し替えができない
    （acquire を monkeypatch しようとすると AttributeError になる）ため、
    ロックオブジェクトそのものをフェイクに差し替えて検証する。
    """
    import app as flask_app
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)

    class _AlwaysBusyLock:
        def acquire(self, timeout=None):
            return False

        def release(self):
            pass

    monkeypatch.setattr(flask_app, "_pdf_lock", _AlwaysBusyLock())
    assert c.get("/api/pdf?display_year=2026&display_month=3").status_code == 503


# ========== 様式API ==========

def test_api_forms_lists(client, monkeypatch, tmp_path):
    """様式一覧が取得できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]["id"] == "tsurigu"
    assert data[0]["form_name"] == "吊具日常点検表"
    assert data[0]["has_pdf"] is True
    assert data[0]["error"] == ""


def test_api_forms_empty(client, monkeypatch, tmp_path):
    """様式が無ければ空の配列を返すこと"""
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    assert c.get("/api/forms").get_json() == []


def test_api_forms_reports_broken(client, monkeypatch, tmp_path):
    """壊れた様式も error 付きで一覧に出ること"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    (forms_dir / "broken").mkdir(parents=True)
    (forms_dir / "broken" / "layout.json").write_text("{ oops", encoding="utf-8")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    data = c.get("/api/forms").get_json()
    assert data[0]["error"] != ""


def test_api_form_assignments(client, monkeypatch, tmp_path):
    """機器と様式の紐づけ一覧が取得できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/assignments")
    assert res.status_code == 200
    assert res.get_json()["A-1"] == ["tsurigu"]


def test_api_form_layout_get(client, monkeypatch, tmp_path):
    """layout.json の中身が取得できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/layout")
    assert res.status_code == 200
    body = res.get_json()
    assert body["period"] == "month"
    assert body["targets"] == ["A-1"]


def test_api_form_layout_get_not_found(client, monkeypatch, tmp_path):
    """存在しない様式は404になること"""
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    assert c.get("/api/forms/nothing/layout").status_code == 404


def test_api_form_layout_get_broken(client, monkeypatch, tmp_path):
    """壊れた layout.json は400になること"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    (forms_dir / "broken").mkdir(parents=True)
    (forms_dir / "broken" / "layout.json").write_text("{ oops", encoding="utf-8")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    assert c.get("/api/forms/broken/layout").status_code == 400


def test_api_form_layout_rejects_traversal(client, monkeypatch, tmp_path):
    """様式IDに危険な文字があると404になること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    for bad in ("..%2Fetc", "%2e%2e", "NUL", "con", "a%20b"):
        res = c.get(f"/api/forms/{bad}/layout")
        assert res.status_code == 404, f"{bad} が404にならない: {res.status_code}"


def test_api_form_layout_post(client, monkeypatch, tmp_path):
    """layout.json を保存できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    changed = json.loads(json.dumps(MONTH_LAYOUT))
    changed["form_name"] = "変更後"
    res = c.post("/api/forms/tsurigu/layout",
                 data=json.dumps(changed), content_type="application/json")
    assert res.status_code == 200
    assert c.get("/api/forms/tsurigu/layout").get_json()["form_name"] == "変更後"


def test_api_form_layout_post_invalid(client, monkeypatch, tmp_path):
    """period が不正な layout は400になり、元の内容が壊れないこと"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    bad = json.loads(json.dumps(MONTH_LAYOUT))
    bad["period"] = "weekly"
    res = c.post("/api/forms/tsurigu/layout",
                 data=json.dumps(bad), content_type="application/json")
    assert res.status_code == 400
    assert c.get("/api/forms/tsurigu/layout").get_json()["period"] == "month"


def test_api_form_layout_post_empty_body(client, monkeypatch, tmp_path):
    """空のリクエストは400になること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.post("/api/forms/tsurigu/layout", data="{}",
                 content_type="application/json")
    assert res.status_code == 400


def test_api_form_layout_post_not_found(client, monkeypatch, tmp_path):
    """存在しない様式への保存は404になること"""
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    res = c.post("/api/forms/nothing/layout",
                 data=json.dumps(MONTH_LAYOUT), content_type="application/json")
    assert res.status_code == 404


def test_api_form_pdf(client, monkeypatch, tmp_path):
    """様式PDF本体を取得できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/pdf")
    assert res.status_code == 200
    assert res.data[:5] == b"%PDF-"


def test_api_form_pdf_missing(client, monkeypatch, tmp_path):
    """様式PDFが無ければ404になること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT, with_pdf=False)
    assert c.get("/api/forms/tsurigu/pdf").status_code == 404


def test_api_form_pdf_rejects_traversal(client, monkeypatch, tmp_path):
    """様式PDFの取得でもパストラバーサルを弾くこと"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    assert c.get("/api/forms/..%2Fetc/pdf").status_code == 404
    assert c.get("/api/forms/NUL/pdf").status_code == 404


def test_api_form_layout_post_requires_admin(client, monkeypatch, tmp_path):
    """別PCからの保存は管理者キーが必要なこと"""
    import app as flask_app
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.post("/api/forms/tsurigu/layout",
                 data=json.dumps(MONTH_LAYOUT),
                 content_type="application/json",
                 environ_base={"REMOTE_ADDR": "192.168.1.50"})
    assert res.status_code == 401


# ========== 0ページの様式PDF（実機確認で見つかった不具合） ==========

def _make_empty_pdf(path):
    """ページを1枚も持たないPDFを作る（showPage を呼ばない）"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    c = canvas.Canvas(str(path), pagesize=A4)
    c.save()
    return path


def test_make_empty_pdf_really_has_no_pages(tmp_path):
    """前提確認: showPage を呼ばないと0ページのPDFになること"""
    from pypdf import PdfReader
    p = _make_empty_pdf(tmp_path / "empty.pdf")
    assert len(PdfReader(str(p)).pages) == 0


def test_build_form_pdf_rejects_empty_pdf(tmp_path):
    """0ページの様式PDFは例外にすること"""
    import pdf_forms
    form = _make_empty_pdf(tmp_path / "form.pdf")
    layout = {"period": "single", "targets": [], "fields": [
        {"source": "meta.inspector", "page": 0, "x": 100, "y": 700},
    ]}
    with pytest.raises(ValueError):
        pdf_forms.build_form_pdf(form, layout, {1: SINGLE_SLOT},
                                 {"year": 2026, "month": 3})


def test_api_pdf_falls_back_when_form_pdf_has_no_pages(client, monkeypatch, tmp_path):
    """0ページの様式PDFは表出力に落ちてヘッダーで知らせること"""
    from pypdf import PdfReader
    import io as _io
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    baseline = c.get("/api/pdf?display_year=2026&display_month=3")
    base_pages = len(PdfReader(_io.BytesIO(baseline.data)).pages)

    forms_dir = _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT,
                                 with_pdf=False)
    _make_empty_pdf(forms_dir / "tsurigu" / "form.pdf")
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert "tsurigu" in res.headers.get("X-Form-Fallback", ""), \
        "0ページの様式が黙って無視されている"
    assert len(PdfReader(_io.BytesIO(res.data)).pages) == base_pages


def test_api_pdf_single_with_no_records_is_not_a_fallback(client, monkeypatch,
                                                          tmp_path):
    """single 型で点検日が0日なのは正常。フォールバック扱いにしないこと"""
    c, _ = client
    single = json.loads(json.dumps(MONTH_LAYOUT))
    single["period"] = "single"
    single.pop("axis", None)
    single["fields"] = [{"source": "meta.inspector", "page": 0, "x": 60, "y": 700}]
    _setup_forms_dir(tmp_path, monkeypatch, single)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert "X-Form-Fallback" not in res.headers


def test_api_pdf_normal_form_still_works(client, monkeypatch, tmp_path):
    """正常な様式はこれまでどおり出力されること（回帰）"""
    from pypdf import PdfReader
    import io as _io
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    base = len(PdfReader(_io.BytesIO(
        c.get("/api/pdf?display_year=2026&display_month=3").data)).pages)
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert "X-Form-Fallback" not in res.headers
    assert len(PdfReader(_io.BytesIO(res.data)).pages) == base + 1


# ========== レイアウト画面 ==========

def test_layout_page_returns_200(client):
    """レイアウト画面が開けること"""
    c, _ = client
    res = c.get("/layout")
    assert res.status_code == 200
    assert b"layout.js" in res.data


def test_layout_page_requires_admin(client):
    """別PCからは管理者キーが必要なこと"""
    c, _ = client
    res = c.get("/layout", environ_base={"REMOTE_ADDR": "192.168.1.50"})
    assert res.status_code == 401


def test_layout_css_served(client):
    """レイアウト画面のCSSが配信されること"""
    c, _ = client
    assert c.get("/layout.css").status_code == 200


def test_layout_js_served(client):
    """レイアウト画面のJSが配信されること"""
    c, _ = client
    res = c.get("/layout.js")
    assert res.status_code == 200
    assert b"pdfjsLib" in res.data


# ========== 様式の新規作成 ==========

def _create_form_payload(pdf_bytes, form_id="new_form", period="month",
                         targets=None, form_name="新しい様式"):
    """様式作成APIに送る multipart のデータを組み立てる"""
    import io as _io
    return {
        "form_id": form_id,
        "form_name": form_name,
        "period": period,
        "inspection_type": "使用前",
        "targets": json.dumps(targets if targets is not None else ["A-1"],
                              ensure_ascii=False),
        "file": (_io.BytesIO(pdf_bytes), "form.pdf"),
    }


def _forms_dir_for_create(tmp_path, monkeypatch):
    import app as flask_app
    forms_dir = tmp_path / "forms"
    forms_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    return forms_dir


def test_api_create_form(client, monkeypatch, tmp_path):
    """様式PDFをアップロードして様式を作れること"""
    c, _ = client
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    res = c.post("/api/forms", data=_create_form_payload(pdf),
                 content_type="multipart/form-data")
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["id"] == "new_form"
    assert (forms_dir / "new_form" / "form.pdf").exists()
    assert (forms_dir / "new_form" / "layout.json").exists()


def test_api_create_form_layout_contents(client, monkeypatch, tmp_path):
    """作られた layout.json の中身が正しいこと"""
    c, _ = client
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    c.post("/api/forms", data=_create_form_payload(pdf, targets=["A-1", "A-2"]),
           content_type="multipart/form-data")
    import forms_layout
    layout = forms_layout.load_layout(forms_dir / "new_form")
    assert layout["form_name"] == "新しい様式"
    assert layout["period"] == "month"
    assert layout["inspection_type"] == "使用前"
    assert layout["targets"] == ["A-1", "A-2"]
    assert layout["fields"] == []
    assert layout["axis"]["count"] == 31


def test_api_create_form_single_has_no_axis(client, monkeypatch, tmp_path):
    """single 型には axis を作らないこと"""
    c, _ = client
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    c.post("/api/forms", data=_create_form_payload(pdf, period="single"),
           content_type="multipart/form-data")
    import forms_layout
    assert "axis" not in forms_layout.load_layout(forms_dir / "new_form")


def test_api_create_form_year_axis_count(client, monkeypatch, tmp_path):
    """year 型の欄数の既定が12になること"""
    c, _ = client
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    c.post("/api/forms", data=_create_form_payload(pdf, period="year"),
           content_type="multipart/form-data")
    import forms_layout
    assert forms_layout.load_layout(forms_dir / "new_form")["axis"]["count"] == 12


def test_api_create_form_rejects_non_pdf(client, monkeypatch, tmp_path):
    """PDFでないファイルは400になり、フォルダも残らないこと"""
    c, _ = client
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    res = c.post("/api/forms", data=_create_form_payload(b"this is not a pdf"),
                 content_type="multipart/form-data")
    assert res.status_code == 400
    assert not (forms_dir / "new_form").exists()


def test_api_create_form_rejects_empty_pdf(client, monkeypatch, tmp_path):
    """ページを持たないPDFは400になること"""
    c, _ = client
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_empty_pdf(tmp_path / "empty.pdf").read_bytes()
    res = c.post("/api/forms", data=_create_form_payload(pdf),
                 content_type="multipart/form-data")
    assert res.status_code == 400
    assert not (forms_dir / "new_form").exists()


def test_api_create_form_rejects_bad_id(client, monkeypatch, tmp_path):
    """様式IDに使えない文字があると400になること"""
    c, _ = client
    _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    for bad in ("../escape", "吊具", "NUL", "a b", "a" * 65, ""):
        res = c.post("/api/forms", data=_create_form_payload(pdf, form_id=bad),
                     content_type="multipart/form-data")
        assert res.status_code == 400, f"{bad!r} が400にならない"


def test_api_create_form_rejects_duplicate(client, monkeypatch, tmp_path):
    """同じ様式IDが既にあれば400になり、元のフォルダを壊さないこと"""
    c, _ = client
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    assert c.post("/api/forms", data=_create_form_payload(pdf),
                  content_type="multipart/form-data").status_code == 200
    before = (forms_dir / "new_form" / "layout.json").read_bytes()
    res = c.post("/api/forms",
                 data=_create_form_payload(pdf, form_name="上書きしたい"),
                 content_type="multipart/form-data")
    assert res.status_code == 400
    assert (forms_dir / "new_form" / "layout.json").read_bytes() == before


def test_api_create_form_rejects_bad_period(client, monkeypatch, tmp_path):
    """様式の型が不正なら400になること"""
    c, _ = client
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    res = c.post("/api/forms", data=_create_form_payload(pdf, period="weekly"),
                 content_type="multipart/form-data")
    assert res.status_code == 400
    assert not (forms_dir / "new_form").exists()


def test_api_create_form_rejects_bad_targets(client, monkeypatch, tmp_path):
    """targets の形式が不正なら400になること"""
    import io as _io
    c, _ = client
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    for bad in ("こわれてる", json.dumps({"a": 1}), json.dumps(["A-1", 123])):
        data = _create_form_payload(pdf)
        data["targets"] = bad
        data["file"] = (_io.BytesIO(pdf), "form.pdf")
        res = c.post("/api/forms", data=data, content_type="multipart/form-data")
        assert res.status_code == 400, f"{bad!r} が400にならない"
        assert not (forms_dir / "new_form").exists()


def test_api_create_form_requires_file(client, monkeypatch, tmp_path):
    """ファイルが無ければ400になること"""
    c, _ = client
    _forms_dir_for_create(tmp_path, monkeypatch)
    res = c.post("/api/forms", data={
        "form_id": "new_form", "form_name": "名前", "period": "month",
        "inspection_type": "使用前", "targets": json.dumps(["A-1"]),
    }, content_type="multipart/form-data")
    assert res.status_code == 400


def test_api_create_form_requires_admin(client, monkeypatch, tmp_path):
    """別PCからの作成は管理者キーが必要なこと"""
    c, _ = client
    _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    res = c.post("/api/forms", data=_create_form_payload(pdf),
                 content_type="multipart/form-data",
                 environ_base={"REMOTE_ADDR": "192.168.1.50"})
    assert res.status_code == 401


def test_api_create_form_appears_in_list(client, monkeypatch, tmp_path):
    """作った様式が一覧に出ること"""
    c, _ = client
    _forms_dir_for_create(tmp_path, monkeypatch)
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    c.post("/api/forms", data=_create_form_payload(pdf),
           content_type="multipart/form-data")
    ids = [f["id"] for f in c.get("/api/forms").get_json()]
    assert "new_form" in ids


def test_max_content_length_allows_form_pdf():
    """アップロード上限が50MB以上に引き上げられていること"""
    import app as flask_app
    assert flask_app.app.config["MAX_CONTENT_LENGTH"] >= 50 * 1024 * 1024


# ========== 試し刷り ==========

def test_layout_item_names():
    """layout の fields から (機器名, 点検項目名) を取り出せること"""
    import pdf_forms
    layout = {"fields": [
        {"source": "item:吊具A|傷はないか"},
        {"source": "remark:吊具A|傷はないか"},
        {"source": "meta.month"},
        {"source": "item:吊具B|油圧"},
        {"source": "item:こわれてる"},
    ]}
    names = pdf_forms.layout_item_names(layout)
    assert ("吊具A", "傷はないか") in names
    assert ("吊具B", "油圧") in names
    assert len(names) == 2


def test_build_sample_records_month():
    """month 型はサイクルの全日分のサンプルを作ること"""
    import app as flask_app
    import pdf_forms
    cycle = flask_app.get_cycle_dates(2026, 3)
    layout = {"period": "month", "inspection_type": "使用前",
              "targets": ["A-1"],
              "fields": [{"source": "item:A-1|傷はないか"}]}
    records = pdf_forms.build_sample_records(layout, cycle, 2026, set())
    assert len(records) == len(cycle)
    assert records[0]["category_minor"] == "A-1"
    assert records[0]["results"][0]["result"] == "✓"


def test_build_sample_records_year():
    """year 型は12か月分のサンプルを作ること"""
    import pdf_forms
    layout = {"period": "year", "inspection_type": "月例", "targets": ["A-1"],
              "fields": [{"source": "item:A-1|傷はないか"}]}
    records = pdf_forms.build_sample_records(layout, [], 2026, set())
    months = {r["inspection_date"][5:7] for r in records}
    assert len(months) == 12


def test_build_sample_records_number_item():
    """数値項目には数値のサンプルを入れること"""
    import app as flask_app
    import pdf_forms
    cycle = flask_app.get_cycle_dates(2026, 3)
    layout = {"period": "month", "inspection_type": "使用前", "targets": ["A-1"],
              "fields": [{"source": "item:A-1|油圧"}]}
    records = pdf_forms.build_sample_records(layout, cycle, 2026, {"油圧"})
    assert records[0]["results"][0]["result"] == pdf_forms.SAMPLE_NUMBER


def test_build_sample_records_multiple_equipment():
    """複数機器の様式では機器ごとにサンプルを作ること"""
    import app as flask_app
    import pdf_forms
    cycle = flask_app.get_cycle_dates(2026, 3)
    layout = {"period": "month", "inspection_type": "使用前",
              "targets": ["A-1", "A-2"],
              "fields": [{"source": "item:A-1|傷はないか"},
                         {"source": "item:A-2|傷はないか"}]}
    records = pdf_forms.build_sample_records(layout, cycle, 2026, set())
    minors = {r["category_minor"] for r in records}
    assert minors == {"A-1", "A-2"}


def test_api_form_preview(client, monkeypatch, tmp_path):
    """試し刷りPDFが生成できること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/preview?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert res.data[:5] == b"%PDF-"


def test_api_form_preview_fills_all_slots(client, monkeypatch, tmp_path):
    """試し刷りは全欄を埋めること（28日サイクルなら29〜31に「ー」が入る）"""
    from pypdf import PdfReader
    import io as _io
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/preview?display_year=2026&display_month=3")
    text = PdfReader(_io.BytesIO(res.data)).pages[0].extract_text() or ""
    assert "✓" in text
    assert "ー" in text
    assert "24" in text


def test_api_form_preview_month_matters(client, monkeypatch, tmp_path):
    """31日サイクルの月では「ー」が出ないこと"""
    from pypdf import PdfReader
    import io as _io
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/preview?display_year=2026&display_month=4")
    text = PdfReader(_io.BytesIO(res.data)).pages[0].extract_text() or ""
    assert "✓" in text
    assert "ー" not in text


def test_api_form_preview_not_found(client, monkeypatch, tmp_path):
    """存在しない様式は404になること"""
    c, _ = client
    _empty_forms_dir(tmp_path, monkeypatch)
    assert c.get("/api/forms/nothing/preview").status_code == 404


def test_api_form_preview_rejects_traversal(client, monkeypatch, tmp_path):
    """試し刷りでもパストラバーサルを弾くこと"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    for bad in ("..%2Fetc", "NUL", "con"):
        assert c.get(f"/api/forms/{bad}/preview").status_code == 404


def test_api_form_preview_requires_admin(client, monkeypatch, tmp_path):
    """別PCからの試し刷りは管理者キーが必要なこと"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/forms/tsurigu/preview?display_year=2026&display_month=3",
                environ_base={"REMOTE_ADDR": "192.168.1.50"})
    assert res.status_code == 401


def test_api_form_preview_missing_pdf(client, monkeypatch, tmp_path):
    """様式PDFが無ければ404になること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT, with_pdf=False)
    assert c.get("/api/forms/tsurigu/preview").status_code == 404


def test_api_form_preview_broken_layout(client, monkeypatch, tmp_path):
    """設定が壊れていれば400になること"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    (forms_dir / "broken").mkdir(parents=True)
    (forms_dir / "broken" / "layout.json").write_text("{ oops", encoding="utf-8")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    assert c.get("/api/forms/broken/preview").status_code == 400


def test_api_create_form_handles_race(client, monkeypatch, tmp_path):
    """フォルダ作成が競合しても500にならないこと"""
    import app as flask_app
    forms_dir = _forms_dir_for_create(tmp_path, monkeypatch)
    (forms_dir / "new_form").mkdir()
    real_exists = flask_app.Path.exists

    def fake_exists(self):
        # 存在チェックだけをすり抜けさせ、mkdir で衝突させる
        if self.name == "new_form":
            return False
        return real_exists(self)

    monkeypatch.setattr(flask_app.Path, "exists", fake_exists)
    c, _ = client
    pdf = _make_form_pdf(tmp_path / "src.pdf").read_bytes()
    res = c.post("/api/forms", data=_create_form_payload(pdf),
                 content_type="multipart/form-data")
    assert res.status_code == 400


# ========== 前回値の取得 ==========

def _post_result(c, date_str, item, value, major="設備A", minor="A-1"):
    """点検結果を1件保存する"""
    return c.post("/api/results", data=json.dumps({
        "inspection_type": "使用前",
        "inspection_date": date_str,
        "category_major": major,
        "category_minor": minor,
        "inspector_name": "テスト",
        "department": "テスト部",
        "results": [{"equipment_name": major, "inspection_item": item,
                     "result": value, "remark": ""}],
    }), content_type="application/json")


def test_api_previous_values(client, monkeypatch, tmp_path):
    """直近の記録を取得できること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    _post_result(c, "2026-03-02", "油圧", "0.52")
    res = c.get("/api/results/previous?type=使用前&category_major=設備A"
                "&category_minor=A-1&before=2026-03-05")
    assert res.status_code == 200
    assert res.get_json()["油圧"] == "0.52"


def test_api_previous_values_excludes_same_day(client, monkeypatch, tmp_path):
    """指定日そのものは前回値に含めないこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    _post_result(c, "2026-03-05", "油圧", "0.60")
    res = c.get("/api/results/previous?type=使用前&category_major=設備A"
                "&category_minor=A-1&before=2026-03-05")
    assert res.get_json() == {}


def test_api_previous_values_uses_latest(client, monkeypatch, tmp_path):
    """複数の記録があれば一番新しいものを返すこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    _post_result(c, "2026-03-01", "油圧", "0.40")
    _post_result(c, "2026-03-03", "油圧", "0.55")
    res = c.get("/api/results/previous?type=使用前&category_major=設備A"
                "&category_minor=A-1&before=2026-03-05")
    assert res.get_json()["油圧"] == "0.55"


def test_api_previous_values_crosses_month(client, monkeypatch, tmp_path):
    """前の月の記録も遡って探すこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    _post_result(c, "2026-01-20", "油圧", "0.33")
    res = c.get("/api/results/previous?type=使用前&category_major=設備A"
                "&category_minor=A-1&before=2026-03-05")
    assert res.get_json()["油圧"] == "0.33"


def test_api_previous_values_gives_up_after_lookback(client, monkeypatch, tmp_path):
    """遡る範囲を超えた古い記録は返さないこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    _post_result(c, "2025-06-10", "油圧", "0.11")
    res = c.get("/api/results/previous?type=使用前&category_major=設備A"
                "&category_minor=A-1&before=2026-03-05")
    assert res.get_json() == {}


def test_api_previous_values_filters_by_equipment(client, monkeypatch, tmp_path):
    """別の機器の記録は返さないこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    _post_result(c, "2026-03-02", "油圧", "0.52", major="設備B", minor="B-1")
    res = c.get("/api/results/previous?type=使用前&category_major=設備A"
                "&category_minor=A-1&before=2026-03-05")
    assert res.get_json() == {}


def test_api_previous_values_invalid_date(client):
    """日付が不正なら400になること"""
    c, _ = client
    res = c.get("/api/results/previous?type=使用前&category_major=設備A"
                "&category_minor=A-1&before=xx")
    assert res.status_code == 400


def test_api_previous_values_no_records(client, monkeypatch, tmp_path):
    """記録が無ければ空の辞書を返すこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    c, _ = client
    res = c.get("/api/results/previous?type=使用前&category_major=設備A"
                "&category_minor=A-1&before=2026-03-05")
    assert res.status_code == 200
    assert res.get_json() == {}


# ========== 設定画面から保存できること ==========

def test_settings_payload_saves_forms_and_cycle(client):
    """画面が送る形の設定を保存できること"""
    c, _ = client
    payload = {
        "save_directory": "",
        "forms_directory": "\\\\server\\forms",
        "cycle_start_day": 20,
        "building_info": {"building_name": "テストビル", "managers": []},
    }
    res = c.post("/api/config", data=json.dumps(payload),
                 content_type="application/json")
    assert res.status_code == 200
    cfg = c.get("/api/config").get_json()
    assert cfg["forms_directory"] == "\\\\server\\forms"
    assert cfg["cycle_start_day"] == 20
    assert cfg["building_info"]["building_name"] == "テストビル"


def test_settings_payload_rejects_bad_cycle_day(client):
    """締め日が範囲外なら400になり、他の設定も保存されないこと"""
    c, _ = client
    before = c.get("/api/config").get_json().get("forms_directory", "")
    res = c.post("/api/config", data=json.dumps({
        "forms_directory": "\\\\server\\changed",
        "cycle_start_day": 99,
    }), content_type="application/json")
    assert res.status_code == 400
    assert c.get("/api/config").get_json().get("forms_directory", "") == before


# ==================================================================
# 判定記号（✓ / A / △ / ×）
# ==================================================================

def test_normalize_judgment_converts_legacy_maru():
    """旧仕様の「○」は「良（✓）」に読み替えられること"""
    import forms_layout
    assert forms_layout.normalize_judgment("○") == "✓"


def test_normalize_judgment_keeps_other_marks():
    """✓・A・△・×・ー と数値はそのまま返すこと"""
    import forms_layout
    for value in ("✓", "A", "△", "×", "ー", "0.52", ""):
        assert forms_layout.normalize_judgment(value) == value


def test_normalize_judgment_rejects_non_string():
    """文字列以外は空文字にすること（印字で落ちないように）"""
    import forms_layout
    assert forms_layout.normalize_judgment(None) == ""
    assert forms_layout.normalize_judgment(3) == ""


@pytest.mark.parametrize("mark", ["✓", "A", "△", "×", "ー"])
def test_build_form_pdf_writes_each_mark(tmp_path, mark):
    """5つの記号がそれぞれ様式PDFに印字されること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slot = {"date": None, "month": None, "exists": True, "mark": "",
            "values": {"吊具A|傷はないか": mark}, "remarks": {}, "meta": {}}
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "item:吊具A|傷はないか", "page": 0, "x": 100, "y": 700},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: slot}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert mark in _read_text(out)


def test_build_form_pdf_applies_adjust_and_repair_overrides(tmp_path):
    """要調整・修理も様式ごとの文字に置き換えられること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slot = {"date": None, "month": None, "exists": True, "mark": "",
            "values": {"吊具A|傷はないか": "A", "吊具A|油圧": "△"},
            "remarks": {}, "meta": {}}
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "item:吊具A|傷はないか", "page": 0, "x": 100, "y": 700,
         "mark_adjust": "調"},
        {"source": "item:吊具A|油圧", "page": 0, "x": 100, "y": 680,
         "mark_repair": "修"},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: slot}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    text = _read_text(out)
    assert "調" in text and "修" in text


def test_build_form_pdf_mark_ng_still_applies_to_replace(tmp_path):
    """既存の layout.json の mark_ng が要取替（×）に効き続けること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slot = {"date": None, "month": None, "exists": True, "mark": "",
            "values": {"吊具A|傷はないか": "×"}, "remarks": {}, "meta": {}}
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "item:吊具A|傷はないか", "page": 0, "x": 100, "y": 700,
         "mark_ng": "N"},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: slot}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert "N" in _read_text(out)


def test_post_results_accepts_new_marks(client):
    """新しい記号（A・△・×）が保存できること"""
    c, _ = client
    for mark in ("✓", "A", "△", "×", "ー"):
        res = _post_one(c, "設備C", "シャッター1", "点検項目C-1", mark)
        assert res.status_code == 200, mark


# ==================================================================
# 使用せず
# ==================================================================

UNUSED_LAYOUT = {
    "form_name": "吊具日常点検表",
    "period": "month",
    "inspection_type": "使用前",
    "targets": ["A-1"],
    "axis": {"step_x": 15.0, "step_y": 0.0, "count": 31},
    "fields": [
        {"source": "meta.unused", "page": 0, "x": 50, "y": 600,
         "on_axis": True},
    ],
}


def _unused_slots(records_by_date, today, layout=None, cycle=None):
    """使用せず判定だけを取り出すヘルパー"""
    import app as flask_app
    import pdf_forms
    cycle = cycle or flask_app.get_cycle_dates(2026, 3)
    slots = pdf_forms.build_slots(
        layout or UNUSED_LAYOUT, 2026, 3, cycle, records_by_date, {},
        today=today)
    return {n: s["unused"] for n, s in slots.items()}


def test_unused_marks_past_day_without_record():
    """24時を過ぎた日に記録が無ければ使用せずになること"""
    from datetime import date
    flags = _unused_slots({}, today=date(2026, 3, 23))
    # サイクルは 2/24〜3/23。1番目（2/24）は過去なので使用せず
    assert flags[1] is True


def test_unused_skips_day_with_record():
    """記録がある日は使用せずにしないこと"""
    from datetime import date
    records = {"2026-02-24": {"values": {"A-1|傷はないか": "✓"},
                              "remarks": {}, "meta": {}}}
    flags = _unused_slots(records, today=date(2026, 3, 23))
    assert flags[1] is False


def test_unused_skips_today_and_future():
    """当日と未来の日は空欄のままにすること"""
    from datetime import date
    import app as flask_app
    cycle = flask_app.get_cycle_dates(2026, 3)
    today = date(2026, 3, 1)
    flags = _unused_slots({}, today=today, cycle=cycle)
    today_index = cycle.index(today) + 1
    assert flags[today_index] is False           # 当日
    assert flags[today_index + 1] is False       # 翌日（未来）
    assert flags[today_index - 1] is True        # 前日（過去）


def test_unused_skips_extra_slots():
    """余りマス（その月に存在しない日）は使用せずにしないこと"""
    from datetime import date
    # 2026年3月分は 2/24〜3/23 の28日。29〜31番目は余りマス
    flags = _unused_slots({}, today=date(2026, 4, 1))
    assert flags[29] is False
    assert flags[30] is False
    assert flags[31] is False


def test_unused_not_used_for_monthly_layout():
    """月例点検の様式には使用せずを出さないこと"""
    from datetime import date
    layout = dict(UNUSED_LAYOUT, inspection_type="月例")
    flags = _unused_slots({}, today=date(2026, 4, 1), layout=layout)
    assert all(v is False for v in flags.values())


def test_unused_prints_check_mark_on_form(tmp_path):
    """使用せずの欄に✓が印字されること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slot = {"date": None, "month": None, "exists": True, "mark": "",
            "unused": True, "values": {}, "remarks": {}, "meta": {}}
    layout = {"period": "single", "targets": ["A-1"], "fields": [
        {"source": "meta.unused", "page": 0, "x": 100, "y": 700},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: slot}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert "✓" in _read_text(out)


def test_unused_prints_nothing_when_not_unused(tmp_path):
    """使用せずでない欄には何も印字しないこと"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slot = {"date": None, "month": None, "exists": True, "mark": "",
            "unused": False, "values": {}, "remarks": {}, "meta": {}}
    layout = {"period": "single", "targets": ["A-1"], "fields": [
        {"source": "meta.unused", "page": 0, "x": 100, "y": 700},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: slot}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert "✓" not in (_read_text(out) or "")


def test_unused_mark_can_be_overridden(tmp_path):
    """mark_unused で✓以外の文字も指定できること"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slot = {"date": None, "month": None, "exists": True, "mark": "",
            "unused": True, "values": {}, "remarks": {}, "meta": {}}
    layout = {"period": "single", "targets": ["A-1"], "fields": [
        {"source": "meta.unused", "page": 0, "x": 100, "y": 700,
         "mark_unused": "レ"},
    ]}
    out = _write_out(pdf_forms.build_form_pdf(
        form, layout, {1: slot}, {"year": 2026, "month": 3}),
        tmp_path / "out.pdf")
    assert "レ" in _read_text(out)


def test_sample_marks_every_slot_unused(tmp_path):
    """試し刷りでは位置合わせのため全欄に使用せずが出ること"""
    import app as flask_app
    import pdf_forms
    cycle = flask_app.get_cycle_dates(2026, 4)   # 31日サイクル
    records = {d.strftime("%Y-%m-%d"): {"values": {}, "remarks": {}, "meta": {}}
               for d in cycle}
    slots = pdf_forms.build_slots(UNUSED_LAYOUT, 2026, 4, cycle, records, {},
                                  sample=True)
    # 記録があっても、実在する欄はすべて使用せず扱いになる
    assert all(s["unused"] for s in slots.values() if s["exists"])


# ==================================================================
# 様式フォルダの置き場所と様式ID
# ==================================================================

def test_list_forms_flags_folder_name_that_cannot_be_edited(tmp_path):
    """様式IDの規則から外れたフォルダ名に、理由付きの警告が付くこと"""
    import forms_layout
    forms_dir = tmp_path / "forms"
    for name in ("日常点検", "crane-daily"):
        d = forms_dir / name
        d.mkdir(parents=True)
        (d / "layout.json").write_text(
            json.dumps({"period": "single", "targets": [], "fields": []}),
            encoding="utf-8")
    entries = {e["id"]: e for e in forms_layout.list_forms(forms_dir)}
    for name in ("日常点検", "crane-daily"):
        assert entries[name]["editable"] is False
        assert name in entries[name]["warning"]
        # 出力そのものは動かしたいので error にはしない
        assert entries[name]["error"] == ""


def test_list_forms_marks_valid_folder_as_editable(tmp_path):
    """正しいフォルダ名には警告を付けないこと"""
    import forms_layout
    d = tmp_path / "forms" / "crane_daily"
    d.mkdir(parents=True)
    (d / "layout.json").write_text(
        json.dumps({"period": "single", "targets": [], "fields": []}),
        encoding="utf-8")
    entry = forms_layout.list_forms(tmp_path / "forms")[0]
    assert entry["editable"] is True
    assert entry["warning"] == ""


def test_form_output_still_works_for_japanese_folder_name(tmp_path):
    """フォルダ名が日本語でも、様式PDFの出力自体は従来どおり動くこと

    レイアウト画面では開けないが、すでに使っている現場の出力を
    止めてしまわないための確認。
    """
    import forms_layout
    forms_dir = tmp_path / "forms"
    d = forms_dir / "日常点検"
    d.mkdir(parents=True)
    (d / "layout.json").write_text(json.dumps(
        {"period": "single", "targets": ["A-1"], "fields": []},
        ensure_ascii=False), encoding="utf-8")
    assert forms_layout.form_assignments(forms_dir) == {"A-1": ["日常点検"]}


def test_forms_directory_may_contain_japanese_path(tmp_path, monkeypatch, client):
    """様式フォルダまでのパスに日本語が入っていても開けること"""
    import app as flask_app
    c, _ = client
    forms_dir = tmp_path / "設備 点検" / "様式" / "forms"
    d = forms_dir / "crane_daily"
    d.mkdir(parents=True)
    (d / "layout.json").write_text(json.dumps(MONTH_LAYOUT, ensure_ascii=False),
                                   encoding="utf-8")
    _make_form_pdf(d / "form.pdf")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    assert c.get("/api/forms/crane_daily/layout").status_code == 200
    assert c.get("/api/forms/crane_daily/pdf").status_code == 200


@pytest.mark.parametrize("bad_id", ["crane-daily", "日常点検", "sub/form", "..", "NUL"])
def test_create_form_rejects_bad_id_with_helpful_message(client, monkeypatch,
                                                         tmp_path, bad_id):
    """様式IDを弾くとき、フォルダ名になることまで伝えること"""
    _empty_forms_dir(tmp_path, monkeypatch)
    c, _ = client
    res = c.post("/api/forms", data={"form_id": bad_id})
    assert res.status_code == 400
    msg = res.get_json()["error"]
    assert "フォルダ名" in msg
    assert "crane_daily" in msg


def test_build_form_pdf_keeps_page_when_nothing_printed(tmp_path):
    """印字する中身が1つも無いページでも、様式のページが残ること

    何も描かないまま reportlab を save() すると0ページのPDFになり、
    重ね書きの段階で落ちる。1件も記録が無い月に実際に起きる。
    """
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf")
    slot = {"date": None, "month": None, "exists": True, "mark": "",
            "unused": False, "values": {}, "remarks": {}, "meta": {}}
    layout = {"period": "single", "targets": ["A-1"], "fields": [
        {"source": "item:A-1|傷はないか", "page": 0, "x": 100, "y": 700},
    ]}
    writer = pdf_forms.build_form_pdf(
        form, layout, {1: slot}, {"year": 2026, "month": 3})
    assert len(writer.pages) == 1


def test_build_form_pdf_page_count_unchanged_with_content(tmp_path):
    """中身があるときにページが増えていないこと（showPage の二重呼び出し防止）"""
    import pdf_forms
    form = _make_form_pdf(tmp_path / "form.pdf", pages=2)
    layout = {"period": "single", "targets": ["吊具A"], "fields": [
        {"source": "item:吊具A|傷はないか", "page": 0, "x": 100, "y": 700},
        {"source": "item:吊具A|油圧", "page": 1, "x": 100, "y": 700},
    ]}
    writer = pdf_forms.build_form_pdf(
        form, layout, {1: SINGLE_SLOT}, {"year": 2026, "month": 3})
    assert len(writer.pages) == 2


def test_api_pdf_table_has_unused_row(client, monkeypatch, tmp_path):
    """表出力に「使用せず」行が入ること（1枚目は特記事項なので2枚目を見る）"""
    from pypdf import PdfReader
    import io as _io
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _empty_forms_dir(tmp_path, monkeypatch)
    c, _ = client
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    text = PdfReader(_io.BytesIO(res.data)).pages[1].extract_text() or ""
    assert "使用せず" in text


# ==================================================================
# 縦書き
# ==================================================================

class _RecordingCanvas:
    """drawString の呼び出しを記録するだけの偽キャンバス"""

    def __init__(self):
        self.calls = []

    def setFont(self, *a):
        pass

    def setFillColor(self, *a):
        pass

    def drawString(self, x, y, text):
        self.calls.append((x, y, text))

    def drawCentredString(self, x, y, text):
        self.calls.append(("center", x, y, text))


def test_draw_field_vertical_stacks_characters():
    """縦書きは1文字ずつ下へ積むこと（PDFのYは上が正なので減らす）"""
    import pdf_forms
    c = _RecordingCanvas()
    field = {"source": "meta.inspector", "vertical": True, "font_size": 10}
    pdf_forms._draw_field(c, field, 100, 700, "見本", 11)
    assert c.calls == [(100, 700, "見"), (100, 690, "本")]


def test_draw_field_horizontal_unchanged():
    """縦書きを指定しなければ、いままでどおり1回で書くこと"""
    import pdf_forms
    c = _RecordingCanvas()
    pdf_forms._draw_field(c, {"source": "meta.inspector"}, 100, 700, "見本 太郎", 11)
    assert c.calls == [(100, 700, "見本 太郎")]


def test_draw_field_vertical_uses_default_font_size():
    """文字サイズを指定しなければ、様式の既定値で積むこと"""
    import pdf_forms
    c = _RecordingCanvas()
    pdf_forms._draw_field(c, {"source": "x", "vertical": True}, 0, 100, "ab", 20)
    assert c.calls == [(0, 100, "a"), (0, 80, "b")]


def test_draw_field_vertical_skips_empty_text():
    """空文字なら縦書きでも何も描かないこと"""
    import pdf_forms
    c = _RecordingCanvas()
    pdf_forms._draw_field(c, {"source": "x", "vertical": True}, 0, 100, "", 11)
    assert c.calls == []


# ==================================================================
# 様式の削除（ゴミ箱への移動）
# ==================================================================

def _make_form(forms_dir, name, with_pdf=True):
    """テスト用の様式フォルダを1つ作る"""
    d = forms_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "layout.json").write_text(json.dumps(
        {"form_name": name, "period": "single", "inspection_type": "使用前",
         "targets": [], "fields": []}, ensure_ascii=False), encoding="utf-8")
    if with_pdf:
        _make_form_pdf(d / "form.pdf")
    return d


def test_list_forms_skips_dot_directories(tmp_path):
    """ゴミ箱（.trash）を様式として並べないこと"""
    import forms_layout
    forms_dir = tmp_path / "forms"
    _make_form(forms_dir, "crane_daily")
    (forms_dir / ".trash" / "old_20260830_120000").mkdir(parents=True)
    ids = [e["id"] for e in forms_layout.list_forms(forms_dir)]
    assert ids == ["crane_daily"]


def test_delete_form_moves_it_to_trash(client, monkeypatch, tmp_path):
    """削除すると .trash に移り、一覧から消えること"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    _make_form(forms_dir, "crane_daily")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    res = c.delete("/api/forms/crane_daily")
    assert res.status_code == 200
    assert not (forms_dir / "crane_daily").exists()
    moved = list((forms_dir / ".trash").iterdir())
    assert len(moved) == 1
    assert moved[0].name.startswith("crane_daily_")
    assert (moved[0] / "form.pdf").exists()      # PDFごと残っている
    assert c.get("/api/forms").get_json() == []


def test_delete_form_works_for_a_broken_form(client, monkeypatch, tmp_path):
    """レイアウト画面で開けない様式も削除できること（これが主目的）"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    d = forms_dir / "日常点検"          # 様式IDの規則から外れた名前
    d.mkdir(parents=True)
    (d / "layout.json").write_text("{ 壊れている", encoding="utf-8")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    assert c.delete("/api/forms/日常点検").status_code == 200
    assert not d.exists()


@pytest.mark.parametrize("bad", ["..", ".", ".trash"])
def test_delete_form_rejects_unsafe_names(client, monkeypatch, tmp_path, bad):
    """ドットで始まる名前は消させないこと（ゴミ箱自身と親フォルダ）"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    forms_dir.mkdir(parents=True)
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    assert c.delete(f"/api/forms/{bad}").status_code == 400


def test_delete_form_rejects_path_separators(client, monkeypatch, tmp_path):
    """パス区切りを含む名前は消させないこと"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    forms_dir.mkdir(parents=True)
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    # URLに入れられない形なので、関数を直接確かめる
    assert flask_app._safe_form_dir_for_delete("a/b") is None
    assert flask_app._safe_form_dir_for_delete("a\\b") is None
    assert flask_app._safe_form_dir_for_delete("") is None
    assert flask_app._safe_form_dir_for_delete(None) is None


def test_delete_form_returns_404_when_missing(client, monkeypatch, tmp_path):
    """存在しない様式は404にすること"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    forms_dir.mkdir(parents=True)
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    assert c.delete("/api/forms/nothing").status_code == 404


def test_delete_form_keeps_other_forms(client, monkeypatch, tmp_path):
    """他の様式は消さないこと"""
    import app as flask_app
    forms_dir = tmp_path / "forms"
    _make_form(forms_dir, "keep_me")
    _make_form(forms_dir, "delete_me")
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    c.delete("/api/forms/delete_me")
    assert [e["id"] for e in c.get("/api/forms").get_json()] == ["keep_me"]


def test_delete_form_twice_keeps_both_copies(client, monkeypatch, tmp_path):
    """同じ名前を作り直して再度消しても、前の分を上書きしないこと"""
    import app as flask_app
    import time
    forms_dir = tmp_path / "forms"
    monkeypatch.setattr(flask_app, "get_forms_directory", lambda: forms_dir)
    c, _ = client
    _make_form(forms_dir, "same_name")
    assert c.delete("/api/forms/same_name").status_code == 200
    time.sleep(1.1)          # 名前に秒までの日時を使うので、1秒空ける
    _make_form(forms_dir, "same_name")
    assert c.delete("/api/forms/same_name").status_code == 200
    assert len(list((forms_dir / ".trash").iterdir())) == 2


# ==================================================================
# 月の変わり目の表示
# ==================================================================

def _month_slots(year, month):
    """その表示月のマスを作る（締め日は既定の24日）"""
    import app as flask_app
    import pdf_forms
    cycle = flask_app.get_cycle_dates(year, month)
    layout = {"period": "month", "inspection_type": "使用前", "targets": [],
              "axis": {"step_x": 10.0, "step_y": 0.0, "count": 31}, "fields": []}
    return pdf_forms.build_slots(layout, year, month, cycle, {}, {})


def test_slots_carry_their_index():
    """各マスが自分の番号を持つこと（前月の表示に使う）"""
    slots = _month_slots(2026, 8)
    assert slots[1]["index"] == 1
    assert slots[9]["index"] == 9


def test_month_start_prints_only_on_the_first_day_slot():
    """実施月は「日にちが1のマス」にだけ出ること"""
    import pdf_forms
    slots = _month_slots(2026, 8)          # 7/24〜8/23。8/1 は9マス目
    field = {"source": "meta.month_start"}
    meta = {"year": 2026, "month": 8}
    assert pdf_forms._field_value(field, slots[9], meta) == "8月"
    assert pdf_forms._field_value(field, slots[1], meta) == ""
    assert pdf_forms._field_value(field, slots[8], meta) == ""


def test_month_start_follows_the_cycle_length():
    """月によって1日のマスの位置が変わること"""
    import pdf_forms
    field = {"source": "meta.month_start"}
    meta = {"year": 2026, "month": 3}
    slots = _month_slots(2026, 3)          # 2/24〜3/23。3/1 は6マス目
    assert pdf_forms._field_value(field, slots[6], meta) == "3月"
    assert pdf_forms._field_value(field, slots[9], meta) == ""


def test_month_prev_prints_only_on_the_first_slot():
    """前月は1マス目にだけ出ること"""
    import pdf_forms
    slots = _month_slots(2026, 8)
    field = {"source": "meta.month_prev"}
    meta = {"year": 2026, "month": 8}
    assert pdf_forms._field_value(field, slots[1], meta) == "7月"
    assert pdf_forms._field_value(field, slots[2], meta) == ""
    assert pdf_forms._field_value(field, slots[9], meta) == ""


def test_month_marks_stay_empty_on_extra_slots():
    """余りマスには出ないこと"""
    import pdf_forms
    slots = _month_slots(2026, 3)          # 28日サイクル。29〜31は余りマス
    meta = {"year": 2026, "month": 3}
    for source in ("meta.month_start", "meta.month_prev"):
        assert pdf_forms._field_value({"source": source}, slots[30], meta) == ""


def test_month_prev_crosses_the_year_boundary():
    """年をまたぐ場合も前月を正しく出すこと（1月分なら前年12月）"""
    import pdf_forms
    slots = _month_slots(2026, 1)          # 2025/12/24〜2026/1/23
    meta = {"year": 2026, "month": 1}
    assert pdf_forms._field_value({"source": "meta.month_prev"}, slots[1], meta) == "12月"


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


def test_sample_records_fill_all_targets_item():
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


def _use_crane_master(monkeypatch, tmp_path):
    """点検項目マスタを クレーン1 → クレーン2 の順の小さな表に差し替える。
    data/ の中身（配布用のサンプル）に左右されないようにするため。"""
    import app as flask_app
    master = tmp_path / "equipment_master.csv"
    master.write_text(
        "category_major,category_minor,inspection_item,inspection_type\n"
        "クレーン,クレーン1,点検項目C-1,使用前\n"
        "クレーン,クレーン2,点検項目C-1,使用前\n", encoding="utf-8-sig")
    monkeypatch.setattr(flask_app, "EQUIPMENT_CSV", master)


def test_collect_remarks_sorts_by_master_then_date(client, monkeypatch, tmp_path):
    """機器は点検項目マスタの順、機器の中は日付順に並ぶこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _use_crane_master(monkeypatch, tmp_path)
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
    _use_crane_master(monkeypatch, tmp_path)
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


def test_collect_remarks_tolerates_broken_machine_name(client, monkeypatch, tmp_path):
    """機器名が None や数値の壊れた記録があっても落ちないこと"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _use_crane_master(monkeypatch, tmp_path)
    broken = _remark_record("2026-03-02", "ダミー", "壊れた記録")
    broken["category_minor"] = None
    number = _remark_record("2026-03-03", "ダミー", "数値の機器名")
    number["category_minor"] = 12
    _write_results(tmp_path, "使用前", 2026, 3, [
        broken, number, _remark_record("2026-03-04", "クレーン1", "正常な記録"),
    ])
    rows = flask_app._collect_remarks(2026, 3)
    # 3件とも残り、マスタにある機器が先頭に来る
    assert len(rows) == 3
    assert rows[0]["machine"] == "クレーン1"
    assert all(isinstance(r["machine"], str) for r in rows)


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


def test_remark_machine_spans_merges_consecutive():
    """同じ機器が続く行だけを縦につなぐこと（表の行番号は並びの番号+1）"""
    import app as flask_app
    rows = [{"machine": "A"}, {"machine": "B"}, {"machine": "B"}, {"machine": "C"}]
    assert flask_app._remark_machine_spans(rows) == [("SPAN", (0, 2), (0, 3))]


def test_remark_machine_spans_last_machine():
    """最後の機器が複数行でもつなぐこと"""
    import app as flask_app
    rows = [{"machine": "A"}, {"machine": "B"}, {"machine": "B"}]
    assert flask_app._remark_machine_spans(rows) == [("SPAN", (0, 2), (0, 3))]


def test_remark_machine_spans_all_same():
    """全部同じ機器なら1つの範囲になること"""
    import app as flask_app
    rows = [{"machine": "A"}, {"machine": "A"}, {"machine": "A"}]
    assert flask_app._remark_machine_spans(rows) == [("SPAN", (0, 1), (0, 3))]


def test_remark_machine_spans_no_merge_needed():
    """1行ずつ・1件だけ・0件では、つなぐ範囲が無いこと"""
    import app as flask_app
    assert flask_app._remark_machine_spans([{"machine": "A"}, {"machine": "B"}]) == []
    assert flask_app._remark_machine_spans([{"machine": "A"}]) == []
    assert flask_app._remark_machine_spans([]) == []


def test_remark_page_keeps_angle_brackets(client, monkeypatch, tmp_path):
    """山括弧やアンパサンドを含む特記事項が消えずに印字されること"""
    import app as flask_app
    monkeypatch.setattr(flask_app, "get_save_directory", lambda: tmp_path)
    _write_results(tmp_path, "使用前", 2026, 3,
                   [_remark_record("2026-03-02", "クレーン1", "型番<AB-12>を交換 & 調整")])
    text = "".join(_remark_page_text(2026, 3).split())
    assert "型番<AB-12>を交換" in text
    assert "&" in text


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


def test_ordered_form_entries_tolerates_broken_config():
    """手編集で壊れた form_order でも落ちず、無視されること"""
    import app as flask_app
    entries = _entries("a", "b")
    # 文字列以外が混じっている（ネストしたlistは辞書のキーにできない）
    assert [e["id"] for e in flask_app._ordered_form_entries(
        entries, ["b", ["x"], None, 3, {"y": 1}])] == ["b", "a"]
    # 配列ではなく文字列そのものが書かれている
    assert [e["id"] for e in flask_app._ordered_form_entries(
        entries, "ba")] == ["a", "b"]


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
    # 表出力にも「特記事項なし」が出るので、in では見分けられない。
    # 特記事項ページのタイトルそのもので判定する。
    assert _pdf_first_page_text(res).startswith("テスト2026年3月特記事項")


def test_api_pdf_first_page_is_remarks_with_forms(client, monkeypatch, tmp_path):
    """様式があっても、1枚目が特記事項になること"""
    c, _ = client
    _setup_forms_dir(tmp_path, monkeypatch, MONTH_LAYOUT)
    res = c.get("/api/pdf?display_year=2026&display_month=3")
    assert res.status_code == 200
    assert _pdf_first_page_text(res).startswith("テスト2026年3月特記事項")


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


# ========== バージョンとキャッシュ設定 ==========

def test_health_reports_version(client):
    """/api/health がアプリのバージョンを返すこと"""
    import app as flask_app
    c, _ = client
    body = c.get("/api/health").get_json()
    assert body["status"] == "ok"
    assert body["version"] == flask_app.APP_VERSION


def test_app_version_looks_like_a_version():
    """APP_VERSION が x.y.z の形であること"""
    import re
    import app as flask_app
    assert re.fullmatch(r"\d+\.\d+\.\d+", flask_app.APP_VERSION)


def test_static_files_are_not_cached_by_the_browser():
    """JS・CSSをブラウザに貯め込ませない設定であること。

    0 でないと、直したファイルが利用者のブラウザに届かない。
    以前はURLに ?v= を手で付けて回避していたが、上げ忘れが起きた。
    """
    import app as flask_app
    assert flask_app.app.config["SEND_FILE_MAX_AGE_DEFAULT"] == 0


def test_static_pages_have_no_version_query():
    """画面のHTMLに ?v= が残っていないこと（付け忘れの温床になるため）"""
    import app as flask_app
    for path in sorted(flask_app.static_folder.glob("*.html")):
        assert "?v=" not in path.read_text(encoding="utf-8"), path.name


# ========== 曜日の表示 ==========

class _DrawRecorder:
    """キャンバスのふりをして、呼ばれた描画命令を記録する。

    色はPDFを解析しても読み取りにくいので、描画命令を直接受け止めて確かめる。
    """
    def __init__(self):
        self.fill = None
        self.text = None
        self.circled = False

    def setFont(self, *a, **k):
        pass

    def setFillColor(self, color):
        self.fill = str(color)

    def setStrokeColor(self, color):
        pass

    def setLineWidth(self, *a, **k):
        pass

    def drawCentredString(self, x, y, text):
        self.text = text

    def drawString(self, x, y, text):
        self.text = text

    def circle(self, *a, **k):
        self.circled = True


def _slot_for(target, custom=None):
    """その日1日ぶんのスロットを作る（mark が入った状態になる）"""
    from datetime import timedelta
    import pdf_forms
    layout = {"period": "month", "axis": {"count": 1}}
    slots = pdf_forms.build_slots(layout, target.year, target.month, [target],
                                  {}, custom or {},
                                  today=target + timedelta(days=1))
    return slots[1]


def _draw_weekday(target, custom=None, field=None):
    """曜日を1つ描いて、記録した命令を返す"""
    import pdf_forms
    rec = _DrawRecorder()
    pdf_forms._draw_weekday_field(rec, field or {"source": "meta.weekday"},
                                  100.0, 500.0, _slot_for(target, custom), 9)
    return rec


def _expect_color(hex_value):
    """reportlab が受け取る色の文字列表現に直す"""
    from reportlab.lib.colors import HexColor
    return str(HexColor(hex_value))


def test_weekday_characters_match_the_day():
    """月曜から日曜まで、正しい1文字が印字されること"""
    from datetime import date
    # 2026-09-07 は月曜
    expected = ["月", "火", "水", "木", "金", "土", "日"]
    for i, want in enumerate(expected):
        d = date(2026, 9, 7 + i)
        assert _draw_weekday(d).text == want, d


def test_weekday_saturday_is_blue():
    """土曜の曜日が青になること"""
    from datetime import date
    import pdf_forms
    assert _draw_weekday(date(2026, 9, 12)).fill == _expect_color(
        pdf_forms.COLOR_SATURDAY)


def test_weekday_sunday_is_red():
    """日曜の曜日が赤になること"""
    from datetime import date
    import pdf_forms
    assert _draw_weekday(date(2026, 9, 13)).fill == _expect_color(
        pdf_forms.COLOR_HOLIDAY)


def test_weekday_national_holiday_is_red():
    """祝日の曜日が赤になること（2026-09-21 は敬老の日）"""
    from datetime import date
    import jpholiday
    import pdf_forms
    assert jpholiday.is_holiday(date(2026, 9, 21)), "前提：この日は祝日"
    assert _draw_weekday(date(2026, 9, 21)).fill == _expect_color(
        pdf_forms.COLOR_HOLIDAY)


def test_weekday_custom_holiday_is_red():
    """会社の休業日の曜日が赤になること"""
    from datetime import date
    import pdf_forms
    rec = _draw_weekday(date(2026, 9, 8), custom={"2026-09-08": "会社休日"})
    assert rec.fill == _expect_color(pdf_forms.COLOR_HOLIDAY)


def test_weekday_plain_day_is_black():
    """平日の曜日が黒になること"""
    from datetime import date
    assert _draw_weekday(date(2026, 9, 8)).fill == _expect_color("#000000")


def test_weekday_saturday_holiday_is_red():
    """土曜と休業日が重なった日は赤になること（日にちと同じ優先順位）"""
    from datetime import date
    import pdf_forms
    rec = _draw_weekday(date(2026, 9, 12), custom={"2026-09-12": "会社休日"})
    assert rec.fill == _expect_color(pdf_forms.COLOR_HOLIDAY)


def test_weekday_uses_field_color_on_plain_days():
    """平日は様式で指定した色を使うこと"""
    from datetime import date
    rec = _draw_weekday(date(2026, 9, 8),
                        field={"source": "meta.weekday", "color": "#00aa00"})
    assert rec.fill == _expect_color("#00aa00")


def test_weekday_saturday_ignores_field_color():
    """土日祝は様式の色指定より、青・赤を優先すること"""
    from datetime import date
    import pdf_forms
    rec = _draw_weekday(date(2026, 9, 12),
                        field={"source": "meta.weekday", "color": "#00aa00"})
    assert rec.fill == _expect_color(pdf_forms.COLOR_SATURDAY)


def test_weekday_draws_no_circle():
    """曜日には丸を描かないこと（丸は日にちだけ）"""
    from datetime import date
    assert _draw_weekday(date(2026, 9, 13)).circled is False


def test_weekday_blank_on_extra_cell():
    """その月に無い日（余りマス）には何も描かないこと"""
    import pdf_forms
    rec = _DrawRecorder()
    pdf_forms._draw_slot_field(rec, {"source": "meta.weekday"}, 100.0, 500.0,
                               {"exists": False, "date": None}, {}, 9)
    assert rec.text is None
    assert rec.circled is False


def test_weekday_is_dispatched_by_draw_slot_field():
    """_draw_slot_field から曜日の描画へ振り分けられること"""
    from datetime import date
    import pdf_forms
    rec = _DrawRecorder()
    pdf_forms._draw_slot_field(rec, {"source": "meta.weekday"}, 100.0, 500.0,
                               _slot_for(date(2026, 9, 13)), {}, 9)
    assert rec.text == "日"


def test_day_field_still_circles_and_colours():
    """日にちの描画が変わっていないこと（丸と色）"""
    from datetime import date
    import pdf_forms
    rec = _DrawRecorder()
    pdf_forms._draw_day_field(rec, {"source": "meta.day"}, 100.0, 500.0,
                              _slot_for(date(2026, 9, 12)), 9)
    assert rec.text == "12"
    assert rec.fill == _expect_color(pdf_forms.COLOR_SATURDAY)
    assert rec.circled is True
