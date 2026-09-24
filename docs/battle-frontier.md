# 自分の1ターン内の候補を列挙する

`svdeck.battle_frontier` は、現在の手番の中で到達できる局面を列挙します。手札を使わない、1枚だけ使う、複数枚を使う、使用順を変える、攻撃・進化を間に挟む候補を扱います。相手の応答や次ターンは探索しません。各局面で止めることができ、`end_turn` の終了時効果・次手番の開始処理・ドローは実行しません。

バリア・必殺・疾走・突進・守護、指定／ランダム／古い順の割り振りダメージ、確定除去、召喚、能力付与、スタッツ変更、繰り返しを扱います。未対応の効果を除去して計算せず、エラーで知らせます。ラストワード・誘発・クレストなど、既存の `battle_practical.validate_scope` が拒否する機能は対象外です。対戦エンジン自体の全カード対応を意味しません。

## Pythonから使う

```python
from svdeck.battle import Battle
from svdeck.battle_frontier import analyze, state_at, witness_steps
from svdeck.battle_practical import replay_branch

result = analyze(Battle(case['state'], case['cards']),
                 max_states=100000, seconds=10)
if result['complete']:
    for node in result['candidates']:
        state = state_at(result, node)
        steps = witness_steps(result, node)
        # ランダムを含む場合は、指定された出目が生じた条件での再生。
        verified = replay_branch(result['record'], steps)
```

`candidates` は盤面・資源のPareto候補です。自身の攻撃力・体力・最大体力・リーダー体力・PP・EP・SEPが全て同等以上、敵側の数値が全て同等以下となり、残り手札も全て同じ状態で保持できる結果がある場合にだけ、比較対象を除きます。余分な手札を残せる側は優越できます。能力、カード効果、進化状態、盤面の順番、個体数の違いは比較群を分けます。別々の手札を残す結果や、高攻撃／低体力と低攻撃／高体力は両方残ります。同等の停止盤面は代表1件にまとめます。

残り攻撃権・登場ターンが違う結果も別候補として残します。顔への打点と攻撃権温存は交換条件であり、一方を下位互換として除きません。将来登場する全カードに対する戦略的な下位互換の証明ではないため、履歴などの全状態を使って続けて評価するときには、全操作を含むグラフを使います。探索途中では数値比較による枝刈りを行いません。

## 学習・評価用の省メモリAPI

全操作の辺を先に保存する必要がなければ、`analyze_catalog` で全停止状態と候補を作り、評価する局面の操作・抽選分布をその都度復元できます。整数化できる入力はNumbaで処理し、対応範囲外は既存の解析へ自動的に戻ります。既存の全グラフAPIの出力形式は変わりません。

```powershell
.venv/Scripts/python.exe -m pip install -e ".[performance]"
```

```python
from svdeck.battle_frontier_catalog import analyze_catalog

catalog = analyze_catalog(battle, max_states=100000000, seconds=3600)
if catalog.complete:
    state = catalog.state_at(catalog.candidates[0])
    for choice in catalog.expand(0):
        # choice['outcomes']の全stateをprobability（有理数文字列）で平均する。
        # 観測されたstateごとに、その後の操作を選び直せる。
        print(choice['action'], choice['outcomes'])
```

`candidates` はnode番号、`state_at(node)` は局面、`witness_steps(node)` は条件付きの到達例です。`expand(node)` は各合法操作と全出目の `state`・`probability`・`draws` を返します。候補だけから好きな抽選結果を選んで期待値を計算することはできません。全停止状態を内部に保持しているので、候補整理で外れた途中局面の操作も復元できます。

`backend='reference'` は従来方式、`backend='cache'` は局所的な計算を再利用する方式、`backend='native'` はコンパイル方式の対応範囲を厳密に指定する方式です。既定の `auto` は任意依存が未導入の場合にも従来方式を使い、`stats.fallback_reason` に理由を記録します。`complete`・`enumeration_complete`・`frontier_complete`・`cutoffs` を必ず確認してください。初回のJIT準備は別途記録し、`stats.elapsed_ms` は準備・探索・表の解放・候補整理を含みます。小さい入力では初回準備の費用が支配的になります。

## ランダム結果と操作を区別する

不利な出目を除いて再正規化することはありません。操作ごとに全出目と正確な有理数確率を保存し、抽選結果を見てから選べる次の操作も残します。**抽選後の候補を、好きな確率結果を選べる手順として扱わないでください。** `witness_steps` はその局面への到達例であり、複数の経路を合計した到達確率や最適方策ではありません。

グラフの各操作は `choices = [開始node, action番号, outcomes開始位置, outcomes終了位置]` で表します。対応する `outcomes` の各行は `[到達node, probability番号, draws番号]` です。`actions`・`probabilities`・`draws` の各共有表を参照します。1操作の全outcomeの確率の和は1です。将来の期待値評価では各操作の全outcomeを平均し、操作同士を比較します。

`positions`・`players`・`zones`・`entities`・`metadata` は状態の共有表です。直接編集せず `state_at` で復元します。`expanded` は全操作を調べ終えたnode番号で、全nodeが停止候補です。盤面順・個体ID・攻撃権・手札内容・資源・公開デッキ情報を保存し、乱数seedと現対象効果では参照されない破壊履歴の順番だけを同一視します。実際の破壊順が必要なら到達例を再生します。

単独効果のスペルと基本能力だけで表せる入力は、`encoding=fixed-slots-v1` の整数表で計算します。この形式には `players` などの補助表はありませんが、`state_at`・`witness_steps` は同じように使えます。複合効果などは自動的に汎用処理へ戻します。`backend='generic'` で汎用処理を指定して比較することもできます。

Python上の大きな表は省メモリの行配列です（辺は `Rows`、整数状態は `States`）。通常の添字・slice・反復に対応します。自分でJSON保存する場合は `svdeck.battle_frontier_io.dump_graph(result, Path(...))`、`json.dumps` には同モジュールの `json_default` を `default=` に指定してください。CLI・HTTPの出力は標準JSONの配列なので、受取側に専用decoderは不要です。

## 計測CLIとHTTP

```powershell
.venv/Scripts/python.exe -X utf8 -m svdeck.battle_frontier --cases tests/fixtures/turn_frontier_cases.json --case hand_none_a_b_ab --output output/frontier-example
```

未使用の保存先に `graph.json`（全候補・全操作・全確率）と `report.json`（完了状態・時間・メモリ）を保存します。大きいケースのグラフは大容量になります。`stats.elapsed_ms` は解析時間でファイル保存は含まず、メモリはPythonプロセス全体の最大常駐量です。比較計測はケースごとに新しいCLIプロセスで行います。

既定は10万状態・10秒・1操作4096出目です。PythonとCLIでは `max_states`／`--max-states` は最大1億、`seconds`／`--seconds` は最大3600、`--max-outcomes` は最大10000まで指定できます。HTTPの時間上限は60秒のままです。整数処理のCLIは10万展開ごとにstderrへ進捗JSONを出し、最終結果だけをstdoutへ出します。大盤面の測定例は次のとおりです。

```powershell
.venv/Scripts/python.exe -X utf8 -m svdeck.battle_frontier --cases tests/fixtures/battle_lookahead_hard.json --case hard_full_board_branching_1 --max-states 100000000 --seconds 3600 --output output/frontier-hard-one
```

この5対5ケースは、既存の1000万状態・600秒という計測予算では未完了でした。その結果は上限を拡大しても完了には変わりません。より大きい予算で全数を調べる場合は、別の保存先で新しく計測します。許容上限の拡大は高速化ではなく、使用できる時間・メモリを増やすための変更です。

`POST http://localhost:8767/api/turn-frontier` も同じ結果を返します。

```json
{"record": "Battle.export()で得たオブジェクト", "options": {"max_states": 100000, "seconds": 10}}
```

`record` には文字列ではなく実際の記録オブジェクトを渡します。任意で `cursor` を指定できます。HTTPでは `seconds` は最大60秒、長い測定にはCLIを使います。現在のAI対戦の一手選択や、画面の「能力なしの盤面候補」とは別のAPIです。

状態数・時間・1操作内の抽選数の上限で停止すると `complete=false` と理由が返ります。`enumeration_complete` と `frontier_complete` で列挙・候補整理を区別します。途中の抽選分布は出力しません。上限に達した結果を「候補を全部出した」と判断してはいけません。

独立した公開Battle全列挙との状態集合・全操作・全出目・確率照合、到達例の再生は `tests/test_battle_frontier.py` で検査します。

5対5・手札6枚の2ケースは、上の拡大予算で全件完了を確認しました。約1,194万／866万状態で、保存込み約14.8／10.7分、最大常駐約6.10／4.36GiBです。即時応答用としては重い処理です。[正確性の検証・時間・メモリの記録](evidence/turn-frontier/README.md)に、元の1,000万状態上限での未完了結果も含めて保存しています。
