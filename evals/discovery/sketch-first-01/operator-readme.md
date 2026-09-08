# shadowverse-deckmaker

Shadowverse: Worlds Beyondで、独自性があり、そこそこ戦えるデッキの種を探す支援システムです。
カードの別用途、複数段の組み合わせ、序盤と後半の役割配分を扱います。出力は核カードと構築方針までで、対戦シミュレータや勝率予測は作りません。

現在は探索工程の試作です。新しい入口で仮説を発展させ、弱い案の推薦を防げるかを検査しています。方法の有用性はまだ確認途中です。

## 探索手法の進捗と検証記録

一覧から過去・進行中の試行を選び、工程時刻、結果、採否理由、保存した根拠資料を確認できます。
画面からもCLIからも更新でき、訂正前の報告と根拠は残ります。

```bash
python -m svdeck.experiments init
python -m svdeck.experiments serve
```

[探索の記録を開く](http://127.0.0.1:8765/)。複数の作業コピーでは同じ本体を `--root` で指定します。
[記録・バックアップ・別PCへの復元手順](docs/experiment-journal.md)を参照してください。

## 準備

Python 3.10以上。リポジトリのルートで実行します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

カードDBは `data/cards.db` を使います。未取得なら `python -m svdeck.fetch` で公式データを取得します。
通常の取得は新規追加分を保存し、既存カードの能力変更を反映する場合は `python -m svdeck.fetch --refresh` を使います。
ユーザーの注記は公式データの更新で上書きしません。

## AIと探索を進める

`discovery` は、AIへ渡す資料を作り、AIが考えた回答を取り込み、次の探索と別評価へつなぐ入口です。
このコマンド自体はAIサービスを呼び出しません。Codexなどの作業担当が、生成された資料を読み、回答JSONを作って次のコマンドへ渡します。

```bash
# 新しい保存先を指定して開始。特定の主役カードの登録は不要です。
python -m svdeck.discovery start data/discovery/trial-01 \
  --class エルフ --format rotation \
  --objective '後半の補充を別のカードに任せ、序盤の採用配分を変える可能性を調べる'

# 対象全文、生成物、両側の注記、ルール、回答形式を出す
python -m svdeck.discovery packet data/discovery/trial-01 > /tmp/discovery-packet.json

# 資料を読んだAIが /tmp/discovery-answer.json を作成した後に取り込む
python -m svdeck.discovery submit data/discovery/trial-01 /tmp/discovery-answer.json

# 仮説に残った問いを再検索し、次の改訂用の資料を出す
python -m svdeck.discovery packet data/discovery/trial-01 > /tmp/discovery-next.json
```

回答は資料の `data.response_example` の形式に従い、`packet_hash` へ資料の `sha256` を入れます。
全文JSONでは、カード・ルール・用語・既知デッキは `data.context` 内、案・検索・追加資料・回答例は
`data` 直下です。例えばカードは `data.context.cards`、ルールは `data.context.rules` にあります。

正式な提出の前に、短い着想を一案だけ保存する任意の入口もあります。全文資料・両側の注記・ルール・原則・
既知構築・追加資料は従来と同じです。効果の役割変更、得る働き、残る不足と次の確認を短く記し、完全な手順や40枚は要りません。

```bash
python -m svdeck.discovery packet data/discovery/trial-01 --stage sketch > /tmp/sketch-packet.json
# この資料の回答例に沿って /tmp/sketch-answer.json を作成した後に保存
python -m svdeck.discovery sketch data/discovery/trial-01 /tmp/sketch-answer.json
python -m svdeck.discovery packet data/discovery/trial-01 > /tmp/discovery-packet.json
# 上の通常資料を読み、そのsha256で正式回答を作成してsubmitへ進む
```

着想は元の資料識別値と回答全文を含む「生成した着想（未検証の仮説）」の追加資料になります。同じ回答を再実行しても重複しません。
正式な提出前のrevision 0だけで利用でき、着想の保存は改訂・評価を増やしません。着想用のhashを直接submitへ渡すことはできません。
通常の資料と `read ... sources` で全文を読め、`report` には表題・種類・source_hashが出ます。成立・採用利益・強さ・独自性の確認ではありません。

資料が長くて一度に読めない場合は、全文出力の代わりに概要と区分の一覧を出します。

```bash
python -m svdeck.discovery packet data/discovery/trial-01 --summary
# 上で返されたsha256をPACKET_HASHに指定。カードは2枚ずつ、ルールは30行ずつ読む例です。
python -m svdeck.discovery read data/discovery/trial-01 PACKET_HASH cards --offset 0 --limit 2
python -m svdeck.discovery read data/discovery/trial-01 PACKET_HASH rules --offset 0 --limit 30
```

概要には保存先、指示、回答例、区分ごとの総数が入ります。`cards`、`rules`、`keywords`、`principles`、
`known_decks`、`search`、`proposal`、`previous_reviews` などを、一覧から選んで読めます。
各読出しの `total` は総数、`next_offset` は次に指定する位置です。0から始め、`next_offset` が `null` に
なるまで同じ区分を読み進めてください。カードは枚数、長い文章やJSONの案は行数で区切ります。
行単位の `content` は改行を保持しているため、順につなげると全文に戻せます。
概要の各区分にある `full_packet_path` は、全文JSONでの元の位置を示します。例えば `keywords` の元は
`data.context.ability_keywords` です。旧版に元の項目がない場合は `null` になります。
`read` はその内容を分割用に整形して返し、メタデータ区分は示した位置のうち他区分に含まれない属性を返します。

分割しても `sha256` は元の全文資料と同じです。回答の `packet_hash` にもこの値を使います。
`read` は資料を作り直しません。途中で別評価が追加されても、指定した保存版だけを読みます。
従来の `packet` による全文出力も使えます。

比較に使う構築資料や、実際の対戦での観察は、開始後でも追記できます。
例えば次のJSONを `/tmp/discovery-sources.json` に用意します。

```json
{
  "sources": [{
    "title": "比較に使う観察メモ",
    "kind": "対戦観察の要約",
    "location": "手元の対戦記録 2026-09-08",
    "observed_at": "2026-09-08",
    "content": "要約：準備中に序盤の盤面を取り返せなかった。\n対戦数は2試合。",
    "limitations": ["少数の対戦の観察で、勝率の証明ではない"]
  }]
}
```

```bash
python -m svdeck.discovery attach data/discovery/trial-01 /tmp/discovery-sources.json
python -m svdeck.discovery packet data/discovery/trial-01 --summary
python -m svdeck.discovery read data/discovery/trial-01 PACKET_HASH sources --offset 0 --limit 20
```

6項目はすべて必要です。`kind` は資料の種類を自由に書き、`location` はURLや手元の記録の場所を示します。
`observed_at` は観察時点が不明なら `null`、`limitations` は記載する限界がなければ空配列にできます。
`content` は原文、または要約であると明示した文章を入れます。コマンドはURLを取得せず、出典や主張の真偽も判定しません。

追加資料は全文とその識別値 `source_hash` を保存し、新しく作る資料の `data.sources` に入ります。
同じ入力内容は重複して保存しません。引用は提出案・別評価の `evidence` に
`{"source_hash": "資料の識別値", "quote": "contentから正確に抜いた文章"}` と書きます。
引用が資料本文に存在するかを検査し、主張を支えるかどうかは別評価で判断します。
`read sources` は行数で分割し、各資料の `content` を改行保持の文字列配列として表示します。
ページを順につないだJSONを読み、`content` の配列を連結すると元の本文に戻ります。

資料追加は改訂や評価を作りません。追加前の `packet_hash` はその時点の資料を保ち、追加後も読出し・回答に使えます。
後から加えた資料を引用する場合は、新しい `packet_hash` を使います。
`report` には資料の一覧と、各提出・評価へ渡した `packet_hash` が残ります。

`report` の各改訂と、新しく作る改訂用の `packet` には `review_contexts` も入ります。
評価を保存した内容の識別値 `review_hash` ごとに、入力版の `input_packet_hash`、その版に含まれていた
`input_source_hashes`、現在の資料のうちその版に含まれない `additional_source_hashes`、その評価が残した
`next_questions` を示します。資料の本文・表題は `source_hash` で `sources` と対応させられます。
同じ入力版に対する異なる評価もすべて保持します。評価・対応情報の配列の並びは日時順や優先順位ではありません。

```bash
python -m svdeck.discovery packet data/discovery/trial-01 --summary
python -m svdeck.discovery read data/discovery/trial-01 PACKET_HASH review_contexts --offset 0 --limit 20
```

ここでいう差分は評価の**入力版に含まれなかった資料**です。実際に読んだ証明や、評価を提出した後に追加された
という時刻の証明ではありません。件数や新旧は評価の正しさを意味せず、資料追加だけで古い問いを解決済みにしません。
古い `packet_hash` の読出しは当時の差分を保ちます。対応情報がない旧版では、この区分は空配列、概要の
`full_packet_path` は `null` です。追加資料機能より前の評価入力は資料0件として扱います。
別評価用の `packet --stage review` では過去の評価と対応情報は空配列です。

比較前後の全40枚がある場合は、実際の交換札を計算できます。2件の資料を `attach` し、それぞれの
`content` に `[{"card_id": 123, "count": 3, "name": "原資料の名前"}, ...]` のJSON配列を入れます。
`name` は省略できます。省略記号は使わず、既知のカードIDと枚数で両側とも40枚すべてを記してください。

```bash
python -m svdeck.discovery compare data/discovery/trial-01 BEFORE_SOURCE_HASH AFTER_SOURCE_HASH
```

`before` / `after` に全札と種類別・コスト別の枚数、`delta.added` / `delta.removed` に実際の交換札が出ます。
`delta.exchanged_count` は入れた総枚数（抜いた総枚数と同じ）で、`delta.type_net_change` は種類ごとの純増減です。
例えばスペルの純増が8枚でも、同じ種類同士の交換があれば交換総数は8枚を超えます。
元資料の名前は `recorded_name`、保存DBから取得した名前は `name` に分けて保持します。

結果は元の2資料と保存DBの識別値を持つ追加資料として残り、返された `source_hash` で次の案・別評価から引用できます。
同じ比較を繰り返しても資料は重複しません。欠けたリスト・総数の内訳だけ・重複ID・未知IDは拒否し、資料を作りません。
現在の対象クラスやフォーマットで採用できない札も歴史比較から除外せず、各札の `eligibility_issues` に表示します。
種類・コスト・採用上限は保存DBの時点の値です。過去の能力・合法性、元資料の実在、勝率や交換の強さは判定しません。

途中の案では `plan` や `steps` を空にできます。未解決の条件は `questions` に残します。
`roles` は、採用する札を `access: "deck"`、効果で得る札を `access: "effect"` として区別します。
後者の `via` には、生成元の役割のカードIDを並べます。生成元も `roles` に記してください。
これで他クラスや生成専用カードの役割も表せますが、実際に生成できるかは本文と手順から別途検査します。
`tag` は既存の要求タグまたは供給タグが分かる場合に指定し、分からなければ `null` にします。
検索結果が0件でも、同じ資料の全文を使って考え続けられます。

前の案を変えた理由と内容を記し、次の回答も `submit` で取り込みます。
`packet --revision 1` のように親を選べば枝分かれでき、`--revision 0` は別の着想の入口です。
`history` には選んだ案の先祖だけが古い順に入り、各案を提出する際の検索結果と追加資料の識別値も残ります。
別評価でもこの履歴を読めます。無関係な枝や過去の評価記録は含めません。
検索の一致件数は、その条件を調べ尽くした証明ではありません。実施した比較・全文検査の結果は、
範囲と限界を記した資料として `attach` で加えてください。履歴の読出しは `read SESSION HASH history` です。

推薦する前は、提案担当とは別のAIセッションで評価します。

```bash
python -m svdeck.discovery packet data/discovery/trial-01 --stage review > /tmp/discovery-review-packet.json
# 別担当が資料と案を読み、/tmp/discovery-review.json を作成
python -m svdeck.discovery review data/discovery/trial-01 /tmp/discovery-review.json
python -m svdeck.discovery report data/discovery/trial-01
```

評価は「手順」「検討・試行の価値」「既出状況」を分けます。古い案への評価は改訂案へ引き継ぎません。
AIの評価を保存したことは、強さや新発見の証明にはなりません。初見の有利さ、Tier、勝率を自動で加点しません。
`web_checks` は調べたURLごとの記録です。各項目に `url`（単一URL）、`query`（検索語・照合対象）、
`checked_at`（確認日時）、`finding`（確認内容と限界）の4つの文字列を入れます。
調査していない場合は `[]` にしてください。回答例の説明文は、実際の記録に置き換えて使います。

資料とDBは開始時点で固定します。開始後のDB更新はその探索へ混ざりません。
新しいカードや注記でやり直す場合は別の保存先で開始してください。保存時刻は公式能力の適用日を意味しません。
本文にカード名を列挙しない生成効果のため、資料には全生成専用カードと、用語定義が参照するパックの札も添えます。
資料にある札をすべて生成できるわけではありません。生成される集合の内容は原文・定義で確認します。

## 既存の検索・データ入口

| コマンド | 用途 |
|---|---|
| `python -m svdeck.explore CARD_ID --format rotation` | 登録済みの主役から要求に型が合う候補を調べる。数量概算は手順成立の判定ではない |
| `python -m svdeck.reverse CARD_ID --format rotation` | 供給する効果から登録済みの要求を逆引きする |
| `python -m svdeck.require recheck` | 新弾取得後、以前供給がなかった要求を再検索する。DB変更なし |
| `python -m svdeck.profile decks` | 保存した環境デッキを一覧する。数値資料は強さ点数として使わない |
| `python -m svdeck.meta --db data/cards.db` | 環境デッキを取得し、全件の整合確認後に保存済み一覧を置き換える |

Game8の記事は、主レシピ節の見出しごとにある**デッキコピー用リンクの対象リスト**を取得します。
記事の表示表とコピー対象が違う場合は、枚数と札の差・コピー先をログに明示します。
取得対象、元記事、見出し、コピー先と表示表との差分をDBにも保存し、探索資料の `known_decks[].source` へ渡します。
古い保存データでこの来歴が残っていなければ `source` は `null` です。
例えば表示表だけが37枚でも、欠けた札を推測せず、コピーリンクに明記された全40枚を読みます。
前寄せ・後ろ寄せなど複数のレシピがある記事は、元の見出し名を添えて別々に保存し、記事内の実在する見出しへリンクします。
コピーリンクがない場合は表示リストを使います。全40枚・正の整数枚数・同名重複なしを満たさないリストや、
取得・解析の失敗があれば処理を中止し、保存済みの一覧は置き換えません。ログは必要に応じてファイルへ保存してください。
表示表とコピー対象がともに40枚でも内容が一致するとは限らず、コピー対象を取得したことは記事内の表記の一致や強さの証明ではありません。
| `python -m svdeck.meta --db PATH` | 指定DBの環境デッキ資料を再取得する。検査時はカードDBの複製を指定。`--help`は取得しない |

設計は [docs/design.md](docs/design.md)、ゲームルールの索引は [docs/rules.md](docs/rules.md) を参照してください。

## 開発時の確認

```bash
python -m pip install pytest mypy
python -m pytest -q tests --ignore=tests/temp
python -m mypy --follow-imports=silent src/svdeck/discovery.py src/svdeck/discovery_evidence.py src/svdeck/discovery_read.py src/svdeck/discovery_sources.py src/svdeck/discovery_compare.py src/svdeck/explore.py
```

`tests/temp/` は過去の使い捨て確認用で、配布・回帰テストの対象に含めません。

コードはMITライセンスです。カードデータの権利は各権利者に帰属します。
