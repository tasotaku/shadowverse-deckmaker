---
source_file: src/svdeck/keywords.py
---

# ファイル: keywords.py
## 目的
公式のキーワード用語辞書API（abilityKeywordList）から「ファンファーレ」等のゲーム用語の公式定義文を取得し、ability_keyword 表（ミラー層）へ保存する。ability_keyword は用語の正準定義で、推論・目利きでキーワード挙動に迷ったらこの表を引く。 <!-- @inferred -->

## 要件・制約
- 約2.6KBの小さなマスタなので、fetch.py の名称辞書（card_set/skill_name/tribe）と同じ扱いで毎回 DELETE→全INSERT で作り直す。差分更新はしない。 <!-- @inferred -->
- 取得成功後に消す順序（通信→DELETE→INSERT→commit）なので、通信失敗時は古いデータがそのまま残り、表が空になる事故は起きない。 <!-- @inferred -->
- HTTP境界の例外は握りつぶさず伝播（fetch.py / meta.py と同じ作法）。 <!-- @inferred -->

## 関数: _get_json
### 目的
URLへHTTPアクセスしてJSONを受け取るだけの通信境界。失敗は呼び出し元へ伝播。
### 構成
1. 取得と復号 → anchor: "def _get_json("

## 関数: fetch_keywords
### 目的
API応答から（用語名, 説明文）のペアのリストを取り出す。?lang=ja で日本語版を指定。
### 構成
1. 取得とペア化 → anchor: "def fetch_keywords("

## 関数: run
### 目的
エントリポイント。DBを開き、ability_keyword を DELETE→全INSERT で作り直して確定し、件数を報告する。
### 構成
1. 作り直し → anchor: "conn.execute(\"DELETE FROM ability_keyword\")"
2. 確定と報告 → anchor: "print(f\"[keywords] 完了: {len(keywords)}件\")"
