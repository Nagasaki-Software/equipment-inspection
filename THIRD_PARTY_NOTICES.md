# 同梱しているソフトウェアのライセンス（Third-party notices）

このリポジトリのうち、下の表のフォルダは他の作者のソフトウェアをそのまま同梱しています。
これらは、このアプリの Apache License 2.0（`LICENSE`）ではなく、それぞれのライセンスに従います。

| 名前 | 場所 | 作者 | ライセンス | ライセンス本文 |
|---|---|---|---|---|
| PDF.js | `static/pdfjs/`（`cmaps/` を除く） | Mozilla Foundation | Apache License 2.0 | [`static/pdfjs/LICENSE`](static/pdfjs/LICENSE) |
| PDF.js 同梱の文字データ（CMap） | `static/pdfjs/cmaps/` | Adobe Systems Incorporated | BSD 3-Clause | [`static/pdfjs/cmaps/LICENSE`](static/pdfjs/cmaps/LICENSE) |

PDF.js の各ファイルの先頭にある著作権表示は、変更せずに残しています。

## 初回セットアップで入る部品

`初回セットアップ.bat` は、次の部品をインターネット（PyPI）から利用者のPCにダウンロードします。
これらはこのリポジトリには含まれていません。

| 部品 | ライセンス |
|---|---|
| Flask | BSD-3-Clause |
| waitress | ZPL 2.1 |
| filelock | MIT |
| jpholiday | MIT |
| reportlab | BSD |
| Pillow（reportlab が使う） | MIT-CMU |
| pypdf | BSD-3-Clause |
| pytest | MIT |

（各部品のライセンスは、それぞれの配布元の表示が正となります。上の表は、確認した時点の表示を写したものです。）
