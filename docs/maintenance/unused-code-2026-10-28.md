# src/svdeck の未使用コード整理（2026-10-28）

## 対象と判断

対象は現行 `src/svdeck` の67 Pythonモジュール。`src`・`tests`・`scripts` の構文木による名前・属性・import参照、README、設計資料、起動設定、Web画面の文字列参照を照合した。
保存済み `docs/evidence` と `evals` の実装コピーは過去の検証資料として変更しない。同名関数が過去コピーで呼ばれていても、現行実装の呼出しとは分けた。

ファイル単位の判定: **67 = 別ファイルからimportあり63 + 独立CLI3 + パッケージ定義1**。ファイル削除は0件。
独立CLIは `augment.py`・`atoms.py`・`vectorize.py`。`python -m` で直接起動するため、import元がないことを削除理由にしない。
`vector.py` は設計資料§11の凍結・保持判断があり、参照もあるため保持する。

## 削除したもの

- `battle_frontier_skyline._features`: 現行コード・テスト・補助スクリプトから参照のない旧変換処理。現行の `_group_features` を保持。
- `battle_frontier_fast.Kernel.initial_own`: 初期化後に読み出さない属性。
- `battle_ai.POLICY_VERSION`、`battle_roles.ROLES`: 読み出しも公開画面での利用もない定義。
- 6ファイルの不要なimport 9件。別ファイルによる再公開名の利用も確認して除外。
- `battle.py` の未使用変数 `received` は保持。代入だけを外しても独立参照の証明書のエンジンハッシュが変わり、保存済み正解を受理できなくなるため、今回は対戦エンジンを変更しない。

`battle_frontier_skyline._decode` は `battle_frontier_export` が使用、`battle_frontier_native_core._unpack` は数値表現の往復検査が使用するため保持。
HTTP/HTMLParserの処理メソッド、シグナル処理の引数、公開コマンドは枠組みから呼ばれるため削除しない。

## 検証対象

- 通常系: 探索・候補列挙・対戦と公開入口が引き続き利用できること。
- 境界: 候補の比較、空入力、探索上限、盤面の反撃とリーダーへの攻撃。
- エラー: 不正入力と探索の打切りが従来どおり扱われること。

既存の `tests/` の回帰試験、mypy strict、未使用import・変数の検査で確認する。
検証結果:

- `PYTHONPATH=src:tests .venv/bin/python -m pytest tests --ignore=tests/temp -q`: 1624 passed / 6 skipped / 3 failed。
- 失敗3件はいずれも `test_combat_benchmark` の独立参照にある `engine_sha256` と現在の対戦エンジンの不一致。開始版 `d6e4791` のソースと固定資料を `/tmp` に展開し、同じ3失敗を再現した。正解資料の識別値は書き換えていない。
- `tests/temp` はGit管理外の過去の使い捨てテスト。削除済みの `insert_new_cards` を参照し収集に失敗するため、現行の管理対象テストと分けた。
- 変更した10ソースのmypy strict（import先はsilent）: PASS。全67ソースの型検査には、変更前から `combat_benchmark.py` の `subprocess.CREATE_NO_WINDOW` に1件のエラーあり。
- 未使用import・再定義の検査: PASS。`battle.py.received` は前述の理由で残し、変数検査の既存指摘も残る。
- 独立した差分レビュー: 誤削除の指摘なし。UIの変更はない。

届け先は `shadowverse-deckmaker` の現行チェックアウト。実行時の候補列挙・対戦・探索の回帰試験をそこで実行した。
