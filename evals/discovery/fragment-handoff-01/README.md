# 共通前段：未完成な着想の収集

実験専用の `scout-run.py` は、正式改訂・評価0件のstart済み探索を複製し、最大3件の未完成な着想を公開資料へ保存する。カード名・完成案・順位・採否は指定しない。実数が3件未満でも創作で埋めない。各件はID、出典付き効果、効果の後に残る/減るもの、使えそうな役割、今は困る条件一つ。

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/miyauchitsubasa/.pyenv/versions/3.10.12/bin/python evals/discovery/fragment-handoff-01/scout-run.py SOURCE OUTPUT --codex CODEX_PATH --seconds 300
```

任意の担当時間記録は `--journal-root ROOT --experiment-id ID --stage-id STAGE` を一組で指定する。全体工程の記録と内容の採否はこの入口では扱わない。

配布資料はinquiry/revision0、proposal=None、previous_reviews=[]。調査目的は自由な目的文とorigin=experiment-fragmentsだけで、架空の評価識別値は作らない。既存の公開添付、新版全文再読、report、finish、worker停止前後検査を使う。自然終了も同じ提出検査を通す。元入力・実装・正式0件を保持し、完成出力を複製した後にも終了証拠を再検査する。

公開成果はOUTPUT/inquiry/answer.md・operations・設定・finish証拠、完成時はOUTPUT/sessionとreport.jsonへ残る。OUTPUT/result.jsonで完了・未提出・期限停止・失敗を区別し、担当runメタデータと入力/実装の識別値を残す。私的stdout/JSONLは成果へコピーしない。

機能検査は合成資料と合成プロセスで21件PASS、型検査PASS。実AIと内容の意味的な検査は未実施。件数・記入欄・保存成功を着想の正しさや有用性の証明にはしない。計画・検査コード・結果はtest-evidenceに保存する。
