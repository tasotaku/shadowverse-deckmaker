# 共通前段の実験用入口：検査計画

開始: 2026-09-13 14:49:13 UTC。製品srcは変更しない。実AIは起動しない。

(a) 正常系
1. 既存start済みで正式案0件の合成sessionから、公開CLIで資料を読み、answer.mdを添付・新版全文再読・report・finishし、群不在と停止後一致まで確認する。
2. finishなしの自然0終了でも同じ保存検査を受ける。
3. 完了後に保存されたfinish証拠を既存check_finishで再検査できる。入力・成果の正式案/評価は0件。
4. 任意RunJournal接続は担当の時刻だけを合成台帳へ記録し、採否は変更しない。

(b) 境界
5. 0・負・無限・NaN秒と不完全な台帳引数は起動前拒否。既存出力は上書きしない。
6. 配布packetはinquiry/revision0、proposal=None、previous_reviews=[]、inquiry_focusは目的とoriginのみ。架空のreview_hashを作らない。
7. 断片は最大3件、順位・採否なし、足りない件数を創作で埋めないという公開指示を検査する。本文の意味は自動認定しない。

(c) 失敗系
8. 期限停止、自然非0、未提出を完了へ昇格しない。部分成果は残す。
9. 公開submit/reviewは拒否する。迂回して正式提出・入力・runtime・元資料を変えた場合も失敗にする。
10. 受付後のanswer変更を停止後検査で拒否する。完了記録を後から改変した場合も既存finish再検査で拒否する。
11. 正式案・評価を持つ既存入力は出力作成前に拒否する。

pytestはtests/tempの新規検査、架空DBはpytestの一時領域だけを使用。mypy strictはMYPYPATH=srcで実験用入口を検査する。
