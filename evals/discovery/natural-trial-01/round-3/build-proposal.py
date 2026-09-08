import json
from pathlib import Path
P=Path('/tmp/sv-natural-system-trial/rounds')
old=json.loads((P/'round-1-proposal.json').read_text())
packet=json.loads((P/'round-3-submit-packet.json').read_text())
c=json.loads((P/'round-3-comparison.json').read_text())
sh='87640ab449d5ea1e2af53c95d05b7ba6a5e90985c52f2dbb8d20993b82e6c212'
dh='070e0eae6f35df3612540cdea7595a32cb5e1cc557dc11881088748788c2bb40'
def evidence(quote): return {'source_hash':sh,'quote':quote}
roles=old['roles']
for role in roles:
    if role['card_id']==10514120:
        role['role']='接続役。T8ルリア後のPPをFFと進化時に2回回復する。進化時能力はEPでもSEPでも働く。T8にSEPを使うならT9マガチヨ用の別SEP1個が必要。3枚維持。'
    if role['card_id']==10504110:
        role['role']='核。8枚補充へ切り替える役。採用2枚は仮置き。T8の生存だけでなく、捨てる手札、T9の先行2プレイ、除去・攻撃札、場の空きを一組で検討する。'
roles.append({'card_id':10913310,'role':'維持する除去・1枚ドロー2枚。T8の8枚補充に含まれれば、その終了時コンボ3で3PPとなり、T9の大型除去と再取得へ使える。T9に初めて引いた札は4PP。','access':'deck'})
proposal={
 'packet_hash':packet['sha256'],'author':'/root/natural_trial_generator','parent_revision':1,
 'title':'8枚補充後の攻撃と全体処理を比較するルリア・ゲテンオウ型エルフ（限定改訂）',
 'hypothesis':'保存版ローテーション・エルフで、ダストデイズの山札強化後に手札を8枚へ入れ替え、強化済みの軽い疾走をまとめて引く。原6枚配分によるルリアの確定補充は、保持手札がミロク・世界だけのような状態で、基準の先行10点よりT9の決着に寄与する指定例がある。一方、基準はマガチヨ1枚または舎弟頭の2枚補充で先に決着する指定例もある。原案の運用を一律のT9疾走にせず、全体処理と残手札へ変える分岐まで比較する。採用の総合利益と独自性は未確定。',
 'change':'原6枚の内訳は仮置きのまま。round2の停止は撤回する。別評価2の指摘を受け、例2のオルテニア後はルリアが残ること、基準ではセタスがルリアを強化することを訂正した。不要札を世界とし、全残山札と同じ共通札順の3組をT9まで追った。補充がT9の18点決着へ変わる組、基準の先行決着に対して全体処理・残手札へ変わる組を新たに示す。EP必須と山札残数の旧記述も訂正する。',
 'roles':roles,
 'steps':[
   old['steps'][0],
   {
    'action':'既存例2の境界状態だけを固定する。自分先攻T8、体力12、相手18、PP8、EP0、SEP2、場空、手札は未強化ルリア・未強化ミロク・世界。相手は未強化ストレイ2/2。山札は公開基準40枚または原案6枚交換後40枚から同じ16枚を除いた24枚で、全残フォロワーは3回強化済み。添付に山札外16枚と検索後23枚の全内訳を示す。T1からの実測ではない。',
    'resources':c['t8_correction']['original']+' 基準側：'+c['t8_correction']['base'],
    'result':'相手はオルテニア8を超進化。原案側は能力でゲテンオウ、攻撃でミロクを破壊してルリアのバリアだけを消す。基準側は能力でセタス、攻撃2回で2/2ルリアを除去する。双方体力11。相手場はオルテニア10/10と新緑3/3守護3体。原案はルリア1/1が残り手札9・相手体力17、基準は場空・手札3・相手体力8となる。',
    'evidence':[evidence(c['t8_correction']['original_removal']),evidence(c['t8_correction']['base_removal']),{'card_id':10814110,'field':'skill_text','quote':'【ファンファーレ】相手の場のフォロワー1枚を選ぶ。それを破壊。自分の場の他のフォロワーすべては+1/+1する。\n\n【疾走】\n【守護】'}]
   },
   {
    'action':'引き順Aで、原案の補充9枚は世界・ミロク・マガチヨ・レイピア2・緋岸・ゲテンオウ・ダスト・飛翔。基準の通常ドローは同じ順の1枚目の世界で、保持ミロクと世界を合わせて3枚。原案は残ったルリアを守護へ攻撃して失い、場を空ける。',
    'resources':c['paired_t9_cases'][0]['original_line'],
    'result':c['paired_t9_cases'][0]['original_result']+' 基準の世界2枚とミロクからフェアリー4枚を作る補充は、世界が割れて次のミロク・マガチヨを引いた時点で0PP。ミロクで守護を処理する別選択もあるが、相手8を当ターンに削り切れない。',
    'evidence':[evidence(c['paired_t9_cases'][0]['original_result']),evidence(c['paired_t9_cases'][0]['base_comparison']),{'card_id':10914110,'field':'skill_text','quote':'【ファンファーレ】相手の場のフォロワー1枚を選ぶ。それに4ダメージ。【コンボ_3】1枚を選ぶのではなくすべて。\n\n【超進化時】これは【疾走】を持つ。'}]
   },
   {
    'action':'同じ境界状態で引き順B/Cも比較する。Bの基準は通常ドローのマガチヨ1枚、Cは通常ドロー舎弟頭から追加2枚でマガチヨを得る。原案は先行打点が少ないため、指定手順ではT9決着に届かず相手盤面全体の処理へ回る。',
    'resources':'B基準：世界1→ミロク3で2回復→マガチヨ3で4PP残し、3プレイ・場3・手札0、SEP1消費、8点決着。B原案：ルリアを守護へ攻撃→ダスト4でオルテニア処理→飛翔2→マガチヨ3。追加コンボでマガチヨ時4、0PP・場2・手札7、8点と全処理。C基準：世界→ミロク→舎弟頭（マガチヨと世界を2枚引く）→マガチヨ、2PP・場4・手札1で8点決着。C原案：ルリアを守護へ攻撃→T8に引いて3PPの緋岸でオルテニア処理し和気藹々を引く→世界1→マガチヨ3→レイピア2、0PP・場3・手札6で13点と全処理。いずれもSEP1消費。',
    'result':'原案Bは相手9、Cは相手4を残す。盤面全処理と手札7/6という具体的な出力はあるが、基準のT9決着を上回ったとはしない。Cの追加ドローは緋岸1枚だけで、手札9→8→9と上限内。原案の全手順の最適値は未検証。',
    'evidence':[evidence(c['paired_t9_cases'][1]['original_result']),evidence(c['paired_t9_cases'][2]['base_line']),evidence(c['paired_t9_cases'][2]['original_line'])]
   },
   {
    'action':'既存の少数補充案（優雅1→ゲテンオウ1、セタス3維持）との違いを局面内で確かめる。',
    'resources':c['one_refill_comparison']['before_lyria'],
    'result':c['one_refill_comparison']['conclusion']+' 少数補充案もゲテンオウを検索したA分岐なら同じ共通先頭5枚で18点が成立する。セタスを検索したB/C分岐なら基準と同じ先行決着が成立する。両分岐を持つことと、いつも補充へ行けることの優劣を頻度なしで確定しない。',
    'evidence':[evidence(c['one_refill_comparison']['A_when_get']),evidence(c['one_refill_comparison']['conclusion'])]
   },
   old['steps'][-1]
 ],
 'plan':{
   'early':old['plan']['early'],
   'transition':'T5〜7の山札強化と和気藹々の条件付き回復は初回の仮説として残る。T8の一括補充は、相手の次の攻撃で敗北せず、捨てる手札が既存の決着を失わせない条件で検討する。EPによるミロク回復以外にSEPでも接続可能だが、T9マガチヨを使うなら別SEP1個が必要。後攻追加PPを残すT8とT9以降は別の接続条件。',
   'finish':'一括補充後の全手札を見る。軽い2プレイとマガチヨ・レイピア2枚が揃えば、守護を4点で処理して18点を狙う指定手順がある。盤面が残れば、残存ルリアを守護へ攻撃して場を空けるなどの手順が必要。届かない指定例ではダストまたは軽減済み緋岸で大型を処理し、マガチヨで残る守護を消して攻撃と手札を残せる。残手札を次の勝ちの保証にはしない。',
   'without_core':'基準で先行セタスが残した8体力は、マガチヨ1枚や舎弟頭の2枚補充でも詰められる。この選択を原案は失う。原案のゲテンオウを引けず、ルリア接続のPP・進化権が足りない時は既存の軽い攻撃札を使うが、同等に戦える根拠はない。ダストデイズ不在で同じ打点にはならない。',
   'allocation':old['plan']['allocation'],
   'comparison':'確定補充の局面内利益は例Aで確認できるため、利益が残らないという停止は撤回する。ただしB/Cでは基準の先行10点が軽い取得だけで決着へ変わり、原案の盤面全処理・残手札より早い。少数補充案でも補充分岐は同じAを再現する。6枠の全てが必要か、確定補充の機会が増える利益がセタス喪失を上回るか、局面への到達頻度を含む総合判断は未確定。'
 },
 'questions':[
   {'question':'添付の全残山札・指定引き順A/B/Cについて、T9のPP、手札上限、場、追加取得、残存ルリア処理を含む手順に未訂正の誤読はあるか。','tag':None,'why':'補充の利益があるとして停止を撤回した直接の根拠である。'},
   {'question':'例Aの確定補充の利益とB/Cの先行決着を失う負担を合わせると、この限定改訂は配分仮説として残す意味があるか。それとも6枚枝はこの範囲の理由で止めるべきか。','tag':None,'why':'手順成立と試す価値を分け、提出を増やした事実で成功扱いしない。'},
   {'question':'この補充時点・採用配分の差は、保存資料と既出検索の範囲で意味のある差として認められるか。','tag':None,'why':'新しい既出調査はしておらず、PP訂正や検索で未発見というだけでは独自性にならない。'}
 ],
 'uncertainties':c['limitations']+[
   '比較状態では通常ドロー前23枚から8枚補充し、次の通常ドロー後14枚。一般にもT9通常ドローまで行うにはゲテンオウ直前の山札9枚以上が必要。旧案の8枚未満を避けるだけという記述は訂正する。',
   'ミロクの接続に通常EP1の温存は必須ではないが、同一ターンのEP/SEP重複使用はできず、T9マガチヨ用SEPが残ることは別途必要。',
   '和気藹々2・飛翔2を含む6枚配分の全てを必要とする比較ではない。序中盤を支える頻度や適量は未確認。',
   '8枚補充の後の決着・全体処理そのものは少数補充案でも得られる。原案固有の候補は必要時に補充先へ確定検索することに限定する。',
   '新しい現環境・能力更新・既出状況の主張はなく、今回のWeb追加確認は0件。保存本文と別評価の公式ルール確認を出典とする。'
 ]
}
# Verify only data linkage, not strategic correctness or an independent review.
sources={s['source_hash']:s for s in packet['data']['sources']}
for step in proposal['steps']:
    for ev in step['evidence']:
        if 'source_hash' in ev:
            assert ev['quote'] in sources[ev['source_hash']]['content'], ev
(P/'round-3-proposal.json').write_text(json.dumps(proposal,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'packet_hash':proposal['packet_hash'],'parent_revision':1,'steps':len(proposal['steps']),'roles':len(proposal['roles']),'source_quotes_present':True},ensure_ascii=False))
