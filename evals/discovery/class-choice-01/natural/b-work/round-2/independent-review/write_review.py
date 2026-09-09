import json
from pathlib import Path
out=Path('/tmp/sv-class-choice-01/b-work/round-2/independent-review')
p=json.load(open('/tmp/sv-class-choice-01/b/session/packets/a9acff6c262c56fbb8b616c5581fc8118fd28e2885e71e12be4b873bb687d86a.json'))['data']
sources={s['source_hash']:s for s in p['sources']}
summary='88f010284162ecbdf35c31519eb6a63f3d34cfce75379f0db2962c4d1eb7e1f5'
late='933100a37722595f1c8ab43fda9ecb0390a49f5ee7b099c281d5d52d2aabf55e'
early='f3c48d7ed3699e6a7e9bb97e9a974d144065b862334d6bdc801086ef80722950'
web='48b97094eba37f681d8e83c3b3d648024a8ede1e7475767f319a35745b36b2e5'
def evidence(h,q):
 assert q in sources[h]['content'],q
 return {'source_hash':h,'quote':q}
web_checks=[
 {'url':'https://shadowverse-wb.com/ja/system/cardbattle/battle/','query':'初手、通常ドロー、手札・場上限、進化開始時期の照合','checked_at':'2026-09-09T03:55:55Z〜03:58:53Z（取得後の読了確認を含む範囲）','finding':'公式説明で初手4枚、各ターン1ドロー、手札9枚、場5枚、進化/超進化各2回を確認。指定取得順の一般則を支持し、到達頻度や生存は証明しない。'},
 {'url':'https://gamewith.jp/shadowverse-wb/575049','query':'元構築14種40枚と玩具・ヨグゼンタ・ベルゼバブ・ナイフ・シアターの通常用途','checked_at':'2026-09-09T03:55:55Z〜03:58:53Z（取得後の読了確認を含む範囲）','finding':'2026-09-08更新表示。表示リスト14種40枚が固定比較前と一致。標準の決着と事前の人形準備を確認。コピー先は再取得せず、記事の評価を本案へ転用しない。'},
 {'url':'https://note.com/udonkaree_2/n/n27684e02338b','query':'2Pick当事者メモのヨグゼンタ・ゴッデス用途','checked_at':'2026-09-09T03:55:55Z〜03:58:53Z（取得後の読了確認を含む範囲）','finding':'ネメシス節にカミシラや決着札を増やす用法がある。自己2PP化と玩具維持の具体手順を示す記事とは確認できず、ローテでの強さの根拠にも使わない。'}]
for c in json.loads((out/'official-checks.json').read_text()):
 web_checks.append({'url':c['url'],'query':c['name']+'の主要能力・コスト・個別Q&A','checked_at':c['checked_at'],'finding':c['finding']})
review={
 'packet_hash':'a9acff6c262c56fbb8b616c5581fc8118fd28e2885e71e12be4b873bb687d86a',
 'author':'/root/class_choice_b2_review','procedure':'conditional','value':'drop','novelty':'unconfirmed',
 'findings':[
  {'axis':'procedure','reason':'追加資料の指定手札・取得順では、初手から7ターン目までの2経路と、8〜10ターン目の3経路を条件付きで支持する。4ターン目は2+2PP、初回コピーは5+2PP、再コピーを省く人形準備は3+2+1+2=8PP。再コピーを残す修正例は後攻追加PPを温存して2+2+3+2=9PPとし、誠心を省いて深淵をコピーする。手札最大9枚、通常ドローの廃棄、シアターのカウント、決着時の場上限を確認した。20点は9PPとベルゼバブの効果、0PP人形2枚、生成人形を退場させる相手の場、生存、妨害・軽減がない条件を伴う。元のrevision 1本文の8PP行動へシアター2PPを足すと10PPになり、後攻でも8ターン目には収まらない。正式本文は古いままで、そのまま人形2枚へつながったとは認定しない。軽減状態コピーは固定注記に依存し、今回取得した公式4枚の空の個別Q&Aから仕様を証明してはいない。',
   'evidence':[evidence(late,'T8の再コピー2PPをシアター2PPへ回す。通常ドローNを保持し、同じ3枚補充を得る。'),evidence(early,'T5/T6の処理へEPを使うと、ゴッデスはT7を含め最大2回しか手動進化できない。'),{'card_id':10502110,'field':'note','quote':'状態ごとコピー(スペブ回数・融合カウント・バフ込み)'},{'card_id':10072210,'field':'skill_text','quote':'自分のターン終了時、『操り人形』1枚を自分の手札に加える。'}]},
  {'axis':'value','reason':'この保存案は資料を残して探索対象から外すのが妥当で、試す候補へ推薦しない。追加調査は、人形の用意と通常ドロー保持を具体化し、序盤の守りと進化権の競合まで調べた実質的な発展である。一方、7ターン目の初回だけで玩具2枚を得るため、10ターン目に決着する比較例では8ターン目の再コピーによる補充回数を使わない。再コピーを残す例で得る大きな本体と余分な深淵は実在する利益だが、同じ3枚補充に対して後攻追加PP・進化権・誠心を失い、その差を勝ちや必要な防御へ変える根拠はない。初回にも7PP、捨てる3枚、ヨグゼンタの用途、既存除去に使える進化権を払う。比較の1枠交換は軽いが、ベルゼバブ3→2で決着支援の取得を減らし、序盤の採用配分は改善していない。核がなくても残る39枚の通常用途は認めるが、その実績は新用途の価値を保証しない。長期戦の3回目以降の補充という可能性は残るものの、普通の玩具＋ヨグゼンタによる早い補充・既存除去との比較で負担に見合う局面がまだ特定されていない。全経路が無価値という反証や、40枚完成・勝率証明を要求した棄却ではない。未確認だけを根拠に継続枠へ残さず、この案の推薦と自動継続を止める。',
   'evidence':[evidence(summary,'9ターン目にベルゼバブ、10ターン目に決着する指定例では、8ターン目の自己反復で増やした補充回数を使わない。'),evidence(summary,'3PP玩具をプレイし、ヨグゼンタ2から同じ3PP玩具を作り直すなら5PPで3枚補充を先に行える。'),evidence('8dcebe816f704b5bd399decd6a809f97a119df0b19a57a6864e43210c29f0e73','"exchanged_count": 1')]},
  {'axis':'novelty','reason':'既出状況は未確認。標準の玩具＋ヨグゼンタ、ベルゼバブ＋ナイフ、ゴッデスによる必要札の複製は既知の用途であり、自己2PP化と玩具維持の普及状況とは分ける。固定ハイランダーネメシスでゴッデスとヨグゼンタが同居することも確認したが、同居だけで今回の用法を既知とは断定しない。追加資料の検索10件を読んだほか、当担当も3ページと公式4枚を開き、組名2件を検索した。検索結果は一覧・採用数・一般的なコピー用途の言及が主で、今回の反復の普及を判断できない。全投稿・動画本編・字幕・他言語は未調査。検索の空振り、Tier、勝率、初見への期待を加点しない。',
   'evidence':[evidence(web,'動画本編や字幕の取得・視聴なし。全投稿・全言語未網羅。'),evidence('0fdecef9c31fa413eed0f1b3523f6e96c02661edcfd0b02f00d870bb8fcd14b2','終盤はベルゼバブとナイフストリンガーで決着する構築として説明されている。')]}
 ],
 'next_questions':['再開するなら、9〜10ターン目にベルゼバブ未所持・玩具残り1枚・2PPゴッデスと進化権を持つ具体的な局面で、普通の補充や除去では資源が尽きるが再コピーなら追加補充を実際に使い、防御から決着まで進める例を示せるか。初回7PPと捨て札、ベルゼバブ1枠減の負担を含む同条件比較が判断を変える条件であり、単なるQ&A取得や未確認の存在を理由に直ちに継続しない。'],
 'web_checks':web_checks}
(out/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
(out/'web-search-checks.json').write_text(json.dumps({'queries':['"スターライトゴッデス" "低劣の玩具" "コピー"','"スターライトゴッデス" "ヨグゼンタ" "2コスト"'],'checked_at_range_utc':['2026-09-09T03:58:53Z','2026-09-09T04:02:00Z'],'finding':'カード一覧、2Pick採用数、一般のゴッデス用途議論が返った。個別検索結果ページの本文は開かず、検索出力だけ。特定反復の既知性の証拠にはしない。','result_urls':['https://www.svlabo-wb.com/data/073/2pick/','https://game8.jp/shadowverse-beyond/699451','https://appmedia.jp/shadowverse-wb/78674501','https://game8.jp/shadowverse-beyond/698617','https://open.open2ch.net/test/read.cgi/onjgame/1772507441/']},ensure_ascii=False,indent=2))
print('review.json saved; source quotes verified; no public review registered by this script')
