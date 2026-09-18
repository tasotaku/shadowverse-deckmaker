# 実戦探索・独立参照との照合

全ケースと全初手の今ターン勝利確率が独立総当たりと一致。各ケースを新しいCLIプロセスで実行。

| ケース | 勝利確率 | 完了 | 解析 ms | Peak MiB | 再生辺数 |
|---|---:|---|---:|---:|---:|
| [barrier-target-order](barrier-target-order/report.md) | 1 | True | 1.883 | 20.52 | 12 |
| [bane-barrier-rush](bane-barrier-rush/report.md) | 1 | True | 0.863 | 20.61 | 4 |
| [split-oldest-first](split-oldest-first/report.md) | 1 | True | 3.204 | 20.64 | 22 |
| [fanfare-self-storm](fanfare-self-storm/report.md) | 1 | True | 0.620 | 20.55 | 2 |
| [ally-keyword-grant](ally-keyword-grant/report.md) | 1 | True | 2.007 | 20.48 | 10 |
| [slot-pp-evolve](slot-pp-evolve/report.md) | 1 | True | 6.394 | 20.74 | 36 |
| [random-adaptive-target](random-adaptive-target/report.md) | 1 | True | 10.846 | 20.94 | 91 |
| [rng-cheating-choice](rng-cheating-choice/report.md) | 2/3 | True | 4.907 | 20.68 | 26 |
| [random-half-anchor](random-half-anchor/report.md) | 1/2 | True | 1.442 | 20.50 | 7 |
| [random-two-ward-adaptive-anchor](random-two-ward-adaptive-anchor/report.md) | 1 | True | 2.939 | 20.58 | 21 |
| [summon-repeat-super-evolve](summon-repeat-super-evolve/report.md) | 1 | True | 0.796 | 20.33 | 3 |
| [objective-preserve-versus-win](objective-preserve-versus-win/report.md) | 1 | True | 0.784 | 20.60 | 4 |
| [spent-attack-pp-shortage](spent-attack-pp-shortage/report.md) | 0 | True | 0.299 | 20.52 | 0 |

解析時間は解析呼出しのみ、メモリはPythonを含むプロセス最大常駐量。起動・全分岐再生・保存は時間計測外。各ケース1回の観測値。

[独立参照](../reference.json) / [各回の記録](summary.json)
