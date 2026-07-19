---
source_file: src/svdeck/vectorize.py
---

# ファイル: vectorize.py
## 目的
効果スキーマ v5（design.md §11.10）の入出力＋検証CLI。「意味の翻訳＝LLM／算数＝ルール」の分業のうちLLM側の受け口で、抽出そのものはLLMが docs/vector-extraction-prompt.md（指示書）に従って行い、本モジュールは LLM入力JSONの書き出し（dump）・抽出結果の形式検証（check/validate）・card_vschema 表への取り込み（load）・確認表示（show）を担う。閉じたスキーマ（決められた語彙）をコードで検証してLLM出力のドリフトを明示的に炙り出す＝silentに落とさない。826枚抽出済みの card_vschema が層4の資産で、その唯一の入口。 <!-- @confirmed 2026-07-16 -->

## 要件・制約
- 検証は足切りでなく炙り出し: load は違反があっても保存し（欠落させない）、違反内容を標準出力へ全件列挙する。人が違反一覧を見て指示書か抽出結果を直す運用。 <!-- @confirmed 2026-07-19 -->
- 閉じた語彙は冒頭の定数集合（種類9種 KIND・対象 TARGET・範囲 RANGE_TYPE・除去 REMOVAL・資源 RESOURCE 等）が正。未知値は検証エラーになる＝LLMドリフト検出。 <!-- @confirmed 2026-07-19 -->
- dump は参照先効果（card.ref_effect_text）を同梱する。無いとクレスト持ち69枚のスキーマがクレスト欄空で抽出される（2026-07-16追加）。2026-07-17のスキーマ統合後は card 表の列を読むだけで、LLM入力のキー名「参照先効果」は据え置き。 <!-- @inferred -->
- load は card_id が card 表に存在しなければ例外で止める（check は自己検証用にDBへ触らず、存在チェックもしない。load が最終防衛）。 <!-- @inferred -->
- card_vschema の CREATE TABLE（表の新規作成）だけがこのファイル（_ensure_table）にあり、db.py の棚割り集約に入っていない。意図でなく成り行き（開発者確認）。将来 db.py へ移してよい（db.py.md の同項と対）。 <!-- @confirmed 2026-07-19 -->
- 取り込みは1カード単位の DELETE→INSERT（再抽出で常に最新1行に置き換わる）。extracted_at と抽出モデル名を残す。 <!-- @inferred -->

## 関数: dump
### 目的
抽出のLLM入力となるカード情報（能力値・本文・参照先効果）をJSON文字列で返す。card_id 指定が無ければ全カード。atoms.py の dump と同形式。 <!-- @confirmed 2026-07-19 -->
### 構成
1. カード読取と参照先効果の同梱 → anchor: "def dump("

## 関数: validate
### 目的
カード1枚分の抽出結果が v5 スキーマに沿うかを検査し、エラー文のリストを返す（空＝合格）。card_id の型・自身（フォロワー=攻体+特性／アミュレット=特性のみ／スペル=null）・効果リストの各エントリ（種類が9種の語彙内か・条件がリストか）を見る。 <!-- @confirmed 2026-07-19 -->
### 構成
1. 自身と効果リストの検査 → anchor: "def validate("

## 関数: _validate_effect
### 目的
効果エントリ1つを種類別に検査する（登場=経路必須／処理=対象・範囲・効果と変化（置き換え・条件必須）／随伴／リソース（生成種別・変化可）／手札処理・デッキ処理／クレスト／資源／その他=自由記述必須）。分岐は種類で機械的。 <!-- @inferred -->
### 構成
1. 種類別の分岐 → anchor: "def _validate_effect("

## 関数: _ensure_table
### 目的
card_vschema 表（card_id 主キー・スキーマJSON・抽出モデル名・抽出日時）を無ければ作る。db.py に集約されていない唯一の CREATE TABLE（上記の要件・制約参照）。 <!-- @inferred -->
### 構成
1. 表の作成 → anchor: "def _ensure_table("

## 関数: load
### 目的
抽出結果JSON（配列）を検証して card_vschema へ取り込み、（合格数, 違反あり数）を返す。違反は弾かず保存しつつ標準出力へ列挙する（silent禁止）。card 表に無い card_id は例外で停止。commit は全件処理後に1回。 <!-- @confirmed 2026-07-19 -->
### 構成
1. 検証と取り込みループ → anchor: "def load("

## 関数: check
### 目的
抽出結果JSONをDBに触らず検証だけする（バッチ抽出でサブエージェントが自己検証する用）。違反件数を返し、内容を標準出力へ列挙。 <!-- @confirmed 2026-07-19 -->
### 構成
1. 検証ループ → anchor: "def check("

## 関数: show
### 目的
取り込み済みスキーマを整形して返す（無ければ未取り込みメッセージ）。人手の確認用。 <!-- @confirmed 2026-07-19 -->
### 構成
1. 読取と整形 → anchor: "def show("

## 関数: main
### 目的
CLI入口（dump / check / load / show の4サブコマンド）。引数不正は usage 表示で終了。check は違反があれば終了コード1。 <!-- @inferred -->
### 構成
1. サブコマンド分岐 → anchor: "def main("
