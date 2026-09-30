# 役割AIの検証記録

対象: 公開デッキと役割から相手の返しを生成する `roles` 方式。利用方法・確率の意味・制約は [battle-roles.md](../../battle-roles.md)。

## 検証対象と結果

正常系は複数の役割、条件・進化・生成札の順序、役割ごとの候補保持、公開API・保存再生・評価コマンドを対象とした。境界は手札の重複、枚数不足、ランダム枝の予算切れ、未知ドロー、手札溢れ、使える札がない返し、比較範囲の一致を対象とした。エラー系は候補数・確率入力の型と範囲を対象とした。

- 厳密な型検査: 変更したAI・API・CLIとテストの11ファイル、PASS。
- JavaScript: `node --check src/svdeck/battle_web/app.js`、PASS。
- 関連テスト: `pytest -q tests -k 'battle or combat' --tb=short`、**1418 passed / 4 skipped / 211 deselected、72.59秒**。
- 新方式の接続テスト: 41件PASS。追加した探索境界の回帰6件は上記全体テストに含む。
- 静的レビューで見つかった、未知ドローの確定扱い・確率枝の混在・後続候補の予算不足・手札不要候補の脱落・公開消費の反映漏れを修正。小再現で再確認した。

全探索・最善手・強さの証明ではない。スキップ4件をPASS件数には含めていない。

## 開発中の試走

seed93002、rolesランプドラゴン（先手）対searchラストワードナイトメア。K=5、1500遷移、3秒予算、要求3ターン。これは既定予算の比較実験とは別の動作確認。

| 測定 | 結果 |
|---|---:|
| 結果 | roles側勝利、57操作で終局 |
| 対戦時間 | 42.064秒 |
| roles判断数 | 29 |
| roles判断時間平均 / 最大 | 1.387秒 / 2.135秒 |
| 全判断時間平均 | 0.736秒 |
| プロセスのピークメモリ | 54.23 MiB |
| rolesの比較境界 | 2ターン28回、終局評価3ターン1回 |

保存・再生の最終状態は一致。メモリはWindows `PeakWorkingSetSize`、プロセス寿命全体。単体テストとの短時間の並行実行を含むため、厳密な単独性能比較には用いない。

再現コマンド:

```powershell
.venv/Scripts/python.exe -X utf8 -m svdeck.battle_training replay --output output/role-response-dev-game.json --policy roles --opponent search --seed 93002 --decks ramp-dragon last-words-nightmare --role-k 5 --max-nodes 1500 --seconds 3 --turns 3
```

## 独立した利用者検証

実装前に [spec.v1.json](spec.v1.json) と [independent-fixtures.v1.json](independent-fixtures.v1.json) を固定した。実装・設計担当とは別の新しい担当が、公開入口からT1（局面・確率・非公開情報）、T2（先後2試合）、T3（画面・保存再生）を検証する。最終結果は個別のacceptanceレポートに保存し、完了後この項へ追記する。
