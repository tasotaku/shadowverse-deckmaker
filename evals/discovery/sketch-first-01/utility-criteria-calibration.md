固定基準には、40枚完成・Tier証明・全状況での優越の明文要求はありません。既存記録でも、役割の成立と採用価値を分けています。ただし「今回の試行で有用な出力が得られなかった」を「案や過去の成功自体に価値がない」へ広げる誤読余地はあります。基準は変更せず、今回のa/bは採点していません。

1. **ユーザー非要求の上乗せは不可。** [固定utility](/tmp/sv-sketch-first-01/protocol.json:22)は「採用負担に見合う可能性が根拠付きで残る」とし、[design.md](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/docs/design.md:15)は「40枚デッキは組まない」と明記しています。役割の損得と核が揃わない時の方針は必要ですが、全40枚・毎試合の成立・勝率の証明は要求していません。逆に、その役割や負担の根拠を不要にして合格させる読み方もできません。

2. **否定・歴史未確認・資料不足は別の結論です。** [correctness](/tmp/sv-sketch-first-01/protocol.json:20)は「未確認は未確認」、[設計](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/docs/design.md:121)は当時の本文がなければ「歴史再現未確認」、[既存採点条件](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/known-candidate-review/expected.json:73)は「入力不足等で評価不能なら未確認として理由を残し、PASSにしない」としています。資料不足は合格になりませんが、案の価値の否定にもなりません。全棄却・未完成保留だけの試行を有用性未達とする現基準は維持でき、その理由と個別案の未確認事項を併記できます。utility本文だけでは、その記録の分け方まで定まっていません。

3. **成功例の意味を残す原則はあり、4例全部の実際の採点確認はまだできません。** [設計の教材記録](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/docs/design.md:622)は、山札の中身調整と0コスト札の複数段応用、ミルティオの累積打点と他の攻撃、ビバティー・ササニドの強い基盤、マゼルの前後半の役割分担を保持しています。[マゼルの正例条件](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/mazel-role-review/expected.json:6)も「条件付きの優先度判断と意味の成立を分離」し、[実際の評価](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/mazel-role-review/evaluation.json:192)は「打点0、未完成、40枚不足だけによる正例の一律棄却は観測されない」と記録しています。ただし、これは既知説明の意味検査です。自然発見・歴史再現・現候補の有用性の合格には転用できません。他3例もユーザー評価を保持する材料であり、公式事実や勝率を補完していません。

読取範囲は適用ルール、docs/design.mdの上記該当節、固定5基準のみ、過去のマゼル・履歴・既知候補の採点条件と評価記録です。正確な範囲・部分読出し・検索範囲は[JSON](/tmp/sv-utility-criteria-calibration-01.json)に記録しました。初回の長い出力に省略があり、必要な引用範囲を行番号付きで再読しました。

読取逸脱が1件あります。evals/discovery/README.mdの検索出力に禁止対象idea-comparison-01の最終結果要約1行が混入しました。親担当へ申告済みで、結論・採点の根拠に使っていません。禁止対象ディレクトリ内のファイルと今回a/bは未読ですが、完全な非接触を達成したとは主張しません。

この点検は基準文の整合確認に限定します。4例の実行試験や方式の優越、未知の成功例は作っていません。リポジトリ・DB・基準を変更せず、指定の一時成果物2件だけを保存しました。

開始: 2026-09-08T14:20:28+00:00。確認終了: 2026-09-08T14:24:00+00:00。保存終了記録: 2026-09-08T14:26:22.038825+00:00（すべてUTC）。
