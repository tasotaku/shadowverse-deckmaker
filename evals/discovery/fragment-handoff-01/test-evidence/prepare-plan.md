# A/B準備入口の検査項目

対象はprepare-arms.pyと生成される隔離runtimeだけ。製品src・README・実AI実行・本番台帳は変更しない。

1. 正常: 完了したscoutのsessionと公開提出・終了証拠を再確認し、両群のsourceを同じ内容へ複製する。
2. 境界: 完了版を一切変えず別コピーへ参考資料を追加した共有sourceも受け入れる。固定する着想報告HASHは完了resultと提出証拠の両方から一致を確認する。
3. 正常: 現行FINISHとDEVELOP末尾の同状態比較文を両群共通とし、Aの通常発展文をBにも持たせる。Bだけ一度の引受・条件変更・小効果見直しと公開記録を追加する。
4. 差分: 実packetからinstructionを除いた全文が一致すること、runtime差分が指示文だけであること、通常REVIEWが元文と完全一致することを準備時に検査する。
5. 正常: 合成processで公開packet、資料添付、再packet、正式案1件、report、finish、通常review、finishを一巡する。両工程終了後にcheck_finishを再実行する。
6. 境界: Pythonモジュールの直接CLIとdiscovery_run/public.pyの両方で固定HASHが使われる。別HASH指定は拒否する。
7. 保持: 元scout、追加資料を含む共有source、両群source、起動元runtimeは終了後も完全一致する。既存OUTPUTは上書きしない。
8. 失敗: 未完了result、変わった完了session、変わったanswer、別の報告HASHを準備前に拒否する。

合成入力は既存test_discoveryとtest_fragment_scout_tempのfixtureを再利用。実カードの期待答え・評価期待値は設定しない。型検査は入口をmypy strictで確認し、生成runtimeは公開起動で読み込む。
