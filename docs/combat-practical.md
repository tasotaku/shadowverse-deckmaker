# 能力・手札・ランダム効果を含む現在ターン探索

PythonやHTTPから、今のターンにどの順でカード使用・攻撃・進化を行うか調べる手順です。ランダム効果は全結果を確率付きで計算し、結果が判明した後の次の手も返します。**表示する確率は今ターン中の勝利確率であり、対戦全体の勝率ではありません。**

入口は新しいCLIと通常サーバーのAPIです。画面のボタンや自動対戦AIへの接続は含みません。従来の能力なし探索 `/api/combat` は別の入口として残ります。

## 大盤面の高速探索（2026-09-18）

両盤面の合計が7体以上で、場のフォロワーに追加効果がなく、手札が単発の指定／ランダムダメージスペルだけの場合は、整数状態を使う厳密探索へ自動で切り替わります。5種の能力、攻撃権、通常進化・超進化、PPと追加PP、抽選後の意思決定を保持します。条件付き効果・召喚・割り振り・付与など、この高速経路の対象外は従来の一般探索で処理します。

高速経路では全合法手を比較しますが、JSONには**選ばれた最適な条件別方策だけ**を保存します。`policy_scope` にその範囲を表示します。出力された全辺は通常Battleでも再生検査します。計算上の状態数は `stats.states`、出力した状態数は `stats.policy_nodes` で、両者は別です。

状態上限の省略時は一般探索10,000、高速探索500,000です。高速探索の単位は整数の計算用状態で、以前の盤面・全候補手を含む出力ノードとは異なります。`--max-states` / APIの `max_states` に整数を指定すれば両経路ともその数を上限とします（1〜1,000,000）。時間は従来どおり既定10秒です。高速経路の方策出力にも時間制限と最大10,000ノードの上限があり、打切りなら `complete=false, optimal=false` と理由を返します。任意の盤面で完了する保証はありません。

以前打ち切られた5対5の入力は、そのまま次で実行できます。ケース配列と単一ケースJSONの両方を受け付けます。

```powershell
.venv/Scripts/python.exe -X utf8 -m svdeck.battle.battle_practical --cases docs/evidence/combat-practical/stress/input.json --case mixed-keywords-5v5 --output output/practical-stress-check
```

この入力の独立した全合法手の総当たりは、今ターン勝利確率0・最適期待評価点−4でした。独立参照の再現スクリプトと計測は [大盤面検証](evidence/combat-practical-limits/validation.md) を参照してください。

## 1. サンプルを実行する

以下はリポジトリのルートで実行するWindows PowerShell例です。既存の仮想環境があれば初期設定は不要です。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e '.[dev]'
.venv/Scripts/python.exe -m svdeck.battle.battle_practical --help
.venv/Scripts/python.exe -m svdeck.battle.battle_practical --cases tests/fixtures/combat_practical_cases.json --case random-half-anchor --output docs/evidence/combat-practical/manual-half
```

保存先は**まだ存在しないディレクトリ**を指定します。再実行する場合は別の名前を使ってください。Linux/macOSでは実行ファイルを `.venv/bin/python` に読み替えます。

出力は `case.json`（入力）、`report.json`（全状態・操作・確率・条件別推奨手）、`report.md`（要約）です。この例の正確な今ターン勝利確率は `1/2` です。ランダム1ダメージが体力1の守護に当たる場合だけ、待機中の味方が相手リーダーを倒せます。もう一方の対象はそのダメージでは倒れません。

CLIは出力した**全操作の全結果**を条件付き再生で確認し、`replay.status` と `edges_checked` を保存します。これは遷移と確率の整合確認です。探索の最適性は別項目の `complete` と `optimal` を確認してください。

## 2. 何を優先するか選ぶ

| 設定 | 第1優先 | 同点時の第2優先 |
|---|---|---|
| `--objective lethal`（既定） | 今ターン勝利確率 | 仮の盤面・資源評価点の期待値 |
| `--objective value` | 仮の盤面・資源評価点の期待値 | 今ターン勝利確率 |

評価点は手作業で決めた重み付き合計です。学習済みの勝率ではありません。既定の重みは次の通りで、実際に用いた値は結果の `weights` にすべて記録します。

```json
{"leader":1,"attack":2,"health":1,"body":2,"hand":3,"pp":1,"ep":3,"sep":5,"keyword":2,"win":10000,"own_board_health":0}
```

`leader` は自分と相手のリーダー体力差、`attack`・`health`・`body`・`keyword` は盤面の攻撃力・体力・枚数・能力数について自分を加点、相手を減点します。`hand`・`pp`・`ep`・`sep` は自分の残り資源、`win` は勝利した場合の加点です。`own_board_health` は自分の盤面体力合計だけを追加加点する重みです。

`--weights` はJSONオブジェクトを受け取り、省略したキーは既定値を保ちます。各値は0〜100000の整数です。PowerShellの外部コマンドへのJSON引用符の違いを避けるため、次の例ではPythonで引数を組み立てます。

```powershell
@'
import json, subprocess, sys
weights = dict.fromkeys(["leader", "attack", "health", "body", "hand", "pp", "ep", "sep", "keyword", "win", "own_board_health"], 0)
weights["own_board_health"] = 1
for objective in ("lethal", "value"):
    subprocess.run([sys.executable, "-m", "svdeck.battle.battle_practical",
        "--cases", "tests/fixtures/combat_practical_cases.json",
        "--case", "objective-preserve-versus-win", "--objective", objective,
        "--weights", json.dumps(weights),
        "--output", "docs/evidence/combat-practical/manual-" + objective], check=True)
'@ | .venv/Scripts/python.exe -
```

この入力では、勝つには味方1体を失います。上の重みなら `lethal` は勝利確率1・評価点20の手順、`value` は操作を止めて味方体力合計21を保つ判断になります。操作を止める判断は `recommended_action: null` です。

## 3. HTTPから使う

別のターミナルで通常のサーバーを起動します。既に8767で動いている場合は、対応版が起動していることを確認してそのまま使います。

```powershell
.venv/Scripts/python.exe -m svdeck.battle.battle_server --port 8767
```

`POST http://localhost:8767/api/combat-practical` にJSONを送ります。

```json
{"record": "Battle.export()で作る記録オブジェクト", "cursor": 0, "options": {"objective":"lethal", "max_states":10000, "max_outcomes":4096, "max_depth":64, "seconds":10}}
```

上の `record` の文字列は説明用です。実際には次のようにオブジェクトを渡します。`cursor` は記録の先頭から何操作進めた状態を調べるかで、省略時は記録の末尾です。`options` も省略可能です。

```powershell
@'
import json, urllib.request
from pathlib import Path
from svdeck.battle.battle import Battle
cases = json.loads(Path("tests/fixtures/combat_practical_cases.json").read_text(encoding="utf-8"))
case = next(c for c in cases if c["id"] == "random-half-anchor")
record = Battle(case["state"], case["cards"]).export()
def post(route, payload):
    request = urllib.request.Request("http://localhost:8767" + route,
        data=json.dumps(payload).encode("utf-8"), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)
result = post("/api/combat-practical", {"record":record, "options":{"objective":"lethal"}})
with open("practical-http-result.json", "x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
print(result["win_probability_exact"], result["recommended_action"], result["complete"])
'@ | .venv/Scripts/python.exe -
```

サンプルは結果ファイルを上書きしません。再実行時は出力名を変更してください。HTTPの結果はCLIの `report.json` と共通の探索形式ですが、CLI固有の `case_id`・自動再生結果 `replay` は付与しません。

## 4. 分岐結果を読み、再生する

`policy` は局面のリストです。`root` が開始局面の番号です。各局面は `id`、全状態 `state`、要約 `position`、候補 `actions`、推奨候補の添字 `best_action`、そこで止めた評価 `stop`、推奨方針の評価 `value` を持ちます。

`best_action` が数値なら `actions[best_action]` を選びます。各候補の `action` が実際の操作で、`outcomes` は `{node, probability, draws}` のリストです。`node` は結果局面の番号、`probability` は `"1/2"` などの正確な確率、`draws` は再生用の抽選添字です。結果が判明したら該当局面へ進み、その局面の `best_action` を読みます。結果が異なれば、次の操作や対象も変わります。

`best_action: null` は現在の局面で操作列を止める判断です。`end_turn` の実行ではなく、ターン終了時効果や次ターンのドローは計算しません。評価が同点なら停止または先に見つかった候補を保ちます。

`POST /api/combat-practical-replay` は、観測した抽選結果を指定して手順を確認する入口です。抽選結果を選べるゲーム操作ではありません。

```json
{"record": "記録オブジェクト", "steps": [{"action": "操作オブジェクト", "draws": [0]}]}
```

`steps` は128操作以内です。非ランダム操作は `draws: []` とします。不足・余分・範囲外の抽選値、不正な操作や対象は拒否します。返る `probability` は指定した手順と抽選結果の条件付き確率で、`state` はその終了状態です。

HTTPだけで**返された全候補の全結果**を検査するには、上のPython例の `result`・`post` の直後に次を追加します。

```python
from fractions import Fraction
checked = 0
for node in result["policy"]:
    for choice in node["actions"]:
        total = Fraction(0)
        expected_win = Fraction(0)
        expected_value = Fraction(0)
        for edge in choice["outcomes"]:
            local_record = dict(result["record"], initial=node["state"], actions=[], frames=[])
            replayed = post("/api/combat-practical-replay", {"record":local_record,
                "steps":[{"action":choice["action"], "draws":edge["draws"]}]})
            target = result["policy"][edge["node"]]
            without_rng = lambda state: {k:v for k,v in state.items() if k != "rng"}
            assert without_rng(replayed["state"]) == without_rng(target["state"])
            probability = Fraction(edge["probability"])
            assert Fraction(replayed["probability"]) == probability
            total += probability
            expected_win += probability * Fraction(target["value"]["win_probability_exact"])
            expected_value += probability * Fraction(target["value"]["expected_value_exact"])
            checked += 1
        assert total == 1
        assert expected_win == Fraction(choice["win_probability_exact"])
        assert expected_value == Fraction(choice["expected_value_exact"])
print("全結果の再生・確率・期待値を確認:", checked)
```

抽選は候補から一様に選ぶモデルです。`rng` の隠れた固定列を未来の情報として読みません。状態比較ではその `rng` だけを除外し、個体ID・盤面順・攻撃権・体力などはすべて一致を確認します。

## 5. 対応範囲と入力の作り方

入力例は [`tests/fixtures/combat_practical_cases.json`](../tests/fixtures/combat_practical_cases.json) にあります。CLI用JSONは `{id, state, cards}` を持つオブジェクトの配列です。`description` や `expected` は補足資料で、探索への入力は `state` と `cards` です。既存例をコピーして `Battle(state, cards).export()` で検証・記録化してからHTTPへ送れます。

`cards` はカードIDから定義への対応、`state.players` は両者の状態です。盤面・手札の各個体は一意の `id` と `card_id` を持ちます。リーダー体力、PP、EP、SEP、ターン、各個体の体力・攻撃済み回数なども例から変更できます。可能な操作はその状態から生成され、PP不足・満員盤面・使い切った攻撃権・進化制限を守ります。任意配置入力が実際の対戦で到達可能だったことまでは証明しません。

対応能力は**バリア・必殺・疾走・突進・守護**です。フォロワーとスペルについて次の効果を扱います。

| 効果 `op` | 内容 |
|---|---|
| `damage` | 対象・全体・ランダム対象へのダメージ |
| `split_damage` | 古い相手フォロワーから順に割り振るダメージ |
| `destroy` | 対象の破壊 |
| `grant` | 対応する能力の付与 |
| `buff` | 攻撃力・体力の変更 |
| `summon` | 指定カードを場へ出す |
| `repeat` | 内側の効果を繰り返す |

これらは `effects`、`fanfare`、`evolve`、`super_evolve`、`enhance_effects` で扱います。ファンファーレは手札からの使用時に処理し、効果による召喚では発動しません。参照される召喚先も対応範囲の確認対象です。

**盤面JSONの配列は、場に出た順の古いものから新しいものへの順序です。** 表示上の左右や個体IDの辞書順に並べ替えないでください。`entered_turn` はそのターンに出た個体の攻撃可能性を判定する情報で、同一ターン内の登場順を表しません。

割り振りの根拠は [ゲームルールの「割り振り」](rules.md#割り振りダメージの範囲2026-07-12ユーザー確定) です。エンジンでは古い順に、その時点の体力分までを割り当て、最後の対象には残量を割り当てます。バリアはその対象へのダメージを防ぎますが、**割り当てた量は消費**され、後の対象へ繰り越しません。実例 `split-oldest-first` では古いバリア守護への小ダメージを先に使うかどうかで結果が変わります。

ドロー、生成、ラストワード、攻撃時効果、各種誘発、ターン終了時効果、クレスト、リーダー保護、アミュレット、別形態やモードなどは対象外です。対応外能力は省略して探索するのではなく、入力エラーとして拒否します。現在の手番側の手札と両者の盤面、そこから参照するカード定義が確認対象です。手札にある間に発動する誘発能力は相手側の手札も確認して拒否します。

1カードの効果展開は繰り返し回数込みで100000まで、対象選択欄の種類は2つまでです。これを超える定義も入力エラーです。入れ子の繰り返し処理中も探索の時間予算を確認します。

## 6. 完了・予算・計測を確認する

| CLI | HTTP `options` | 既定値 | 許容範囲 |
|---|---|---:|---:|
| `--max-states` | `max_states` | 一般10000／高速500000 | 1〜1000000 |
| `--max-outcomes` | `max_outcomes` | 4096 | 1〜10000 |
| `--max-depth` | `max_depth` | 64 | 1〜128 |
| `--seconds` | `seconds` | 10 | 0より大きく60以下 |

`max_states` は一般探索では出力する局面ノード数、高速探索では計算用の整数状態数です。`max_outcomes` は1操作内の抽選分岐の上限、`max_depth` は操作列の深さです。`seconds` は探索の時間予算です。高速側の方策構築も含みますが、シリアライズ、ファイル保存、HTTP転送、CLIの全分岐再生は含まれないため、外側の実時間も別に測ってください。

`complete: true`・`optimal: true` は対応モデル内で探索を完了した結果です。予算に達したら両方が `false` となり、`cutoffs` に `states`・`depth`・`time`・`chance outcomes` などの理由が入ります。このときの推奨手は得られた範囲での候補で、最適性を保証しません。CLIの正常終了やHTTP 200だけを完了判定に使わないでください。

```powershell
.venv/Scripts/python.exe -m svdeck.battle.battle_practical --cases tests/fixtures/combat_practical_cases.json --case random-half-anchor --max-states 1 --output docs/evidence/combat-practical/manual-limited
```

この例は状態数予算による未完了を確認する入力です。必要に応じて予算を増やし、必ず新しい出力先で再計算します。許容範囲外の予算、未知の重み、対応外効果などは入力エラーです。HTTPは `400` と `{"error":"理由"}` を返します。

`stats.elapsed_ms` は探索のみの時間です。`peak_rss_bytes` は**プロセス全体の最大常駐メモリ**で、HTTPでは前のリクエストを含む起動以来のピークです。1回の探索が増やしたメモリ量ではありません。`memory_method` と `memory_scope` を計測値と一緒に保存してください。速度やメモリの保証値はここでは定めていません。

## 7. 小さい問題で確率と手順を照合する

独立した探索計算は次で実行できます。

```powershell
.venv/Scripts/python.exe scripts/practical_reference.py --output docs/evidence/combat-practical/manual-reference.json
```

このスクリプトは実戦探索の評価計算を呼ばず、公開 `Battle` の合法操作と全抽選結果を総当たりし、分数で今ターン勝利確率を求めます。戦闘ルール処理は同じ `Battle` を共有するため、別実装のゲームルール検証ではありません。評価点優先の照合は上記の体力合計21対20の手計算と分けます。

主要なサンプルを次に挙げます。全件は入力JSON内の `id`・`description`・`expected` を参照してください。

| `--case` | 確認する内容 |
|---|---|
| `barrier-target-order` | バリアを外してから大ダメージを与える順序 |
| `bane-barrier-rush` | 必殺・バリア・突進と攻撃対象 |
| `split-oldest-first` | 登場順による割り振り |
| `fanfare-self-storm` / `ally-keyword-grant` | 手札使用・ファンファーレ・疾走・能力付与 |
| `slot-pp-evolve` | 攻撃で空きを作ってから使用・進化する順序 |
| `random-half-anchor` | 正確な勝利確率1/2 |
| `random-two-ward-adaptive-anchor` | 抽選で残った守護に合わせた次の攻撃で確率1 |
| `random-adaptive-target` | 抽選後に対象を変える除去の組合せ |
| `rng-cheating-choice` | 固定乱数を先読みすると誤る選択、正解は確率2/3 |
| `summon-repeat-super-evolve` | 召喚・繰り返しダメージ・超進化 |
| `objective-preserve-versus-win` | 勝利優先と盤面保存優先の違い |
| `spent-attack-pp-shortage` | 攻撃済み・PP不足のため勝利不可 |

入力、全分岐、確率、独立計算、再生結果、時間・メモリ、完了状態を一組として比較してください。小さい入力での一致から、大きな盤面の探索完了や対戦AI全体の強さまでは推定できません。
