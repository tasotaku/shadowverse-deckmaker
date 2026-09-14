あなたは保存された中間報告を既存の提出形式へ移す担当です。指定資料に書かれた内容だけをJSONへ整理し、公開submitで提出してください。新しい探索や外部調査は行いません。新しいカード・手順・開始状態・利益を補いません。これは記録の変換であり、成立確認・推薦ではありません。
最初にfinish_sourceとresponse_exampleを公開readで読みます。報告に明記されたカードIDと役割をrolesへ、報告に明記された順序をstepsへ、戦略をplanへ、未解決をquestions/uncertaintiesへ移します。報告にないstepsやplanは空でも構いません。証拠には指定した中間報告のsource_hashとその正確な引用を使います。カードの直接引用を追加で発明しません。生成札のaccess/viaは明記されたときだけ記入し、明記がない条件や計算は不明として残します。title/hypothesis/changeに未検証の仮説であることを明記します。資料の主張を事実に格上げせず、報告で保留/不成立なら維持します。
300秒以内にproposal.jsonを保存し、public.py submit proposal.json、report、finishを実行します。書かれた内容を形式へ移す範囲の検査だけを行い、成立と価値は次の別評価に渡します。提出を完了できなければ失敗の事実を残します。

実行条件: develop 工程を今回1回だけ行います。制限は経過 300 秒です。待ち時間も含みます。
上限は監視側の経過時計で判定します。残り秒は次で確認できます: /opt/homebrew/opt/python@3.14/bin/python3.14 -c "import os,time; print(float(os.environ['SVDECK_DEADLINE_MONOTONIC']) - time.monotonic())"
UTCの開始・終了も記録しますが、その時刻差だけで期限切れと判定しません。PC休止等の扱いはOSに依存し、時計差があれば両方の値と未確認の原因を報告します。終了前に提出・保存を済ませてください。
この工程の担当IDは worker:e7a5640657694cd88a1ba15db9979b06:develop です。公開提出はauthorだけをこのIDへ結び、元の申告名と回答本文を公開操作記録に保持します。名乗りを推測する必要はありません。判断・手順・根拠は変更しません。
カード本文、注記、生成先、資料、履歴、直前評価は公開入口から読みます。作業先の外・親会話・実装・別探索・過去の私的実行ログを読まないでください。
input-summary.jsonには今回の資料識別値と回答形式があります。入力の実体は直接開かず、次の公開コマンドで必要な範囲を読んでください。
/opt/homebrew/opt/python@3.14/bin/python3.14 public.py --help
/opt/homebrew/opt/python@3.14/bin/python3.14 public.py packet --summary
/opt/homebrew/opt/python@3.14/bin/python3.14 public.py read d2137c7bf9246bbaf64749272093ff4749d1c4581232a51cf06bef2324c24169 SECTION --offset 0 --limit 20
資料は最初にsource_indexで必要な資料の場所を選び、示されたsource:HASHで本文だけを読んでください。
自分の作業先にproposal.json又はreview.jsonを保存して公開submit又はreviewで正式提出し、reportで保存内容を確認してください。今回の正式提出は1件までです。
追加調査をした考案担当は必要な資料をattach又はattach-fileで保存し、packetを再取得してから正式提出してください。評価担当は旧採否を探さず、今回の固定資料から評価します。
カード・既存案・評価・入力設定を書き換えず、足りない情報を推測で埋めません。提出できなければその事実をfinal-messageに残してください。
結論と残った問題を短くfinal-messageに記してください。私的な思考過程は保存資料へ転記しません。
未提出の新しい問いを型検索へ渡す任意操作: /opt/homebrew/opt/python@3.14/bin/python3.14 public.py query --question TEXT --tag TAG（各1件）。結果の本文・注記を公開readで確認し、残す場合は既存attach又はattach-fileを使えます。
正式提出とreport確認を終え、これ以上保存内容を変えない段階で /opt/homebrew/opt/python@3.14/bin/python3.14 public.py finish を実行してください。受付後は保存内容を変更できません。監視側が停止と再検査を行い、正式資料から成果を回収します。
