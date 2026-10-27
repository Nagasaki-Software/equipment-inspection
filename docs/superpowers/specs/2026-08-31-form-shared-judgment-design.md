# 様式PDF「全機器まとめ」と「対象機器欄」 設計書

**作成日:** 2026-08-31
**状態:** 未承認
**前提:** `2026-08-30-layout-followups-design.md` の実装完了後（ブランチ `feature/layout-ui`）

## 目的

同じ点検項目を持つ複数の機器（例：クレーン1・クレーン2）の点検結果を、1枚の様式PDFに収める。

いまも1つの様式に機器を複数ひも付けることはでき、機器ごとに判定欄を並べれば印字される。
しかしその方式では **判定欄が「項目数 × 機器数 × 31日」になり、紙1枚に収まらない。**

そこで紙の様式を次の形にする。

```
                        24日 25日 26日 27日 …
   点検項目C-1           ✓    ×    ×    ✓
   点検項目C-2           ✓    ✓    ✓    ✓
   点検項目C-3           ✓    ✓    ✓    ✓
  ──────────────────────────────────────────
   対象  クレーン1       ✓    ✓         ✓
         クレーン2            ✓    ✓    ✓
```

- **判定は機器をまたいで1マス。** 行が増えないので31日分が1枚に収まる
- 下の「対象」欄で、その日にどの機器を点検したかを示す。**記録から自動で判断する**（手入力はしない）
- 26日は クレーン2 だけを点検した日、と読む

判定が1マスなので、同じ日にクレーン1が✓・クレーン2が×という矛盾が起こりうる。
**その説明は備考（特記事項）に書く運用とする。**

---

## 追加する項目

`layout.json` の `fields[].source` に、2つの書き方を追加する。

| 左の一覧での表示 | source | 印字されるもの |
|---|---|---|
| 全機器まとめ／点検項目C-1 | `item:*｜点検項目C-1` | その日に記録がある機器の判定のうち、いちばん悪いもの |
| 対象機器／クレーン1 | `target:クレーン1` | その日にクレーン1の記録があれば ✓（無ければ空欄） |

（表中の `｜` は実際には半角の縦棒。既存の `item:機器名|項目名` と同じ区切り。）

`*` を機器名の位置に置く形にしたのは、`item:` として扱えば
**余りマスに「ー」を入れる規則（`_draw_slot_field`）と `mark_*` の上書きがそのまま効く**ため。
`*` は点検項目マスタの機器名として存在しえない。

### 定数は2か所に置く

```python
# forms_layout.py
ALL_TARGETS = "*"   # item:*|<項目名> の、機器名の位置に入る印
```

```javascript
// static/layout.js
const ALL_TARGETS = "*";
```

判定記号（`MARK_*`）と同じく、**片方だけ直すとズレる。**

---

## 印字の規則

### 1. 悪い順

```
 ×要取替  ＞  △修理  ＞  A要調整  ＞  ✓良  ＞  ー対象外  ＞  記録なし（空欄）
```

```python
# forms_layout.py
_SEVERITY = {
    NOT_APPLICABLE_MARK: 1,   # ー 対象外
    MARK_OK: 2,               # ✓ 良
    MARK_ADJUST: 3,           # A 要調整
    MARK_REPAIR: 4,           # △ 修理
    MARK_REPLACE: 5,          # × 要取替
}


def worst_judgment(values) -> str:
    """判定を並べて、いちばん悪いものを返す。

    知っている判定記号が1つも無ければ（数値項目など）、最後の値を返す。
    旧仕様の「○」は normalize_judgment で✓に読み替えてから比べる。
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

### 2. 数値項目

2機器分の数値を1マスに書けないため、**画面の「全機器まとめ」には数値項目を出さない。**
それでも `layout.json` に数値項目が書かれていた場合は、`worst_judgment` の
「知らない値なら最後の値」の規則で、**最後に点検した機器の値**が出る（保険）。

### 3. 備考（特記事項）

いまは同じ日に2機器を保存すると、`_index` の `slot["meta"] = payload["meta"]` により
**あとから保存したほうの備考だけが残り、もう片方が消える。**
矛盾の説明を備考に書く運用の前提が崩れるため、まとめる。

```python
def _merge_remark(notes) -> str:
    """機器ごとの備考をまとめる。

    notes は [(機器名, 備考), ...] を保存順で。
    備考を書いた機器が1つだけなら、これまでどおり機器名を付けずにそのまま返す
    （1機器だけの様式の見た目を変えないため）。
    """
    written = [(name, text) for name, text in notes if text]
    if not written:
        return ""
    if len(written) == 1:
        return written[0][1]
    return "／".join(f"{name}：{text}" for name, text in written)
```

**点検者名・所属・建物名は今回まとめない。** 今までどおり最後に保存した機器のものが出る。

### 4. 余りマス（その月に存在しない日）

| 欄 | 余りマス |
|---|---|
| 全機器まとめ | 「ー」（今の判定欄と同じ。`_draw_slot_field` の既存の規則がそのまま効く） |
| 対象機器 | 空欄（`item:` で始まらないので何も描かれない） |

---

## サーバー側の変更

### スロットに「その日に記録がある機器」を持たせる

`slot` は、その日どの機器を点検したかを知らない（`has_record` は真偽値1つだけ）。
保存順の機器名リストを足す。

| 場所 | 変更 |
|---|---|
| `_empty_slot()` | `"machines": []` を足す |
| `_index()` | 機器名を保存順で `machines` に足す（重複は入れない）。備考を `{機器名: 備考}` で集め、最後に `meta["general_remark"]` を `_merge_remark` の結果で上書きする |
| `_attach()` | `slot["machines"] = record.get("machines", [])` |
| `build_slots()` の docstring | `machines` の説明を足す |
| `build_form_writer()` の single 分岐 | 手で組み立てているスロットに `"machines": payload.get("machines", [])` を足す。**忘れると single 型の様式で対象欄と全機器まとめが黙って空になる** |

`_index()` の中身は次のとおり。`setdefault` の初期値にも `machines` と `notes` を入れる
（入れ忘れると `KeyError` で落ちる）。

```python
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
    # 備考は日付ごとに1つしか出せないので、機器ごとの記入をまとめ直す
    for slot in store.values():
        slot["meta"] = dict(slot["meta"])   # 元の payload を書き換えない
        slot["meta"]["general_remark"] = _merge_remark(
            [(name, slot["notes"].get(name, "")) for name in slot["machines"]])
    return store
```

### `_field_value()` の分岐

```python
    if source.startswith("item:"):
        body = source[5:]
        equip, _, item = body.partition("|")
        if equip == forms_layout.ALL_TARGETS:
            # その日に記録がある機器の判定を集めて、いちばん悪いものを出す
            values = [slot.get("values", {}).get(f"{m}|{item}", "")
                      for m in slot.get("machines", [])]
            return _apply_marks(field, forms_layout.worst_judgment(values))
        return _apply_marks(field, slot.get("values", {}).get(body, ""))
    if source.startswith("target:"):
        # 対象機器欄。その日に記録があればチェックを入れる。
        if source[7:] not in slot.get("machines", []):
            return ""
        return field.get("mark_target", forms_layout.MARK_OK)
```

`target:` の分岐は `remark:` の前後どちらでもよいが、**`meta.` の分岐より前**に置く。

### 試し刷り（`layout_item_names`）

いまは `item:*|C-1` の機器名を `*` として返すため、`build_sample_records` の
`equip == name` に一致せず、**試し刷りで全機器まとめの欄が空になる。**

`layout_item_names` で `*` を `layout["targets"]` の全機器に展開する。

```python
            equip, item = body.split("|", 1)
            equips = targets if equip == ALL_TARGETS else [equip]
            for e in equips:
                if (e, item) in seen:
                    continue
                seen.add((e, item))
                names.append((e, item))
```

`target:` のフィールドは、`build_sample_records` が全機器×全日付の記録を作るため
何もしなくても全マスに✓が出る。

---

## 画面（`/layout`）の変更

### 左の一覧

**機器が2つ以上ひも付いている様式でだけ**、2つのグループを既存の機器グループの前に足す。

```
 ▼ 共通
 ▼ 全機器まとめ            ← 追加
      点検項目C-1
      点検項目C-2
      点検項目C-3
 ▼ 対象機器                ← 追加
      クレーン1
      クレーン2
 ▼ クレーン1               ← 今までどおり
 ▼ クレーン2
```

「全機器まとめ」に出す項目は、次の両方を満たすものだけ。

- **2つ以上の機器が持っている**点検項目名（目的が「同じ点検項目の機器A・機器B」のため）
- **判定項目である**（`input_type` が `数値` でない）

### 「置き忘れ」の数え方

いまは全機器の全項目を置かないと「まだ置いていない項目があります」と出続ける。
**`item:*|C-1` を置いたら、その項目名を持つ全機器の `item:機器名|C-1` も置いたものとして数える。**

`renderItemList()` / `countUnplaced()` / `renderProgress()` の3か所が
それぞれ `new Set(fields.map(f => f.source))` を作っている。
**共通の関数を1つ作り、3か所ともそれを使う**（数え方がズレると警告が消えない・消えすぎる）。
左の一覧の ✓ 印も同じ関数を使うので、まとめて置いた項目には機器ごとの行にも ✓ が付く。

```javascript
/** 置いた source の集合。item:*|X は全機器の item:機器|X も置いたものとして数える。 */
function placedSourceSet() {
    const placed = new Set();
    const targets = (state.layout && state.layout.targets) || [];
    for (const f of ((state.layout && state.layout.fields) || [])) {
        placed.add(f.source);
        if (!f.source.startsWith("item:")) continue;
        const body = f.source.slice(5);
        const bar = body.indexOf("|");
        if (bar < 0 || body.slice(0, bar) !== ALL_TARGETS) continue;
        const item = body.slice(bar + 1);
        for (const name of targets) placed.add(`item:${name}|${item}`);
    }
    return placed;
}
```

### 右パネル（変更しない）

**いまの右パネルには判定記号（`mark_ok` など）を編集する欄が無い。**
記号の上書きは `layout.json` に直接書く運用で、画面からは触らない設計になっている。
対象欄のチェック文字（`mark_target`）だけ画面に出すと不統一になるため、**右パネルは変更しない。**

項目名の表示（「全機器まとめ／点検項目C-1」など）は `collectItems()` の結果を引いて
決めているので、左の一覧にグループを足せば**自動で正しい名前になる。**

### 版数

`?v=15` → `?v=16` に **4か所すべて**上げる。
`layout.html` の css と js、`layout.js` の中の `layout-wizard.js?v=` と `layout-preview.js?v=`。

---

## プレビュー（`layout-preview.js`）

サーバーと同じ規則にする。**片方だけ直すとプレビューが嘘をつく。**

| source | 実在するマス | 余りマス | 直す必要 |
|---|---|---|---|
| `item:*｜項目名` | `mark_ok`（既定 ✓） | `mark_na`（既定 ー） | **不要**（後述） |
| `target:機器名` | `mark_target`（既定 ✓） | 空欄 | 分岐を1つ足す |

`item:*|項目名` は既存のコードのままで正しく動く。`sampleValue()` の `item:` の分岐は
**縦棒より後ろ（点検項目名）しか見ていない**ため、機器名の位置が `*` でも同じ結果になる。
余りマスの「ー」も `source.startsWith("item:")` で判定しているのでそのまま効く。

`target:` は `item:` で始まらないので、余りマスは何も描かれない（空欄）。
実在するマスの分岐だけを足す。

プレビューは全機器・全日に点検があった前提の見本を描くので、
**全機器まとめは常に ✓、対象機器は全マスに ✓** になる。
`mark_*` の上書きは**空文字も尊重する**（既存の規則と同じ）。

---

## 変えないもの

- **既存の様式の見た目と出力。** 新しい source を置いたときだけ動く
- 1機器だけの様式の備考（`_merge_remark` は1機器なら素通し）
- 点検画面・表出力（HTML）・CSV・保存されるJSONの形
- ポート5000・締め日区切り・`utf-8-sig`

## 対象外（今回やらないこと）

- 点検者名・所属・建物名を機器ごとにまとめること
- 数値項目を「全機器まとめ」に出すこと
- 点検項目ごとの備考（`remark:`）を機器をまたいでまとめること（矛盾の説明は共通の備考欄に書く運用のため）
- 「機器ごと複製」の入力窓（`prompt()`）の作り直し（別途）
- 対象欄に「点検していない機器」を示す記号を出すこと（空欄とする）

## 検証方法

### pytest（追加するテスト）

1. 全機器まとめ：クレーン1=✓・クレーン2=× の日に **×** が出る
2. 全機器まとめ：4段階すべての組み合わせで悪いほうが出る。`ー` は `✓` より弱い
3. 全機器まとめ：旧仕様の「○」が✓として比べられる
4. 対象機器：記録がある機器の欄にだけ ✓ が出る
5. 対象機器：余りマスは空欄、全機器まとめは「ー」
6. 備考：2機器とも書いたら「クレーン1：…／クレーン2：…」。1機器だけならそのまま
7. single 型の様式でも対象欄と全機器まとめが出る
8. 試し刷りで全機器まとめの欄が埋まる
9. **既存の様式（`sample_daily`）の出力が変わらない**

### 実機（テストだけでは足りない）

- ブラウザで2機器の様式を作り、左の一覧に2グループが出ること
- 「全機器まとめ」を置いたら置き忘れの警告が消えること
- **試し刷りのPDFを実際に開いて、対象欄と判定欄を目で見る**
- 実データ（クレーン1=✓／クレーン2=×）で本番のPDFを出し、× が出ること
