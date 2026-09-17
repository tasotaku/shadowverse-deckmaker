# 盤面アルゴリズムの正解・時間・メモリを記録する

固定ケースを毎回新しい子プロセスで実行し、正解照合・時間・メモリをJSONとMarkdownへ保存する。
難しい5対5は下の認証済みsuiteを使う。既定の12ケースは小盤面の回帰確認と従来測定用に残している。
相打ち、攻防の違い、大型と横展開、複数体での処理、削って止める攻撃、進化、超進化の最後の一撃、
召喚酔い、攻撃済み、空盤面、攻撃力ゼロと、5対5の性能ケースを含む。

2026-09-17時点の履歴として、[比較表](evidence/combat-benchmark-recorded-20260917/report.md) と
[各回の記録](evidence/combat-benchmark-recorded-20260917/report.json) を保存した。
当時は12ケース×2方式×2回の48測定を実施。正解照合対象の10ケース・40測定は全て一致し、5対5の8測定は正解未検証だった。
ランナーと盤面候補の関連33テスト、型チェック、[独立したCLI利用テスト](evidence/combat-benchmark-tests/execution/report.json) はPASS。

リポジトリ内で実行：

```powershell
.venv/Scripts/python.exe -m svdeck.combat_benchmark --list-cases
.venv/Scripts/python.exe -m svdeck.combat_benchmark --repeat 3 --output output/combat-run-001
```

保存先は新しいディレクトリを指定する。過去の記録は上書きしない。
`pip install -e .` 後は `svdeck-combat-benchmark` でも同じ操作ができる。

## 認証済みの難しい5対5を実行する

攻撃先の割当、複数体の犠牲、進化対象・タイミングを含む3ケースを
[難問入力](../tests/fixtures/combat_hard_cases.json) と
[独立に作成した全解](../tests/fixtures/combat_hard_answers.json) に保存している。
カード使用・固有能力・キーワードは含めず、基本の通常進化・超進化は残す。
`frontier` は、終了時点の比較で明確に劣るものを除いた候補集合を指す。

| ケースID | 確認する判断 | 認証済みfrontier件数 |
|---|---|---:|
| `varied-5v5` | 両陣営の攻防が全て異なる盤面での攻撃先と進化対象 | 13,483 |
| `allocation-5v5` | 処理先の競合、複数体での処理、攻撃力と体力の優劣が逆の残し方 | 14,326 |
| `timing-finisher-5v5` | 負傷・攻撃済み・召喚酔い・既存超進化と最後の一撃 | 858 |

一覧、1ケース、全3ケースの順に実行できる。保存先は未使用のディレクトリにする。

```powershell
.venv/Scripts/python.exe -X utf8 -m svdeck.combat_benchmark --cases tests/fixtures/combat_hard_cases.json --list-cases
.venv/Scripts/python.exe -X utf8 -m svdeck.combat_benchmark --cases tests/fixtures/combat_hard_cases.json --reference-file tests/fixtures/combat_hard_answers.json --case varied-5v5 --repeat 1 --output output/combat-hard-varied-001
.venv/Scripts/python.exe -X utf8 -m svdeck.combat_benchmark --cases tests/fixtures/combat_hard_cases.json --reference-file tests/fixtures/combat_hard_answers.json --repeat 1 --output output/combat-hard-all-001
```

`report.md` の「正解判定」が `PASS`、完了回数が実行回数と一致することを確認する。
単なる実行成功や候補数一致だけでは合格にならない。全候補を再生し、参照集合との欠落・余分がともに0件で、
探索が完了した場合に正解 `PASS` となる。時間とメモリは今回の出力を読む。上の件数は独立参照の値であり、性能の測定値ではない。

認証モードでは通常の3ファイルに加え、次を保存する。

- `reference.json`：利用した独立全解と生成方法・完了記録・入力とエンジンのハッシュ。
- `answers-<ケース番号>-<方式>-<反復番号>.json`：全候補の終了盤面と操作列、および全候補を再生した終了状態の署名。
  `report.md` から各ファイルを開ける。

全解を生成する [scripts/combat_reference.py](../scripts/combat_reference.py) は、製品solverの出力を使わず、
攻撃先の有限割当、実行可能な最後の攻撃者、攻撃前後の進化を列挙して独立に優劣を比較する。
小盤面では対戦エンジンの全合法操作列との全終了状態一致を確認し、難問では上表の全候補をエンジンで再生した記録を持つ。
参照ファイルは生成方法、完了フラグ、候補件数、全署名、全witness、再生件数を含む。
ベンチマークは参照の完了、入力・回答・現在の対戦エンジンのハッシュを照合してから使用する。
同じ対戦エンジンで再生するため、エンジン自体のゲームルールの誤りまで独立に証明するものではない。

参照を作り直す開発者は `.venv/Scripts/python.exe -X utf8 scripts/combat_reference.py` を実行する。
これは `tests/fixtures/combat_hard_answers.json` を更新する重い事前処理であり、通常の計測で毎回実行する必要はない。

## 同じ難問を通常HTTP APIで使う

`http://127.0.0.1:8767` が起動している環境で、公開fixtureからrequest用JSONを作る。
`make_battle(case).export()` は再生に必要な初期状態とカード定義を含むrecordを返す。

```python
import json
from pathlib import Path
from urllib.request import Request, urlopen
from svdeck import combat_benchmark as bench

cases = json.loads(Path('tests/fixtures/combat_hard_cases.json').read_text(encoding='utf-8'))
case = next(c for c in cases if c['id'] == 'timing-finisher-5v5')
record = bench.make_battle(case).export()
payload = {'record': record, 'cursor': 0, 'mode': case['mode']}
request = Request('http://127.0.0.1:8767/api/combat',
                  data=json.dumps(payload).encode('utf-8'),
                  headers={'Content-Type': 'application/json'})
with urlopen(request, timeout=60) as response:
    result = json.load(response)
```

HTTP応答の構造は [対戦AIのAPI説明](battle-ai.md) を参照する。
候補の比較には `bench.signature(candidate)` を使う。候補は `own_board`、`enemy_board`、`enemy_health`、
`ep`、`sep`、`win` を持ち、各盤面の個体には `attack`、`health`、`max_health`、`evolved` が必要。
署名は勝利なら `WIN`、それ以外は各陣営の個体の上記4値をソートした配列と相手体力・EP・SEPを含むJSON文字列。
個体IDと左右位置の違いを除いて参照の `expected` と集合比較する。
候補の再生は、応答の `record` の `actions` を候補の `actions` へ置換し、`frames=[]` にして
`POST /api/replay` へ `{record, cursor}` を送る。`cursor` はその候補の操作数とする。
通常APIで確認する時は探索予算を上書きせず、`complete=true` と全解一致を確認する。

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

既定catalogの5対5の2ケースは `oracle=false`。参照ファイルを指定しない従来の実行では、正解集合は作らず全候補から等間隔に最大32件を再生する。
再生に成功しても正解判定は **UNVERIFIED（正解未検証）** のまま。
`replay_coverage` と `replay_indices` に全件/抽出の区別と確認した候補番号を残す。
`varied-5v5` の全解検証には上の難問suiteと `--reference-file` を組み合わせる。難問suiteでは全候補を再生する。

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

標準の組合せ方式では `max_states=50000` を重複統合後の終了状態件数に適用する。
`stats.budget_unit='unique completed endpoints'` が計数単位、`states` がその件数、
`transitions` は深さ優先探索で訪れた割当枝数、`allocations` は重複統合前の終了割当数。
2026-09-17の途中状態を数える `states` や旧全探索の状態数とは単位が異なるため、数値を直接比較しない。
