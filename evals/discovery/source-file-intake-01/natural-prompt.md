あなたは新しいロイヤル探索の考案担当です。保存されたカードと原則を使い、目的に合う種を一つ、成立性・構築配分・既出の疑問まで具体化して提出してください。作業先は /tmp/sv-source-file-intake-01/natural/work、探索は /tmp/sv-source-file-intake-01/natural/work/session です。
最初に input-summary.json と時計を確認してください。公開入口は /tmp/sv-system-venv/bin/python public.py、入力資料は 74e560dd1f8d59dbcb14e0e9be049931e1e821373c766df84b0f4d2085458c07。
例: /tmp/sv-system-venv/bin/python public.py read /tmp/sv-source-file-intake-01/natural/work/session 74e560dd1f8d59dbcb14e0e9be049931e1e821373c766df84b0f4d2085458c07 cards --offset 0 --limit 40
必要な区分を目録から選び、関連するカードの全文、生成物、主役と相方の注記、用語、原則の適用範囲を確認してください。全文を機械的に毎回読み直す作業へ広げず、何を読んだかは公開入口の記録に残します。カードは通常の主役に限定せず、役割の変更・副作用・複数段・強い基盤での配分から一つの仮説を選んでください。

これは保存入口を使った実利用の確認でもあります。調査で分かったことや残った問いを research-report.json（自由なJSONオブジェクト、またはMarkdownならresearch-report.md）へ早めに記録し、そのファイルを次の入口へそのまま渡してください。
  /tmp/sv-system-venv/bin/python public.py attach-file /tmp/sv-source-file-intake-01/natural/work/session research-report.json --title '実際の調査題名' --kind '調査の要約' --location '実際の出典や保存入力の識別値' --observed-at '実際の確認日時' --limitation '未確認の範囲'
limitは複数あれば --limitation を繰り返せます。不明な日時を作らず、その場合は --observed-at を省略してください。報告の内容を別のJSON文字列へ手作業で詰め直す必要はありません。kind/location/limitationsは内容に合うものを自分で指定してください。
返されたadded/existing/source_hash相当の識別値とinput_fileの照合結果をsave-receipt.jsonに保存します。ファイルの本文と出典・限界が保存されていることを、新しいpacketとread sourcesから確認し、handoff-check.jsonへ記録してください。公開入口の保存成功は、内容の正しさや強さを意味しません。

追加の公開調査も行えます。検索・閲覧ごとにURL/query/実時刻/finding/限界をweb-checks.jsonへ保存し、実施していない実機や対戦観察、未取得本文、独自性や勝率の断定を作りません。引用は外部1ページ25語以内、原則自分の言葉で要約してください。先行用途と同じカード名だけで同用途と判定せず、一般に共有された標準の使い方との差を調べ、未確認は残してください。

保存した追加資料を使う場合、/tmp/sv-system-venv/bin/python public.py packet /tmp/sv-source-file-intake-01/natural/work/session --summary で新しい資料を作り、そのhashのresponse_exampleに沿って proposal.json を用意し、/tmp/sv-system-venv/bin/python public.py submit /tmp/sv-source-file-intake-01/natural/work/session proposal.json で提出してください。核が不成立ならその根拠と残った問いを保存し、無理に強い案にしないでください。未完成の着想は未完成として記載できます。核が無い時の動きと得る/失う役割、PP・手札・盤面・進化権・相手依存を具体化します。40枚完成は必須ではなく、配分比較に全リストを使う時は出典の実際の全リストを用います。最後に conclusion.md へ、何を保存できたか・残った不明・提出の状態を簡潔に残してください。

制限は実行側900秒。SVDECK_DEADLINE_UTCが実期限です。期限3分前から新しい調査を止め、報告の保存・再読・提出を優先して終了してください。早く保存した途中報告は未完として区別し、後の変更は追記として保持してください。既存の案・評価・固定DB・本文・他の作業先は変更せず、自分のwork内だけに書きます。別担当は起動しません。内部の思考は報告へ保存しません。
