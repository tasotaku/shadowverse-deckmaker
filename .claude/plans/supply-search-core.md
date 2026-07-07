# 計画書: 供給探索の核拡張（card_note統合＋LIKE廃止＋トークン能力伝播）

状態: 完了
最終更新: 2026-07-07

## ゴール
design.md 2026-07-07改訂の §6.1（検索の2本化）と「トークン能力の伝播」を実装する。判定できる形:
1. `python -m svdeck.memo` が出す `data/card_memo.txt` の各行が **skill_text（マークアップ除去）＋card_note** になっている（効果要約でなく）。
2. `python -m svdeck.explore <anchor>` の調書に **[全文検索]セクションが無く**、LLM走査パックが**全active要求**に付く。
3. `トークン召喚(T)`/`存在(T)` を持つカードが、**Tの供給タグを「(トークンT経由)」注記付きで**候補理由に出す（例: レミラミが `守護保持(トークンガーディアンゴーレム経由)` を持つ）。

## 完成形の具体像
```
# card_memo.txt（Step1後）: 効果要約でなく skill_text忠実＋note
10032110|ウィッチ|3|相貌の魔女・レミラミ|【ファンファーレ】「ガーディアンゴーレム」を1体出す。... / note:(あれば)

# explore 調書（Step2後）: [全文検索] 行が消え、LLM走査パックが全要求に付く
--- 要求1 (event/active): 味方フォロワーの破壊
  [タグ検索] 3件
    ...
（[全文検索] セクションは無い）
=== LLM走査パック（skill_text+card_noteコーパスを走査）===   ← 0件時だけでなく全要求ぶん

# トークン伝播（Step3後）: レミラミが守護供給として浮く
    10032110 相貌の魔女・レミラミ (コスト3) [守護保持(トークンガーディアンゴーレム経由)]
```

## スコープ
### やること（IN）
- Step1: `memo.py` を「skill_text（`<color=...>`マークアップ除去）＋card_note」コーパス生成器に作り替え
- Step2: `explore.py` から LIKE全文検索（`fulltext_search`/`_search_terms`）を除去、LLM走査パックを全active要求で常設化、クロージャはタグ検索ヒットのみで組む
- Step3: `explore.py` の候補構築で `トークン召喚(T)`/`存在(T)` のTを名前→トークンcard_id解決し、Tの供給タグを注記付きでAの間接供給に足す

### やらないこと（OUT）
- 逆方向マッチング（§6.4）・LLM走査の**API自動化**・タグ昇格フェーズ・言い換え変換表 → 別計画（design.mdには反映済み）
- explore.py に実LLM APIコールを埋め込むこと（ペーストパック踏襲で確定）
- トークン以外（is_token=0の名前指定カード）の存在伝播 → 今回はトークン限定
- 算術チェックの体数会計（連携/墓場のトークン寄与）への変更 → 既に §6.2 で別処理。今回はタグ一致の経路だけ
- fulfillment_map・rules.md・抽出プロンプトの変更

## 技術的決定事項
- 言語: Python 3.10+ / 静的型 mypy strict（既存踏襲）
- 新規ファイル: なし（memo.py・explore.py の改修のみ）
- コーパスファイル名: `data/card_memo.txt` を維持（explore の走査パック指示文が参照）。中身だけ差し替え
- skill_text クリーニング: `re.sub(r"</?color[^>]*>", "", text)` でキーワード装飾タグを除去し、`re.sub(r"\s+"," ")` で空白畳み。is_token=0 のみ対象（従来通り）
- card_note 連結: `card_note` を LEFT JOIN し、あれば ` / note:<note>` を末尾に付す
- トークン解決: `トークン召喚(X)`/`存在(X)` の param X で `card WHERE name=X AND is_token=1` を引く。複数体・未存在・自己参照は握らずスキップ（型一致の判定は既存 `_matches` に委ねる）。注記は候補の `reason` 文字列に `(トークンX経由)` を埋める
- クロージャ: `fulltext_hits` 廃止に伴い候補プールは `tag_hits` のみ。LLM走査ヒットは手動ループで人が足す（現状の人間協働モデル踏襲）
- 委譲プロンプトには本計画書・design.md §6.1・対象カードの card_note を含める（design §8-6）

## 検証方針（タスク分類の結果 = ロジック変更）
- 静的チェック: `python -m mypy src/svdeck/memo.py src/svdeck/explore.py`
- テスト: `/test`（対象: memoのマークアップ除去＋note連結／explore調書に全文検索が無く走査パックが全要求／トークン伝播で守護供給が浮く）。使い捨てテストは `tests/temp/test_*_temp.py` 形式・tmp DB自作フィクスチャ・本番`data/cards.db`を触らない
- 生成物目視: `python -m svdeck.memo` → `card_memo.txt` 先頭を確認／`python -m svdeck.explore 10113140`（殺戮のリノセウス・エルフ）で調書の形を目視

## ステップ（実行順）

### Step 1: memo.py をコーパス生成器に作り替え
- 作業内容: `build_memo` を atoms_json 入力から **skill_text＋card_note** 入力に変更。`<color=...>`除去＋空白畳み。`run()` の SQL を `SELECT c.card_id, c.name, c.class_name, c.cost, c.skill_text, n.note FROM card c LEFT JOIN card_note n USING(card_id) WHERE c.is_token=0 ORDER BY c.card_id` に。行format `cid|class|cost|name|<cleaned skill_text>[ / note:<note>]`。モジュール docstring を「効果要約でなくskill_text忠実＋note」に更新。AI_NOTE を付ける
- 完了条件: `python -m svdeck.memo` が成功し、`card_memo.txt` の行に装飾タグ`<color`が残らず、card_noteを持つカード行に` / note:`が付く（`grep -c "note:" data/card_memo.txt` ≥1、`grep -c "<color" data/card_memo.txt` =0）
- 検証ゲート: `python -m mypy src/svdeck/memo.py` PASS ＋ 上記grep2件 ＋ `/test`（build_memoのマークアップ除去・note連結の単体テスト）
- 実行担当: Sonnet（general-purpose + model sonnet）
- 依存: なし

### Step 2: LIKE全文検索の除去とLLM走査パックの常設化
- 作業内容: `explore.py` から `fulltext_search`・`_search_terms`・`_SEARCH_NOISE` を削除。`RequirementReport` の `fulltext_hits` を廃止。`build_requirement_report` は tag_search のみ（`already_hit`不要）。`format_report` の [全文検索] セクション削除・`total_hits`＝tag_hits数。`_closure_candidate_pool`・`find_closures`・`format_closures` の `+ fulltext_hits`／`not report.fulltext_hits` を tag_hits のみに。`format_scan_pack` の対象を「manual or 0件」から**全active要求**に変更し、指示文を「skill_text+card_noteコーパス(card_memo.txt)を走査」に更新。触った関数に AI_NOTE
- 完了条件: `python -m svdeck.explore 10113140` の出力に「[全文検索]」が現れず、「=== LLM走査パック」が全active要求ぶん列挙される。クロージャ節がタグ検索ヒットから成立
- 検証ゲート: `python -m mypy src/svdeck/explore.py` PASS ＋ `/test`（調書に全文検索が無い・走査パックが全active要求を含む・クロージャがtag_hitsで成立、をtmp DBフィクスチャで）＋ 上記 explore 実行の目視
- 実行担当: Sonnet（クロージャ周りの削除は司令塔が差分レビュー）
- 依存: Step 1

### Step 3: トークン能力の伝播
- 作業内容: `explore.py` に helper `_token_supply_tags(conn, token_name) -> list[tuple[str, Tag]]` を追加（name→is_token=1のcard_id→そのkind='supply'タグをparse。未存在/自己はスキップ）。`_class_filtered_candidates` で各候補の自前 supply_tags を組んだ後、`トークン召喚(X)`/`存在(X)` の各タグについて X を取り出し、`_token_supply_tags` の結果を **raw文字列に`(トークンX経由)`を付けて** supply_tags に追記。`_matched_supply_tag`→`format_candidate` の reason にその注記が出る。AI_NOTE で「なぜトークン限定で問題ないか」を1行
- 完了条件: レミラミ(10032110)を候補に含む守護系要求のexploreで、レミラミの候補行 reason に `守護保持(トークンガーディアンゴーレム経由)` が出る（もしくはtmp DBフィクスチャで A=トークン召喚(T)・T=守護保持 → Aが守護要求に伝播ヒット）
- 検証ゲート: `python -m mypy src/svdeck/explore.py` PASS ＋ `/test`（合成フィクスチャ: 生成カードAがトークンTの守護保持を経由供給として持つ）＋ 実データでの目視（レミラミ）
- 実行担当: Sonnet（新規メカニズム・名前解決のエッジケースは司令塔が検証）
- 依存: Step 2

## 進捗チェックリスト（実行中に更新する）
- [x] Step 1: memo.py コーパス化（524beb8・mypy/pytest/生成物grep PASS）
- [x] Step 2: LIKE除去＋走査パック常設化（867f3c1・mypy/pytest83件/explore目視 PASS）
- [x] Step 3: トークン能力伝播（b51e404・実データでレミラミ→守護保持伝播確認）
- [x] 追加fix: 供給候補からトークン除外（12fec84・Step3で発見した既存バグ）
- [x] 最終ゲート（/self-review🔴ゼロ + mypy 2ファイルclean + pytest 85件PASS + explore目視）
      ※ self-reviewで発見した require.py の同型トークン混入は別タスク task_b5b8caa6 に切り出し

## 詰まったときのルール
- `card_note` を持つカードがゼロ/極少でnote連結を確認できない: DBを直接引いて存在を確認（`SELECT COUNT(*) FROM card_note WHERE note IS NOT NULL`）。0なら合成フィクスチャのテストで代替し、実データ目視はskilled_textクリーニングのみで判定
- `fulltext_hits` 削除で既存テスト（test_explore_temp.py）が落ちる: そのテストは仕様変更に追随して更新する（LIKE前提のアサーションは削る）。テスト削除でなく期待値更新で対応
- トークン名の解決が多対多で曖昧（同名の非トークンがいる等）: is_token=1 に厳密に絞る。それでも複数なら全件の供給を合算（重複タグはdedup）。判定は既存 `_matches` に委ね、伝播は候補浮上（想起）に留める
- 30分以上進まない: 現状と詰まり箇所を報告して判断を仰ぐ

## スコープ外だが気づいたこと（記録用・手を出さない）
- LLM走査ヒットをクロージャ／算術に機械で還流させる仕組みは未実装（今は人が手で足す）。常設化(別計画Step)で再検討
