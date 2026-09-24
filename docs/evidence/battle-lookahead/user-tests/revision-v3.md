# Spec v3 revision

判定: TEST_SPEC_ISSUEとしてv3を作成することが妥当。独立担当がv2、design-user-tests skillとcontract、実行前の観測制約だけを読み、製品source・diff・製品結果は参照していない。

v2 U3のvisibilitychange observerは許可されたread-only channelで装着できない。利用者目標は通常対戦画面で先読みAIを選択し、一手実行の結果を同じタブで確認すること。OSの前面状態や区間中の連続監視は明示されていない。v3では押下直前・各操作/応答観測時・更新完了時にbrowser selectedTab、document.visibilityState、選択欄の現在値を直接測定する。時点間の瞬間的な変化はblind spotへ明記し、連続保持を証明したとは扱わない。静止画からの推定は禁止を維持する。

30秒以内という期限は維持し、時計は操作元の外側の実行環境で利用できる単調時計を使用する。Date.nowだけを単調時計の代用としては扱わない。押下を開始event、更新盤面と操作可能な次状態の直接確認を終了eventとする。不要な別タブへの自動遷移・手動再読込禁止も維持する。

既存localhost:8767には保存状態があり、localhost.:8767はIABでERR_BLOCKED_BY_CLIENTとなるため、保存状態なしの専用originとして同じコード・配信版を未使用localhostポートで配信するsetupを許す。今回のoriginはhttp://localhost:8793/。製品コード、分析条件、fixtureの変更を許すものではない。

変更パスはversion、revision、T3 setup[0]、T3 ux_checks[2]、coverage.blind_spotsへの1項目追加だけ。T1/T2はJSON構造として完全一致し、T3の全functional_expectations、actions、budget、U1/U2/U4も完全一致を機械確認済み。操作数6以内、手動切替0回、1366x768とscroll上限は不変。旧v1/v2およびlockには書き込んでいない。

T1 canonical JSON SHA-256: d7212e1e08036010b9bf63e927a9afefff6287a7405634b507ddef9e9bd0611a

T2 canonical JSON SHA-256: dad02e58be018700ad7d91948fcdae697dad7338d1184508dbbc5bd547241a3f

Validation: lint_user_test_artifact.py spec spec-v3.json --previous spec-v2.json --create-lock spec-v3.lock.json はPASS。v3 SHA-256: 3d77bbae90e0815006139980985f4e03c37d9271af43107d3a1ca44769bd6835。

これは観測契約の改訂であり、製品テストの実行結果または製品合格の判定ではない。
