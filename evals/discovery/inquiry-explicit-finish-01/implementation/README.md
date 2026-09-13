# 調査・照合の任意終了：実装と検査

`discovery_inquiry --explicit-finish` を追加した。選択時だけ、担当の公開添付・新版からの全文再読・最新reportを既存の検査で照合し、公開finishを受け付ける。監視側は既存workerの期限・停止前後照合・群不在確認を使う。終了根拠は設定・session・answer・公開操作の名前と内容のSHA256に固定する。

変更は `discovery_inquiry.py` と `discovery_run.py` の2ファイル。既定の自然終了、cycleの対象、採点、期限、自然非0終了の優先順位は維持する。worker本体は変更していない。終了後に要求が消えた場合も全体成功へ進めない。親点検を受け、次の照合担当がfinishなしで自然終了した場合にも、完了済み調査資料の完全一致を検査する。

## 検査結果

- mypy strict: 変更2ファイルでPASS。
- 新規: 74件PASS（公開終了68件、全体記録3件、次工程の自然終了時の資料保持3件）。
- 関連回帰: 194件PASS。
- 合計268件 = 新規74 + 回帰194。失敗・除外0件。
- 公開CLIの合成プロセスで、調査→照合と照合だけの終了受付、停止、群不在、停止後一致を観測した。
- 未提出、古いreport、本文・入力・公開操作・要求の変更、自然非0終了、期限、停止時変更、記録同期失敗が成功へ昇格しないことを確認した。

実行結果は `verification.json`、各JUnit XML・テキスト、型検査は `mypy.txt` に保存。検査項目の事前整理は `test-plan.md`。新規検査と利用した補助検査のコピーも同梱した。元のtests/tempは追跡・push対象にしない。

## 再実行

リポジトリの作業先から、保存した補助検査をtests/tempへコピーして次を使う。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests:tests/temp /Users/miyauchitsubasa/.pyenv/versions/3.10.12/bin/python -m mypy src/svdeck/discovery_inquiry.py src/svdeck/discovery_run.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests:tests/temp /Users/miyauchitsubasa/.pyenv/versions/3.10.12/bin/python -m pytest -q tests/temp/test_inquiry_explicit_finish_temp.py tests/temp/test_discovery_inquiry_temp.py tests/temp/test_novelty_followup_temp.py tests/temp/test_discovery_run_temp.py tests/temp/test_explicit_finish_current_temp.py tests/temp/test_finished_session_stability_temp.py tests/temp/test_worker_journal_temp.py tests/temp/test_worker_clock_temp.py tests/temp/test_worker_deadline_temp.py tests/temp/test_discovery_cycle_temp.py
```

## 残る確認

実AIによる利用は親担当が後続で行う。ここでは実AI、実DB、本番台帳を操作していない。私的Codexログは読んでいない。既存の期限停止を完了へ変更しておらず、実装の機能検査を問いの解決・発見力・調査の有用性の証明とはしない。

届け先: 指定された独立worktreeとそのcommit。主作業先への反映と実AI確認は親担当へ引き渡す。
