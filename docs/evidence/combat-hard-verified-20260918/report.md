# 盤面アルゴリズム検証

実行日時: 2026-09-17T22:44:38.774841+00:00
総合判定: PASS

各測定は新しい子プロセス。時間は解析のみ。メモリは解析終了までのプロセス全体の最大常駐量（Python本体・入力・キャッシュ込み）。
正解作成・再生確認は測定外。UNVERIFIEDは正解集合との一致を未確認。

| ケース | 方式 | 実行 | 正解判定 | 時間中央値 ms | 最大メモリ MiB | 完了回数 |
|---|---|---|---|---:|---:|---:|
| varied-5v5 | grouped | PASS | PASS | 4993.078 | 106.23 | 1/1 |
| allocation-5v5 | grouped | PASS | PASS | 5833.796 | 126.28 | 1/1 |
| timing-finisher-5v5 | grouped | PASS | PASS | 405.322 | 29.91 | 1/1 |

独立参照: [認証済み全解](reference.json)。参照の完了・入力ハッシュを検査済み。
各回の全候補・再生後の終了状態は次のファイルに保存しています。

- varied-5v5 grouped #1: [answers-1-grouped-1.json](answers-1-grouped-1.json)
- allocation-5v5 grouped #1: [answers-2-grouped-1.json](answers-2-grouped-1.json)
- timing-finisher-5v5 grouped #1: [answers-3-grouped-1.json](answers-3-grouped-1.json)
