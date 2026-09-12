今回は、考案中の新要求を検索する公開入口の利用確認です。デッキ案の作り直しや正式な改訂・評価の提出は行いません。保存された案・残った問いから、さらに検索すると判断に役立つ問いを1件だけ自分で選び、提供された語彙で空でない検索条件へ対応づけ、queryで既存の型検索へ渡してください。既存searchの問いと条件をそのまま再実行するのでなく、未確定の点から新しい条件を具体化してください。個別カードや特定の答えは指定されていません。
型検索が返した候補の本文・進化・参照先・主役と候補双方の注記を固定資料から読み、問いに対して何を確認できたか、何が未確認かを書いてください。一致0なら調べた条件と範囲を記し、全範囲で不可能とは断定しません。ヒット件数を強さや新規性の証明にしません。queryは固定DBの型検索で、PP・場・手札や実際の生成可能性の証明ではありません。

上限は待ち時間込み経過360秒、今回1回だけです。残り秒は /opt/homebrew/opt/python@3.14/bin/python3.14 -c "import os,time; print(float(os.environ['SVDECK_DEADLINE_MONOTONIC']) - time.monotonic())" で確認できます。UTCの開始・終了と経過時計は区別してください。
入力は次の公開入口だけで読みます。作業先外、親会話、実装、別探索、私的な実行ログは読みません。既存入力を直接開いたり変更したりしません。公開操作の出力を自分の作業先へ保存し再読してよいですが、私的な思考過程は転記しません。
/opt/homebrew/opt/python@3.14/bin/python3.14 public.py --help
/opt/homebrew/opt/python@3.14/bin/python3.14 public.py packet --summary
/opt/homebrew/opt/python@3.14/bin/python3.14 public.py read 72c7a090a1c778dc405afd500627670a57f388dff4adf9448f8eb1529dad9ee2 SECTION --offset 0 --limit 20
/opt/homebrew/opt/python@3.14/bin/python3.14 public.py query --question '自分で選んだ問い' --tag '自分で対応づけた条件'
案はproposal、残問はprevious_reviews/search、カード本文と注記はcards、語彙はfulfillment_mapやcardsのtagsです。readの返すoffset/next_offsetで分割して読めます。1ページのlimitは100以下です。query結果の参照案内から候補の本文・注記を照合してください。queryは読み取りのみであり、以下の添付が成果保存になります。

answer.mdへ、選んだ問い・対応づけた検索条件と理由・query結果の原文JSON・固定版の識別・候補本文と注記の引用・その候補が満たす条件と残る制約・確認時刻・この道具でできたことと未確認のことを簡潔にまとめてください。外部検索、採点変更、formal submit/review、追加の新要求検索は不要です。
/opt/homebrew/opt/python@3.14/bin/python3.14 public.py attach-file answer.md --title '考案中の新要求を検索した利用報告' --kind live-query-use --location live-query:39d4dfce1ccd4d8582dedc9960a83aae:use
添付後にpacket --summaryを再取得し、新しい識別値のsourcesから自分の追加報告の全文を公開readで再読してください。全旧資料を読み直す必要はありません。添付前後のsources行数と返った内容から位置を特定できます。最後に /opt/homebrew/opt/python@3.14/bin/python3.14 public.py report で保存を確かめ、通常終了してください。finishは正式な改訂・評価用のため今回は使いません。保存できなければ代理提出は求めず、その事実をfinal-messageへ書いてください。
最終回答には報告の識別値と実際に確認した結論・未確認だけを短く記してください。
