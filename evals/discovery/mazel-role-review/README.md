# 前半と後半の役割分担を読む検査

2026-09-08の固定条件による意味解釈の採点は **PASS、2/2件**。
既知のユーザー注記と保存カード本文を読んだ評価であり、自然な探索で用途を発見した実績ではない。
優先度ラベルの一致を合格条件にはしていない。

| 入力 | 実際の回答 | 確認できた意味判断 |
|---|---|---|
| a | conditional / develop / known | 元の構築を前半の攻撃と手札消費へ寄せ、後半の補充をマゼルの置換先へ任せる役割分担を認めた。置換後の元札取得は必要としない。 |
| b | refuted / drop / unconfirmed | 元山札の3枚目のベイルを置換後の通常6ドローで得る主張を反証した。既に手札にある札の残存と終了時破棄は分け、役割分担全体やカード全般の禁止へ広げなかった。 |

指定例は、ベイル2枚を手札に持つ間に味方が4回場を離れ、現在8PP、通常進化権1の状態。
ベイル4PP＋マゼル4PPを使い、残りのベイルと生成した証明の2枚を持つ。
終了時にベイル1枚を捨て、証明1枚＋置換先から6枚の計7枚、終了直前から純増5枚と処理した。
この状態の取得頻度や最速到達を保証する入力ではない。

**未確認の範囲は残る。** 76枚という用語定義と、保存DBの同パック非生成カード77行の不一致は未解決。
除外される1枚、全構成、抽選確率は推測していない。自然な探索・未知の役割変更・方式比較・実戦価値・
正確な40枚・勝率・過去の構築の完全再現・最新公式情報への外部再照合も検証していない。
bは既手札と終了時破棄の境界を正しく述べたが、**置換直後から終了前の追加プレイは未検証**。
指定例は残PP0であり、別資源条件でその行動を判断できるかまでは示さない。

このPASSは、[既知案の評価で残ったFAIL](../known-candidate-review/README.md)を覆さない。
両検査は入力と判定目的が異なる。同じ資料での再採点も、新しい未知評価とは数えない。

## 保存物と証拠の対応

- `expected.json`：回答前に固定した条件。優先度の特定ラベルは要求しない。
- `evaluation.json` / `evaluation.md`：別担当による採点。条件・資源・時間境界・限界を記録。
- `a/` / `b/`：提出案、追加資料、実際の回答、公開入口の開始・提出結果と要約、公開reportの読出し控え。
- `*/develop-packet.json.gz` / `*/review-packet.json.gz`：入力作成・評価時の全文資料を可逆圧縮したもの。
  カード原文、双方の注記、用語、指示、目的、追加資料を含む。レビュー資料は両方とも初版で、過去評価と履歴は空。
- `input-manifest.json` / `input-verification.json`：入力作成時の識別値と確認記録。
  `reviews_saved: 0` は提出直後の状態であり、回答保存後の値ではない。
- `create-inputs.py` / `cli-log.jsonl.gz`：当時の入力作成スクリプトと公開CLI実行記録。スクリプトは実行記録の原本として保持した。
- `manifest.json` / `archive-verification.json`：本保存物の識別値、圧縮前との対応、引用と公開report保存の照合結果。

資料内の `/tmp/sv-mazel-role-eval/` と元リポジトリの絶対パスは実行当時の参照。
移動後は本ディレクトリ内の同名ファイルを使い、改名・圧縮したものは `manifest.json` の
`source_relative_path` で対応をたどれる。原本の条件・回答・採点の内容は書き換えていない。

## 再採点と再生成の条件

保存資料だけを使う再採点ではDBは不要。次のように全文を復元し、各案の回答と固定条件を照合できる。
評価担当へ渡すのはレビュー用全文資料だけとし、固定条件・採点・作成コードは採点側へ分離する。

```python
from pathlib import Path
import gzip
import hashlib
import json

root = Path("evals/discovery/mazel-role-review")
manifest = json.loads((root / "manifest.json").read_text())
name = "a/review-packet.json.gz"
raw = gzip.decompress((root / name).read_bytes())
assert hashlib.sha256(raw).hexdigest() == manifest["files"][name]["source_sha256"]
packet = json.loads(raw)
assert packet["sha256"] == manifest["packet_hashes"]["a"]
print(packet["data"]["proposal"])
```

公開CLIのセッションを再生成する場合は、別の新規出力先と、当時の保存状態に対応するDBが必要。
元DBのSHA-256は `11aef89fae292ce671781ce31da124d695b15b28f64d7813c6e0c9ad720e1414`、
a/b共通の固定DBは `e58fc4e70fd22d292e0ee37bcb7b20e4410d6dae83a77c423cfddbbfe816c6a5`。
DB本体は同梱しない。異なる現行DBから同じ資料が生成されるとは扱わない。

実行時のPythonは `/tmp/sv-system-venv/bin/python`、読み込み元はリポジトリの `src`。
`create-inputs.py` は元リポジトリ・DB・出力先・Pythonの絶対パスと当時の時刻生成を含むため、
再生成には実行用コピーでパスを指定し、空の出力ディレクトリを準備する必要がある。
スクリプトが行う `start → attach → packet → submit → packet` と引数は圧縮した実行ログに残る。
入力はエルフ・unlimitedで、目的文は `objective.txt`、条件は `scope.json`、追加資料は各 `source-input.json`。
再生成では時刻や資料の識別値が変わるため、保存済み回答をそのまま別の資料へ結び付けない。
新しく得たレビュー用資料を別担当が読み、`python -m svdeck.discovery review SESSION ANSWER` で保存し、
`python -m svdeck.discovery report SESSION` で読み戻す。

入力作成時の正確な実装commitは記録されていない。`manifest.json` の `archive_base_commit` は保存作業の開始点であり、
当時の実装や同一バイト列の再生成を証明する値ではない。元資料の内容を調べる際は、保存した全文資料を基準にする。
