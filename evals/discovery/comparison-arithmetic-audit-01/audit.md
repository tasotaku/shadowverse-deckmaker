# 次の小さな修正候補の読取点検

候補は、**二案のPPと未使用追加PPを行動順から自動で引き継ぎ、同じ終点で比較する公開操作**です。成立性・比較計算の補助であり、独自な種の発見を増やす効果は未検証です。

終了済みの自然試行は、配分・引き順・次ターン比較を追加しても原6枠の必要性を支持できず、限定停止しました。着想比較試行も、aは通常案に残る追加PPを考慮して差を2PPから1PPへ訂正した後、その小差が役立つ根拠を得られず停止。bは一手守った後の反撃と採用損の比較が残りました。初回指示には既に副作用・複数段・配分・資源時系列があり、説明不足だけが失敗原因とは言えません。

直接の対象は [a第2回の評価](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-2/review-response.json:69) と [訂正と停止](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/answer.json:9) のPP比較です。通常案は追加PPを温存しており、現在PPの差と実際に使えるPPの差を分ける必要がありました。

現行の [取り込み検査](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/src/svdeck/discovery.py:329) は資源欄を文章として受け、[全40枚比較](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/src/svdeck/discovery_compare.py:66) は交換札・種類・コストを集計します。[exploreの数量概算](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/src/svdeck/explore.py:257) はPPの二重使用・時点を検査しません。タグ再検索・全文読出し・資料追加・別案への分岐は既にあります。人やAIが個別コードで計算して資料に添えることも既に可能です。

追加する動作は、開始PPと追加PP使用権、二案の支出・回復・ターン更新を入力し、各時点の残量を計算することです。未使用追加PPは自動で残し、現在PPと利用可能な追加分を別々に返します。条件不明は未確認のままにします。自己申告残量との差、負残量、使用済み追加PPの再使用を返します。既存資料の引用と識別値を保持し、結果保存には既存のattachを使えます。

最小範囲は小モジュール1個、公開操作1個、入力例と算術検査です。本文から効果を自動推測せず、盤面・戦闘・手札・相手の行動へ広げません。したがって [自然試行の場残り誤り](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/natural-trial-01/round-4/decision.json:9) まで直せるとは言いません。

次の1回は、a第2回の訂正前資料を固定し、現行操作と新操作で比較します。正解は、通常側に残る追加PPを失わず、現在PP差2と利用可能PP差1を区別すること。転記・解釈・確認を含めた総時間も測ります。新操作でも取り落とす、同精度の現行操作より時間が増す、正解を知った転記が必要、一般対戦再現へ膨らむ場合は採用しません。通っても既知事例の算術補助に限る証拠で、発見力の合格にはしません。

観測した開始: 2026-09-08T21:29:57Z。保存時の終了: 2026-09-09T01:54:34.236492+00:00。時計が途中で大幅に進んだため、8分以内の完了や能動作業時間は主張しません。主担当へ時計観測差を通知済みです。

対象はmainの `53f73dcda8a578c8ccee8564c6c6643eb38c333d`。新試行0、コード編集0、DB編集0、子担当0。指定された報告2件以外は変更していません。進行中のsketch-firstと指定一時領域、他担当の会話は読みませんでした。全保存記録・全コード・全カードの網羅監査ではなく、読取範囲と位置は [JSON](/tmp/sv-discovery-next-mechanism-audit.json) に残しました。
