---
source_file: src/svdeck/db.py
---

# ファイル: db.py
## 目的
プロジェクト唯一のデータ置き場（SQLiteファイル1個 = data/cards.db）の棚割りを決めるファイル。全テーブル（14個。card_vschema を足すとDB全体では15個）の形の宣言と、DBを開く関数 connect() だけを持ち、データの取得・変換・削除は一切しない。 <!-- @confirmed 2026-07-17 -->

## 要件・制約
- 1ファイル同居のリスク（消し間違い）は、テーブルを性格で4グループに分けた運用ルールで抑える: 公式の鏡写し（card等・再取得で戻るので作り直し可）／LLM変換の結果（atom_tag等・再変換で戻るので作り直し可）／ユーザーの判断（card_note・anchor_require等・戻せないので絶対に消さない）／攻略サイトの写し（meta_deck・毎回作り直す）。 <!-- @confirmed 2026-07-17 -->
- 生の効果文（card.skill_text）は恒久保存する。LLM変換は間違うので、原文が「再変換の原料」と「検証の証拠」になる。 <!-- @confirmed 2026-07-17 -->
- 「毎回作り直す」テーブルの DELETE は db.py は持たず、各取得モジュール（fetch.py / meta.py 等）が自分の責任で行う。 <!-- @confirmed 2026-07-17 -->
- 例外: card_vschema（効果構造化JSONの置き場）だけ vectorize.py 側で CREATE しており、db.py に集約されていない。意図か成り行きかは未確認。 <!-- @inferred -->
- 参照先効果（クレスト/結晶/アクセラレート/信仰）は専用テーブルでなく card 表の ref_effect_text 列（本文・「種別名(コスト): 〜」の見出し付き）で持つ。旧 specific_effect / effect_crawl の2表は2026-07-17に廃止統合（利用箇所が「同一カード分を本文へ連結」しかしておらず、帰属修正後は厳密に1カード1効果のため）。取得済みの判定は card 行の有無（fetch.py が単体APIから中身と参照先効果を同時に入れる）なので、走査記録の列・表は持たない。 <!-- @confirmed 2026-07-17 -->

## 関数: connect
### 目的
DBファイルを開き、足りないテーブルだけ作ってから接続ハンドルを返す。呼ぶ側は「DBファイルある？テーブルある？」を一切気にしなくてよい。
### 要件・制約
- 何度呼んでもデータが消えない。全テーブルを CREATE TABLE IF NOT EXISTS（無ければ作る・あれば無視）のみで作ることで担保。 <!-- @confirmed 2026-07-17 -->
- 例外として _migrate_ref_effect（旧スキーマ→card列統合の一回きり移行）だけは ALTER/UPDATE/DROP を行うが、対象は廃止済みの旧2表（specific_effect / effect_crawl）と統合途中形の列（effect_crawled_at）のみで冪等。走査記録は移さず捨てる（取得済み判定が card 行の有無に変わったため。既存DBは全カード走査済みが前提）。ユーザレイヤには触れない。全DBコピーが新スキーマに揃ったら削除してよい。 <!-- @confirmed 2026-07-17 -->
- anchor_require は不成立確定でも行を DELETE せず status='dead' に更新して残す（判定根拠を失わない・新弾後 recheck の「前はdead→今は供給あり」検出の前提）。 <!-- @confirmed 2026-07-17 -->
- DB_PATH はデフォルト引数でなく呼び出し時に解決する（def時束縛だとテストの monkeypatch が効かない）。 <!-- @inferred -->
- DB接続失敗の例外は握りつぶさず伝播（外部I/O境界）。 <!-- @inferred -->
### 方針
14個の CREATE TABLE 文を1つの文字列 _SCHEMA に集約し、開くたびに executescript（複数SQL文の一括実行）で流す。外部キー制約はSQLiteの初期状態がOFFのため開くたびONにする。 <!-- @confirmed 2026-07-17 -->
### 構成
1. DBパス定義 → anchor: "DB_PATH = Path(__file__)"
2. 棚割り宣言（4グループ14テーブル） → anchor: "CREATE TABLE IF NOT EXISTS card ("
3. 開く＋足りない棚だけ作る → anchor: "def connect("
4. 旧スキーマの一回きり移行 → anchor: "def _migrate_ref_effect("
