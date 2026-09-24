# 暗号ライブラリ失敗時の修正

最初の統合版 `a6dddc5084d2eebee99a8ecd02a321eab0593998` の独立ソースレビューで、SHA256シンボルが存在してもOpenSSLの設定次第ではNULLを返すこと、その戻り値を無視すると未初期化の照合値を返し得ることが見つかった。

`legacy-only.cnf` を **子プロセスだけの** `OPENSSL_CONF` に指定して実際に再現した。[生結果](crypto-failure.json)では実DLLのSHA256がNULLを返し、Python hashlibは正しいSHA256を返した。ホスト設定・グローバル環境は変更していない。

修正は以下の三点。

- ライブラリを選ぶ際、既知の入力 `abc` のSHA256が正しいことを確認する。
- 機械語の各SHA256呼び出しで戻り値を確認する。
- 失敗時、autoは途中の結果をすべて捨てて従来のPython経路で再計算し、compiledを明示した場合は例外にする。

専用テストではC関数のNULL戻り値を、即時失敗／2回成功してから失敗、それぞれ1／4スレッドで注入した。全整数行・全ハッシュがPython経路と一致し、strict指定では例外になることを確認した。実OpenSSL設定でも全結果一致。出力・公開入口の回帰テスト162 PASS、変更境界・テスト・再現スクリプトのstrict mypyもPASS。ソースレビュー担当の再確認で指摘解消、追加指摘なし。

修正版の関連全体テストも再実行し、**1,379 PASS、既存4 SKIP、無関係211 deselected、75.93秒**。コマンドは `.venv/Scripts/python.exe -X utf8 -m pytest tests/ -q -k 'battle or combat' --tb=short --disable-warnings`。

最初の受入 `../acceptance/` は小規模検証の途中で打ち切り、**INCOMPLETE** として保持した。中・大規模の性能計測は開始していない。結果をPASSへ読み替えず、修正版は別のfresh担当が同じ固定specで `../acceptance-final/` に一度だけ実行する。

再現コマンドは次のとおり。設定はこのPowerShellプロセスと子プロセスに限る。

```powershell
$env:OPENSSL_CONF='C:/Users/tasog/source/shadowverse-deckmaker/docs/evidence/turn-search-max/development/legacy-only.cnf'
.venv/Scripts/python.exe -X utf8 scripts/probe_crypto_failure.py docs/evidence/turn-search-max/development/crypto-failure.json
```

NRT allocationプロファイルが対象とした公開catalogの探索・比較モジュールはこの修正で変えていない。整形・ハッシュの修正後の全体時間は新しい受入計測を用い、修正前の部分計測を最終CLI時間とはしない。
