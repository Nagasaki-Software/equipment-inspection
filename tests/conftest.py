import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app as flask_app
    config = {
        "save_directory": "",
        "building_info": {"building_name": "テスト", "managers": []},
        "signage": {"idle_return_seconds": 30},
        "document_categories": {
            "button_count": 2,
            "categories": [
                {"label": "資料", "folder": str(tmp_path)},
                {"label": "空", "folder": ""},
            ],
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(flask_app, "CONFIG_PATH", config_path)
    # テスト間でキャッシュが残らないようリセットする
    monkeypatch.setattr(flask_app, "_config_cache", {"data": None, "mtime": 0.0})
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c, tmp_path
