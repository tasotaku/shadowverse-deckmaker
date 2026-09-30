# 役割から相手の返しを読むAI

対戦画面のAI方式で **「役割から相手の返しを読む」** を選び、「AIが一手実行」で使えます。既存のAI方式も選択できます。ローカル起動は次のコマンドです。

```powershell
.venv/Scripts/python.exe -X utf8 -m svdeck.battle_server --port 8767
```

画面は http://127.0.0.1:8767/ 。登録済みの「ランプドラゴン」「ラストワードナイトメア」の条件で対戦できます。これはリポジトリに保存されたデッキの対応で、全クラス・最新環境の網羅を意味しません。

通常の保存対戦に触れずに試す場合は `http://127.0.0.1:8767/?session=<新しいUUID>` を別タブで開きます。`session` があるURLでは、保存対戦・再生位置・開始条件・手札表示・AI選択・演出設定のすべてを専用の保存キーに分けます。新しいUUIDは保存記録がない状態と既定の演出設定から始まり、そのタブでの保存・開く・再読み込みも同じ専用領域を使います。通常URLや別UUIDの記録は読まず、変更もしません。同じUUIDのURLを再び開くと、その実験の記録を復元します。表示や対戦処理は通常URLと共通です。

## 判断の内容

カードの実装済み効果から、回復、単体除去、複数面除去、全体除去、打点、リソース、防御、展開、補助を複数割り当てます。発動条件・進化前後・タイミング・ランダム対象数を保持します。盤面から必要な役割を優先し、公開デッキの残数で実在可能な手札を作って返しを試します。生成札を作ってから使う手順も対象です。

単純に上位の評価値だけで候補を埋めず、役割ごとの候補と手札不要の返しを保持します。返しに必要な元の手札について、一様・非復元抽選を仮定した所持確率を計算します。同じ手札が複数の返しを持てる場合は、相手にとって高評価の返しへ一度だけ重みを割り当てます。

**近似探索です。** 手札の補完、隠れたコスト変更、候補数、行動数、評価関数には近似があります。所持確率の正確さは、この抽選仮定と申告した必要札の集合についてだけ成立します。勝率や全手順の探索率ではありません。実際の相手手札・山札順・乱数状態はAIへ渡しません。

通常は「自分のターン＋相手の返し」の2ターン境界で比較します。3ターン以上を要求しても、未知のドローを確定札として使わず、その境界で止まります。終了局面は以後も評価が変わらないため、要求した深さに利用できます。予算切れでは、候補すべてで評価できた共通の深さに戻して比較します。従来の盤面取り合いの厳密列挙とは別の、通常の対戦エンジンを使う有限探索です。

## 設定と記録

Pythonの公開入口は `Player(cards, 'roles', role_k=5, turns=3, max_nodes=6000, seconds=8, seed=1).choose(battle.observation(active_player))` です。`Player` は `svdeck.battle_ai`、`Battle` は `svdeck.battle` から取得します。`battle.observation(...)` が公開情報の入力で、全状態を直接渡す用途ではありません。登録デッキの開始状態は `svdeck.battle_decks.new_match('ramp-dragon', 'last-words-nightmare', seed=93001)` で作れます。

| 設定 | 意味 |
|---|---|
| `role_k` | 役割ごとの候補数、1〜20。合計候補数はKを超える |
| `turns` | 要求するターン数、1〜5。実際の比較範囲は結果の`depth` |
| `max_nodes` | 遷移評価数の上限。Player/APIは1〜100000、CLIは1〜10000 |
| `seconds` | 判断の時間予算、0より大きく60以下。後処理を含む壁時計の厳密上限ではない |

APIは `POST /api/ai-step` に `{"record": battle.export(), "policy": "roles", "options": {"role_k": 5, "turns": 3, "max_nodes": 6000, "seconds": 8}}` を送ります。判断は通常のリプレイへ保存されます。

結果の `depth_unit='turns'`、`depth` は共通の比較境界です。全合法手を調べた深さではなく、`complete`・`optimal`・`proven_win` はfalseです。`role_search.own_candidates` に各候補の到達範囲と共通比較範囲、`cutoffs` に省略理由を保存します。主な理由は `turn_nodes`（ターン内の割当）、`beam`（行動候補の選別）、`role_types/role_hands`（カード・手札仮説の選別）、`unknown_draw/future_unknown_draw`（未知ドロー）、`common_horizon`（比較範囲をそろえた）、`time/nodes`（予算）です。

## 候補を検査する公開診断

```python
from svdeck.battle_role_response import analyze_responses
from svdeck.battle_roles import card_roles, response_weights

profiles = card_roles(battle.cards)
report = analyze_responses(
    battle, remaining_cards, hidden_hand_count,
    known_hand=[], role_k=5, max_nodes=6000, seconds=10,
)
```

`battle` は返しを行う側の手番の通常のBattle、`remaining_cards` は公開消費・公開された手札を除く残数 `{card_id: count}`、`hidden_hand_count` はそのうち非公開手札に入る枚数です。元の仮手札・山札はこの残数に置き換えて診断します。公開済み手札がある場合は `known_hand` に渡します（合計9枚以下）。小さい合成テストにも使えます。実戦の公開観測にある `deck_knowledge` は、プレイヤーごとの `deck_list`、`revealed`（元カードID→カード種）、`known_hand` を持ちます。

`profiles[card_id]` の `roles` と `paths` で分類と発動条件を検査できます。`paths` には `phase`、`form`、`conditions`、`repetitions`、元の効果情報、生成先などが残ります。

候補には次が含まれます。

- `required_cards`：必要な元の手札。途中で生成する札は含めない。
- `required_unknown`：そのうち非公開の必要札。
- `availability_exact`：この必要札を持つ周辺確率。
- `weight_exact`：より高評価の返しを持つ手札を除いた割当確率。
- `witness_record`：具体的に合法な仮手札から始める通常のBattle記録。
- `steps` / `outcomes`：操作・ランダム選択番号・到達状態・確率。`steps`は代表枝で、評価は全枝の期待値。

決定的な候補は `replay(witness_record)` から各 `step['action']` を通常の `Battle.step` で実行できます。確率枝は `step['draws']` で指定した抽選列の条件付き証拠であり、普通の乱数リプレイで任意の枝を再現するという意味ではありません。

確率の独立した検算には `response_weights(Counter(remaining_cards), hidden_hand_count, required_sets)` も使えます。戻り値は必要札集合の順に互いに排他的なFractionを並べ、最後の要素がどれも満たさない確率です。単独集合だけ渡せば周辺確率、複数集合を渡せば合計がその和集合の確率になります。

`coverage_exact` は「候補の空でない必要札集合のいずれかを持つ」確率です。手札不要の返しは含めません。`fallback_weight_exact` は評価済み候補へ割り当てられなかった確率です。診断全体の `complete=false` は近似モデルであることを表し、`witness_search_complete` は選んだ仮説内での打切り有無だけを表します。

## 対戦・評価・リプレイ

```powershell
.venv/Scripts/python.exe -X utf8 -m svdeck.battle_training evaluate --output output/roles-eval.json --policy roles --opponent search --workers 1 --seed 93001 --seeds 1 --decks ramp-dragon last-words-nightmare --seat 0 --replay-dir output/roles-replays
.venv/Scripts/python.exe -X utf8 -m svdeck.battle_training replay --output output/roles-game.json --policy roles --opponent search --seed 93001 --decks last-words-nightmare ramp-dragon --seat 1
```

時間を抑えて反復する設定例は `--role-k 5 --max-nodes 1500 --seconds 3 --turns 3` です。既定予算との強さの優劣は未確定です。

レポートは操作ごとの判断時間、実際の比較深さ、候補・打切り、プロセスのピークメモリを保存します。Windowsでは `PeakWorkingSetSize` を使い、同一workerの過去処理も含むプロセス寿命全体の値です。`--max-actions` に達して未決着なら `unfinished` として保存し、勝利扱いにはしません。保存JSONは対戦画面の「開く」で読み込めます。
