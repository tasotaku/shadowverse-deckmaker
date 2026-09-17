# 盤面アルゴリズムの正解・時間・メモリを記録する

12個の固定ケースを、毎回新しい子プロセスで実行し、JSONとMarkdownの表を保存する。
相打ち、攻防の違い、大型と横展開、複数体での処理、削って止める攻撃、進化、超進化の最後の一撃、
召喚酔い、攻撃済み、空盤面、攻撃力ゼロと、5対5の性能ケースを含む。

[実行済みの比較表](evidence/combat-benchmark-recorded-20260917/report.md) と
[各回の記録](evidence/combat-benchmark-recorded-20260917/report.json) を保存した。
12ケース×2方式×2回の48測定を実施。正解照合対象の10ケース・40測定は全て一致し、5対5の8測定は正解未検証。
ランナーと盤面候補の関連33テスト、型チェック、[独立したCLI利用テスト](evidence/combat-benchmark-tests/execution/report.json) はPASS。

リポジトリ内で実行：

```powershell
.venv/Scripts/python.exe -m svdeck.combat_benchmark --list-cases
.venv/Scripts/python.exe -m svdeck.combat_benchmark --repeat 3 --output output/combat-run-001
```

保存先は新しいディレクトリを指定する。過去の記録は上書きしない。
`pip install -e .` 後は `svdeck-combat-benchmark` でも同じ操作ができる。

対象を絞り、旧全探索と同条件で比べる：

```powershell
.venv/Scripts/python.exe -m svdeck.combat_benchmark --case tall-wide --case super-finish --repeat 3 --strategy grouped --strategy exhaustive --timeout 60 --max-states 50000 --output output/combat-comparison-001
```

各試行は順番に実行する。性能を比較する時は、他の重い作業を止め、同じPC・ケース・上限・繰り返し数を使う。
ケースを追加する時は [ケース定義](../src/svdeck/data/combat_benchmark_cases.json) を参考に別JSONを作り、
`--cases PATH` で指定できる。`own`・`enemy` は `[攻撃力, 体力]`、または `attack`・`health`・
`evolved`・`attacks`・`entered_turn` などを持つ個体の配列。
`required_clear_survivors` には、敵を全処理した結果に残るべき味方の `[攻撃力, 体力]` の組合せを書く。

保存するファイル：

- `cases.json`：実際に使った入力。後でケース定義が変わっても再現できる。
- `report.json`：各ケース・方式・反復の生データ、比較正解、欠落/余分な回答数と例、再生確認範囲、
  処理時間、メモリ、探索件数、完了フラグ、エラー。Python・OS・CPU情報とコード/入力ハッシュも保存。
- `report.md`：ケースごとの正解判定、実行状態、時間中央値、最大メモリ、探索完了回数の表。

## 正解の確認

小さい10ケースは `oracle=true`。対戦エンジンで合法な全操作列を列挙し、個体の対応付けも独立に総当たりして、
残るべき終了状態の集合を作る。候補生成アルゴリズム側の状態遷移・優劣比較関数は正解作成に使わない。
全候補を再生し、表示された盤面・顔体力・EP/SEPと一致するかも検査する。
「特定の味方が残るべき」という手書きの期待条件も一部のケースに固定している。
ただし共通の対戦エンジン自体のルール不具合まで独立に保証するものではない。

5対5の2ケースは `oracle=false`。正解集合は作らず、全候補から等間隔に最大32件を再生する。
再生に成功しても正解判定は **UNVERIFIED（正解未検証）** のまま。
`replay_coverage` と `replay_indices` に全件/抽出の区別と確認した候補番号を残す。

正解判定は `PASS` / `FAIL` / `INCOMPLETE` / `UNVERIFIED` / `UNKNOWN`。
探索打切りで完全な照合ができなければ `INCOMPLETE`、正解作成や実行に失敗した場合は `UNKNOWN`。
実行状態の `PASS` は正常に計測と所定の検査を終えた意味であり、正解判定とは別の列。
総合 `PARTIAL` は未検証・打切りを含み、全件の正解保証ではない。
不正解・実行エラー・タイムアウトは終了コード1、引数不正は2、正常完了または明示した部分検証は0。

## 時間とメモリの測定範囲

時間は `analyze()` の呼出し前後。入力作成、子プロセス起動、正解作成、結果の再生、レポート保存は含めない。
メモリは解析直後にOSから取得した、その子プロセス全体の最大常駐メモリ。
Windowsでは `PeakWorkingSetSize`、Linux/macOSでは `ru_maxrss` をバイトへ統一して保存する。
Python本体、読み込んだモジュール、入力、解析中のキャッシュも含み、アルゴリズムだけの純増量ではない。
解析前の最大値も `baseline_peak_rss_bytes` に保存する。表はMiB（1,048,576バイト）表示。
正解作成は別の子プロセスで実行し、再生検査はメモリ値を確定してから実行する。

`--timeout` は子プロセスの起動・解析・再生確認を含む全実行時間の上限。
制限に達した試行は `TIMEOUT` として保存し、次へ進む。解析が完了していた場合は取得済みの時間・メモリを残し、
`phase` で再生検査中の時間切れと区別する。未取得の数値をゼロで埋めない。
記録の書込み途中に止まっても、最後に書き終えたJSONを保持する。
