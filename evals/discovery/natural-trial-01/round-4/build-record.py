import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

P=Path('/tmp/sv-natural-system-trial/rounds')
packet=json.loads((P/'round-4-input-packet.json').read_text())
ctx=packet['data']['context']
card={c['card_id']:c for c in ctx['cards']}
prior_source=next(s for s in packet['data']['sources'] if s['source_hash']=='87640ab449d5ea1e2af53c95d05b7ba6a5e90985c52f2dbb8d20993b82e6c212')
prior=json.loads(prior_source['content'])
orders=prior['orders']['A_refill_finishes']
assert packet['sha256']=='f3aed803295861e661dfab2a8ce5ca383e4efc07474e1bff5cf6e3ee3cc2c10f'
for name, order in orders.items():
    assert len(order)==23
    expected=Counter({r['card_id']:r['count'] for r in prior['fixed_state']['residual_after_search_23'][name]})
    assert Counter(r['card_id'] for r in order)==expected

record={
 'kind':'要約：既存例Aの同じ23枚・引き順・手札を固定し、オルテニアの除去順だけを変更したT9手計算。実対戦ではない。',
 'input_packet_hash':packet['sha256'],
 'read_review':{
  'author':'/root/natural_trial_review_3','review_input_packet_hash':'cd1ec12c183bd1e8c48dc0aaf87f9e4326eba9ce2b5db34006d2361506522295',
  'read_scope':'procedure/value/novelty全8所見、next_questions 1件、web_checks 1件を公開packetから全文読んだ。',
  'addressed_question':packet['data']['previous_reviews'][0]['next_questions'][0]
 },
 'provenance':{
  'snapshot':{'captured_at':ctx['captured_at'],'input_packet_hash':packet['sha256'],'path':'data.context.cards / ability_keywords / rules'},
  'fixed_comparison_source_hash':prior_source['source_hash'],
  'base_list_source_hash':'3f5085652f7a6a84820c88f9127e0d93b3057d32041ce691d1268b18fe7ad622',
  'base_list_url':'https://gamewith.jp/shadowverse-wb/559139',
  'web_this_round':'追加確認なし。新しい現環境・普及・能力変更を主張せず、保存本文と実際の独立評価が添付した公式ルール確認を使った。'
 },
 'unchanged_inputs':{
  'boundary_state':prior['fixed_state'],
  'all_23_orders':orders,
  'scope':'以前のAだけ。B/Cの新しい引き順・局面や確率調査は作らない。Bは実際の評価で指摘された既存手順の訂正のみ記録する。'
 },
 'changed_opponent_line':{
  'original_t8_before_opponent':'原案と少数補充案のGet検索分岐は、ルリア・ミロクSEP・ゲテンオウの順でT8に8枚補充した状態。自分12、相手はミロクの攻撃破壊1点で17。自分の場はルリア1/1バリア、ミロク5/5超進化、ゲテンオウ11/11。EP0、SEP1。',
  'opponent_action':'同じ未強化オルテニア8を超進化して10/10、能力でミロクを破壊する。ゲテンオウ11/11へ2回攻撃し、1回目は残体力1、2回目に破壊する。オルテニアは自分のターン中の超進化耐性で反撃ダメージを受けない。攻撃破壊は1体なので自分リーダーは12→11。ルリアのバリアは触らずに残る。',
  't9_start':'自分PP9、体力11、EP0、SEP1、場はルリア1/1バリア1体。相手体力17、場はオルテニア10/10と自動進化した新緑フェアリー3/3守護3体。補充8枚+通常1枚で手札9、残山札14。',
  'original_hand_9':orders['original'][:9],
  'one_get_hand_9':orders['one_get'][:9],
  'base_branch':'基準および少数補充案のセタス検索分岐にはゲテンオウがいないため、この「ゲテンオウへ2回攻撃」の応手を適用しない。従来どおり能力でセタス、攻撃2回でバリア持ち2/2ルリアを処理。T9自分11・相手8、場空、手札は保持ミロク・保持世界・通常ドロー世界。'
 },
 'failed_previous_line':{
  'reason':'バリア付きルリアで守護へ一度攻撃しても、バリアが消えてルリア1/1が残り、守護が3/2になるだけ。1ターン1回の攻撃を消費するので、もう一度攻撃して場を空けることはできない。',
  'resource_failure':'世界→ミロク→マガチヨ→レイピア→レイピアはPP9には収まるが、残存ルリアと合わせて6枚になる。5枠の場へそのまま置けない。',
  'limited_conclusion':'以前の18点手順はこの除去順に対応しない。全てのT9手順やゲテンオウの用法が不成立という意味ではない。'
 },
 'line_D_dust_mag_rapier':{
  'shared_between':'原6枚案と既存少数補充案のGet検索分岐の両方。同じAの9枚から、ダスト・マガチヨ・レイピア1枚を使う。',
  'step_1':'ダストデイズ4PPをプレイ。自分の場はルリアとダストの2枚、手札9→8、PP9→5。実際の1プレイとダスト能力でコンボ2。ダストは3回強化により6/6なので、オルテニアを-0/-6し、10/4にする。単独では破壊しない。',
  'step_2':'マガチヨ3PPをプレイ。PP5→2、手札8→7、場3枚、実際の2プレイ目でコンボ3。全体4点がオルテニアの残4と守護3体の体力3を同時に処理する。マガチヨを超進化して8/8疾走、SEP1→0。能力破壊に超進化攻撃破壊の1点は加算しない。',
  'step_3':'レイピア2PPをプレイ。PP2→0、手札7→6、場4枚、コンボ4で疾走を持つ。レイピアは5/5。相手守護が消えた後でルリアを相手リーダーへ攻撃させる。マガチヨ8点、レイピア5点、ルリア1点で計14点、相手17→3。ルリアのバリアは残る。',
  'own_end_board':[{'name':'ルリア','atk':1,'life':1,'barrier':True},{'name':'ダストデイズ','atk':6,'life':6},{'name':'マガチヨ','atk':8,'life':8,'super_evolved':True},{'name':'レイピア使い','atk':5,'life':5}],
  'resources':'T9のプレイは3枚、最大場4枚、最終PP0、手札6、山札14、EP0、SEP0、自分体力11、相手体力3、相手場0。追加ドローなし。ルリアを先に守護へ攻撃させない。',
  'original_remaining_hand':['世界','ミロク','レイピア1枚','緋岸橙酔','ゲテンオウ','飛翔'],
  'one_get_remaining_hand':['世界','ミロク','レイピア1枚','緋岸橙酔','セタス2枚'],
  'end_turn_note':'この手順で保持した緋岸はT8終了時に4→3PPになっており、T9終了時コンボ4で3→2PPになる。ダストを進化していないため新しいダストのクレストは得ない。手札の今後の使用、相手の次のドロー・行動、勝敗は計算しない。',
  'finding':'指定応手でも、同じA手札から14点・相手盤面全処理・手札6を得る対応は残る。これは原案だけでなく、少数補充案のGet検索分岐でも同じである。'
 },
 'line_S_scarlet_miro_mag_rapier':{
  'shared_between':'原6枚案と少数補充案のGet検索分岐の両方。Aの緋岸はT8に引いたため3PP。',
  'line':'緋岸3でオルテニアを破壊し、固定順10枚目のルリア（3回強化4/4、通常2PP）を引く→ミロク3のFFで2PP回復→マガチヨ3を超進化→レイピア2。ルリアのリーダー攻撃はマガチヨが守護を除去した後。',
  'PP':'9→6→3→5→2→0。緋岸、ミロク、マガチヨ、レイピアの4プレイ。マガチヨ時コンボ3。',
  'hand':'9→緋岸使用8→ドロー9→ミロク8→マガチヨ7→レイピア6。上限9を超えない。山札14→13。引いた新ルリアはこの手順でプレイせず、場を追加しない。',
  'result':'マガチヨで守護3体を処理し、旧ルリア1+マガチヨ8+レイピア5=14点、相手3。自分の場は旧ルリア1/1バリア・新ミロク5/5・マガチヨ8/8超進化・レイピア5/5の4枚。自分体力11、PP0、EP0、SEP0。',
  'original_remaining_hand':['世界','レイピア1枚','ゲテンオウ','ダストデイズ','飛翔','新たに引いたルリア'],
  'one_get_remaining_hand':['世界','レイピア1枚','セタス2枚','ダストデイズ','新たに引いたルリア'],
  'finding':'場を占める世界を先行2プレイから外し、緋岸を大型処理と1枚取得に使う別手順でも同じ14点と全体処理が成立する。これはダストを引き直す仮定や新しい引き順を加えた比較ではない。'
 },
 'all_hand_consideration':{
  'world_and_miro':'世界1＋ミロクの2回復による実質1PPを先行2プレイにする方法は安いが、世界自身が場を使う。世界はT9に新しく置くカウント5で、旧ルリアを含めても元の5枚手順中に割れて場を空ける計算にはならない。',
  'mag_and_two_rapiers':'9枚中の攻撃役3枚は全て確認した。片方のレイピアをオルテニアへ攻撃して失い、次のレイピアの場を作る方法はあるが、そのレイピアの5点をリーダーへも加算しない。元の18点を維持した説明にはできない。',
  'flight':'原案のみの飛翔2はフェアリー1を作れるが、飛翔2+フェアリー1を先行2プレイにすると3PPかかり、マガチヨ3+レイピア2+2と合わせ10PPになる。生成フェアリーを元から0PP札のように扱わない。',
  'dust_scarlet':'両方を含む全手札を見直し、上のD/Sという4枠以内の対応を得た。緋岸の追加取得は固定順のルリアまで明記した。',
  'get_again':'原案の2枚目ゲテンオウも手札にある。再使用すれば旧マガチヨとレイピア等を全て捨てる。固定次順は10ルリア・11ササニドで、8枚モードなら10〜17（ルリア、ササニド2、レイピア、ダスト、鹿王2、モエル）を引く。2枚軽減モードなら最初のルリアとササニドが軽減対象になる。既存の18点手順に、その捨てた攻撃札を残したまま新取得を足すことはできない。今回この再補充の全分岐を最適化しておらず、手札全体からのT9決着不能を証明したとはしない。',
  'setas_in_one':'少数補充案の9枚には原案のゲテンオウ・飛翔に代わってセタス2枚がある。7PPのセタスを上のマガチヨ3＋レイピア2へそのまま加えることはできず、別配分が必要。ミロクへSEPを使ってさらにPPを回復するなら、その同じSEPをマガチヨの疾走にも使う計算にはしない。セタスを残した手札の将来の利益や全T9手順の最適値は未比較。'
 },
 'base_and_one_comparison':{
  'base_A':'基準は保持ミロク・世界・通常世界の3枚のまま。ミロクのFF/SEPを両方3点除去へ使い、守護2体へ各3点、超進化攻撃で残る守護1体を破壊すれば、守護3体とリーダー1点を得る。相手体力8→7、オルテニア10/10は残る。この手順では相手盤面全処理にはならない。',
  'base_draw':'ミロクからフェアリー4枚を作り、世界2枚を置いて最初の世界を割る別手順は、合計9PPとミロクへのSEPを消費する。そこで得た固定次順のミロク・マガチヨを、このターンの疾走へ接続する資源は残らない。新しい引き順を使って基準を弱くしていない。',
  'positive_difference':'今回の原案D/Sは基準のこの手札より、多くのリーダーダメージ、オルテニアを含む全体処理、残手札を同時に得る具体的対応である。相手T9以降も勝ることや、基準の全手順の資源を支配することまでは言わない。',
  'one_get':'少数補充案でもGetを検索した分岐ならD/Sが同じPP・場4枚・14点で成立する。違うのは保持する手札にセタス2枚が残ること。手札枚数は同じ6。',
  'access_difference':'ルリア直前の指定24枚には、原案はGet2のみが高コスト検索対象、少数補充案はSetas3とGet1が対象として残る。従って必要時に補充へ確実に行けるという差は消えていない。検索頻度の新計算や実測はしない。',
  'cost_not_erased':'この残る局面内利益で、過去の攻撃継続例の生存損失、B/Cでの基準の先行決着、舎弟頭2と優雅1を減らす負担が解消されたとはしない。和気藹々2・飛翔2を含む全6枠の必要性も示されない。'
 },
 'B_correction':{
  'old_error':'round3の「ダストデイズ4でオルテニアを選び-0/-10して破壊」を撤回する。Xは対象オルテニアの攻撃力ではなくダストデイズ自身の攻撃力で、3回強化なら6。',
  'fixed_shorter_line':'既存Bでは従来のバリアなしルリアを守護へ攻撃して場を空け、ダスト4でオルテニアを10/4にする。ダストの追加コンボにより、その次のマガチヨ3がコンボ3で全体4点を与え、オルテニアと守護を全処理する。超進化マガチヨ8点で相手17→9。',
  'resources':'9PP→5→2、手札9→8→7、最大場2、EP0・SEP1→0。手札7はダスト、鹿王2、ゲテンオウ、和気藹々2、飛翔。飛翔を使わないため、生成フェアリーを得たとはしない。',
  'limit':'Bの引き順や基準のT9決着は変えていない。短い処理手順と残PPの訂正であり、原案が基準の決着を上回ったという変更ではない。'
 },
 'limits':[
  '同じA境界状態、指定23枚・順番、指定相手手札と今回の除去順だけを比較した。新しい局面、引き順、確率を追加していない。',
  'D/Sという具体的な対応は確認したが、ゲテンオウ再使用や少数補充案のセタスを含む全合法手順の最適値・T9決着不能の証明はしていない。',
  '局面へのT1からの完全な到達履歴・到達頻度、相手T9以降の応手、勝率は未確認。',
  '6枠配分の採用価値・独自性を自己評価で認定しない。実対戦数0、今回追加Web調査0。'
 ]
}

decision={
 'actor':'/root/natural_trial_generator',
 'action':'stop_developing_specific_six_slot_allocation',
 'input_packet_hash':packet['sha256'],
 'target_revision':2,
 'scope':'セタス3・舎弟頭2・優雅1を抜き、Get2・和気藹々2・飛翔2を入れる、ルリア確定補充の原6枚配分を採用候補としてさらに進める作業を、この比較範囲で止める。',
 'confirmed_positive':'バリアを残す応手にもD/Sで14点・相手全体処理・手札6が残り、基準Aの保持手札より意味のある対応はある。確定検索による補充機会の差も残る。「利益が無くなった」「不可能」とは判断しない。',
 'decision_reason':[
  '同じ相手手札の除去先変更により、これまで直接の決着差として使った18点手順は場5枠を超える。新しいD/Sは有効な対応だが、相手3体力を残すため、その後まで決着の優位を移せたことは未確認。これだけを停止理由とはしない。',
  '新しい14点・全体処理の対応そのものは既存少数補充案のGet分岐にも同じ資源で成立する。原6枚に固有なのは補充先を固定する機会の差だけで、和気藹々2・飛翔2を含む全配分の必要性を支持する追加根拠にはならない。',
  '既存の攻撃継続例でのセタスの除去・守護を失う負担、B/Cの先行決着を失う負担は残る。この固定局面だけから、それらと交換して原6枚を採用する利益の大きさを決められない。',
  '追加された根拠は手順と局面内出力の訂正・限定であり、採用配分の変更や総合利益の根拠を伴う新提案ではない。残り提出枠を使うためのrevision3は作らず、既存revision2にこの補足を付けた独立評価用資料を出す。'
 ],
 'not_stopped':['Get8枚補充という役割の可能性全体。','少数補充採用や他の配分の全て。','指定Aで補充が基準より意味のある対応へ変わるという確認済み事実。','エルフ全体やシステム探索全体。'],
 'not_claimed':['原6枚が全局面で劣ること。','T9の全合法手順で決着できないこと。','14点が絶対的な最高値であること。','相手3残しだから役立たないこと。','未使用の提出枠や実対戦0という数自体を停止理由にすること。'],
 'restart_conditions':['この指定例の計算の言い換えではなく、セタス喪失や軽い補充削減の負担に対して、確定補充の機会増が重要になる比較根拠が新たに得られること。','全6枠を維持するなら、増やした序中盤の防御配分も必要である根拠があること。そうでなければ原6枚そのものを再提出する根拠にはしない。'],
 'new_revision_submitted':False,
 'submissions_used_total':2,
 'self_review_registered':False,
 'limits':record['limits']
}

def save(name,obj):
    (P/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
save('round-4-comparison.json',record)
save('round-4-decision.json',decision)
now=datetime.now(timezone.utc).isoformat()
sources=[]
for filename,title in [('round-4-comparison.json','例Aのバリア付きルリア残しへの対応と例Bの訂正'),('round-4-decision.json','局面内の利益を保持した原6枚配分の限定停止')]:
    sources.append({'title':title,'kind':'要約・指定状態の手計算と限定判断（実対戦ではない）','location':str(P/filename),'observed_at':now,'content':(P/filename).read_text(),'limitations':record['limits']})
save('round-4-sources.json',{'sources':sources})
print(json.dumps({'input_hash':packet['sha256'],'saved':['round-4-comparison.json','round-4-decision.json','round-4-sources.json'],'fixed_A_orders':{k:len(v) for k,v in orders.items()},'submit_planned':False},ensure_ascii=False))
