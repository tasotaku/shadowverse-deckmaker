# 計画書: アンカー要求台帳の完成 → explore CLI(深掘りパイプライン)

状態: 承認済み・実行中
最終更新: 2026-07-06

## ゴール

1. **フェーズ1**: 全32アンカー(card_tag='anchor')の要求が anchor_require に永続化されている。
   `python -m svdeck.require list` で32枚全部が表示され、各アンカーに希少要件が1件以上
   (該当なしのアンカーは note 付きの明示行で)入っている
2. **フェーズ2**: `python -m svdeck.explore <card_id>` が1コマンドで「アンカー調書」
   (要求別供給候補・算術判定・クロージャ候補・novelty照合・LLM走査パック)を出力する

## 完成形の具体像

```
$ python -m svdeck.explore 10454120
=== アンカー調書: [10454120] 狡知の堕天司・ベリアル (ナイトメア) ===
card_note: (既存noteを表示)

--- 要求1 (event/active): 進化イベントを規定回数発生させる手段 deadline=T7
  [タグ検索] 5件: 10453110 生滅の技巧・ネハン(自動進化付与), ...
  [全文検索] 追加2件: ...
  [算術] 供給合計 8回 ≥ 要求 6回 by T7 → PASS(貪欲スケジュール: T3ネハン→...)
--- 要求2 (...): ...

=== クロージャ候補(全要求を閉じる最小セット・PP収支順) ===
1. {ネハン, X, Y} 3枚 / PP収支 PASS / novelty: meta_deck共起なし
2. ...

=== novelty照合 ===
- ペア(ベリアル×ネハン): 環境デッキ「進化NM」に同居あり → 既出壁(再浮上条件は要求台帳noteを参照)

=== LLM走査パック(タグ・全文で埋まらなかった要求) ===
要求3「◯◯」は機械検索0件。data/card_memo.txt を読み以下のクエリで走査せよ: ...
```

## スコープ

### やること（IN）
- フェーズ1: 32アンカーの要求コンパイル(既存10枚も「別の達成手段」の観点で増強)→ユーザーレビュー→`require load`
- フェーズ2: `src/svdeck/explore.py` 新規作成(はしご1〜2段の機械検索・算術チェック・クロージャ組み・novelty照合・3段目用プロンプトパック出力)
- explore のユニットテスト(tests/temp/test_explore_temp.py)

### やらないこと（OUT）
- 自動探索モード(全アンカー一括列挙・design.md §3.1従モード)
- はしご3段目のAPI自動実行(LLM走査はパック出力まで。実走査はメインセッションの仕事)
- noveltyのPMI正規化・meta.py の取得範囲拡張(デッキ一覧ページ対応)
- anchor_require のスキーマ変更・statusの自動書き換え(dead/active判断は人とメインセッション)
- アンカーの追加・除外(32枚は確定済みとして扱う)

## 技術的決定事項
- 言語: Python 3.10+ / 依存追加なし / mypy strict 準拠
- 新規ファイル: `src/svdeck/explore.py` のみ。CLI入口は `python -m svdeck.explore <card_id> [--format rotation|unlimited]`(省略時rotation)
- 再利用: タグ照合=bench.py の `_matches`/`FulfillmentMap`/`CategoryLookup`、自然増レート・PP会計=bench.py の実測レート関数、要求読込=require.py の anchor_require 参照。**bench.py のロジックは複製せず import する**(公開が必要な `_matches` 等はリネームせずそのまま import してよい)
- はしご2段目: `card.skill_text` への LIKE 検索。検索語は要求の req_tag/requirement から機械生成(タグのパラメータ部と名詞)+ fulfillment_map の supplies 語
- クロージャ組み(§6.3): 同クラス+ニュートラル・同フォーマット合法(`card.is_include_rotation`)の候補から、全active要求を閉じる3枚以内の組合せを列挙。1枚で2要求を満たすカードを優先し、蓄積型はbench会計でPP収支検査。組合せ爆発対策: 要求ごとの候補を効率順(Δ/PP)上位8枚に絞ってから直積
- **算術FAILはハードフィルタにしない(2026-07-06ユーザー指摘)**: 実測レートは既存アーキの上限で、特化構築は超えうる。調書では専用構築レート(最上位プロファイル)+供給上乗せの楽観上界で判定し、FAILでも候補を非表示にせず**不足量(あと何枚/どのレートなら届くか)を添えて表示**する。汎用レートでの不足は警告表示のみ(design.md §6.2に追記済み)
- novelty照合: meta_deck_card でアンカー×候補ペアの同居デッキを SQL 検索し結果を調書に添える(design.md §7「フィルタしない・全部見せる」に従い候補は落とさない)
- フェーズ1の要求JSON: 既存 `require dump` と同形式。req_tag はタグ文法(parse_tag が通る形)で埋められるものは必ず埋める(recheck の manual 落ちを減らす)。source は `compile-20260706`
- フェーズ1のstatus初期値: 供給検索前なので全行 `active`。dead化はロード後に recheck+人の判断で行う(既存の運用と同じ)

## 検証方針（タスク分類の結果）
- 静的チェック: `mypy src/`(strict・エラー0)
- テスト: `/test`(対象: explore の要求読込・候補列挙・クロージャ組みの各関数 + 既存 tests/temp 一式のリグレッション。実行は `python -m pytest tests/temp/ -q`)
- 目視・生成物: explore はCLIテキスト出力のため /visual-verify 不要。代わりに**実アンカー3枚(ベリアル10454120・ミルティオ10554110・リアントース10664120)で実行し、過去の手動探索の既知結論(card_note・anchor_require の既存行)と矛盾しないか司令塔が照合**する
- フェーズ1(データのみ): `require load` の戻り件数と `require list` の目視 + `require recheck` がエラーなく全行を分類すること

## ステップ（実行順）

### Step 1: コンパイル材料の準備
- 作業内容: 32アンカー分の材料ファイルを scratchpad に生成する。カードごとに skill_text・atoms_json・card_note・既存 anchor_require 行・クラス/コスト/フォーマット合法性を1ファイルにまとめる(SQLで機械抽出)
- 完了条件: 材料ファイルに32枚全員が含まれ、欠落フィールドがない
- 検証ゲート: 件数チェック(32件)+ランダム2枚の目視
- 実行担当: Sonnet
- 依存: なし

### Step 2〜5: 要求コンパイル(8枚×4バッチ)
- 作業内容: バッチごとに deep-exec へ委譲。プロンプトに **docs/rules.md 全文・design.md §5/§6・対象カードの材料(Step 1)・既存 anchor_require の全行(dead理由が別達成手段探しのヒントになる)** を含め、各アンカーの希少要件を requirement(短文)+req_type+req_tag(タグ文法)+deadline_turn+note で列挙させる。既存10枚は「既存行と別の達成手段があるか」を明示的に問う。ファンファーレ等の自動充足要件は出力しない(design.md §4.2)
- 完了条件: バッチ分の要求JSONが `require dump` 互換形式で出力され、司令塔レビュー(下記)を通過
- 検証ゲート: 司令塔が各バッチを検品——(a) req_type が4種のいずれか (b) req_tag が parse_tag を通るか確認 (c) §5目利き基準との矛盾(自動充足要件の混入・供給側視点の混入)がないか (d) card_note の既知判定と矛盾しないか
- 実行担当: deep-exec(コンパイル)+ Opus=司令塔(検品)
- 依存: Step 1(バッチ間は独立・並列可)

### Step 6: ユーザーレビュー → load → コミット
- 作業内容: 全32枚の要求一覧を整形して提示し、**ユーザーの確認を待つ**(台帳は人が確定する教師レイヤのため。ここだけ自律実行を中断してよい)。承認後 `python -m svdeck.require load` で取り込み、`require recheck` を1回回して分類が全行通ることを確認、コミット
- 完了条件: `require list` に32枚全員が表示・recheck がエラーなし・コミット済み
- 検証ゲート: load の戻り件数 + recheck 実行 + list 目視
- 実行担当: Opus(自分)
- 依存: Step 2〜5

### Step 7: explore.py 骨格 + はしご1〜2段
- 作業内容: `src/svdeck/explore.py` を新規作成。anchor_require から対象カードの active/dead 要求を読み、要求ごとに (1)タグ検索=bench の `_matches` 経由 (2)skill_text LIKE 検索 の候補card_idリストを返す関数群 + 調書のテキスト整形。CLI入口(`__main__`)も付ける
- 完了条件: `python -m svdeck.explore 10454120` が要求別候補リストを出力する
- 検証ゲート: mypy + 実行して出力に既知供給(ネハン等・card_note記載)が含まれることを確認
- 実行担当: Sonnet
- 依存: Step 6

### Step 8: 算術チェック + クロージャ組み
- 作業内容: 蓄積型要求に bench.py の実測レート・PP会計を接続し PASS/FAIL と貪欲スケジュールを出力。全要求を閉じる3枚以内のクロージャ候補列挙(技術的決定事項の絞り込みルールに従う)を実装
- 完了条件: ベリアルでクロージャ候補が1件以上出力され、PP収支の根拠数字が表示される
- 検証ゲート: mypy + `/test`(クロージャ組みの単体テスト: 2要求を1枚で閉じる優先・候補8枚絞り込み・フォーマット合法フィルタ)
- 実行担当: Sonnet
- 依存: Step 7

### Step 9: novelty照合 + LLM走査パック + テスト仕上げ
- 作業内容: meta_deck_card 共起SQLを調書に接続。機械検索0件の要求について card_memo.txt への走査指示文(クエリ+対象要求)を調書末尾に出力。test_explore_temp.py を整備
- 完了条件: 調書に novelty 節と走査パック節が出る・pytest 全通過
- 検証ゲート: mypy + `python -m pytest tests/temp/ -q` 全通過
- 実行担当: Sonnet
- 依存: Step 8

### Step 10: 実アンカー3枚で照合 + 最終ゲート
- 作業内容: ベリアル・ミルティオ・リアントースで explore を実行し、既知結論(card_note・既存require行・既出壁の記録)と矛盾がないか司令塔が照合。/self-review で差分レビュー、修正、コミット
- 完了条件: 3枚の調書が既知事実と無矛盾・self-reviewの🔴なし
- 検証ゲート: /self-review + mypy + pytest 全体
- 実行担当: Opus(自分)
- 依存: Step 9

## 進捗チェックリスト（実行中に更新する）
- [x] Step 1: コンパイル材料の準備(scratchpad/anchor_materials.json・32件欠落なし)
- [x] Step 2: バッチ1(6行・検品PASS)
- [x] Step 3: バッチ2(11行・検品PASS)
- [x] Step 4: バッチ3(11行・検品PASS)
- [x] Step 5: バッチ4(8行・検品PASS)
- [ ] Step 6: ユーザーレビュー → load → コミット
- [ ] Step 7: explore.py 骨格 + はしご1〜2段
- [ ] Step 8: 算術チェック + クロージャ組み
- [ ] Step 9: novelty照合 + LLM走査パック + テスト
- [ ] Step 10: 実アンカー3枚照合 + 最終ゲート(/self-review + 全体検証)

## 詰まったときのルール
- 要求コンパイルで目利き基準の解釈に迷う(§5に無いパターン): その1枚を保留にして先へ進み、Step 6 のユーザーレビューで保留一覧として提示する。勝手に基準を新設しない
- bench.py の関数が private で import しづらい / 引数が合わない: リファクタせずそのまま import して使う。どうしても形が合わない場合のみ bench.py 側に最小の公開ラッパを足す(挙動変更禁止・既存テストで確認)
- クロージャ組みが組合せ爆発する: 候補絞り込みを8枚→5枚に下げる。それでも遅ければ直積を「1枚で複数要求を満たすカード優先の貪欲」に落として報告
- 既知結論と explore の出力が矛盾(Step 10): 原因を特定(コンパイル漏れ/検索漏れ/会計バグ)。1時間で解決しなければ矛盾内容を報告して判断を仰ぐ
- その他30分以上進まない: 現状と詰まり箇所を報告
