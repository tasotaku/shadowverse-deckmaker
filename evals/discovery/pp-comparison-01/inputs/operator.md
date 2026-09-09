# 保存した比較資料を検算する操作

実行環境: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/sv-pp-comparison-prototype/src /tmp/sv-system-venv/bin/python -m svdeck.discovery`
SESSIONは各担当の指定保存先。`packet SESSION --summary`で保存資料のhashを得て、`read SESSION HASH sources --offset N --limit N`で本文を分割して読みます。通常のファイル・JSON読みも使えますが、少なくとも元資料を一度公開readで確認してください。既存資料は変えず、`attach SESSION INPUT.json`で結果を保存できます。入力は `{"sources":[{"title":"…","kind":"検算","location":"…","observed_at":null,"content":"…","limitations":["…"]}]}`。`report SESSION`で保存した識別値を確認します。

B方式のみ使う任意の `pp SESSION INPUT.json` は、二つの行動順を入力すると計算結果を資料に追加します。A方式は通常のスクリプト等で同じ検算を行います。道具の動作説明も両担当へ同じものを渡します。

pp入力は `plans`（二つの計画）と任意の `source_hashes`（このsessionに保存された根拠資料のhash配列）。計画には `name`、`side`（first/second）、`start`（turn・pp・extra_pp）、`actions` が必要です。追加分の状態は available/used/unknown、turnは1以上、PP量は0以上の整数です。

行動の形式:
- `{"kind":"pay","amount":N}`: 明示された支払。
- `{"kind":"gain","amount":N}`: 上限や条件を外部で確認した後の実際の増加。印刷された回復量の解釈はしない。
- `{"kind":"use_extra"}`: 未使用の追加分を使う。原文の行動へ勝手に補わない。
- `{"kind":"next_turn","turn":N,"pp":N}`: 次の連続する自分ターンと開始PP。
行動には任意の `label` を付けられます。現在PPは最大値ではありません。先攻でavailableを設定できません。入力欄名・数値の型・根拠hashの誤りは終了2、手順の途中停止は終了0で結果として保存します。

出力の `plans[].rows` が行ごとの前後、`end` が完了した終点、`difference` が最初の計画から次の計画を引いた差です。問題行は `issue` を持ち、以降は未計算でendはnull。`current_pp` と `available_pp`、不明時の `available_pp_range` を分けます。入力の意味・カード効果・回復上限・手札・盤面・進化権・強さは検査しません。

結果を保存しただけで正しさは確定しません。元資料に合う入力かと、出力をその意味どおりに読んだかを確認し、検査外を記してください。思考の逐語記録は不要です。
