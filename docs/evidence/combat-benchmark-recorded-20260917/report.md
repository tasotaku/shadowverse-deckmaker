# 盤面アルゴリズム検証

実行日時: 2026-09-17T07:07:32.778876+00:00
総合判定: PARTIAL

各測定は新しい子プロセス。時間は解析のみ。メモリは解析終了までのプロセス全体の最大常駐量（Python本体・入力・キャッシュ込み）。
正解作成・再生確認は測定外。UNVERIFIEDは正解集合との一致を未確認。

| ケース | 方式 | 実行 | 正解判定 | 時間中央値 ms | 最大メモリ MiB | 完了回数 |
|---|---|---|---|---:|---:|---:|
| cheap-trade | grouped | PASS | PASS | 1.132 | 21.19 | 2/2 |
| cheap-trade | exhaustive | PASS | PASS | 1.552 | 21.25 | 2/2 |
| incomparable | grouped | PASS | PASS | 1.047 | 21.23 | 2/2 |
| incomparable | exhaustive | PASS | PASS | 0.998 | 20.92 | 2/2 |
| tall-wide | grouped | PASS | PASS | 1.502 | 21.01 | 2/2 |
| tall-wide | exhaustive | PASS | PASS | 1.772 | 21.15 | 2/2 |
| partial-damage | grouped | PASS | PASS | 1.019 | 21.11 | 2/2 |
| partial-damage | exhaustive | PASS | PASS | 0.644 | 21.25 | 2/2 |
| evolution | grouped | PASS | PASS | 0.657 | 21.10 | 2/2 |
| evolution | exhaustive | PASS | PASS | 0.944 | 21.29 | 2/2 |
| super-finish | grouped | PASS | PASS | 4.115 | 21.30 | 2/2 |
| super-finish | exhaustive | PASS | PASS | 2.926 | 21.29 | 2/2 |
| sickness | grouped | PASS | PASS | 0.689 | 21.16 | 2/2 |
| sickness | exhaustive | PASS | PASS | 0.498 | 21.38 | 2/2 |
| spent-attack | grouped | PASS | PASS | 1.840 | 21.34 | 2/2 |
| spent-attack | exhaustive | PASS | PASS | 1.765 | 21.08 | 2/2 |
| empty | grouped | PASS | PASS | 0.486 | 21.20 | 2/2 |
| empty | exhaustive | PASS | PASS | 0.401 | 21.29 | 2/2 |
| zero-attack | grouped | PASS | PASS | 2.966 | 21.12 | 2/2 |
| zero-attack | exhaustive | PASS | PASS | 3.081 | 21.35 | 2/2 |
| identical-5v5 | grouped | PASS | UNVERIFIED | 27.549 | 21.96 | 2/2 |
| identical-5v5 | exhaustive | PASS | UNVERIFIED | 32.177 | 22.52 | 2/2 |
| varied-5v5 | grouped | PASS | UNVERIFIED | 5694.745 | 108.39 | 0/2 |
| varied-5v5 | exhaustive | PASS | UNVERIFIED | 8337.838 | 173.57 | 0/2 |
