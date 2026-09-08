# 仮想カードでの因果関係の検査

2026-09-08の初回実行は **2件ともPASS**。9枚の仮想カード集合で、場への生成を手札条件の供給へ読み替え、手札戻しと軽減をつなぐ課題を検査した。
一条件を変えた対照では同じ答えを繰り返さず、到達できる打点を下げて判断した。

| 入力 | 事前の正解 | 実際の提案 | 扱い |
|---|---|---|---|
| a | 9PPで13点に届く | 合法な別解で13点 | 指定手順は成立。実戦推薦は未確認 |
| b | 元コスト条件が開かず最大8点 | 8点の手順と上限の根拠 | 13点を狙う枝は見送り。他用途は否定しない |

探索担当は実装と正解を読まず、READMEと `start → packet → submit` を使った。
別担当が `packet --stage review → review → report` を実行し、固定した正解と照合した。
採点担当は入力と正解の作成者で、探索担当とは別。正解を知らない盲検採点者ではない。

両件とも初版で解けたため、複数改訂や追加検索が役立つかは未確認。
実カード発見力、従来方式との差、実戦の強さを示す結果でもない。以後この入力は開発用であり、未知評価には再使用しない。

## 保存した証拠

- `input-a.sql` / `input-b.sql`：固定DBのSQL書き出し。実カードDBへ取り込まない。
- `objective.txt`：両件共通の指定状態と目的。
- `expected.json`：探索担当へ渡さなかった事前の正解。
- `packet-*.json` / `review-packet-*.json`：実際に渡した資料と指示。
- `proposal-*.json` / `review-*.json`：実際に提出・保存した回答。
- `observed.json`：独立採点、入力の識別値、限界。`/tmp`のパスは実行時の記録。
- `manifest.json`：この保存物のSHA-256。

資料と回答は初回実行時のまま。実行中に見つかった生成物の役割欄と資料の読み出し負担は、後の実装で直している。
生成物の役割欄は、同じ既知回答へ役割を戻し、`access="effect"`・`via`を使う修正後の公開指示で1回の提出に成功した。
これは形式の修正確認で、新しい発見の得点にはしない。

## 同じ入力を用意する

リポジトリのルートで、未使用の保存先へ実行する。

```python
from pathlib import Path
import sqlite3
import subprocess
import sys

source = Path("evals/discovery/role-chain")
work = Path("/tmp/sv-role-chain-replay")
work.mkdir()  # 既存の実験は上書きしない
for case in ("a", "b"):
    database = work / f"{case}.db"
    conn = sqlite3.connect(database)
    conn.executescript((source / f"input-{case}.sql").read_text())
    conn.close()
    subprocess.run([
        sys.executable, "-m", "svdeck.discovery", "start", str(work / case),
        "--db", str(database), "--class", "ウィッチ", "--format", "rotation",
        "--objective", (source / "objective.txt").read_text(),
    ], check=True)
```

この後は新しい `packet` を読み、回答・別評価を行う。保存済み回答を取り込むだけの再実行は、発想の検査には数えない。
保存時刻と実装が変われば資料のhashも変わるため、古い `packet_hash` の回答はそのまま取り込めない。
