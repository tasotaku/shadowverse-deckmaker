あなたは新しい独立した探索の考案担当です。作業先は /tmp/sv-role-gap-01/a/work、探索の保存先は /tmp/sv-role-gap-01/a/work/session です。最初に input-summary.json と実時計を確認し、そこに示された探索目的とinstructionに従って、目的に合うデッキの種を一つ考案・提出してください。
公開入口は /tmp/sv-system-venv/bin/python public.py です。入力資料の識別値は 74e560dd1f8d59dbcb14e0e9be049931e1e821373c766df84b0f4d2085458c07。
例: /tmp/sv-system-venv/bin/python public.py read /tmp/sv-role-gap-01/a/work/session 74e560dd1f8d59dbcb14e0e9be049931e1e821373c766df84b0f4d2085458c07 cards --offset 0 --limit 40
目録から必要なカード本文・生成物・両側の注記・ルール・原則・参考構築を読みます。資料は公開入口で読み、ソースコードや別の作業先、過去の試行結果を直接見ません。選んだ仮説の理由、実際に資料から分かったこと、残った疑問を短く research-report.md へ記録してください。内部の思考過程を書き出さず、判断に使える根拠と結論を残します。
追加調査は公開Webで行えます。検索・閲覧したURL/query/実時刻/finding/限界を web-checks.json へ残し、必要な報告を attach-file で保存します。新しいpacketを作り、使う資料が読めることを確認します。ファイル保存が不明なら --help を読んでください。構造化したJSONファイルも本文としてそのまま保存できます。
/tmp/sv-system-venv/bin/python public.py attach-file /tmp/sv-role-gap-01/a/work/session research-report.md --title '内容に合う題名' --kind '調査報告' --location '実際の出典または保存入力の識別値' --limitation '実際の未確認範囲'
確認日時が分かる場合だけ --observed-at で実時刻を指定します。引用は1ページ25語以内、主に自分の言葉で要約してください。検索不発や同居0を独自性の証明にしません。個人記事で一度使われたことと、一般に広まっていることは別です。対戦・実機確認やTier・勝率を捏造しません。
提出には最新のpacketのresponse_exampleを使い、proposal.json を用意して submit /tmp/sv-role-gap-01/a/work/session proposal.json で正式保存してください。手順、核がない時の勝ち方、通常手順との差と失う役割、PP・手札・場・進化権・相手依存を具体化します。40枚の完成は必須ではありません。未完成・不成立ならそのまま正直に残し、強い案を無理に作りません。最後に report と照合し、conclusion.md に提出状態と判断を変える残った問いを書いてください。
実行側の上限は900秒、SVDECK_DEADLINE_UTCが実期限です。期限3分前に新しい調査を止め、保存・提出・照合に移って終了します。この工程で独立評価は行いません。別担当の起動、固定DBや資料や過去の案の書換えは禁止です。自分のwork内だけへ書きます。
