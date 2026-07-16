# ディレクトリ: docs/

## 目的
人が読む設計の正本と、LLMが読む抽出指示書を置く。 <!-- @confirmed 2026-07-16 -->

- `design.md` — システム設計の正本。§1.5 フォーマット公理・§5 アンカー基準・§6 マッチング・§7 novelty は毎周使う。 <!-- @confirmed 2026-07-16 -->
- `rules.md` — ゲームルール・用語の索引。公式キーワード定義はDB（ability_keyword）が正で、ここには複製しない。 <!-- @confirmed 2026-07-16 -->
- `extraction-prompt.md` — 効果分解（供給/要求タグ）のLLM向け抽出指示書。atoms.py の dump/load と対になる。 <!-- @inferred -->
- `vector-extraction-prompt.md` — 効果スキーマ（card_vschema・v5）のLLM向け抽出指示書。vectorize.py と対になる。 <!-- @inferred -->
- `pilot/` — 初期パイロット（extraction-v0）の記録。現行仕様ではなく経緯の保存。 <!-- @inferred -->
