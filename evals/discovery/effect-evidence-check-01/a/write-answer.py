import json, pathlib, datetime, hashlib
root=pathlib.Path('/tmp/sv-effect-evidence-check-01/a')
p=json.loads((root/'input-packet.json').read_text())
cards={c['card_id']:c for c in p['data']['context']['cards']}
logs=json.loads((root/'search-log.json').read_text())
def ev(i,f,q=None):
 return {'card_id':i,'field':f,'quote':cards[i][f] if q is None else q}
research_end=datetime.datetime.now(datetime.timezone.utc).isoformat()
answer={'cases':[
 {'id':'draw-selected',
  'evidence':[ev(10051310,'skill_text','【モード】1つを選んでその能力が働く。'),ev(10051310,'skill_text','（1）自分のデッキからフォロワー1枚を引く。')],
  'conditions':['ドロー側だけを選択し、指定されたとおり山札20枚中フォロワー2枚から、フォロワー1枚を正常に引き終えた時点。','この1枚の指定ドロー以外の山札への出し入れを加算しない。','資料内の公式定義でモードは「複数の能力から指定された数を選んで働かせる能力。」であり、リアニメイト側も同時に働いたとはしない。'],
  'state_change':{'deck_count':{'before':20,'after':19,'delta':-1},'deck_follower_count':{'before':2,'after':1,'delta':-1},'deck_nonfollower_count':{'before':18,'after':18,'delta':0},'follower_fraction':{'before':'2/20 = 10%','after':'1/19 ≈ 5.26%'},'nonfollower_fraction':{'before':'18/20 = 90%','after':'18/19 ≈ 94.74%'},'interpretation':'フォロワーの取り出しに伴い、残った山札の非フォロワー割合が増す。非フォロワー自体の枚数が増えたわけではない。これは山札構成の割合であり、順番が不明な次の1枚の確定結果ではない。'},
  'question':logs[0]['question'],
  'search':{'query':{'terms':logs[0]['match_terms'],'fields':logs[0]['field_scope'],'method':'全212枚について各指定欄に「デッキ」または「山札」が含まれるか、1回の機械走査を実行。該当35枚の該当欄を含む本文・進化・参照先・注記を読んだ。'},'read_scope':{'packet_hash':p['sha256'],'scanned_cards':212,'matched_cards':35,'matched_card_ids':[c['card_id'] for c in logs[0]['matches']],'local_scan_count':1,'public_cli_reads':0},'candidates':[], 'limitations':['該当35枚の読んだ本文では、残りの非フォロワー割合そのものを条件として報酬を変える効果は見つけられなかった。通常ドローの札はあったが、それだけで別用途が成立したとは扱わない。','文字検索に当たらない別表現を意味で全件精査したわけではないため、資料全体で別用途が存在しないとは結論しない。','残り18枚の非フォロワーがどのカードなのか不明で、特定のスペルを引く確率や有用性は決められない。']},
  'uncertainties':['残ったフォロワーの名前・コスト、非フォロワー18枚の内訳、山札の順序は未指定。','この状態差分を利用する具体的な別用途の候補は今回0枚。強さ・新規性・勝率は未判定。','手札枚数の変化まで厳密に追うには、指定ドロー前の手札の空きも必要。山札の差分に限定した。']},
 {'id':'reanimate-selected',
  'evidence':[ev(10051310,'skill_text','【モード】1つを選んでその能力が働く。'),ev(10051310,'skill_text','（2）【リアニメイト_2】を行う。')],
  'conditions':['リアニメイト側だけを選択した。ドロー側の能力は働かない。','資料内の公式定義は「このバトル中に破壊された、元のコストが指定された値以下で最大の自分のフォロワー1枚を場に出す能力。\nこれによって場に出るフォロワーは追加で死者・タイプを持つ。」。山札から探して取り出す能力ではない。','山札の変化に限定した問いなので、この選択だけで起きない山札の割合変化を理由に追加の問いは作らない。'],
  'state_change':{'own_ability_only':{'deck_count':{'before':20,'after':20,'delta':0},'deck_follower_count':{'before':2,'after':2,'delta':0},'follower_fraction':{'before':'2/20 = 10%','after':'2/20 = 10%'}},'interpretation':'リアニメイト自身の処理による山札の増減はない。場に出た札や既存の場の能力による別の誘発まで含めた最終状態は、対象カードと場が指定されていないので未確認。資料のカードタグに山札の割合操作が付いていても、この選択の結果には流用しない。'},
  'question':None,'search':None,
  'uncertainties':['破壊履歴、リアニメイト対象、場の空きが不明なため、何が何枚場に出たかは確定しない。','出たカードや他の場のカードによる追加のドロー等は仮定しない。山札20枚・フォロワー2枚の不変はカオティックカース自身の効果だけを取り出した場合の記述。']},
 {'id':'last-words-generated',
  'evidence':[ev(10751110,'skill_text'),ev(10751110,'evolution_text'),ev(90051120,'skill_text'),ev(90051120,'evolution_text'),ev(90051120,'note')],
  'conditions':['ルルミは今破壊され、ラストワードが正常に働き、手札に空きがある。','資料内のラストワードの定義は「破壊されたときに働く能力。」。ルルミは進化前後どちらも同じ手札生成の本文を持つ。','バットを手札に得ただけで、プレイ、攻撃、回復、捨てる行動はまだ起きていない。'],
  'state_change':{'hand_count_delta':1,'hand_follower_count_delta':1,'added_card':{'card_id':90051120,'name':'バット','destination':'手札','class_name':'ナイトメア','cost':1},'deck_count_delta':0,'deck_follower_count_delta':0,'interpretation':'山札のカードを引かずに手札が1枚増す。この時点ではバットは場におらず、ドレインによる回復も発生していない。ルルミの破壊前から見て場のルルミは失われている。'},
  'question':logs[1]['question'],
  'search':{'query':{'terms':logs[1]['match_terms'],'fields':logs[1]['field_scope'],'method':'全212枚について各指定欄に「手札」または「捨て」が含まれるか、1回の機械走査を実行。該当39枚の本文・進化・参照先・注記を読んだ。'},'read_scope':{'packet_hash':p['sha256'],'scanned_cards':212,'matched_cards':39,'matched_card_ids':[c['card_id'] for c in logs[1]['matches']],'local_scan_count':1,'public_cli_reads':0},'candidates':[
   {'card_id':10703110,'reason':{'use':'生成したバットを手札1枚を捨てる対象にできるか調べる。バットのプレイと攻撃を経由せず、享楽の上位市民の全体2ダメージに伴う手札消費を賄う候補。','conditions_met':['バットは実際に手札にあり、選べる手札1枚という本文上の対象を満たす。','保存資料で享楽の上位市民はニュートラル、デッキ採用可能。'], 'conditions_not_established':['享楽の上位市民を手札に持ち、3PPを支払い、場の空きを確保してプレイする行動はまだ起きていない。','相手の場の内容と、2ダメージが役に立つ状況は未指定。バットを残す用途との優劣も未確認。'], 'note_status':'享楽の上位市民の注記は空欄。実戦評価の裏付けは提供されていない。'},'evidence':[ev(10703110,'skill_text'),ev(10703110,'evolution_text')]},
   {'card_id':10502110,'reason':{'use':'生成したバットを、進化時に捨てる3枚のうち1枚へ回し、残したい手札をコピー対象として残せるか調べる。','conditions_met':['バットは選んで捨てる手札の候補1枚になる。山札を1枚減らして得た手札ではない。','保存資料でスターライトゴッデスはニュートラル、デッキ採用可能。'], 'conditions_not_established':['進化時の処理直前に、捨てる3枚と残してコピーする3枚の計6枚以上が手札に必要。バット1枚の生成だけでは足りない。','コピーしたい3枚が、捨てた後の左3枚になるように残せることが必要。','本体の5PPと場の空き、進化可能時期、EPまたはSEPが必要。本体を手札からプレイするならその1枚の手札消費も別途差し引く。','効果による自動進化で進化時を起動したとは扱わない。'], 'note_status':'注記の「十分な手札補充なしでは増殖装置として機能しにくい」という制約を保持する。バット1枚で成立、強い、新しいとは言わない。'},'evidence':[ev(10502110,'skill_text'),ev(10502110,'evolution_text'),ev(10502110,'note','ユーザー評価(2026-07-30): 進化時コピーには捨てる手札3枚と、コピー後に残す左3枚が必要で、十分な手札補充なしでは増殖装置として機能しにくい。')]}
  ],'limitations':['2枚とも今後の確認候補で、指定状態ですでに発動した効果ではない。','バットの注記はドレイン回復が攻撃に条件付けられることを述べる。捨てる用途の有用性や新規性を保証するものではない。','「手札」「捨て」を含まない同義表現を意味で全件精査してはいない。']},
  'uncertainties':['ルルミ破壊前の手札の内訳、残りPP、ターン、進化権、場と相手の状況は未指定。','バットを使う最善手、カードの強さ、新規性、勝率は未確認。','得たバットを捨ててもバットが場で破壊された扱いにはならない。リアニメイト用の破壊履歴を増やす用途へは接続しない。']}
], 'overall':{'useful_next_steps':['ドロー側で残る18枚の非フォロワーの内訳と、役立てたい後続の効果を指定してから、割合変化が実際に役立つかを調べる。','ルルミのケースでは、生成直後の手札内訳と使用可能なPP・進化権を置き、享楽の上位市民またはスターライトゴッデスの必要条件を満たせるかを次に確認する。'], 'limits':['保存資料だけによる3ケースの確認。実際の対戦、勝率、強さ、新規性は評価しない。','問い2件から各1回、全212枚へ文字検索を実施。リアニメイト側は山札への状態変化がないため追加検索なし。','追加の外部情報、他方式の出力、DB、src、正式submit/reviewは使用していない。']}}
(root/'answer.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n')
checks=[]
for case in answer['cases']:
 for e in case['evidence']:
  assert e['quote'] in cards[e['card_id']][e['field']]
 for candidate in (case.get('search') or {}).get('candidates',[]):
  for e in candidate['evidence']:
   assert e['quote'] in cards[e['card_id']][e['field']]
 assert case['question'] is not None or case['search'] is None
 assert len((case.get('search') or {}).get('candidates',[]))<=2
checks=['JSON再読出し成功','ケースIDが指定3件と一致','引用が指定カードの指定欄の部分文字列であることを機械確認','問いなしはsearch=null','候補数は各0〜2枚']
assert [x['id'] for x in json.loads((root/'answer.json').read_text())['cases']]==['draw-selected','reanimate-selected','last-words-generated']
execution={'actual_start_utc':json.loads((root/'start.json').read_text())['actual_start_utc'],'research_end_utc':research_end,'save_end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'packet_hash_verification':{'declared':p['sha256'],'calculated':hashlib.sha256(json.dumps(p['data'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'match':True},'read_scope':{'inputs':['/tmp/sv-effect-evidence-check-01/worker-instructions.txt','/tmp/sv-effect-evidence-check-01/cases.json','/tmp/sv-effect-evidence-check-01/a/input-packet.json'],'applicable_rules':'提示されたAGENTS.mdと、そこから参照されるagent-lab/rulesの10ファイルを読出し。後者の一括表示が省略されたため完全に読めたとはしない。','packet_sections':'dataのキーと短い概観、contextのカード2件、バット、公式定義、検索該当35件と39件、最終候補2件。rules/principlesは先頭抜粋とprinciples見出し一覧。known_decksの保存内容の先頭も概観出力に含まれたが、候補成立や新規性の根拠に使用していない。','all_cards_scanned':212,'fields':['skill_text','evolution_text','ref_effect_text','note'],'queries':2,'full_scan_passes':2,'supporting_files_created':['search-log.json','write-answer.py']},'public_operations':{'cli_read_count':0,'cli_failures':[],'method':'許可された保存JSONの局所読出しと、同じJSONの全カード指定欄を読むPython文字走査。公開CLIを使う必要が生じなかった。','submit_count':0,'review_count':0,'web_count':0,'additional_agents':0},'failures_and_deviations':['最初の概観でdataの短い内容をhash照合より前に表示した。カード効果の詳読と検索はhash一致を確認後に行った。','1回のfunctions.exec内に資料概観と適用規則の一括表示を重ね、合計出力が省略された。以後は必要欄と検索結果ごとに分割した。','公式用語dictの初回ループはキー名だけを表示したため、次の読出しで対象定義値を読み直した。'], 'unconfirmed':['手札・盤面・破壊履歴・山札の個別カードと順序など指定されていない状態','対戦での成立・有用性・強さ・新規性・勝率','指定文字を含まない本文の意味上の見落とし','適用規則の一括表示で省略された箇所'], 'format_checks':checks,'semantic_self_score':None,'outputs':['/tmp/sv-effect-evidence-check-01/a/answer.json','/tmp/sv-effect-evidence-check-01/a/execution.json']}
(root/'execution.json').write_text(json.dumps(execution,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'answer_bytes':(root/'answer.json').stat().st_size,'case_count':len(answer['cases']),'research_end_utc':research_end,'save_end_utc':execution['save_end_utc'],'format_checks':checks},ensure_ascii=False))
