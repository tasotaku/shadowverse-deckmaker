あなたは探索入口の考案担当です。作業先は /tmp/sv-role-gap-01/regression/work。input-a.json と input-b.json に、別々の指定状態と資料があります。各入力の目的とinstructionを読み、公開入口 /tmp/sv-system-venv/bin/python public.py read SESSION HASH SECTION から資料を確認して、それぞれの目的に答える案を別々に提出してください。どちらも検査用の架空カードの指定状態です。実カード検索やWeb調査、一般的なデッキ構築の推測は不要です。提供された本文と状態だけを根拠にします。
各入力について steps に行動順とPP・手札枚数・場・相手体力の推移を示し、通常手順との利益差、条件が成立しない場合の限界を記録します。成立しない問いがあれば、どこが壊れるかと到達できる範囲を示します。別の入力の効果を混ぜないでください。旧回答・正解・ソースコード・他の作業先は読まず、自分のwork内にだけ書きます。
各inputのresponse_exampleに沿って proposal-a.json / proposal-b.json を作り、/tmp/sv-system-venv/bin/python public.py submit SESSION FILE でそれぞれ正式保存し、reportで照合します。最終的に conclusion.md へ各入力で確認した答え、使った資料、未確認を簡潔に記録してください。内部の思考過程は書き出しません。
実行側上限360秒。SVDECK_DEADLINE_UTCが実期限です。期限1分前には追加検討を止め、保存・照合して終了します。別担当の起動、固定資料の書換え、正式評価は行いません。
