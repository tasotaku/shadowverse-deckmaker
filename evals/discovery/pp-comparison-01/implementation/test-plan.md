# PP比較試作の検査計画

固定仕様: docs/pp-comparison-prototype.md（設計コミット0e823cc）。開始実時計2026-09-09 03:17:57 UTC。
届け先は依頼で指定された隔離worktree /tmp/sv-pp-comparison-prototype の公開 discovery pp。自然試行・本番DB・本体branchへ反映しない。

## (a) 正常系
1. 現在PP差2と未使用追加分込み差1を別に返す。PP新計算は既存testsに無く gap。
2. 未使用の後半追加PPを翌ターン以降へ保持し、明示use_extraでだけ加算する。gap。
3. gainは宣言された実増分を加算し、上限や発動条件を推測しない。gap。
4. 入力全文・入力hash・固定版hash・参照資料hashを保存し、同一入力は重複しない。既存sources/compare testsは保存共通部分covered、PP接続gap。
5. 人工DBを公開startし、pp→packet/read/reportで計算資料を読み戻す。既存read/report covered、PP往復gap。

## (b) 境界
6. T5→T6で使用済み/未使用/不明の後攻追加分が1回使用可能となり、前半未使用でも2回にはならない。gap。
7. 次の連続する自分ターンだけ受け取り、開始PPは明示値へ置換する。gap。
8. 追加分不明は使用可能とせず、完了案の込み差を範囲で返す。先攻は不明でも追加0。gap。
9. PP0・支払0・gain0・開始PPがターン数より大きい宣言・空行動順を算術として扱う。gap。
10. 終点の先後・ターン不一致、片側途中停止では終点差を計算しない。gap。
11. 根拠未添付は資料0件と明示し、source_hashes省略と明示空配列の入力同一性を区別する。gap。

## (c) エラーと途中停止
12. 先攻の使用・再使用を不正手順として保存、不明の使用を未確認として停止。gap。
13. 支払不足を現在PP不足／明示追加使用が必要／不明／追加込みでも不足へ分け、残高を負にしない。gap。
14. 型の違い（bool/小数/負数）、欄名誤り、計画数不正、先攻availableの開始宣言を保存前に拒否。gap。
15. 未登録・重複資料hash、改変資料・改変固定DB・改変固定contextでは計算資料を保存しない。保存基盤covered、PP接続gap。
16. 公開CLIの入力エラーは終了2・Tracebackなし。計算途中の問題は保存された結果（終了0）に残す。gap。

既存runner: pytest（既存testsはpytest fixture/parametrize）。関連tests/test_discovery*.pyを実行する。
新規不足はtests/temp/test_discovery_resources_temp.pyに作り、繰返し残す回帰検査は検証後tests/test_discovery_resources.pyへ保存する。外部公開/pushは行わない。
目視: UI・バイナリ生成物・外部API実装に当たらない。公開JSONの実値確認を行う。
受入・発見力・本採用は今回の検査外でUNKNOWN、親の後続実利用判断。
