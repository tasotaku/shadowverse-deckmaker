あなたは今回のロイヤル案の考案と保存入口の実装に関わっていない、独立した評価担当です。資料と提案だけを読み、案の成立性・試す理由・既出を理由付きで評価してください。
作業先は /tmp/sv-source-file-intake-01/review/work、自分の探索コピーは /tmp/sv-source-file-intake-01/review/work/session。入力はinput-summary.json、資料識別値は 9b372f67f9ab2b478790b873bcf44e280c1955d204d3802f15aa2ae0ba29f895 です。元の別作業先や過去の評価記録は読まず、コピー内を公開入口から読みます。
公開入口は /tmp/sv-system-venv/bin/python public.py。
例: /tmp/sv-system-venv/bin/python public.py read /tmp/sv-source-file-intake-01/review/work/session 9b372f67f9ab2b478790b873bcf44e280c1955d204d3802f15aa2ae0ba29f895 proposal --offset 0 --limit 50
必要な全文・両側の注記・生成物・用語・追加資料を目録から読み、既定のreview指示に従ってください。資料の主張をそのまま正しいとせず、PP・手札・場・進化権・相手依存と、通常の基盤で得る/失う役割、核を引かない時の動きを確認します。出典や主張が足りなければ未確認を残します。既知のカード名だけで同用途とはせず、一般に共有された標準用途との違いを確認してください。
必要な公開検索は可。実際のURL/検索語/確認時刻/確認範囲はweb_checksへ記録し、検索不発から未知や強さを断定せず、未実施の実機や対戦の観察を作りません。外部ページの引用は1ページ25語以内にし、原則自分の言葉で要約してください。

追加資料に保存された調査報告を実際に読めたか、その報告のどの根拠が評価に使えたかを evidence-use.json に記録してください。未確認の記載も伝わっているかを確認します。保存入口の使いやすさは採点対象にせず、保存の成否から案の良さを加点しないでください。
response_exampleに従ったreview.jsonを作り、/tmp/sv-system-venv/bin/python public.py review /tmp/sv-source-file-intake-01/review/work/session review.json で提出してください。評価はこのコピーへ保存します。原本への反映は開発者が元資料の一致を確認して行います。
最後にevaluation.mdへ、判定理由、実際に解けたことと残った問いを簡潔に残してください。独立評価であり、実装者や考案担当へ期待答案を相談しません。

実行側の制限は600秒。最初に時計とSVDECK_DEADLINE_UTCを確認し、期限2分前から新しい収集を止め、評価の保存を終えてください。途中保存は途中と明記し、正式なreviewが保存されなければ未提出のまま扱います。変更は自分のwork内だけ。元案・カードDB・固定資料は変更せず、別担当を起動しません。内部の思考は保存しません。
