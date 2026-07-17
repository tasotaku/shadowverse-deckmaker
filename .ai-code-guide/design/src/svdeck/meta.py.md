---
source_file: src/svdeck/meta.py
---

# ファイル: meta.py
## 目的
攻略サイト2つ（gamewith/game8）のTier表とデッキ詳細ページから環境デッキを収集し、外部メタ層（meta_deck / meta_deck_card）へミラーする。「思いついたデッキが既出か」の照合相手を作る係で、唯一のスクレイピング（人間向けHTMLから正規表現で抜き出す）モジュール。ローテーション/アンリミテッド両フォーマットを対象にする。 <!-- @confirmed 2026-07-17 -->

## 要件・制約
- 外部メタ層は鮮度が命なので、毎回 DELETE→全INSERT で作り直す。順序は「全ページ取得成功→消す→入れる→確定」で、通信失敗時は古いデータが残る。 <!-- @inferred -->
- 「通信は成功したがサイトの構造変更でパーサが0件を返した」場合の防御は必須（開発者決定 2026-07-17）: いずれかのソースが0件なら警告して中断し、古いデータを守る。空データに気づかず既出照合に使うと偽の新規性判定を静かに量産するため、成り行きの現状（黙って空で上書き・件数報告を人が見るだけ）は不可。実装は別作業。 <!-- @confirmed 2026-07-17 -->
- スクレイピングはページ構造変更で壊れる前提。過去に game8 のアンリミページで見出し番号のズレにより0件になり、より安定した目次見出し（hl_N）区切りへ修繕した経緯がコード内コメントに残る。 <!-- @inferred -->
- 攻略サイトへの負荷対策としてリクエスト間隔 1.0 秒（公式APIの0.35秒より長め）。 <!-- @inferred -->
- サイト内を這い回らない: 入口は TIER_SOURCES（サイト×フォーマット×URLの固定4ページ）だけで、そこから先はTier表に載ったデッキ詳細ページ（環境で入れ替わるため固定不可）へのリンクのみ辿る。1回の実行は約85リクエスト×1秒。フォーマット追加は表に1行足すだけ。 <!-- @confirmed 2026-07-17 -->
- 全工程が機械的処理（検索と正規表現のみ・LLM不使用）。同じ入力なら必ず同じ結果で、壊れる時ははっきり0件になる（こっそり間違えない）性質が、既出照合データの正確さ要件に合う。LLMでの意味読みスクレイピングは模様替えに強いが、コスト・ブレ・静かな読み間違いがあるため不採用。 <!-- @confirmed 2026-07-17 -->

## 関数: _get_html
### 目的
URLへHTTPアクセスしてHTML文字列を返す通信境界。失敗は握りつぶさず伝播（fetch.py と同じ作法）。
### 構成
1. 取得と復号 → anchor: "def _get_html("

## 関数: _normalize_name
### 目的
攻略サイト表記と公式表記の揺れ（中黒「・」の有無、＆/＝の全角半角）を吸収する正規化。card.name との突き合わせ前処理。
### 構成
1. 揺れ吸収 → anchor: "def _normalize_name("

## 関数: parse_gamewith_tier
### 目的
gamewith のTier表HTMLからデッキリンク（名前・Tier・URL）を抜き出す。Tierは数値（1〜4）表記。
### 構成
1. Tier表区間の切り出しと抽出 → anchor: "def parse_gamewith_tier("

## 関数: parse_gamewith_deck
### 目的
gamewith のデッキ詳細HTMLから採用カード（名前, 枚数）と更新日を抜き出す。カード名はページ内JS辞書（サイト独自ID→名前）から引く。
### 構成
1. 更新日とデッキリスト抽出 → anchor: "def parse_gamewith_deck("

## 関数: parse_game8_tier
### 目的
game8 のTier表HTMLからデッキリンクを抜き出す。TierはSS/S/A/B/Cのバナー画像altで判定。
### 方針
区間の切り出しは細かい見出し番号（hm_N・ローテとアンリミでずれて0件事故を起こした）でなく、両ページで安定している目次の大見出し（hl_N）で行う。 <!-- @inferred -->
### 構成
1. Tier表区間の切り出しと抽出 → anchor: "def parse_game8_tier("

## 関数: parse_game8_deck
### 目的
game8 のデッキ詳細HTMLから採用カード（名前, 枚数）と更新日を抜き出す。更新日は構造が安定している記事メタ（JSON-LDのdateModified）から取る。
### 構成
1. 更新日とデッキリスト抽出 → anchor: "def parse_game8_deck("

## 関数: _resolve_card_id
### 目的
攻略サイトのカード名から公式 card 表の card_id を引く。完全一致で見つからなければ正規化して全カードと再照合し、それでも無ければ None（meta_deck_card には名前だけで残る）。
### 構成
1. 完全一致→正規化再照合 → anchor: "def _resolve_card_id("

## 関数: collect_deck_links
### 目的
TIER_SOURCES の全ページ（サイト×フォーマットの4組）を順に取得し、デッキリンクを1本のリストへ集める。
### 構成
1. ソース周回 → anchor: "def collect_deck_links("

## 関数: collect_deck_detail
### 目的
デッキリンク1件の詳細ページを取得し、サイトに応じたパーサで DeckDetail に変換する。
### 構成
1. 取得とパーサ振り分け → anchor: "def collect_deck_detail("

## 関数: run
### 目的
エントリポイント。全デッキを収集・card_id照合してから、meta_deck / meta_deck_card を DELETE→全INSERT で作り直して確定し、デッキ件数とcard_idマッチ率を報告する。
### 構成
1. Tier表からリンク収集 → anchor: "links = collect_deck_links()"
2. 詳細収集とcard_id照合 → anchor: "card_id = _resolve_card_id(conn, card_name)"
3. 作り直しと確定 → anchor: "DELETE FROM meta_deck_card"
4. マッチ率の報告 → anchor: "rate = "
