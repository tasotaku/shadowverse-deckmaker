# 難問対応の検証記録（2026-09-18）

## Test Coverage

- PASS: 数値の異なる5対5、複数敵への攻撃割当、複数体の犠牲、進化対象選択の全候補一致。
- PASS: 攻撃後の進化により、別の超進化個体の最後の一撃を残す回帰ケース。
- PASS: 固定正解と入力が異なる場合、参照未完了、回答ハッシュ不一致を拒否。
- PASS: 全28,667候補の合法な手順と最終盤面の一致を実行時に確認。
- PASS: 正解・打切り・時間・プロセス最大常駐メモリの記録。

関連テスト: `python -X utf8 -m pytest tests/test_battle*.py tests/test_combat_benchmark.py -q`
（PowerShellのglob展開に依存せずPythonで対象ファイルを列挙して実行）。**310 passed in 39.82s**。

型チェック: battle_combat.py、combat_benchmark.py、test_combat_benchmark.py、combat_reference.py のmypy、4ファイルPASS。

独立レビュー担当 hard_review は変更を読み取り専用で確認し、指摘なし。
担当からの実行報告では、固定乱数1,000局面で旧全探索との集合一致、
うち顔体力の少ない500局面で全候補の再生一致。

難問の独立正解は[生成方法](reference/method.md)、実測値と全回答は
[難問レポート](../combat-hard-verified-20260918/report.md)を参照。
旧版の[同一盤面計測](../combat-hard-baseline-20260918/report.md)では探索未完了。
今回の上限は「異なる終了状態の数」なので、旧版の途中状態数とは単位が異なる。
時間は解析呼出しのみ、メモリはPython等を含むプロセス全体、各ケース一回の観測値。

Verdict: **PASS**（能力なし・基本進化までの固定難問と関連回帰テスト）。
任意盤面の証明、カード能力、相手の返し、通常AIへの統合はこの判定に含めない。
