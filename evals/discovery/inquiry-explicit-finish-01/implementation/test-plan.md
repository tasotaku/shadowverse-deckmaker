# 任意の調査終了操作：実装検査計画

開始: 2026-09-13 14:31:44 UTC
作業先: /tmp/sv-inquiry-explicit-finish-worktree
基準版: bf9a8f1
変更対象: src/svdeck/discovery_inquiry.py, src/svdeck/discovery_run.py
実装者の担当は合成データ・合成プロセスによる実装検査まで。実AI、主作業先、実DB、台帳は操作しない。

## (a) 正常系
1. 新規: 明示選択時の調査→照合、保存済み調査から照合のみで公開添付・新版全文再読・最新report・finishを実行し、停止要求・群不在・停止後一致を観測する。
2. 新規: 選択時もfinishなしの自然0終了＋従来のverify_report合格を受理する。
3. 既存 discovery_inquiry: 未選択の自然終了、分割再読、help操作、元案・旧評価・資料保持を維持する。
4. 既存 explicit_finish_current/finished_session_stability: develop/reviewの受付・停止・終了済み資料保持を維持する。

## (b) 境界
5. 新規: finish --helpは要求を作らず、追加引数は拒否し、二重finishと後続readは最初の証拠を変えない。受付後packet/report/attachを拒否する。
6. 新規: 終了根拠の公開操作は名前とhashで固定し、同じ意味になる別の操作や後続操作へ差し替えない。操作名はbasenameだけを許す。公開ロック保持中の監視は待つ。
7. 既存 explicit_finish_current/worker_clock/worker_deadline: 期限直前・期限後・検査中の期限到来、中断、自然非0、群消滅未確認を成功扱いしない。
8. 新規+既存 cycle: CLIの新引数伝達と未指定false、既存呼出しの位置互換、cycleの自動条件を維持する。

## (c) 失敗系
9. 新規+既存 inquiry: answerのみ、公開添付なし、誤kind/location、本文不一致、全文再読なし・不足、reportなし・helpのみ・古いreport・report後追記でfinishを拒否する。
10. 新規: 受付後にanswer、資料・packet、改訂・評価、設定、根拠操作、要求、元入力・実装を変えた場合は拒否する。担当・工程・資料版の変更も拒否する。
11. 新規: 停止時の改変をfinish_invalidとし、終了後に要求が消えた場合も全体成功としない。既存timed_out保存先の再利用を拒否する。
12. 既存 worker_journal: 担当の終了と全体の提出検査を区別し、終了同期失敗を成功にしない。

静的検査: 指定Pythonのmypy strictで変更2ファイル。検査コードはtests/temp、保存コピーと結果は本ディレクトリ。pytestの実行出力とJUnit XMLを保存する。

## 親点検を受けた追加検査

13. 新規: 調査が明示終了した後、照合がfinishなしで自然終了する混合経路でも、完了済みの調査sessionを完全一致で検査する。前工程へのファイル追加・本文改変は全体失敗、無変更は完了とする。指摘への修正後は新規検査全件を再実行する。
