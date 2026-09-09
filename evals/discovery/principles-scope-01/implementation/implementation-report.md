# 任意の原則適用範囲ガイド：実装確認はPASS

指定worktree `/tmp/sv-principles-scope-prototype` の公開CLIに、`start --principles-scope {legacy,scoped}` を追加した。既定は `legacy`。同じ `design.md` からの原則本文を一文字も変更せず、`scoped` のときだけガイド本文と `scoped-v1` の版を別保存する。

commitは `cd3fd078918ec74f28cfa84678b871e52a610cb9`。設計文書を先に記録したcommit `67a67805b60b7ed3327711b9abc2c0219756e860` が直前にある。baseは `a7dba5b979a9ba787f2e269b2665c91f05aa0efe`。追跡先は設定せず、mainへのmerge・pushは行っていない。commit後のgit log/statusで、指定ブランチのHEADと追跡対象の変更なしを確認した。

## 公開操作

以下のCLIを使用する。

```bash
PYTHONPATH=/tmp/sv-principles-scope-prototype/src /tmp/sv-system-venv/bin/python -m svdeck.discovery start SESSION --db DB --class エルフ --format rotation --objective '探索目的' --principles-scope scoped
PYTHONPATH=/tmp/sv-principles-scope-prototype/src /tmp/sv-system-venv/bin/python -m svdeck.discovery packet SESSION --summary
PYTHONPATH=/tmp/sv-principles-scope-prototype/src /tmp/sv-system-venv/bin/python -m svdeck.discovery read SESSION PACKET_HASH principles_scope_guide --offset 0 --limit 20
PYTHONPATH=/tmp/sv-principles-scope-prototype/src /tmp/sv-system-venv/bin/python -m svdeck.discovery read SESSION PACKET_HASH context_metadata --offset 0 --limit 30
```

`SESSION` は未使用の保存先、`DB` は入力DB、`PACKET_HASH` は公開packetが返した値。ガイド全文は `data.context.principles_scope_guide`、版は `data.context.principles_scope_version`。原文は独立した `data.context.principles` に残る。分割読出しでは返された `next_offset` がnullになるまで続ける。考案・評価のどちらのpacketにも、保存ガイドを先に読む指示が付く。

省略時と明示 `legacy` では追加フィールド・新section・追加指示は出ない。旧sessionと保存packetを再編集せず、`read` は指定hashの保存内容だけを返す。ガイドの後日の変更は既存contextに反映しない。

## Test Coverage

テストすべき振る舞いと既存検査の対応は `test-plan.md` に保存した。

1. ✅ 正常：省略とlegacyの同一性、従来の位置引数と開始返答、原則本文の完全一致。
2. ✅ 正常：scopedのガイド・版の別保存、27規則の対応、考案と評価の両方からの読出し。
3. ✅ 正常：合成fixtureで公開start → packet → read → submit → review → report。
4. ✅ 境界：後日のガイド・design変更後も旧保存版が固定。現在contextとDBの欠損後も保存packetは読める。
5. ✅ 境界：未完成案の提出、旧sessionにガイドやsectionを後付けしないこと。
6. ✅ エラー：不正な選択値をDBや保存先へ触る前に拒否。
7. ✅ エラー：違うクラス、ローテ落ち、生成専用札、偽引用、未確認案の推薦を引き続き拒否。

初回検査は既存110件＋追加15件＝125件PASS。mypy strictは関連6モジュールでエラーなし。
変更前baseの合成sessionを、変更後の公開CLIで再読出しし、develop/review packet、summary、principles read、reportの5出力が文字単位で一致した。保存ファイル6件もハッシュと一覧が不変だった。

親担当の指示を受け、ガイドを適用先・拡張しない先へ絞る文言改訂を1件行った。R24は既知壁に当たった用法の再浮上条件へ明示的に限定した。改訂後は原則全文・27項目・両工程・保存版の保持に関わる4件を再実行してPASS、変更3モジュールのmypy strictとdiffチェックもPASS。動作コードを変えていないため125件全体は繰り返していない。

追加テストはtestスキルの規定どおり `tests/temp/test_discovery_principles_scope_temp.py` に置き、同じファイルを本記録ディレクトリにも保存した。追跡対象に含めず、再実行できる状態で残している。

```bash
cd /tmp/sv-principles-scope-prototype
PYTHONPATH=src:tests /tmp/sv-system-venv/bin/python -m pytest -q /tmp/sv-principles-scope-implementation/test_discovery_principles_scope_temp.py
```

Verdict: **PASS（実装・保存互換性）**。

## 変更ファイル

- `docs/discovery-principles-scope.md`：設計判断と保持条件を原則抽出元とは別文書へ保存。
- `src/svdeck/discovery_principles.py`：版、ガイド、両工程共通の参照指示を定義。
- `src/svdeck/discovery.py`：startの任意指定と固定保存、scopedだけの指示追加。
- `src/svdeck/discovery_read.py`：保存版が持つ場合だけガイドの行単位sectionを追加。
- `README.md`：任意指定、公開読出し、未確認範囲への案内。

## 証拠と限界

`execution.json` に実時計と工程、`baseline-commands.json` と `legacy-compatibility.json` に変更前後の公開操作、`check-commands.json` と `wording-check-commands.json` に検査時刻・終了コード、各logに実出力を保存した。公開往復の全引数・出力は `pytest-temp/test_public_cli_round_trip_*/public-commands.json` に残る。

`guide-retention.json` にR01〜R27の対応と原文の同一性を記録した。27件＝対応済み27件。意味・条件・例外の対応は作成担当の自己照合であり、機械検査や第三者評価による意味保証とはしない。ガイド本文のUTF-8 SHA-256は `720ccba6fba57abda4cdebb46b3ddb99b459ef6078229608f4668a3a74fc845e`。

届け先の確認は、指定worktreeの公開CLIと保存された合成session。実カードでの考案・採点、自然試行の入力作成、発見力・勝率の測定は行っていない。原則混在が悪い出力の原因であること、新しいガイドが発見力を改善することは未立証のまま。別の試作・モデル・検索方法・クラス機能を取り込んでいない。

保存終了の実時計（UTC）：2026-09-09T04:28:27.660181+00:00。開始から1179.66秒。
