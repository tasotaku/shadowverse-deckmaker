---
source_file: src/svdeck/fetch.py
---

# ファイル: fetch.py
## 目的
公式APIから全カードを取得して card 表（ミラー層）へ保存する入口。DBが空なら全件取得、既にあれば新弾パックだけ取得、を自動で切り替える。 <!-- @inferred -->

## 要件・制約
- カードは新規だけ INSERT し、既存カードの行は書き換えない。ただしこれは意図した方針ではなく**既知の課題**: 公式の能力調整（エラッタ）を取り込めない。対応を実装すると決定（--refresh モード: 全件再取得→テキスト差分のあるカードだけ UPDATE→変更card_idを報告し、そのカードのLLM変換結果の再抽出につなげる） <!-- @confirmed 2026-07-17 -->
- ユーザレイヤ（card_note 等）には一切触れない <!-- @inferred -->
- 公式APIへの負荷対策としてリクエスト間隔 0.35 秒を空ける <!-- @inferred -->
- APIの1ページは約31〜33件と幅がブレるため、それより小さい固定歩幅（25件）で重ねて取り、重複は除いて取りこぼしを防ぐ <!-- @inferred -->

## 関数: _get_page
### 目的
一覧APIを1ページ分だけ叩くHTTP境界。card_set指定でそのパックに絞れる。例外は握りつぶさず伝播。
### 構成
1. URL組み立てと取得 → anchor: "def _get_page("

## 関数: crawl
### 目的
ページを歩幅25で重ねて末尾まで取得し、カード詳細と名称辞書（パック名・スキル名・種族名）をまとめて返す。
### 方針
窓の重なり＋重複除去で「窓幅のブレによる取りこぼし」を防ぐのが要。総件数はAPI応答の count で知る。
### 構成
1. 重ね取りループ → anchor: "while total_count is None or offset < total_count:"

## 関数: _to_row
### 目的
API応答1件を card 表の1行（辞書）へ整形する。クラス名・レア度名・種別（follower/spell/amulet）はコード内の対応表で日本語/英語名に引き直す。進化・スタイル・原文はJSON文字列のまま列に残す。
### 構成
1. 行の組み立て → anchor: "def _to_row("

## 関数: rebuild_dicts
### 目的
名称辞書3表（card_set / skill_name / tribe）を DELETE→全INSERT で作り直す。
### 方針
どのAPI応答も辞書は毎回全件くれる小さなデータなので、差分更新より作り直しが単純。
### 構成
1. 3表の作り直し → anchor: "def rebuild_dicts("

## 関数: insert_new_cards
### 目的
手元DBに無いカードだけ card / card_tribe へ INSERT し、追加枚数を返す。
### 構成
1. 既存ID集合との突き合わせ → anchor: "existing_ids = "
2. 新規のみINSERT → anchor: "def insert_new_cards("

## 関数: find_new_packs
### 目的
「APIにあって手元に無いパックID」を新弾とみなして列挙する。
### 方針
判定基準は作り直される card_set 表でなく、実際に所有するカードの card_set_id（新規追加のみで消えない）。これなら全件取得が途中で落ちても、取り損ねたパックを次回拾い直せる。
### 構成
1. 所有パックとの差分 → anchor: "def find_new_packs("

## 関数: run
### 目的
エントリポイント。card 表が空なら全件取得、あれば新弾検出→パック単位で追加取得。書き込みは最後に1回で確定（途中で落ちたら何も書かれない）。新カードが増えたときだけ、参照先効果（クレスト等）の増分取得（effects.py）を続けて回す。
### 構成
1. 空DB/新弾の自動分岐 → anchor: "if before == 0:"
2. 確定と報告 → anchor: "conn.commit()"
3. 参照先効果の増分取得 → anchor: "effects_run(conn)"
