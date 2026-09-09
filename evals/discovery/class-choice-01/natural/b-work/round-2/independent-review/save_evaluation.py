import json,datetime
from pathlib import Path
out=Path('/tmp/sv-class-choice-01/b-work/round-2/independent-review')
read=lambda f:json.loads((out/f).read_text())
review=read('review.json');verification=read('report-verification.json')
packet_path='/tmp/sv-class-choice-01/b/session/packets/'+review['packet_hash']+'.json'
p=json.load(open(packet_path))['data']
card_ids=sorted({r['card_id'] for r in p['proposal']['roles']}|{10672110,90071130,90074150,10674110,10771310})
full_source_hashes=[p['sources'][i]['source_hash'] for i in [1,3,8,9,21,22,23,25,36,41]]
reading={
 'packet_path':packet_path,'packet_hash':review['packet_hash'],'fixed_packet_recreated':False,
 'instructions_read':['/tmp/sv-class-choice-01/b-round-2-review-instructions.txt','/tmp/sv-class-choice-01/reviewer-instructions.txt','/tmp/sv-class-choice-01/operator-readme.md','/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/AGENTS.md'],
 'imported_rules_read':['values.md','communication.md','explain.md','parallel.md','design.md','coding.md','workflow.md','knowledge.md','ai-code-guide.md','models/gpt-5-6-terra.md'],
 'rules_root':'/Users/miyauchitsubasa/Desktop/work/agent-lab/rules/',
 'project_design':{'path':'/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/docs/design.md','full_text_line_ranges_read':['1-53','199-423','487-553'],'heading_search':'全体の見出しとnovelty/過去/試行等の一致行を確認。本文の全1036行を読了したとはしない。','reservation':'§5/6/既出判定の一般原則を適用した。埋め込まれた過去別試行の事例・結論・期待評価を今回の採点根拠には使わず、別試行記録へ進んでいない。'},
 'packet_sections':{'proposal':'全項目を分割して読了。途中の出力省略箇所はrolesとsteps[0:2]等を再表示して補った。','instruction':'全文','response_example':'全文。公開readでも35行すべてを取得。','rules':'全117行','keywords':['アクセラレート','カウントダウン','ファンファーレ','突進','進化時'],'cards':{'read_count':len(card_ids),'total':len(p['context']['cards']),'card_ids':card_ids,'fields':'全採用15種と参照生成物6種の本文・進化後本文・関連効果・両側注記・コスト・クラス・合法性。raw全項目/抽出タグ/他593枚の本文は読了していない。'},'known_decks':{'read_count':5,'total':33,'ids':[4,15,19,26,31],'fields':'ネメシス5構築のリスト・来歴・合法性。Tier値は出力から除外。'},'sources':{'titles_indexed':44,'full_read_hashes':full_source_hashes,'partial_read_hashes':['8dcebe816f704b5bd399decd6a809f97a119df0b19a57a6864e43210c29f0e73'],'partial_scope':'比較資料はdeltaと参照元を確認。両方の40枚を別に全文読み、独立に1枚交換と合法性を計算。残る33資料の本文は読了していない。'},'search':'全5問。すべて検索候補0件だが、充足不能とは扱わない。','history':'空配列を確認','previous_reviews':'空配列を確認。過去評価本文は読まない。','review_contexts':'指定review packetでは空配列。登録後reportでは自分のreview_hashに一致する1件のみ抽出。','fulfillment_map':'未読。今回の指定手順評価では本文を使用。','context_metadata':'全文'},
 'round_2_support_read':['research.md','execution.json','hand-ledger.json','early-ledger.json','report-verification.json','root-review-packet-summary.json'],
 'support_material_equality':'research.md/hand-ledger.json/early-ledger.jsonは指定packet中の追加資料本文とバイト単位で一致。4件目の追加資料（Web照合）もpacketから全文を読んだ。',
 'web_scope':{'pages_opened':3,'official_card_api_gets':4,'search_queries':2,'source_research_queries_read':10,'unread':'動画本編・字幕、全投稿・他言語、公式コピー状態仕様の別媒体。検索結果は出力範囲のみで個別本文へ進まない。'},
 'explicit_exclusions':['他方式a','旧自然試行の記録','src/evals','過去評価本文/判定','親会話','考案担当への採点相談','追加agent/子実行','本番DB/snapshot/元資料/既存記録の編集']}
(out/'reading-scope.json').write_text(json.dumps(reading,ensure_ascii=False,indent=2))
criteria=[
 {'point':1,'subject':'公開工程と資料保持','judgment':'tested_path_pass','evidence':'指定版の公開read、公開review1件、公開report2回を成功。reportで提出内容全項目・入力版・44資料・クラス・revisionを照合。元案1件は維持され、新しい正式改訂はない。追加4資料のうち3件は補助記録との完全一致を独立確認。','unknown':'他セッション・他クラス・全入力の操作成功や発見力は未評価。正式本文を更新しない停止のため、追加資料の修正を元本文に適用済みとはしない。'},
 {'point':2,'subject':'手順の正しさと到達準備','judgment':'conditional','evidence':'採用15種はネメシス/ニュートラルのローテ合法。生成物6種を別扱い。初手から7ターンまで2経路、8〜10ターンの3経路を本文と照合し、手札最大9・場最大5・PP・進化権の範囲で成立する。元の8PP行動全部とシアター2PPは8ターン目に同居せず、条件付き判定は追加資料の修正手順へ適用する。','unknown':'軽減状態コピーは固定注記に依存。指定取得順の頻度、相手の全プレイ、実際の生存、必要な攻撃先、妨害やダメージ軽減は未確認。'},
 {'point':3,'subject':'追加調査による発展と停止','judgment':'substantive_progress_stop_supported','evidence':'人形を用意する経路と通常ドローを保つ判断を具体化した。初手からの取得と防御、進化権競合を2経路で可視化。初回コピーだけで得る玩具2枚と再コピーの増分を区別し、公式4枚の本文取得と個別Q&A未取得も分離した。資料追加だけの見かけの前進ではない。','resolved_within_given_conditions':['8〜10ターンの人形接続','8ターン通常ドローの保持'],'partially_resolved':['初手から指定状態への到達（存在例のみ）','自己反復の利益と通常用途比較','既出状況とコピーの個別公式仕様'],'stop':'今の比較では試す理由を強める局面を特定できず、資料保存で止めるのが妥当。未確認を理由に無期限継続しない。'},
 {'point':4,'subject':'採用負担に見合う試す価値','judgment':'drop_current_proposal_archive_materials','evidence':'10ターン目決着例の8ターン再コピーは補充を増やさず、大きな本体と余分な深淵に対し追加PP・進化権・誠心を失う。初回7PP/捨て3枚/深淵用途とベルゼバブ1枠減を払うが、普通の補充・除去を超えて必要な仕事へ変わる局面はない。既存39枚の道を残す軽さは認めるが、序盤配分を改善した証拠や核が揃わない場合の上積みはない。','limitation':'全経路無価値の反証ではなく、現在の保存案への推薦・自動継続を見送る判断。40枚完成、Tier、勝率、全引きでの優越は要求しない。初回コピーによる手札入替と長期戦での追加補充には条件付きの利益が残る。','reopen_condition':review['next_questions'][0]},
 {'point':5,'subject':'既出状況と過大評価の防止','judgment':'unconfirmed_no_unearned_bonus','evidence':'標準の決着と必要札複製は公開用途として確認。ハイランダーでのゴッデスとヨグゼンタ同居は特定の反復の普及とは別。今回の2検索も同用法の普及を確認できず、検索不発は新規性の証拠にならない。','unknown':'特定反復の一般への普及、動画・全投稿・他言語。Tier・勝率・初見の強さを加点していない。'}]
evaluation={'task':'class-choice-01 b round-2 independent review','author':review['author'],'target_revision':1,'input_packet_hash':review['packet_hash'],'verdict':{'procedure':review['procedure'],'value':review['value'],'novelty':review['novelty']},'criteria':criteria,'formal_review':{'target_revision':1,'saved_file':verification['formal_review_saved_file'],'review_hash':verification['review_hash'],'number_note':verification['review_number_note'],'report_path':verification['report_review_path']},'report_checks':verification['checks'],'reading_scope_file':'reading-scope.json','scope_reservation':'正式案1は古いまま。今回の条件付き成立評価の対象はその案と追加4資料の保存版1件で、旧案本文を修正したという評価ではない。','public_review_count_by_this_reviewer':1,'substantive_rescoring_count':0}
(out/'evaluation.json').write_text(json.dumps(evaluation,ensure_ascii=False,indent=2))
text='''判定は **手順は条件付きで成立／この案の推薦と継続は見送り／既出状況は未確認**。追加資料を保存して止める判断を支持する。正式案1は古いままで、以下の成立確認は追加資料の修正を含む保存版へ適用する。

1. 公開操作は確認できた。指定保存版の読出し、独立評価1件の登録、報告との照合が成功した。入力版、44資料、ネメシス、案1、判定と全文が保持された。新しい正式改訂はない。操作の成功を種の有用性とは扱わない。

2. 指定条件の手順には成立する経路がある。8ターン目に再コピーを省けば、玩具3＋ヨグゼンタ2＋誠心1＋シアター2の8PPで人形を用意できる。再コピーを残す例は誠心を省き、後攻追加PPを使う9PP。初手から7ターンまでの2経路も、指定された引き順なら手札と進化権が足りる。20点には相手の攻撃先、生存、妨害や軽減がない条件が要る。元の8PP行動全部にシアターを足す10PP手順が成立したわけではない。軽減状態のコピーは固定注記が根拠で、個別の公式説明は未取得。

3. 追加調査には実際の発展がある。人形の用意と通常ドロー保持を具体化し、守りへ進化権を使うと反復回数が減ることを追跡した。公式本文を得たことと個別仕様を確認できたことも分離している。到達頻度・採用価値・普及状況は解決していない。

4. 今の案を試す候補へは上げない。初回コピーだけで玩具が2枚あり、10ターン目に決着する比較例では8ターン目の再コピーで増やす補充を使わない。大きな本体と余分な深淵は得るが、追加PP・進化権・誠心を失う。初回7PP、捨てる3枚、ベルゼバブ1枠減も必要で、それらの負担を払う意味がある防御や決着の局面は示されていない。既存39枚を残す軽さと長期戦の追加補充の可能性は認める。これは全経路の無価値を証明した判断ではなく、現在の案の推薦・自動継続を止める判断である。

5. 新しさは未確認。既存の決着と必要札複製は知られた用途だが、自己2PP化と玩具維持が一般に広まっているかは確認できない。検索不発、同居の有無、Tier、勝率、初見への期待では加点しない。

再開する条件は、9〜10ターン目にベルゼバブがなく玩具が残り1枚の具体的な局面で、普通の補充・除去では資源が尽き、再コピーが追加補充から防御・決着へつながるという比較材料が得られること。未確認が残るだけで継続しない。

実際に読んだのは、全採用15種と生成物6種の本文・両側注記、提案全文、ルール117行、関連用語5件、追加4資料と指定補助記録、ネメシスの既知構築5件など。全614枚・全組合せの走査は行っていない。過去評価・他方式・旧試行記録は読んでいない。設計書内に現れた過去別試行の例は採点根拠にしていない。

独立のWeb照合では[公式の対戦説明](https://shadowverse-wb.com/ja/system/cardbattle/battle/)、[元のOTK構築](https://gamewith.jp/shadowverse-wb/575049)、[2Pickの用途メモ](https://note.com/udonkaree_2/n/n27684e02338b)と公式カード4枚を読んだ。組名2件も検索した。動画本編・字幕・全投稿・他言語は未調査。

'''
text+=f"正式保存先: `{verification['formal_review_saved_file']}`\n\n評価の識別値: `{verification['review_hash']}`。公開応答の番号は案1で、別の通し評価番号は提供されない。報告では `{verification['report_review_path']}` と自分の識別値に一致する対応情報を照合した。\n\n"
ops=[{'command':'read SESSION HASH response_example --offset 0 --limit 40','success':True,'timing':'個別時刻未採取。開始から03:55:55 UTCの実時計確認までに実行。'},read('public-review-operation.json'),read('public-report-operation.json'),verification['operation']]
finished=datetime.datetime.now(datetime.timezone.utc).isoformat()
execution={'started_at_utc':'2026-09-09T03:54:12Z','substantive_review_finished_at_utc':'2026-09-09T04:01:25Z','confirmation_finished_at_utc':verification['checked_at_utc'],'saved_at_utc':finished,'deadline_utc':'2026-09-09T04:14:12Z','target_revision':1,'review_packet_hash':review['packet_hash'],'public_operations':ops,'public_success_count':4,'public_failure_count':0,'public_review_operations':1,'public_review_format_corrections':0,'substantive_rescoring_count':0,'public_retry_count':0,'local_read_errors':[{'count':1,'error':'ability_keywordsを配列と仮定した補助読取でTypeError。辞書だと確認し、関連5用語と残りの提案部分を再表示した。公開操作の失敗や再採点ではない。'}],'local_metadata_corrections':1,'local_metadata_correction_note':'検索時刻範囲の終端を、保存時に実際に得た04:01:25 UTCへ置換。評価内容変更なし。','formal_review_hash':verification['review_hash'],'formal_review_file':verification['formal_review_saved_file'],'report_verified':all(verification['checks'].values()),'restriction_observance':'書込は自分の出力ディレクトリと公開review1件のみ。実装・DB・snapshot・元資料・既存記録・git・外部サービスを変更しない。追加担当も起動しない。'}
start=datetime.datetime.fromisoformat(execution['started_at_utc'].replace('Z','+00:00'));end=datetime.datetime.fromisoformat(finished)
execution['elapsed_seconds']=(end-start).total_seconds();execution['within_20_minutes']=execution['elapsed_seconds']<=1200
text+=f"開始: {execution['started_at_utc']}。対応確認終了: {execution['confirmation_finished_at_utc']}。保存終了: {finished}。公開操作4件成功、評価登録は1件、失敗・形式修正・再採点は0件。補助読取の型誤認1件は復旧済み。詳細は execution.json、reading-scope.json、report-verification.json。\n"
(out/'evaluation.md').write_text(text)
(out/'execution.json').write_text(json.dumps(execution,ensure_ascii=False,indent=2))
for filename in ['review.json','evaluation.json','execution.json','reading-scope.json','report-verification.json']:
 json.loads((out/filename).read_text())
assert (out/'evaluation.md').stat().st_size>0
print(json.dumps({'saved_files':['review.json','evaluation.json','evaluation.md','execution.json'],'saved_at_utc':finished,'elapsed_seconds':execution['elapsed_seconds'],'within_20_minutes':execution['within_20_minutes'],'report_verified':execution['report_verified'],'card_rows_read':len(card_ids)},ensure_ascii=False))
