# PP比較試作の実装・検査記録

任意の公開 `python -m svdeck.discovery pp SESSION INPUT.json` を追加した。現在PPと未使用追加分を別に持ち、宣言された二案の行動順を計算して既存save_sourcesへ保存する。通常の開始・提出形式は変更していない。

届け先: /tmp/sv-pp-comparison-prototype の公開CLI。人工DBから新しく作った /tmp/sv-pp-comparison-01/implementation/public/session で pp→packet/read/report を実行した。本体・本番DB・進行中の自然試行への反映はしていない。

## 変更と理由

- discovery_resources.py: 入力境界、量の型検査、計画全体の検証、現在PPと追加分の状態、順序計算、二案の差と保存の順に実装した。カード本文の意味を推測しない。
- discovery.py: ppの薄い接続関数とCLIの任意コマンドを追加した。固定context/snapshotの整合検査と既存資料保存を再利用する。
- README.md: 入力例、四つの行動、出力、途中停止、エラー時の扱い、検査外の範囲を記載した。
- tests/test_discovery_resources.py: 88件の回帰検査を追加した。test skillに従って最初はtests/tempで実行し、確認後に継続用へ移した。

追加分だけで不足を補える支払いはneeds_extra、不明ならunknownとしてその行の前で停止する。途中停止ではendと問題行afterをnullにし、後続を計算しない。次ターンのppは入力で置換し、後攻T5→T6だけ追加分を1回使用可能へ戻す。不明の追加分は差を範囲として残す。

## 確認結果

- 静的: PASS。mypy 7ファイル、エラー0。git diff --check PASS。変更した関数のAI_NOTEも確認した。
- テスト: PASS。関連総数198 = 既存110 + 新規88。失敗0。test-plan.mdの正常系1〜5、境界6〜11、エラー・途中停止12〜16をすべて検査した。
- 公開入口: PASS。操作総数19 = 成功15 + 意図した入力拒否4。想定外失敗0。現在PP差2、追加分込み差1を読み戻した。根拠申告・入力全文・入力hash・固定版hash・結果のsource_hashを保持している。
- 保存: PASS。同一内容の再実行はsaved_new=false。欄順を変えた同一JSONでも同じ資料識別値になる。人工DBの元ファイルは不変。入力誤りの4件ではsession内を一切変更していない。
- UI目視: 該当なし。UI・バイナリ生成物・外部APIの変更はない。公開JSONの値を直接照合した。
- 発見力・実利用での入力負担・本採用: UNKNOWN。カード効果、回復上限、手札、盤面、進化権、強さ、入力が資料の意味に合うことも検査外。

## 失敗と修正

追加した同一性検査で1件失敗した。オブジェクトの欄順だけが異なる入力でinput_hashは同じでも保存本文の文字列順が違い、資料が重複した。保存JSONの欄順を固定して修正し、88件を再実行してPASS。その後、関連198件もPASS。コードの修正周回は1回。公開操作の想定外失敗は0回で、終了2の4件はbool量・未知資料・先攻available・JSON破損を拒む確認である。

## 実時刻と保存

すべてUTC。開始2026-09-09 03:17:57、実装終了03:26:47、検査終了03:28:59、保存時刻2026-09-09T03:30:50.266791+00:00。
実装終了はコード・README・回帰検査の保存後、検査終了は関連検査・公開往復・差分点検を確認後の実時計。

branch: codex/discovery-pp-comparison
commits: 968b2443e3fe59f38e797c4eee76cab3dfb33cd2、8d70ef0b1c1b8a7d9a65e25468d93c1aa1b8e830
作業ツリーはclean。merge/pushなし。

入口の入力・結果・実コマンドとUTCはpublic/、静的検査とpytest出力はchecks.jsonおよび各JSON、変更内容はchange.patch、工程と失敗回数はexecution.jsonへ保存した。
