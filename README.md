# shadowverse-deckmaker

Shadowverse: Worlds Beyondで、独自性があり、そこそこ戦えるデッキの種を探す支援システムです。
カードの別用途、複数段の組み合わせ、序盤と後半の役割配分を扱います。出力は核カードと構築方針までで、対戦シミュレータや勝率予測は作りません。

現在は探索工程の試作です。新しい入口で仮説を発展させ、弱い案の推薦を防げるかを検査しています。方法の有用性はまだ確認途中です。

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
`report` には資料の一覧と、各提出・評価が見た `packet_hash` が残ります。

途中の案では `plan` や `steps` を空にできます。未解決の条件は `questions` に残します。
`roles` は、採用する札を `access: "deck"`、効果で得る札を `access: "effect"` として区別します。
後者の `via` には、生成元の役割のカードIDを並べます。生成元も `roles` に記してください。
これで他クラスや生成専用カードの役割も表せますが、実際に生成できるかは本文と手順から別途検査します。
`tag` は既存の要求タグまたは供給タグが分かる場合に指定し、分からなければ `null` にします。
検索結果が0件でも、同じ資料の全文を使って考え続けられます。

前の案を変えた理由と内容を記し、次の回答も `submit` で取り込みます。
`packet --revision 1` のように親を選べば枝分かれでき、`--revision 0` は別の着想の入口です。

推薦する前は、提案担当とは別のAIセッションで評価します。

```bash
python -m svdeck.discovery packet data/discovery/trial-01 --stage review > /tmp/discovery-review-packet.json
# 別担当が資料と案を読み、/tmp/discovery-review.json を作成
python -m svdeck.discovery review data/discovery/trial-01 /tmp/discovery-review.json
python -m svdeck.discovery report data/discovery/trial-01
```

評価は「手順」「検討・試行の価値」「既出状況」を分けます。古い案への評価は改訂案へ引き継ぎません。
AIの評価を保存したことは、強さや新発見の証明にはなりません。初見の有利さ、Tier、勝率を自動で加点しません。

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

設計は [docs/design.md](docs/design.md)、ゲームルールの索引は [docs/rules.md](docs/rules.md) を参照してください。

## 開発時の確認

```bash
python -m pip install pytest mypy
python -m pytest -q tests --ignore=tests/temp
python -m mypy --follow-imports=silent src/svdeck/discovery.py src/svdeck/discovery_evidence.py src/svdeck/discovery_read.py src/svdeck/discovery_sources.py src/svdeck/explore.py
```

`tests/temp/` は過去の使い捨て確認用で、配布・回帰テストの対象に含めません。

コードはMITライセンスです。カードデータの権利は各権利者に帰属します。
