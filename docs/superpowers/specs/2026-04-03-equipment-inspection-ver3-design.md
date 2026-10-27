# equipment-inspection_ver3 設計仕様書

作成日: 2026-04-03

## 概要

equipment-inspection_ver2（Flask製設備点検システム＋サイネージ）と document-post（PyQt6製文書掲示システム）を統合したウェブアプリケーション。

- **技術スタック**：Flask（Python）+ HTML/CSS/JS + PDF.js
- **初期画面**：サイネージ
- **統一UI**：設備点検システム（ver2）のスタイルに統一
- **ベース**：equipment-inspection_ver2 をそのまま流用し、差分のみ追加

---

## URL構成

| 画面 | URL | 備考 |
|------|-----|------|
| サイネージ | `/` | 初期画面（ver2では `/signage.html`） |
| 設備点検 | `/inspection` | ver2では `/`、URLのみ変更 |
| 文書掲示 カテゴリ | `/documents` | 新規 |
| 文書掲示 ファイル一覧 | `/documents/list` | 新規（クエリ: `?folder=...&label=...`） |
| 文書掲示 PDFビューア | `/documents/viewer` | 新規（クエリ: `?folder=...&file=...`） |

---

## 画面仕様

### 1. サイネージ画面（`/`）

- ver2の `signage.html` をベースにそのまま流用
- **変更点**：右下に横並びナビゲーションボタンを追加
  - `📋 点検システム` → `/inspection` へ遷移
  - `📄 文書掲示` → `/documents` へ遷移
- スリープモード（時刻ベース）は既存のまま維持
- 非アクティブタイマーは設置しない（スリープモードで代替）

### 2. 設備点検画面（`/inspection`）

- ver2の `index.html` + `app.js` をベースにそのまま流用
- **変更点**：
  - ヘッダーの「🖥 サイネージ」リンクを `nav.js` 共通バーに統一
  - 非アクティブタイマー（`inactivity.js`）を追加

### 3. 文書掲示 カテゴリ画面（`/documents`）

- document-post のホーム画面に相当（新規HTML）
- カテゴリボタン 1〜5個（config から取得）
- 有効なフォルダが設定されたボタンのみ活性化
- 設備点検システムのCSSスタイルに統一
- 非アクティブタイマー + 「← サイネージに戻る」ボタン

### 4. 文書掲示 ファイル一覧（`/documents/list`）

- document-post の PDFリスト画面に相当（新規HTML）
- クエリパラメータ `folder`・`label` でフォルダとタイトルを受け取る
- `/api/documents/files?folder=...` でPDFファイル一覧を取得
- 拡張子 `.pdf` を非表示（ファイル名のみ表示）
- 「← 戻る」ボタン（カテゴリ画面へ）+ 非アクティブタイマー

### 5. 文書掲示 PDFビューア（`/documents/viewer`）

- document-post の PDFViewerScreen に相当（新規HTML）
- PDF.js（既存の `/pdfjs/`）を使用
- 操作：
  - 左右スワイプ / クリック（← ›）でページ送り
  - ピンチ / ホイールで拡大縮小
- 「← 戻る」ボタン（ファイル一覧へ）+ 非アクティブタイマー

---

## 共通JSモジュール（新規）

### `static/nav.js`

全画面（点検・文書）に読み込む。「← サイネージに戻る」ボタンを生成して `body` に挿入する。

```js
// 使用例（各HTMLのbody末尾で読み込む）
// <script src="/nav.js"></script>
```

### `static/inactivity.js`

全画面（点検・文書）に読み込む。マウス移動・クリック・キー操作・タッチ操作でタイマーをリセット。設定秒数後に `/`（サイネージ）へリダイレクトする。

```js
// 使用例
// <script src="/inactivity.js"></script>
// タイムアウト値は /api/config から取得
```

---

## Flask バックエンド変更・追加

### 変更

| ルート | 提供ファイル | 内容 |
|--------|------------|------|
| `GET /` | `signage.html` | ルートをサイネージに変更（ver2では `index.html`） |
| `GET /inspection` | `inspection.html` | 点検システムを新URLで提供（新規追加） |
| `GET /documents` | `documents.html` | 文書カテゴリ画面（新規追加） |
| `GET /documents/list` | `documents-list.html` | ファイル一覧（新規追加） |
| `GET /documents/viewer` | `documents-viewer.html` | PDFビューア（新規追加） |

### 追加APIルート

```
GET /api/documents/categories
  → config["document_categories"] を返す

GET /api/documents/files?folder=<path>
  → フォルダ内のPDFファイル名一覧を返す（拡張子なし）

GET /api/documents/pdf/<filename>?folder=<path>
  → PDFファイルを返す（send_from_directory 使用）
```

---

## config.json 追加項目

```json
{
  "inactivity_timeout": 60,
  "document_categories": {
    "button_count": 3,
    "categories": [
      {"label": "カテゴリ名", "folder": "フォルダの絶対パスまたはUNCパス"},
      {"label": "カテゴリ名2", "folder": ""},
      {"label": "カテゴリ名3", "folder": ""},
      {"label": "カテゴリ名4", "folder": ""},
      {"label": "カテゴリ名5", "folder": ""}
    ]
  }
}
```

---

## 設定画面（既存パネルに追加）

設備点検システムの既存設定パネル（`index.html` 内）に以下を追加：

- **非アクティブタイムアウト**（秒）：数値入力
- **文書カテゴリ設定**：ボタン数（1〜5）＋ 各カテゴリのラベル・フォルダパス

---

## ファイル構成（差分）

```
equipment-inspection_ver3/
├── app.py                        # ver2から変更（ルート追加 + 文書API追加）
├── config.json                   # ver2から変更（inactivity_timeout, document_categories追加）
├── static/
│   ├── signage.html              # ver2から変更（ナビボタン追加）← ルート"/"で提供
│   ├── inspection.html           # ← ver2の index.html をコピー・リネーム（変更なし）
│   ├── documents.html            # 新規：文書カテゴリ画面
│   ├── documents-list.html       # 新規：PDFファイル一覧
│   ├── documents-viewer.html     # 新規：PDFビューア
│   ├── nav.js                    # 新規：共通ナビゲーション（「← サイネージに戻る」ボタン）
│   ├── inactivity.js             # 新規：非アクティブタイマー
│   ├── signage.js                # ver2からコピー（変更なし）
│   ├── app.js                    # ver2からコピー（変更なし）
│   ├── style.css                 # ver2からコピー（変更なし）
│   ├── signage.css               # ver2からコピー（変更なし）
│   └── pdfjs/                   # ver2からコピー（変更なし）
└── data/                         # ver2からコピー（変更なし）
```

---

## 非機能要件

- ネットワークパス（UNCパス: `\\server\share`）をフォルダパスとして使用可能
- PyInstallerでの実行ファイル化は ver2 と同様の手順で対応可能
- ブラウザはフルスクリーン表示を想定（1920×1080横向き）
