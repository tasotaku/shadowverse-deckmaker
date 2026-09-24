# 独立監査（2026-09-24）

保存済み JSON と比較器・テストを読み、別の集計コードで全件を再照合した。探索の再実行・製品コード変更は行っていない。

- `generated-run`: 128/128 PASS。全初手367件の action 集合と勝率・敗率、局面全体の値、推奨手の参照最適手への所属、policy verification PASS が一致。保存済み expected の value/actions/optimal_first_actions も各 reference.json と一致。
- `hard-run`: exact 6/6 PASS、全初手22件も同じ照合で一致。stress 2件は INCOMPLETE、参照解なし。したがって正解確認は計134局面・389初手であり、5対5の2局面は含まない。全 check.json と summary の各行も一致。
- `expanded-budget`: 2/2 INCOMPLETE。30秒・100,000状態上限でも完了せず、参照比較も未実施。終了コード正常や合法手は最適性・正解の証拠ではない。

|対象|analyze 内の時間|プロセス最大使用メモリ|状態数・結果|
|---|---:|---:|---|
|生成128件|3.012–520.456 ms|22.418–27.836 MiB|全件完了|
|手作り exact 6件|19.428–110.504 ms|22.711–24.125 MiB|全件完了|
|5対5 #1（標準診断予算）|4,327.700 ms|66.957 MiB|10,000、states 打切り|
|5対5 #2（標準診断予算）|6,851.187 ms|71.352 MiB|10,000、states 打切り|
|5対5 #1（拡大診断予算）|30,002.535 ms|265.840 MiB|54,080、time 打切り|
|5対5 #2（拡大診断予算）|30,002.516 ms|220.543 MiB|40,750、time 打切り|

時間は `production.stats.elapsed_ms`。プロセス起動、入力読込、Battle生成、policy再生検証を含む総時間ではない。`production_process.elapsed_seconds` は別の外側測定、summary の elapsed_seconds は workers=2 の全体経過時間。メモリは Windows PeakWorkingSetSize のプロセス生涯ピーク（bytes÷1,048,576をMiB表示）で、探索単体の増分・複数プロセス合算ではない。製品・参照は別プロセス。

通常 Player は診断予算を引き継がず、4,000状態・2秒、非公開情報を2通り仮定する。標準runの runtime.json 外側測定は #1=1,707.708 ms、#2=2,010.592 ms。両方 depth=0/3、complete=false、optimal=false、proven_win=false、fallback=true、fallback_evaluated=true。depth=0 は「1ターン全体を全仮定で比較し終えていない」を表し、評価を全く行わなかった意味ではない。完了した一手評価を使い合法手を返した。

比較器は未完了を先に INCOMPLETE とし、全初手の action→(勝率, -敗率) を辞書で照合する。テストには誤値・初手欠落・未完了の故障注入がある。ここで独立なのは探索・比較手順であり、参照探索も製品と同じ Battle 遷移を利用するため、ルール実装そのものの独立検証とは区別する。
