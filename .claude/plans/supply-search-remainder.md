# 計画書: 供給探索拡張の残り3項目（逆方向走査・言い換え変換表・タグ昇格）

状態: 完了
最終更新: 2026-07-07

## ゴール
design.md §6.1/§6.4 の残り3機能を実装する。判定できる形:
1. `python -m svdeck.reverse <card_id>` が、そのカードが型一致で満たす **active anchor_require の一覧**（アンカー名・要求文・マッチしたタグ）を出す。同クラス+ニュートラル・フォーマット合法・トークン伝播を考慮。
2. `src/svdeck/data/paraphrase_map.json`（言い換え・下位概念変換表）と `python -m svdeck.paraphrase <語>` が、口語/抽象語→システム語（タグ・公式キーワード）の対応を返す。
3. `python -m svdeck.promote` が、LLM走査で見つけた「タグ＋該当card_id群」を**提案→人確認**で `atom_tag(kind='supply')` に書き、再抽出で消えないよう `src/svdeck/data/promoted_tags.json` に永続化・再適用できる。

## 完成形の具体像
```
# Step1: 逆方向走査（供給起点）
$ PYTHONPATH=src python -m svdeck.reverse 10032110
=== 逆方向マッチング: [10032110] 相貌の魔女・レミラミ (ウィッチ) ===
供給タグ: トークン召喚(ガーディアンゴーレム), 存在(ガーディアンゴーレム), 守護保持(トークンガーディアンゴーレム経由), ...
--- 満たしうる active 要求（ウィッチ+ニュートラルのアンカー・rotation合法）---
- [アンカーX] 「<要求文>」 ← マッチ: 守護保持(トークンガーディアンゴーレム経由)
（該当なしなら「満たす active 要求なし」）

# Step2: 言い換え変換表
$ PYTHONPATH=src python -m svdeck.paraphrase 除去
除去 (hyponym) → 破壊(相手フォロワー), 消滅(相手フォロワー), バウンス(味方), 変身
$ PYTHONPATH=src python -m svdeck.paraphrase 顔詰め
顔詰め (synonym) → ダメージ(相手リーダー)

# Step3: タグ昇格（提案→確認）
$ PYTHONPATH=src python -m svdeck.promote --tag "守護付与" --cards 10032110,10234120
[提案] 守護付与 を次の2枚に付与:
  10032110 相貌の魔女・レミラミ
  10234120 アダマントアルケミスト・ノーマン
確認するには --confirm を付けて再実行（atom_tag書込 + promoted_tags.json追記）
$ PYTHONPATH=src python -m svdeck.promote --tag "守護付与" --cards 10032110,10234120 --confirm
[確定] atom_tag に2件書込 / promoted_tags.json に追記
$ PYTHONPATH=src python -m svdeck.promote --reapply   # 再抽出後に永続分を戻す
[reapply] promoted_tags.json の N件を atom_tag へ再適用
```

## スコープ
### やること（IN）
- Step1: `src/svdeck/reverse.py`（新規CLI）。explore.py から「1カードの供給タグ（トークン伝播込み）取得」を再利用ヘルパーに切り出して共用
- Step2: `src/svdeck/data/paraphrase_map.json`（新規・git追跡）＋ `src/svdeck/paraphrase.py`（ローダ・照会・CLI）。公式キーワード37語を種に初期エントリ
- Step3: `src/svdeck/promote.py`（新規CLI）＋ `src/svdeck/data/promoted_tags.json`（永続層）。提案→確認ゲート・再適用

### やらないこと（OUT）
- LLM走査の**API自動化**（ペーストパック方式のまま）・ML/ベクトル検索
- explore.py の調書フォーマット変更（逆方向は別CLI。exploreは触るのは共用ヘルパー抽出のみ）
- fulfillment_map.json の内容変更（変換表は**別ファイル**。混ぜない）
- require.py recheck へのトークン対応（別タスク task_b5b8caa6）
- 変換表の**網羅的な語彙収集**（初期種＝37キーワード＋代表的な口語10〜20語まで。以降はクエリ駆動で育てる）
- promote の GUI・バッチ大量昇格（1回1タグ＋card_id列の単位）

## 技術的決定事項
- 言語: Python 3.10+ / mypy strict / pytest（tests/temp/・gitignore）
- **Step1 逆方向**: 新モジュール `reverse.py`。explore.py の `_class_filtered_candidates` 内のトークン伝播ロジックを
  `card_supply_tags(conn, card_id) -> list[tuple[str, Tag]]`（自前supply + `トークン召喚/存在`のTのタグを注記付き伝播）に**抽出**し、`_class_filtered_candidates` はそれを呼ぶ形に薄くする（既存挙動は不変・回帰テストで担保）。reverse は全 `status='active'` の anchor_require を `anchor_require JOIN card`（アンカー名・class_name・is_include_rotation）で引き、対象カードのclass（=そのカードのclass_nameがアンカーclassと一致 or カードがニュートラル）かつフォーマット合法な要求だけを対象に、`_requirement_tag`→`fmap.classify`/`supplies_for`/`natural_rule_for`→`_matched_supply_tag` で判定。マッチしたら (アンカー, 要求, マッチタグ) を出力
- **Step2 変換表**: `paraphrase_map.json` 構造は fulfillment_map.json の流儀に寄せる:
  `{"_comment": "...", "entries": [{"term":"除去","relation":"hyponym","maps_to":["破壊(相手フォロワー)",...],"confidence":"draft","note":"..."}]}`。
  relation ∈ {synonym, hyponym}。`paraphrase.py` に `load_paraphrase_map()`（bench.load_fulfillment_map と同じ流儀）と `expand(term)->list[str]` と `__main__` の照会CLI。**seedはキーワード37語をmaps_to側のシステム語として据え、口語→それらの対応を張る**（語彙の目利きは司令塔）
- **Step3 昇格**: `promote.py`。`--tag`＋`--cards`（カンマ区切りcard_id）。`--confirm`無し=提案表示のみ（card_id→name解決して確認材料を出す）。`--confirm`=`INSERT OR IGNORE INTO atom_tag(card_id,kind,tag) VALUES(?, 'supply', ?)` 書込＋`promoted_tags.json`（`[{"card_id":..,"tag":..,"confirmed_at":..}]`）に追記。`--reapply`=json全件をatom_tagへ再適用（再抽出後の復元）。**atom_tagは派生層で再抽出で消えるため、永続の正はjson側**（design §8-8 ledger流儀）。カード存在チェック・重複追記防止
- 既存接続: bench.py（`FulfillmentMap`/`_matches`/`CategoryLookup`/`parse_tag`）、explore.py（抽出した`card_supply_tags`・`_matched_supply_tag`）、db.py（`connect`）

## 検証方針（タスク分類の結果 = ロジック＋データ生成物）
- 静的: `python -m mypy src/svdeck/reverse.py src/svdeck/paraphrase.py src/svdeck/promote.py src/svdeck/explore.py`
- テスト: `/test`（対象: 逆方向が同クラス+フォーマット合法の要求だけに一致・トークン伝播が効く／paraphrase expandがsynonym/hyponymを返す・未知語は空／promoteが確認前はDB無変更・confirmでatom_tag書込とjson追記・reapplyが冪等）。tests/temp/
- 目視・生成物: `python -m svdeck.reverse 10032110`／`python -m svdeck.paraphrase 除去`／`python -m svdeck.promote`（提案のみ→confirm→reapply）を実行し出力確認。paraphrase_map.json の中身目視

## ステップ（実行順）

### Step 1: 逆方向マッチング（供給起点）
- 作業内容: explore.py のトークン伝播を `card_supply_tags(conn, card_id)` に抽出し `_class_filtered_candidates` から呼ぶ（挙動不変）。`src/svdeck/reverse.py` 新規: 対象card_id→そのclass/フォーマット合法性を得て、全active anchor_require（`JOIN card`でアンカー名/class/rotation）を走査し、同クラス+ニュートラル・同一フォーマット合法の要求について型一致判定、満たす要求を列挙するCLI。触った関数にAI_NOTE
- 完了条件: `python -m svdeck.reverse 10032110` がレミラミの供給タグ（守護保持(トークン…経由)含む）と満たすactive要求一覧（0件なら「なし」）をエラーなく出す。既存 explore テストが全PASS（抽出リファクタで挙動不変）
- 検証ゲート: `mypy` PASS ＋ `/test`（合成フィクスチャ: 同クラスの要求にのみ一致・別クラスは除外・トークン伝播経由で一致・rotation非合法要求は除外）＋ reverse実行の目視
- 実行担当: Sonnet（抽出リファクタの挙動不変は司令塔がexplore全テストで確認）
- 依存: なし（explore.py の既存トークン伝播を前提）

### Step 2: 言い換え・下位概念変換表
- 作業内容: `paraphrase.py`（`load_paraphrase_map`/`expand`/照会CLI）と `paraphrase_map.json`（構造は技術的決定事項通り）を新規作成。seedは公式キーワード37語＋代表的な口語/抽象語（除去⊃{破壊,消滅,バウンス,変身}、顔詰め=リーダーダメージ、リアニ=リアニメイト 等10〜20語）。AI_NOTE付与
- 完了条件: `python -m svdeck.paraphrase 除去` がhyponym展開を、`python -m svdeck.paraphrase 顔詰め` がsynonym対応を返す。未知語は「該当なし」。json は mypy/ローダで読めて壊れない
- 検証ゲート: `mypy` PASS ＋ `/test`（expandがsynonym/hyponym/未知語を正しく返す・jsonロードの単体）＋ paraphrase実行と json 目視
- 実行担当: Sonnet（ローダ/CLIインフラ）＋ **Opus（seed語彙の目利き＝ゲーム知識が要る対応表の中身は司令塔が確定・レビュー）**
- 依存: なし

### Step 3: タグ昇格フェーズ（提案→人確認）
- 作業内容: `promote.py` 新規。`--tag`/`--cards`/`--confirm`/`--reapply`。confirm前は提案表示のみ（DB無変更）。confirmで atom_tag 書込＋`promoted_tags.json` 追記。reapplyでjson→atom_tag再適用。存在しないcard_id・重複はガード。AI_NOTE付与
- 完了条件: 完成形の具体像通り。`--confirm`無しでDBが変わらないこと・`--confirm`で atom_tag に入り json に残ること・`--reapply` が冪等（二重適用しない）ことを確認
- 検証ゲート: `mypy` PASS ＋ `/test`（tmp DB: 提案のみでatom_tag件数不変・confirmで+N件かつjson追記・reapply冪等・未知card_idスキップ）＋ promote実行の目視（提案→confirm→reapply）
- 実行担当: **Opus（自分）**（DBユーザレイヤ書込＝不可逆寄り・タグ層の信頼に関わるため委譲しない）
- 依存: なし（Step1/2と独立だが最後に置く＝最厳ゲート）

## 進捗チェックリスト（実行中に更新する）
- [x] Step 1: 逆方向マッチング（0405346・reverse.py＋card_supply_tags抽出・実データ目視）
- [x] Step 2: 言い換え変換表（f45cc27・paraphrase.py＋map50件・全maps_toタグ実在確認）
- [x] Step 3: タグ昇格（98ff399・promote.py＋promoted_tags.json・提案/確認/reapply）
- [x] 最終ゲート（/self-review🔴ゼロ・🟡reverse format警告をfix + mypy 4ファイルclean + pytest 103件 + 3CLI目視）

## 詰まったときのルール
- explore の伝播抽出で既存テストが落ちる: 挙動不変が原則。落ちたら抽出前後で `_class_filtered_candidates` の出力差分を取り原因特定（30分で解決しなければ抽出をやめ reverse 側に伝播ロジックを複製して報告）
- 逆方向で active 要求が多く遅い: 全アンカーのdeck_rates計算は不要（型一致だけなら measured 不要）。accumulate要求の算術は逆方向ではスキップし「型一致するか」だけ見る（量の充足は forward explore の仕事）
- promote の atom_tag と再抽出の関係で迷う: 正はjson側・atom_tagは再生成される派生層、という前提を固定（design §8-8）。atom_tagへの直書きは reapply で復元可能な範囲に留める
- 変換表の seed が主観的で決まらない: confidence=draft で入れて note に根拠を書き、確定は人レビュー（fulfillment_map の draft/confirmed 流儀を踏襲）
- その他30分以上進まない: 現状と詰まり箇所を報告

## スコープ外だが気づいたら記録
- 変換表を LLM走査パックの指示文へ自動注入する統合（今回は照会CLIまで。パックへの組込みは別途）
- promote 提案の source（どのアンカー走査で見つけたか）の記録
