固定した5項目で全6検討回と全6別評価を整理した。両方式とも最終時点の有用な出力は得られなかった。総合点、勝者、成功率は作らない。

| 項目 | a | b |
|---|---|---|
| 公開操作の完了 | PASS | PASS |
| 手順の正確さ | PASS | PASS |
| 追加検討の進展 | PASS | PASS |
| 試す理由のある種 | FAIL | FAIL |
| 限界を偽らない記録 | PASS | PASS |

手順のPASSは、最終の提案と訂正資料に書かれた指定条件下で、既知の重大な誤りが残らないという判定。自然な対戦で必要札・盤面・進化権を揃えられることや、勝率・採用価値を認定したものではない。

**方式aの根拠**

公開操作の完了（PASS）：公開読出し・資料追加・比較・2提出・3別評価・レポート対応まで実行できた。第3回の追加資料だけの停止も保存され、偽の第3案は作られていない。 探索用コードの障害修正は記録上不要だった。試行中の別機能統合・設計文書追記とrootの保存補助エラーは別記し、全環境不変・厳密な統制達成とは呼ばない。 根拠：[a/round-1/operations.md](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-1/operations.md), [a/round-2/operations.md](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-2/operations.md), [a/round-3/operations.md](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/operations.md), [a/round-3/review-report.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/review-report.json)。

手順の正確さ（PASS）：最終の提案と訂正資料を一緒に読む範囲では、指定した手順の合法性・効果・PP・手札・場・進化権に既知の重大な誤りは残らない。7→6→3→6枚、T8の9-(5+0+2+2)=0PP/10点、T9の9-(0+0+2+2)=5PP/13点は整合する。通常側に残る追加PPを含めれば4PPで、差は1。 正式revision2本文のPP2差はそのまま残り、訂正は追加資料として保持されている。本文だけを最新の結論とみなしてはいけない。指定ドロー・相手の対象・空き枠・生存・権利温存は条件で、初手からの実用到達や実ゲーム動作をPASSとしたものではない。 根拠：[initial-packet.json.gz](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/initial-packet.json.gz), [a/round-2/answer.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-2/answer.json), [a/round-3/answer.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/answer.json), [a/round-3/review-response.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/review-response.json)。

追加検討の進展（PASS）：実際の指摘から4枚交換を1枚へ縮め、モエルを保持し、手札9枚・フェアリー3枚保持・順番調整を外した。通常側の同時期出力を比較し、PP差の訂正と、利益を補う根拠を得られない枝の停止まで進んだ。言い換えだけではない。 全ての疑問が解決したわけではない。停止は案一般の無価値や不成立の証明ではなく、この枝・この資料範囲の判断。 根拠：[a/round-1/review-response.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-1/review-response.json), [a/round-2/answer.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-2/answer.json), [a/round-2/hand-trace.md](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-2/hand-trace.md), [a/round-3/answer.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/answer.json)。

試す理由のある種（FAIL）：この試行の最終時点では有用な出力は得られなかった。核がない時の通常の攻撃方針と失う役割は説明されたが、差1点/1PPを、5PP・進化権・機能のある捨て札3枚・通常側の守護/追加破壊/手札1枚の損失に見合う利益へ結びつけられず、考案担当と最終別評価とも現案を見送った。 手順の正しさ、引用一致、改訂の実施を有用性へ加点しない。実戦未実施だけを不合格理由にはしていない。 根拠：[a/round-2/answer.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-2/answer.json), [a/round-3/answer.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/answer.json), [a/round-3/review-response.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/review-response.json)。

限界を偽らない記録（PASS）：検索範囲・取得失敗・仮定計算・未確認を分け、共起や検索不一致から未発見とせず、Tier・勝率・初見加点を作っていない。既出の中核と緋岸同時コピー全体を区別し、過大なPP差も公開資料で撤回した。 記録には記事名をSpicaメンバー紹介とした誤記があり、保存Web出力の実題名はおさかな鯖メンバー紹介。中核の言及自体は保存本文にもある。全外部出典の真正性を独立に再取得した評価ではない。 根拠：[a/round-1/research-sources.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-1/research-sources.json), [a/round-2/review-web-log.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-2/review-web-log.json), [a/round-3/review-packet.json.gz](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/review-packet.json.gz), [a/round-3/review-response.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/a/round-3/review-response.json)。

**方式bの根拠**

公開操作の完了（PASS）：短い2着想の比較を最初に公開attachへ残し、選択変更、2提出、追加資料、3別評価、レポート対応まで進んだ。第3回の提出なし停止と別評価の継続余地を両方保持できた。 初回の補助JavaScript構文エラー1件やWeb/UI取得失敗はあった。公開CLIの記録上の失敗は0。探索用コードの修正は記録上不要だが、試行中の外部統合による統制逸脱は別記。 根拠：[b/round-1/operation-record.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-1/operation-record.json), [b/round-2/operation-record.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-2/operation-record.json), [b/round-3/operation-record.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/operation-record.json), [b/round-3/review-report.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/review-report.json)。

手順の正確さ（PASS）：指定条件の手順と最終補足に既知の重大な誤りは残らない。7/7ベア2体は5点を各3点にして7/4、全体4点を各3点にして7/1。Aではヒエン6PPと超進化マガチヨの攻撃を処理に使わせる。B/C/Dの敗北も保持。次ターンは相手14、自分4、既知の3PP+7PPを9PPで併用できず、ヒエン再登場を引き継ぐ。 先攻の到達例と後攻T8・EP0/SEP0の比較は別々の指定状態であり、同じ完全な一試合ではない。相手体力12→14は第3回資料で補足される。手札取得・生存頻度・全自然ドロー分岐・実ゲーム動作は未確認。 根拠：[initial-packet.json.gz](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/initial-packet.json.gz), [b/round-2/proposal.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-2/proposal.json), [b/round-2/fixed-state-comparison.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-2/fixed-state-comparison.json), [b/round-3/continuation-clarification.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/continuation-clarification.json), [b/round-3/review-response.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/review-response.json)。

追加検討の進展（PASS）：3回強化と適時取得への依存を1回強化後の保持へ減らし、単体耐久から同じ全手札での防御比較へ進んだ。守った次のターンの残状態を追って、反撃へ接続したとは言えないことを具体化した。既出資料を加えて水増しの第3案を出さず停止した。 最終別評価はdevelopであり、停止の適切性への完全な一致はない。ただし第2回の構築方針変更と比較の進展だけでも固定development条件を満たす。停止の一致をPASSの必須根拠にしていない。 根拠：[b/round-1/review-response.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-1/review-response.json), [b/round-2/proposal.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-2/proposal.json), [b/round-2/fixed-state-comparison.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-2/fixed-state-comparison.json), [b/round-3/decision.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/decision.json), [b/round-3/continuation-clarification.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/continuation-clarification.json)。

試す理由のある種（FAIL）：この試行の最終時点では有用な出力は得られなかった。守護1体では敗北する指定例で一手を稼ぐ差はあるが、その後に有効な攻撃・防御へ戻れる根拠、ヒエンの早出し・復帰を減らす負担との比較が残る。考案担当は推薦せず停止し、別評価もtestではなくdevelopにとどまった。 不一致や未完成の保留を有用性へ加点しない。基本用途の既出だけで棄却せず、1枚配分の追加利益も検討したが未証明。全状態で弱いという結論ではない。 根拠：[b/round-2/fixed-state-comparison.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-2/fixed-state-comparison.json), [b/round-3/decision.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/decision.json), [b/round-3/continuation-clarification.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/continuation-clarification.json), [b/round-3/review-response.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/review-response.json)。

限界を偽らない記録（PASS）：2着想を自己仮説と明示し、基本用途の既出、1枚配分の未確認、検索・本文・画像の読取範囲、取得失敗、対戦0を分けた。公開仮組と自案の11枚差を残し、第三者の旧対戦成績を今回の勝率へ転用していない。 最終別評価実行記録は現提案を6手順と記すがproposal.stepsは5件で、件数の記録誤りがある。公開X画像そのものは今回の181ファイルに保存されておらず、最終採点者は画像の再目視をしていない。記録された考案者・別評価者の一致以上の一次確認を主張しない。 根拠：[b/round-1/idea-comparison.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-1/idea-comparison.json), [b/round-1/selection-update.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-1/selection-update.json), [b/round-3/operation-record.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/operation-record.json), [b/round-3/review-response.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/b/round-3/review-response.json)。

**6回の結果を保持する**

| 方式・回 | 正式提出 | 別評価（手順 / 価値 / 既出） | 観測された結果と残り |
|---|---:|---|---|
| a・1 | 1 | conditional / develop / unconfirmed | ゴッデスで余剰フェアリーを強化レイピア等へ替える4枚交換を提出。T8/T9の指定例は5点/15点。 手札9枚・捨て札3枚・手札順・EP確保は未解決。別評価はモエルの戻し機能とルリアの確定した大型取得の損失を指摘。 |
| a・2 | 1 | conditional / develop / known | 4枚交換からルリア1→ゴッデス1へ縮小。7枚から3枚だけ残す方式で手札順とフェアリー専用保持を外し、指定ドロー会計を追加。 23点対22点の対応例を作ったが、翌ターンPP差2という記述は通常側の追加PP未使用断面。別評価は実使用差1を指摘。5月の既出言及を確認。 |
| a・3 | 0 | conditional / drop / unconfirmed | 正式提出なし。追加6資料にPP差1への訂正と理由付き停止を保存。別評価も現案をdropとした。 自然な防御・補充と7枚保持の両立、差1点/1PPが必要な局面、旧作者の全40枚・同時コピーの実使用は未解決。 |
| b・1 | 1 | conditional / develop / unconfirmed | 短い2着想をattach後、エルタロの補充からベアの防御へ調査対象を変更。ヒエン1→ベア1を提出。 両着想の基本用途は既知。3回強化の取得経路や従来の防御との比較不足でdevelop。比較記録自体は採用利益に加点しない。 |
| b・2 | 1 | conditional / develop / unconfirmed | 1回強化で引いたら保持へ変更。指定した同じ全手札で従来札と比較し、A/Eはそのターンの敗北を防ぎB/C/Dは防がないことを示した。 先攻T5からの到達例と後攻T8の防御例は別条件。一手を稼いだ後の攻撃・防御の継続とヒエン減の費用は未解決。 |
| b・3 | 0 | conditional / develop / known | 正式提出なし。相手回復14・ヒエン復帰を含む次ターン補足と、ベア1枚を含む8月公開仮組など9資料を追加し、考案担当は停止。 独立評価はdevelop/known。停止と継続余地の不一致を残す。既知手札2枚では稼いだ一手から反撃へ接続せず、自然ドローを含む全否定でもない。 |

aの最終unconfirmedは具体案全体の未確認を指す。前回knownとされた「ゴッデスで強化レイピアを複製する中核」の既出が撤回された意味ではない。bの停止とdevelopの不一致は未解決のまま上限3回で終了した。

**作業負担**

時刻はUTC。生成は実開始→保存終了、評価は実開始→各記録の終了観測。終了時刻の定義は同一ではない。

| 方式・回 | 生成開始→保存終了 | 生成の経過 | 評価開始→終了観測 | 評価の経過 | 生成CLI 成功/失敗 | 保存資料数（累計） |
|---|---|---|---|---|---|---:|
| a・1 | 09:51:52→10:16:40.005956 | 24分48.01秒 | 10:17:52→10:31:18.453400 | 13分26.45秒 | 13/0 | 15 |
| a・2 | 10:33:10.721498→10:53:54.429953 | 20分43.71秒 | 10:55:07→11:07:08 | 12分01.00秒 | 6/0 | 24 |
| a・3 | 11:12:19.700994→11:25:27.948996 | 13分08.25秒 | 11:26:55→11:39:55 | 13分00.00秒 | 3/0 | 30 |
| b・1 | 09:51:59→10:14:45.570285 | 22分46.57秒 | 10:15:56→10:30:02.398870 | 14分06.40秒 | 10/0 | 14 |
| b・2 | 10:31:50→10:52:15.773678 | 20分25.77秒 | 10:53:35→11:05:40 | 12分05.00秒 | 5/0 | 20 |
| b・3 | 11:10:39→11:33:27.868816 | 22分48.87秒 | 11:37:17→11:50:45.855632 | 13分28.86秒 | 5/0 | 29 |

方式a：3検討回、2正式提出、3別評価。生成CLI計22回、記録上の公開CLI失敗0、評価形式の再試行0。生成の経過区間の合計は58分39.96秒、評価は38分27.45秒。
方式b：3検討回、2正式提出、3別評価。生成CLI計20回、記録上の公開CLI失敗0、評価形式の再試行0。生成の経過区間の合計は66分01.21秒、評価は39分40.25秒。

- 各時計差は推論・読取り・通信・保存・ツール待ちを含む実経過。能動作業と待機は分離不能。配信→開始も純待機ではない。
- 初回の個別dispatchは09:51:23〜09:52:35.608016の範囲で連続実施。上表の29秒/36秒は共通開始境界からの差であり個別待機時間ではない。
- a初回・第2回は調査終了専用の時計なし。提出結果ファイル保存時刻は上限にだけ使用。a第2回は主保存10:53:26.298229の後に時刻精度を追記し10:53:54.429953が最終保存。
- 生成終了は保存終了を用いた。評価終了はa1が記録保存時刻、a2/a3/b2が評価・登録・照合後の時計で、その後に最終時刻保存のみが続く。b1は最初のREADME読取直後から保存終了、b3は排他的最終書込時刻。定義は同一ではない。
- protocolのラウンド終了は評価登録時点。上表のreview_endは照合・保存まで含み、その時点と混同しない。a1登録の秒は未記録、b1登録完了観測10:28:48、a2コマンド終了11:04:55.049466、b2終了11:03:30.193243、a3登録観測区間11:36:52〜11:37:56、b3終了11:47:26.936851。
- 生成担当の公開CLIはa=13/6/3、b=10/5/5の自己記録を原結果と対応確認した。全シェル履歴による完全な再計数ではない。レビューの中核登録/レポートは各回1ずつ。a1は追加read2とhelp1を記録、b1は追加read1、b3はhelp1を記録。review以外も含む初回の厳密総数は不足。
- 初期4資料を含む資料件数。機械比較・自己計算・公開記事要約・40枚転記を含み、独立した実戦観察数ではない。両方式とも同条件の対戦観察・ゲーム内試行・勝率推計は0。
- 全6回で正式提出は各回最大1。第3回は両方式とも時間上限前の理由付き停止で、未解決は残る。全評価は配信基準20分以内の終了記録。初回a保存は25分目安を17.006秒越えるが5分の保存猶予内、調査終了の独立時計はない。

各ラウンドのroot配信→実開始の差、生成調査終了の有無、Web/UI件数は [evaluation.json](/tmp/sv-idea-comparison-01/final-evaluation/evaluation.json) のworkload.roundsに保存した。root全操作の完全な回数、トークン費用、能動作業と待機の分離は未計測。

**途中の変更と失敗**

固定条件は途中の本体変更を障害修正に限ったが、10:43:02.584511の記録では別依頼の記録画面を統合している。初期版5a1fcef、統合前fc7e6d0、統合300f0dd、終了時e1f2accを区別する。保存記録では探索関連コードと固定入力は不変。設計文書§4.5の7行追記は現在の文書を読んだ担当に見えた可能性があり、影響ゼロとは断定しない。[system-changes.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/system-changes.json)。

rootには11:13:22のprocedureキー誤認、11:43:32.415435のid/card_id誤認という保存補助の失敗2件がある。元出力を変えず補助処理を直した記録で、評価の再試行ではない。保存準備・新規調査停止通知の配信区間、開始時刻の追加問い合わせ（正確な配信時刻なし）も残した。[round-3-progress.json](/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/evals/discovery/idea-comparison-01/round-3-progress.json)。

各担当に出力省略・Web本文欠落・ブラウザー利用不可などの取得障害があった。b初回の補助JavaScript構文エラー、b第2回のブラウザー1失敗、a第3回のブラウザー3失敗などを公開CLIの成功と混ぜない。保存元は各回の操作・評価実行記録であり、全UI操作の映像を再監査したものではない。

**照合した範囲と省略**

181ファイルの識別値は索引と一致。15個の保存packetを機械照合し、内容の識別値と初期contextとの一致を確認した。初期は212カード・採用可能113カード・追加4資料。終了時のa30/b29資料とは別である。6件の評価は公開reportのauthorと入力番号で各1件へ対応し、回答の全項目が一致した。4提案と6評価の引用照合にも不一致はなかった。これを有用性へ加点していない。

採点者は固定protocol・manifest・指示、全6回の提案/停止と全6評価の主張、操作・時刻記録、固定カード22件の必要項目と両側注記、固定ルール、原則の目的・1.5・3.2・5と6の必要範囲、最終packetの出典一覧と必要本文を読んだ。固定principlesには§7見出しがなく、既出判断は保存された目的・§5およびREVIEW指示を参照した。

全181ファイル全行、212カード全件、タグ/raw/要求全量、原則の非関連節、全比較表の重複行、全Web生ログ、動画全編、元の公開X画像は読了していない。Web出典の多くは保存要約であり、再取得は行わない。a第2回の保存Web生ログでは既出言及の該当段落と公式コピー定義の抜粋を読んだ。読取箇所・機械照合だけの箇所・省略は [execution.json](/tmp/sv-idea-comparison-01/final-evaluation/execution.json) に分けた。

**観測と原因の仮説を分ける**

- この1組ではaは主役を維持しながら交換負担を減らし、最終別評価がdropになった。bは公開した2着想から初回中に選択変更し、最終別評価はdevelop/knownだが考案担当は停止した。
- 両方式とも3検討回・2正式提出・3別評価。初期4資料からaは30、bは29へ増えた。生成CLIはa計22、b計20。これらは成果点や独立観測数ではない。
- 初回bでは短い比較が選択変更の経緯として残った。一方aにも未提出のイヴを山札へ戻す仮説メモがある。aが一案しか考えなかった比較ではない。
- 中核の既出と、具体的な配分/追加カードによる改善の未証明を両方式とも保持した。a最終novelty=unconfirmedと前回knownは対象範囲の違いで、中核の既出が撤回された意味ではない。

- 未確定の仮説：短い比較の明示がbの初回の切替を助けた可能性はある。しかし異なる担当・異なる案・異なるWeb到達で、因果効果は分離できない。
- 未確定の仮説：最終の別評価ラベルの差には、案の限定利益の差と評価担当の判断差の双方があり得る。1組では方式の優越へ帰属できない。
- 未確定の仮説：両方式で同じ枝の追加調査が増えた原因が比較工程の不足か、資料・探索方針・候補そのもの・時間/担当差かは確定していない。

この1組は担当差と別評価者差を含む。別入力への一般化、方式の本採用、全体目標の達成を示さない。未完成を保存したことと、試す理由のある種を得たことを区別する。

評価区切り：2026-09-08T12:08:06.068349+00:00。実開始11:53:51 UTCからの経過は855.068秒。予定12:08:10 UTCより前に保存。未確認は上記とexecution.jsonに保持した。
