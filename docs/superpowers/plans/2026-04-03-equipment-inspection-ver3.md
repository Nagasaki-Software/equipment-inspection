# equipment-inspection-ver3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** equipment-inspection_ver2（Flask設備点検+サイネージ）とdocument-post（文書掲示）を統合した一本のFlaskウェブアプリを`C:\Development\app\equipment-inspection_ver3`に構築する。

**Architecture:** equipment-inspection_ver2をベースにコピーし、ルートURLをサイネージに変更。設備点検は`/inspection`へ移動。文書掲示機能（カテゴリ→ファイル一覧→PDFビューア）を新規HTMLページ3枚+Flask APIとして追加。非アクティブタイマー（`inactivity.js`）を文書ページ用共通モジュールとして作成し、点検側の既存アイドル検知（`app.js`）とリダイレクト先を統一する。

**Tech Stack:** Python 3.x, Flask, pytest, HTML/CSS/JavaScript (ES Modules), PDF.js（既存の`/pdfjs/`を流用）

---

## ファイルマップ

| ファイル | 種別 | 内容 |
|---------|------|------|
| `app.py` | 変更 | ルート変更・文書API追加・config更新 |
| `static/signage.html` | 変更 | ナビボタン2つに変更 |
| `static/signage.css` | 変更 | ナビボタンのCSS追加 |
| `static/inspection.html` | 新規（index.htmlからコピー） | サイネージリンクのURL修正 |
| `static/app.js` | 変更 | アイドルリダイレクトURL修正＋文書カテゴリ設定追加 |
| `static/inactivity.js` | 新規 | 文書ページ用非アクティブタイマー |
| `static/documents.html` | 新規 | 文書カテゴリ画面 |
| `static/documents.js` | 新規 | カテゴリ画面JS |
| `static/documents-list.html` | 新規 | PDFファイル一覧画面 |
| `static/documents-list.js` | 新規 | ファイル一覧JS |
| `static/documents-viewer.html` | 新規 | PDFビューア画面 |
| `static/documents-viewer.js` | 新規 | PDFビューアJS（ES Module） |
| `tests/test_app.py` | 新規 | Flask APIのpytestテスト |
| `tests/conftest.py` | 新規 | テスト用フィクスチャ |

---

## Task 1: プロジェクトセットアップ（ver2ファイルのコピー）

**Files:**
- Create: `C:\Development\app\equipment-inspection_ver3\` （全体）

- [ ] **Step 1: ver2のファイルをver3にコピーする**

```bash
cd "C:/Development/app"
cp -r equipment-inspection_ver2/app.py equipment-inspection_ver3/app.py
cp -r equipment-inspection_ver2/config.json equipment-inspection_ver3/config.json
cp -r equipment-inspection_ver2/data equipment-inspection_ver3/data
mkdir -p equipment-inspection_ver3/static
cp equipment-inspection_ver2/static/signage.html equipment-inspection_ver3/static/signage.html
cp equipment-inspection_ver2/static/signage.css equipment-inspection_ver3/static/signage.css
cp equipment-inspection_ver2/static/signage.js equipment-inspection_ver3/static/signage.js
cp equipment-inspection_ver2/static/index.html equipment-inspection_ver3/static/inspection.html
cp equipment-inspection_ver2/static/inspection_only.html equipment-inspection_ver3/static/inspection_only.html
cp equipment-inspection_ver2/static/app.js equipment-inspection_ver3/static/app.js
cp equipment-inspection_ver2/static/style.css equipment-inspection_ver3/static/style.css
cp -r equipment-inspection_ver2/static/pdfjs equipment-inspection_ver3/static/pdfjs
mkdir -p equipment-inspection_ver3/tests
```

- [ ] **Step 2: ver3が起動することを確認する**

```bash
cd "C:/Development/app/equipment-inspection_ver3"
pip install flask filelock jpholiday reportlab waitress
python app.py
```

Expected: `http://localhost:5000` でver2と同じ点検画面が表示される（まだ変更前）。Ctrl+C で終了。

- [ ] **Step 3: コミット**

```bash
cd "C:/Development/app/equipment-inspection_ver3"
git init
git add app.py config.json data/ static/
git commit -m "initial: copy equipment-inspection-ver2 as ver3 base"
```

---

## Task 2: テスト環境のセットアップ

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: テスト用依存パッケージの確認**

```bash
cd "C:/Development/app/equipment-inspection_ver3"
pip install pytest
```

- [ ] **Step 2: conftest.py を作成する**

`tests/conftest.py` を新規作成：

```python
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
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c, tmp_path
```

- [ ] **Step 3: 最初のテストファイルを作成する（ルート確認）**

`tests/test_app.py` を新規作成：

```python
def test_root_redirects_or_returns_200(client):
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
```

- [ ] **Step 4: テストを実行して失敗を確認する**

```bash
cd "C:/Development/app/equipment-inspection_ver3"
pytest tests/test_app.py -v
```

Expected: FAIL（`/inspection` と `/documents` はまだ存在しない）

---

## Task 3: Flask バックエンド変更

**Files:**
- Modify: `app.py`

- [ ] **Step 1: ルート変更と文書APIのテストを追加する**

`tests/test_app.py` に追記：

```python
import json
from pathlib import Path


def test_api_documents_categories(client):
    c, _ = client
    res = c.get("/api/documents/categories")
    assert res.status_code == 200
    data = res.get_json()
    assert "button_count" in data
    assert "categories" in data


def test_api_documents_files_valid_folder(client):
    c, tmp_path = client
    # tmp_path にPDFを1つ作成
    (tmp_path / "テスト資料.pdf").write_bytes(b"%PDF-1.4")
    res = c.get(f"/api/documents/files?folder={tmp_path}")
    assert res.status_code == 200
    files = res.get_json()
    assert "テスト資料" in files  # 拡張子なし


def test_api_documents_files_empty_folder(client):
    c, _ = client
    res = c.get("/api/documents/files?folder=")
    assert res.status_code == 200
    assert res.get_json() == []


def test_api_documents_files_nonexistent_folder(client):
    c, _ = client
    res = c.get("/api/documents/files?folder=/nonexistent/path/xyz")
    assert res.status_code == 200
    assert res.get_json() == []


def test_api_documents_pdf_found(client):
    c, tmp_path = client
    (tmp_path / "資料.pdf").write_bytes(b"%PDF-1.4 test")
    res = c.get(f"/api/documents/pdf/%E8%B3%87%E6%96%99.pdf?folder={tmp_path}")
    assert res.status_code == 200
    assert res.content_type == "application/pdf"


def test_api_documents_pdf_not_found(client):
    c, tmp_path = client
    res = c.get(f"/api/documents/pdf/notexist.pdf?folder={tmp_path}")
    assert res.status_code == 404


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
```

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
pytest tests/test_app.py -v
```

Expected: 複数 FAIL

- [ ] **Step 3: app.py のルートと文書APIを追加する**

`app.py` の `@app.route("/")` 関数を変更し、新しいルートとAPIを追加する。

`app.py` の `index()` 関数（`@app.route("/")`）を探して以下に置き換え：

```python
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
```

`app.py` の `api_get_config()` の直後（`api_post_config()` 関数内）に `document_categories` の保存処理を追加する。`api_post_config` 内の `save_config(config)` の直前に以下を追加：

```python
    if "document_categories" in data:
        config["document_categories"] = data["document_categories"]
```

既存の `api_health()` ルートの後（ファイル末尾付近）に文書APIを追加：

```python
@app.route("/api/documents/categories")
def api_documents_categories():
    config = load_config()
    default = {"button_count": 3, "categories": []}
    return jsonify(config.get("document_categories", default))


@app.route("/api/documents/files")
def api_documents_files():
    folder = request.args.get("folder", "").strip()
    if not folder:
        return jsonify([])
    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify([])
    files = sorted(
        f.stem
        for f in folder_path.iterdir()
        if f.suffix.lower() == ".pdf" and f.is_file()
    )
    return jsonify(files)


@app.route("/api/documents/pdf/<filename>")
def api_documents_pdf(filename):
    folder = request.args.get("folder", "").strip()
    if not folder:
        return jsonify({"error": "folder required"}), 400
    folder_path = Path(folder)
    safe_name = Path(filename).name
    if not safe_name.lower().endswith(".pdf"):
        safe_name = safe_name + ".pdf"
    file_path = folder_path / safe_name
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(str(folder_path), safe_name, mimetype="application/pdf")
```

- [ ] **Step 4: テストを実行してすべてパスすることを確認する**

```bash
pytest tests/test_app.py -v
```

Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add app.py tests/
git commit -m "feat: add document API routes and /inspection /documents URL structure"
```

---

## Task 4: signage.html のナビゲーションボタン変更

**Files:**
- Modify: `static/signage.html`
- Modify: `static/signage.css`

- [ ] **Step 1: signage.html のボタンを2つに変更する**

`static/signage.html` の以下の行を探す（63行目付近）：

```html
        <!-- 点検システムへのボタン（常時表示） -->
        <a href="/" id="btn-to-inspection">📋 点検システムへ</a>
```

以下に置き換える：

```html
        <!-- 他システムへのナビゲーション -->
        <div id="signage-nav-btns">
            <a href="/inspection" id="btn-to-inspection">📋 点検システム</a>
            <a href="/documents" id="btn-to-documents">📄 文書掲示</a>
        </div>
```

- [ ] **Step 2: signage.css にナビボタンのスタイルを追加する**

`static/signage.css` の末尾に追記：

```css
/* ========== サイネージ ナビゲーションボタン ========== */
#signage-nav-btns {
    position: absolute;
    bottom: 24px;
    right: 20px;
    display: flex;
    flex-direction: row;
    gap: 10px;
    z-index: 10;
}

#signage-nav-btns a {
    padding: 10px 20px;
    background: rgba(26, 58, 92, 0.85);
    color: white;
    text-decoration: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    backdrop-filter: blur(4px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    letter-spacing: 0.5px;
}

#signage-nav-btns a:hover {
    background: rgba(0, 150, 214, 0.9);
}

/* 旧の単体スタイルを上書き（flexコンテナ内では position:static にする） */
#signage-nav-btns #btn-to-inspection {
    position: static;
    bottom: auto;
    right: auto;
}
```

- [ ] **Step 3: ブラウザで動作確認する**

```bash
cd "C:/Development/app/equipment-inspection_ver3"
python app.py
```

ブラウザで `http://localhost:5000` を開く。
Expected: サイネージ画面が表示され、右下に「📋 点検システム」「📄 文書掲示」が横並びで表示される。

- [ ] **Step 4: コミット**

```bash
git add static/signage.html static/signage.css
git commit -m "feat: update signage nav to two buttons (inspection + documents)"
```

---

## Task 5: inspection.html と app.js の修正

**Files:**
- Modify: `static/inspection.html`
- Modify: `static/app.js`

- [ ] **Step 1: inspection.html のサイネージリンクを修正する**

`static/inspection.html` で以下の行を探す（19行目付近）：

```html
                <a href="/signage.html" class="btn btn-secondary" id="btn-to-signage">🖥 サイネージ</a>
```

以下に置き換える：

```html
                <a href="/" class="btn btn-secondary" id="btn-to-signage">🖥 サイネージ</a>
```

- [ ] **Step 2: app.js のアイドルリダイレクト先を修正する**

`static/app.js` で以下の行を探す（1117行目付近）：

```javascript
            window.location.href = "/signage.html";
```

以下に置き換える：

```javascript
            window.location.href = "/";
```

- [ ] **Step 3: ブラウザで動作確認する**

```bash
python app.py
```

`http://localhost:5000/inspection` を開く。
Expected: 点検システムが表示され、ヘッダーの「🖥 サイネージ」ボタンをクリックすると `/` に遷移する。

- [ ] **Step 4: コミット**

```bash
git add static/inspection.html static/app.js
git commit -m "fix: update signage link and idle redirect to use root URL /"
```

---

## Task 6: inactivity.js（文書ページ用非アクティブタイマー）

**Files:**
- Create: `static/inactivity.js`

- [ ] **Step 1: inactivity.js を作成する**

`static/inactivity.js` を新規作成：

```javascript
/**
 * 文書ページ用非アクティブタイマー
 * config.signage.idle_return_seconds 秒間操作がなければ / に戻る
 */
(async function () {
    "use strict";
    let timeoutMs = 60000;
    try {
        const res = await fetch("/api/config");
        if (res.ok) {
            const cfg = await res.json();
            const secs = parseInt((cfg.signage || {}).idle_return_seconds) || 60;
            timeoutMs = Math.max(10, secs) * 1000;
        }
    } catch (_) {}

    let timer;

    function reset() {
        clearTimeout(timer);
        timer = setTimeout(function () {
            window.location.href = "/";
        }, timeoutMs);
    }

    ["mousemove", "mousedown", "keydown", "touchstart", "click", "scroll"].forEach(function (ev) {
        document.addEventListener(ev, reset, { passive: true });
    });

    reset();
}());
```

- [ ] **Step 2: コミット**

```bash
git add static/inactivity.js
git commit -m "feat: add inactivity.js for document pages (idle return to signage)"
```

---

## Task 7: 文書カテゴリ画面（documents.html + documents.js）

**Files:**
- Create: `static/documents.html`
- Create: `static/documents.js`

- [ ] **Step 1: documents.html を作成する**

`static/documents.html` を新規作成：

```html
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>文書掲示</title>
    <link rel="stylesheet" href="/style.css" />
    <style>
        #doc-main {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            flex: 1;
            padding: 40px 60px;
        }
        #categories-container {
            display: flex;
            flex-direction: column;
            gap: 16px;
            width: 100%;
            max-width: 600px;
        }
        .doc-category-btn {
            width: 100%;
            padding: 20px 32px;
            font-size: 20px;
            font-weight: bold;
            letter-spacing: 4px;
            border-radius: 12px;
            border: none;
            background-color: #0071e3;
            color: white;
            cursor: pointer;
        }
        .doc-category-btn:hover {
            background-color: #0077ed;
        }
        .doc-category-btn:disabled {
            background-color: #c7c7cc;
            color: #8e8e93;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div id="app-wrapper">
        <header id="app-header">
            <h1>文書掲示</h1>
            <div class="header-right">
                <a href="/" class="btn btn-secondary">← サイネージに戻る</a>
            </div>
        </header>
        <div id="doc-main">
            <div id="categories-container"></div>
        </div>
    </div>
    <script src="/inactivity.js"></script>
    <script src="/documents.js"></script>
</body>
</html>
```

- [ ] **Step 2: documents.js を作成する**

`static/documents.js` を新規作成：

```javascript
"use strict";

(async function () {
    let data = { button_count: 3, categories: [] };
    try {
        const res = await fetch("/api/documents/categories");
        if (res.ok) data = await res.json();
    } catch (_) {}

    const buttonCount = Math.min(Math.max(parseInt(data.button_count) || 3, 1), 5);
    const categories = data.categories || [];
    const container = document.getElementById("categories-container");

    for (let i = 0; i < buttonCount; i++) {
        const cat = categories[i] || { label: "分類" + (i + 1), folder: "" };
        const btn = document.createElement("button");
        btn.className = "doc-category-btn";
        btn.textContent = cat.label || "分類" + (i + 1);
        btn.disabled = !cat.folder;
        if (cat.folder) {
            const folder = cat.folder;
            const label = cat.label || "分類" + (i + 1);
            btn.addEventListener("click", function () {
                const params = new URLSearchParams({ folder: folder, label: label });
                window.location.href = "/documents/list?" + params.toString();
            });
        }
        container.appendChild(btn);
    }
}());
```

- [ ] **Step 3: ブラウザで動作確認する**

```bash
python app.py
```

`http://localhost:5000/documents` を開く。
Expected: カテゴリボタンが表示され、フォルダが設定されたボタンはクリック可能、未設定は灰色で無効。

- [ ] **Step 4: コミット**

```bash
git add static/documents.html static/documents.js
git commit -m "feat: add document category screen"
```

---

## Task 8: ファイル一覧画面（documents-list.html + documents-list.js）

**Files:**
- Create: `static/documents-list.html`
- Create: `static/documents-list.js`

- [ ] **Step 1: documents-list.html を作成する**

`static/documents-list.html` を新規作成：

```html
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>文書一覧</title>
    <link rel="stylesheet" href="/style.css" />
    <style>
        #file-list {
            list-style: none;
            margin: 16px 0;
            padding: 0;
        }
        .file-list-item {
            padding: 16px 20px;
            border-radius: 8px;
            font-size: 20px;
            cursor: pointer;
            border-bottom: 1px solid #d2d2d7;
        }
        .file-list-item:hover {
            background-color: #e8f0fe;
        }
        .no-files-msg {
            padding: 16px;
            color: #6e6e73;
            font-size: 16px;
        }
        #list-content {
            padding: 20px 40px;
            max-width: 800px;
            margin: 0 auto;
        }
    </style>
</head>
<body>
    <div id="app-wrapper">
        <header id="app-header">
            <h1 id="list-title">文書一覧</h1>
            <div class="header-right">
                <a id="btn-back" href="/documents" class="btn btn-secondary">← 戻る</a>
                <a href="/" class="btn btn-secondary">← サイネージ</a>
            </div>
        </header>
        <div id="list-content">
            <ul id="file-list"></ul>
        </div>
    </div>
    <script src="/inactivity.js"></script>
    <script src="/documents-list.js"></script>
</body>
</html>
```

- [ ] **Step 2: documents-list.js を作成する**

`static/documents-list.js` を新規作成：

```javascript
"use strict";

(function () {
    const params = new URLSearchParams(location.search);
    const folder = params.get("folder") || "";
    const label = params.get("label") || "文書一覧";

    document.title = label;
    const titleEl = document.getElementById("list-title");
    if (titleEl) titleEl.textContent = label;

    if (!folder) {
        const list = document.getElementById("file-list");
        const li = document.createElement("li");
        li.className = "no-files-msg";
        li.textContent = "フォルダが指定されていません";
        list.appendChild(li);
        return;
    }

    fetch("/api/documents/files?folder=" + encodeURIComponent(folder))
        .then(function (res) { return res.json(); })
        .then(function (files) {
            const list = document.getElementById("file-list");
            if (files.length === 0) {
                const li = document.createElement("li");
                li.className = "no-files-msg";
                li.textContent = "PDFファイルがありません";
                list.appendChild(li);
                return;
            }
            files.forEach(function (name) {
                const li = document.createElement("li");
                li.className = "file-list-item";
                li.textContent = name;
                li.addEventListener("click", function () {
                    const p = new URLSearchParams({
                        folder: folder,
                        file: name + ".pdf",
                        label: label,
                    });
                    window.location.href = "/documents/viewer?" + p.toString();
                });
                list.appendChild(li);
            });
        })
        .catch(function () {
            const list = document.getElementById("file-list");
            const li = document.createElement("li");
            li.className = "no-files-msg";
            li.textContent = "ファイル一覧の取得に失敗しました";
            list.appendChild(li);
        });
}());
```

- [ ] **Step 3: ブラウザで動作確認する**

```bash
python app.py
```

`http://localhost:5000/documents` でカテゴリボタンをクリックし、ファイル一覧画面が表示されることを確認。

- [ ] **Step 4: コミット**

```bash
git add static/documents-list.html static/documents-list.js
git commit -m "feat: add document file list screen"
```

---

## Task 9: PDFビューア画面（documents-viewer.html + documents-viewer.js）

**Files:**
- Create: `static/documents-viewer.html`
- Create: `static/documents-viewer.js`

- [ ] **Step 1: documents-viewer.html を作成する**

`static/documents-viewer.html` を新規作成：

```html
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>PDFビューア</title>
    <link rel="stylesheet" href="/style.css" />
    <style>
        #viewer-wrapper {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        #viewer-main {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #333;
            overflow: hidden;
            position: relative;
        }
        #pdf-canvas {
            display: block;
            cursor: grab;
        }
        #pdf-canvas:active {
            cursor: grabbing;
        }
        #page-counter {
            position: absolute;
            bottom: 10px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.5);
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 14px;
        }
        #viewer-error {
            display: none;
            color: white;
            font-size: 18px;
            text-align: center;
            padding: 40px;
        }
    </style>
</head>
<body>
    <div id="viewer-wrapper">
        <header id="app-header">
            <h1 id="viewer-title">PDF</h1>
            <div class="header-right">
                <a id="btn-back" href="/documents/list" class="btn btn-secondary">← 戻る</a>
                <a href="/" class="btn btn-secondary">← サイネージ</a>
            </div>
        </header>
        <div id="viewer-main">
            <canvas id="pdf-canvas"></canvas>
            <div id="page-counter"></div>
            <div id="viewer-error">PDFを読み込めませんでした</div>
        </div>
    </div>
    <script src="/inactivity.js"></script>
    <script type="module" src="/documents-viewer.js"></script>
</body>
</html>
```

- [ ] **Step 2: documents-viewer.js を作成する**

`static/documents-viewer.js` を新規作成：

```javascript
import * as pdfjsLib from "/pdfjs/pdf.mjs";
pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.mjs";

const params = new URLSearchParams(location.search);
const folder = params.get("folder") || "";
const file = params.get("file") || "";
const label = params.get("label") || file.replace(/\.pdf$/i, "");

document.title = label;
const titleEl = document.getElementById("viewer-title");
if (titleEl) titleEl.textContent = label;

const backBtn = document.getElementById("btn-back");
if (backBtn) {
    backBtn.href = "/documents/list?" + new URLSearchParams({ folder, label }).toString();
}

let pdfDoc = null;
let currentPage = 1;
let zoomFactor = 1.0;
const DRAG_THRESHOLD = 80;

const canvas = document.getElementById("pdf-canvas");
const ctx = canvas.getContext("2d");

function getFitZoom(page) {
    const container = document.getElementById("viewer-main");
    const vp = page.getViewport({ scale: 1.0 });
    if (vp.width === 0 || vp.height === 0) return 1.0;
    return Math.min(container.clientWidth / vp.width, container.clientHeight / vp.height) * 0.95;
}

async function renderPage(num) {
    if (!pdfDoc) return;
    const page = await pdfDoc.getPage(num);
    const scale = getFitZoom(page) * zoomFactor;
    const viewport = page.getViewport({ scale });
    const dpr = window.devicePixelRatio || 1;
    canvas.width = viewport.width * dpr;
    canvas.height = viewport.height * dpr;
    canvas.style.width = viewport.width + "px";
    canvas.style.height = viewport.height + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    await page.render({ canvasContext: ctx, viewport }).promise;
    const el = document.getElementById("page-counter");
    if (el) el.textContent = currentPage + " / " + pdfDoc.numPages;
    try { page.cleanup(); } catch (_) {}
}

function goNext() {
    if (pdfDoc && currentPage < pdfDoc.numPages) { currentPage++; renderPage(currentPage); }
}
function goPrev() {
    if (pdfDoc && currentPage > 1) { currentPage--; renderPage(currentPage); }
}

// マウスドラッグ（ページ送り）
let dragStartX = null;
canvas.addEventListener("mousedown", e => { dragStartX = e.clientX; });
canvas.addEventListener("mouseup", e => {
    if (dragStartX === null) return;
    const dx = e.clientX - dragStartX;
    dragStartX = null;
    if (dx < -DRAG_THRESHOLD) goNext();
    else if (dx > DRAG_THRESHOLD) goPrev();
});

// タッチスワイプ（ページ送り）
let touchStartX = null;
canvas.addEventListener("touchstart", e => { touchStartX = e.touches[0].clientX; }, { passive: true });
canvas.addEventListener("touchend", e => {
    if (touchStartX === null) return;
    const dx = e.changedTouches[0].clientX - touchStartX;
    touchStartX = null;
    if (Math.abs(dx) > DRAG_THRESHOLD) { dx < 0 ? goNext() : goPrev(); }
}, { passive: true });

// ホイールズーム
canvas.addEventListener("wheel", e => {
    e.preventDefault();
    zoomFactor = e.deltaY < 0
        ? Math.min(zoomFactor * 1.1, 6.0)
        : Math.max(zoomFactor * 0.9, 0.2);
    renderPage(currentPage);
}, { passive: false });

// ピンチズーム
let pinchDist = null;
canvas.addEventListener("touchstart", e => {
    if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        pinchDist = Math.sqrt(dx * dx + dy * dy);
    }
}, { passive: true });
canvas.addEventListener("touchmove", e => {
    if (e.touches.length !== 2 || !pinchDist) return;
    const dx = e.touches[0].clientX - e.touches[1].clientX;
    const dy = e.touches[0].clientY - e.touches[1].clientY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    zoomFactor = Math.max(0.2, Math.min(6.0, zoomFactor * dist / pinchDist));
    pinchDist = dist;
    renderPage(currentPage);
}, { passive: true });
canvas.addEventListener("touchend", () => { pinchDist = null; });

// リサイズ
window.addEventListener("resize", () => { renderPage(currentPage); });

// PDF読み込み
if (!folder || !file) {
    document.getElementById("viewer-error").style.display = "block";
} else {
    (async () => {
        try {
            const url = "/api/documents/pdf/" + encodeURIComponent(file)
                + "?folder=" + encodeURIComponent(folder);
            pdfDoc = await pdfjsLib.getDocument({
                url,
                cMapUrl: "/pdfjs/cmaps/",
                cMapPacked: true,
            }).promise;
            await renderPage(1);
        } catch (e) {
            console.error("PDF load error:", e);
            document.getElementById("viewer-error").style.display = "block";
        }
    })();
}
```

- [ ] **Step 3: ブラウザで動作確認する**

```bash
python app.py
```

`/documents` → カテゴリ選択 → ファイル一覧 → PDFクリック でビューアが開くことを確認。ドラッグでページ送り、ホイールで拡大縮小が動作することを確認。

- [ ] **Step 4: コミット**

```bash
git add static/documents-viewer.html static/documents-viewer.js
git commit -m "feat: add PDF viewer screen with drag page navigation and pinch/wheel zoom"
```

---

## Task 10: 設定画面への文書カテゴリ設定追加

**Files:**
- Modify: `static/inspection.html`
- Modify: `static/app.js`

- [ ] **Step 1: inspection.html の設定モーダルに文書カテゴリセクションを追加する**

`static/inspection.html` で以下を探す（222行目付近）：

```html
            <div class="modal-actions">
```

その直前に以下を挿入：

```html
            <div style="margin-bottom:18px">
                <h3 style="font-size:13px;color:#1a3a5c;margin-bottom:8px">文書掲示設定</h3>
                <div class="form-row-inline" style="margin-bottom:8px;">
                    <div class="form-row half">
                        <label>ボタン数（1〜5）</label>
                        <input type="number" id="cfg-doc-btn-count" min="1" max="5" style="width:80px;" />
                    </div>
                </div>
                <div id="cfg-doc-categories">
                    <div class="form-row-inline" style="margin-bottom:4px;">
                        <div class="form-row half"><label>ラベル 1</label><input type="text" id="cfg-doc-label-0" /></div>
                        <div class="form-row half"><label>フォルダパス</label><input type="text" id="cfg-doc-folder-0" placeholder="例: \\server\share\docs" /></div>
                    </div>
                    <div class="form-row-inline" style="margin-bottom:4px;">
                        <div class="form-row half"><label>ラベル 2</label><input type="text" id="cfg-doc-label-1" /></div>
                        <div class="form-row half"><label>フォルダパス</label><input type="text" id="cfg-doc-folder-1" placeholder="例: \\server\share\docs" /></div>
                    </div>
                    <div class="form-row-inline" style="margin-bottom:4px;">
                        <div class="form-row half"><label>ラベル 3</label><input type="text" id="cfg-doc-label-2" /></div>
                        <div class="form-row half"><label>フォルダパス</label><input type="text" id="cfg-doc-folder-2" placeholder="例: \\server\share\docs" /></div>
                    </div>
                    <div class="form-row-inline" style="margin-bottom:4px;">
                        <div class="form-row half"><label>ラベル 4</label><input type="text" id="cfg-doc-label-3" /></div>
                        <div class="form-row half"><label>フォルダパス</label><input type="text" id="cfg-doc-folder-3" placeholder="例: \\server\share\docs" /></div>
                    </div>
                    <div class="form-row-inline" style="margin-bottom:4px;">
                        <div class="form-row half"><label>ラベル 5</label><input type="text" id="cfg-doc-label-4" /></div>
                        <div class="form-row half"><label>フォルダパス</label><input type="text" id="cfg-doc-folder-4" placeholder="例: \\server\share\docs" /></div>
                    </div>
                </div>
            </div>
```

- [ ] **Step 2: app.js の openSettings() に文書カテゴリの読み込みを追加する**

`static/app.js` の `openSettings()` 関数内、`document.getElementById("settings-overlay").classList.add("open");` の直前に追加：

```javascript
    // 文書カテゴリ設定を読み込む
    const dc = state.config.document_categories || { button_count: 3, categories: [] };
    const dcBtnCountEl = document.getElementById("cfg-doc-btn-count");
    if (dcBtnCountEl) dcBtnCountEl.value = dc.button_count || 3;
    for (let i = 0; i < 5; i++) {
        const cat = (dc.categories || [])[i] || { label: "", folder: "" };
        const labelEl = document.getElementById("cfg-doc-label-" + i);
        const folderEl = document.getElementById("cfg-doc-folder-" + i);
        if (labelEl) labelEl.value = cat.label || "";
        if (folderEl) folderEl.value = cat.folder || "";
    }
```

- [ ] **Step 3: app.js の handleSettingsSave() に文書カテゴリの保存を追加する**

`static/app.js` の `handleSettingsSave()` 関数内、`const payload = {` ブロックの `signage: { ... }` の後（`};` の直前）に追加：

```javascript
        document_categories: {
            button_count: parseInt(document.getElementById("cfg-doc-btn-count")?.value) || 3,
            categories: [0, 1, 2, 3, 4].map(function (i) {
                return {
                    label: document.getElementById("cfg-doc-label-" + i)?.value.trim() || "",
                    folder: document.getElementById("cfg-doc-folder-" + i)?.value.trim() || "",
                };
            }),
        },
```

- [ ] **Step 4: app.js の initApp() に document_categories のデフォルト値処理を追加する**

`static/app.js` の `initApp()` 関数内、以下の行を探す（1009行目付近）：

```javascript
        state.config = config;
```

その直後に追加：

```javascript
        if (!state.config.document_categories) {
            state.config.document_categories = { button_count: 3, categories: [] };
        }
```

- [ ] **Step 5: ブラウザで動作確認する**

`http://localhost:5000/inspection` を開き、設定（⚙）ボタンをクリック。
Expected: 「文書掲示設定」セクションが表示され、ラベルとフォルダパスを入力して保存できる。保存後に `/documents` でカテゴリが反映されている。

- [ ] **Step 6: コミット**

```bash
git add static/inspection.html static/app.js
git commit -m "feat: add document categories configuration to settings panel"
```

---

## Task 11: 最終動作確認

- [ ] **Step 1: 全テストを実行する**

```bash
cd "C:/Development/app/equipment-inspection_ver3"
pytest tests/ -v
```

Expected: すべて PASS

- [ ] **Step 2: エンドツーエンドの動作確認**

```bash
python app.py
```

以下を順番に確認：

1. `http://localhost:5000` → サイネージ画面が表示される
2. 右下「📋 点検システム」→ `/inspection` で点検システムが開く
3. 右下「📄 文書掲示」→ `/documents` で文書カテゴリ画面が開く
4. 点検システムの設定 → 文書カテゴリを設定して保存
5. 文書掲示でカテゴリボタンをクリック → ファイル一覧が表示される
6. ファイルをクリック → PDFビューアが開く
7. ドラッグでページ送り、ホイールで拡大縮小が動作する
8. 「← 戻る」「← サイネージ」ボタンで遷移できる
9. 操作せずに idle_return_seconds 秒待つ → サイネージに戻る

- [ ] **Step 3: 最終コミット**

```bash
git add -A
git commit -m "feat: complete equipment-inspection-ver3 integration"
```
