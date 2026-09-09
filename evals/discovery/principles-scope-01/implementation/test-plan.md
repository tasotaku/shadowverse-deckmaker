# 変更に対応する検査

対象は任意の原則適用範囲と保存互換性。ゲーム上の発見力・採否を検査しない。

| 区分 | 振る舞い | 対応する検査 |
|---|---|---|
| (a) 正常1 | 省略時と明示legacyが従来の引数・返答・保存内容を保つ | 新規test_default_and_explicit_legacy_are_identical、変更前CLIとの保存版照合 |
| (a) 正常2 | scopedだけに本文と版が別保存され、principles全文は同一 | 新規test_scoped_adds_only_guide_and_version |
| (a) 正常3 | develop/reviewの両方から保存ガイドへ到達し、分割読出しで全文を復元 | 新規test_guide_is_reachable_and_exact_in_both_stages、既存test_discovery_read |
| (a) 正常4 | 公開start/packet/read/submit/review/reportを合成fixtureで一周 | 新規test_public_cli_round_trip（両選択値）、既存test_discovery |
| (b) 境界1 | ガイド更新、設計変更、現在context/DB欠損後でも保存packetのreadが固定 | 新規test_saved_scope_survives_guide_and_docs_update、既存保存版テスト |
| (b) 境界2 | 未完成の案を提出でき、旧sessionにガイド項目を後付けしない | 新規公開往復、旧CLIとの照合、既存test_partial_idea_round_trip_search_revision_review |
| (b) 境界3 | 27規則の対応が揃い、本文が一文字も削られていない | 新規27識別子・本文バイト照合、監査対応の自己確認（意味の第三者評価ではない） |
| (c) エラー1 | 不正な選択値を保存先作成・DB読取りの前に拒否 | 新規test_bad_scope_is_rejected_before_io（APIとCLI） |
| (c) エラー2 | 違うクラス・ローテ落ち・生成専用札の採用、偽引用、未確認案の推薦は従来どおり拒否 | 新規test_scoped_keeps_existing_rejection_boundaries、既存test_discovery |

既存では追加選択値・ガイドの固定保存が未カバーだったため、新規の合成テストをtestスキルの規定どおりtests/tempへ置く。
再実行用の同じファイルをこの記録ディレクトリにも保存する。通常の回帰テスト群は変更しない。
