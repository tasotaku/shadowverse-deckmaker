# リポジトリ: shadowverse-deckmaker

## 目的
「誰もまだ作っていない、そこそこ強いデッキの種を提案する支援システム」（Shadowverse: Worlds Beyond 用）。40枚デッキは組まず、出力は「核カード数枚＋クラス＋噛み合う理由＋勝ち筋」まで。そこから先の40枚化・実戦検証は人間の仕事。 <!-- @confirmed 2026-07-16 -->

## 全体の流れ
カードDB(826枚) → ①効果の分解(LLM) → ②マッチング(機械) → ③新規性チェック → ④出オチ足切り(LLM) → ⑤種として言語化 → 人間が40枚化・実戦検証（docs/design.md §3）。 <!-- @confirmed 2026-07-16 -->

## 原則
- 判定は機械（型一致・集合演算・算術）。LLMは分解と想起の補助だけに使う。 <!-- @confirmed 2026-07-16 -->
- 判定の主役は人。システムは候補と根拠（ヒット全件・棄却理由）を出すところまでで、目利きで完結しない。 <!-- @confirmed 2026-07-16 -->
- ドキュメントの正: 設計は docs/design.md、ゲームルールは docs/rules.md、カード固有の知見はDBの card_note。 <!-- @confirmed 2026-07-16 -->

## ディレクトリ分担
- `src/svdeck/` — 全実装（単一パッケージ）。詳細は src/svdeck/_dir.md。 <!-- @confirmed 2026-07-16 -->
- `src/svdeck/data/` — git追跡する設定・永続台帳（fulfillment_map.json / promoted_tags.json / paraphrase_map.json / anchor_require_ledger.json 等）。コードの一部として管理する。 <!-- @inferred -->
- `data/` — gitignore対象の生成物置き場（cards.db・抽出JSON・レポート・スナップショット）。権利物（カードデータ）を同梱しないための分離。 <!-- @inferred -->
- `docs/` — 設計の正本とLLM向け抽出指示書。詳細は docs/_dir.md。 <!-- @confirmed 2026-07-16 -->
- `tests/` — 恒久テスト（test_vector.py）と使い捨てテスト（temp/・gitignore対象）。詳細は tests/_dir.md。 <!-- @inferred -->

## 現在地（2026-07-16時点）
タグ全件監査（521件・58件修正）が完了。方向A（augment）の1周目は採用0で学びを記録した段階。未実装で設計だけ確定済み: フィニッシャー数値化（design.md §11.9）。 <!-- @confirmed 2026-07-16 -->
