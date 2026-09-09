# 案の提出時にクラスを選ぶ隔離試作

判定：機能検査 PASS。発見力の改善と本採用は未確認。

作業場所は `/tmp/sv-class-choice-prototype`、基点は `39a98e6`、
ブランチは `codex/discovery-class-choice-prototype`。設計を先に `1143f6e` へ保存した。
新しいデッキの探索・勝率評価・本番DBの変更は行っていない。

## 実装

- `start --class all` で全7クラス＋ニュートラルの合法な採用候補を同じ資料へ固定する。
  関連カード、本文、進化、参照先、主役と供給側の注記、ルール、原則、既知構築を保持する。
- 案の `class_name` で実際の一クラスを選ぶ。採用札は選んだクラス＋ニュートラルと
  固定フォーマットの両方を満たす必要がある。効果で得る札の既存の `via` 検査は維持した。
- 改訂、別評価、履歴、reportで選んだクラスを保持し、追加検索もそのクラスへ絞る。
  別クラスへ変える時は改訂0から別案を作る。
- 既知構築と全40枚の比較で複数クラスの混在を合法扱いしない。
  単一クラスの旧回答、既存の資料・追加資料・評価の仕組みはそのまま使える。
- `start --help`、全クラス資料の指示、READMEで一クラス資料と全クラス資料の違いを説明する。

## 確認範囲

全215件 PASS（既存197件＋新規18件）。最終の全文ログは `pytest-full.log`。
先行した探索関連127件のログは `pytest-discovery.log`（全7クラスとアンリミの補強前）。
型検査は既存探索の6ファイルで PASS。初回の型推論エラー1件は型の明示で修正し、
`mypy-initial.log` と最終の `mypy.log` に残した。

| グループ | 実際に確認した振る舞い | 検査 |
|---|---|---|
| 正常 | 同じ固定資料からウィッチとドラゴンの別案を保存 | 新規テスト・公開CLI |
| 正常 | 全7クラス、原文・両側注記・関連札・既知例を保持 | 新規テスト |
| 正常 | 選んだクラスと共通札だけを追加検索 | 新規テスト・公開CLI |
| 正常 | 単一クラスのclass_nameなし旧回答を受理 | 既存・新規テスト・公開CLI |
| 正常 | 全クラスのアンリミ資料では旧札を採用可能 | 新規テスト |
| 境界 | 効果経由の他クラス札・旧札・生成専用札とvia | 既存・新規テスト・公開CLI |
| 境界 | 親0の別クラス分岐、改訂、別評価、履歴、report | 新規テスト・公開CLI |
| 境界 | 全40枚の単一クラス例と混在例を区別 | 新規テスト |
| 失敗 | 未指定・all・ニュートラル・無効値・型違いのclass_name | 新規テスト・公開CLI |
| 失敗 | 他クラス・ローテ対象外・生成専用札・未知IDの採用 | 既存・新規テスト・公開CLI |
| 失敗 | 枝の途中や評価でのクラス変更、欠けたvia | 新規テスト・公開CLI |
| 失敗 | 選んだクラスがない全クラス追加検索 | 新規テスト |

公開CLIは人工DBで24コマンドを実行し、6項目を確認した。
入出力は `cli-log.jsonl.gz`、判定は `cli-result.json`、再実行は次のコマンドで行う。

```bash
PYTHONPATH=src python evals/discovery/class-choice-prototype/run-cli.py
PYTHONPATH=src python -m pytest -q tests --ignore=tests/temp
PYTHONPATH=src python -m mypy --follow-imports=silent src/svdeck/discovery.py src/svdeck/discovery_evidence.py src/svdeck/discovery_read.py src/svdeck/discovery_sources.py src/svdeck/discovery_compare.py src/svdeck/explore.py
```

## 届け先・制約

届け先は指定の隔離ブランチ内の公開CLI。main、本番の起動環境、他の作業場所へ反映していない。
人工DBのSHA256はCLI実行前後で一致した。本番DBはこの担当の機能検査の入力に使っていない。
本番DBについては、この担当では作業開始前の識別値を採っていないため、全工程前後の一致を主張しない。

効果の取得経路は既存と同じ「資料内IDとviaの接続」の検査であり、能力の意味や手順の成立を証明しない。
既知構築の合法印は既存の札ごとの判定にクラス混在の検査を足したもので、40枚総数や採用上限の検査を
新たに全面実装したものではない。全40枚比較には既存の総数・採用上限検査を使用する。
発見力、実戦の強さ、全クラス資料を読ませるコスト、実カードでの探索成果は未検証。

時刻は `timing.json` に記録。各時刻は工程の観測点であり、その間を連続作業と断定しない。

## 単一クラス出力の互換性修正（2026-09-09）

主担当の差分確認で、単一クラスにも資料の追加指示とreportの案ごとの `class_name` が付いていた。
この2点を `all` の場合だけに限定した。単一クラスの採用制約や評価の意味は変えていない。
同じcontext・docs本文・captured_atを含む保存入力なら、単一クラスのpacket/reportは元mainと同じ出力を維持する。

テストスキルの確認対象は、正常系＝元コードとの出力一致、境界＝追加資料・親改訂・別評価後の一致、
失敗系＝既存のクラス不一致・混在・format違反の拒否を維持すること、とした。
探索関連128件 PASS、型検査6ファイル PASS。変更範囲はpacket/reportの出力条件とその回帰検査に限られるため、
今回の再実行は探索関連に絞った。上の全215件は初回試作時の結果として保持している。

元main `39a98e6` のsrcを一時領域へ展開し、同じ人工DBの保存資料を2つ複製して公開CLIへ投入した。
開始資料、分割読出し、提出、追加資料、検索、改訂、別評価、履歴、reportの13比較（26コマンド）で、
stdout文字列がすべて完全一致した。証拠は `compatibility-cli-log.jsonl.gz` と `compatibility-cli-result.json`。
テスト・型検査のログは `compatibility-pytest.log` と `compatibility-mypy.log`。

```bash
PYTHONPATH=src python evals/discovery/class-choice-prototype/run-compatibility.py
PYTHONPATH=src python -m pytest -q tests/test_discovery*.py
```

届け先は同じ隔離ブランチの公開CLI。main・本番DB・別試行は変更していない。
これは過去の人工入力による互換性検査であり、新しい自然探索や発見成果には数えない。
