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
- 7ファイルの不要なimport 9件。別ファイルによる再公開名の利用も確認して除外。
- `battle.py` の未使用変数 `received`。反撃ダメージの呼出し自体は保持。

`battle_frontier_skyline._decode` は `battle_frontier_export` が使用、`battle_frontier_native_core._unpack` は数値表現の往復検査が使用するため保持。
HTTP/HTMLParserの処理メソッド、シグナル処理の引数、公開コマンドは枠組みから呼ばれるため削除しない。

## 検証対象

- 通常系: 探索・候補列挙・対戦と公開入口が引き続き利用できること。
- 境界: 候補の比較、空入力、探索上限、盤面の反撃とリーダーへの攻撃。
- エラー: 不正入力と探索の打切りが従来どおり扱われること。

既存の `tests/` の回帰試験、mypy strict、未使用import・変数の検査で確認する。
検証結果は作業コミット後の実行結果を会話で報告する。
