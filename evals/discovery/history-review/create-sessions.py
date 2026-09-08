from pathlib import Path
import json,subprocess,datetime,hashlib,sqlite3,copy
ROOT=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker')
OUT=Path('/tmp/sv-history-eval');PYTHON='/tmp/sv-system-venv/bin/python'
NOW=datetime.datetime.now(datetime.timezone.utc).isoformat();AUTHOR='/root/continuation_eval_audit'
log=[]

def save(path,value):
 with path.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def cli(*args):
 proc=subprocess.run([PYTHON,'-m','svdeck.discovery',*map(str,args)],cwd=ROOT,capture_output=True,text=True)
 entry={'args':list(map(str,args)),'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr};log.append(entry)
 with (OUT/'cli-log.jsonl').open('a') as f:f.write(json.dumps(entry,ensure_ascii=False)+'\n')
 if proc.returncode:raise RuntimeError(entry)
 return json.loads(proc.stdout)

def ref(cards,cid):return {'card_id':cid,'field':'skill_text','quote':cards[cid]['skill_text']}
def srch(q,why,tag=None):return {'question':q,'tag':tag,'why':why}
def step(action,resources,result,evidence):return dict(action=action,resources=resources,result=result,evidence=evidence)
def role(cid,text,effect=False):return {'card_id':cid,'role':text,'access':'effect' if effect else 'deck',**({'via':[94070002]} if effect else {})}

base_objective=(ROOT/'evals/discovery/role-chain/objective.txt').read_text()
objective=base_objective+'\n\n今回の履歴について：入力担当が開発用に初版と改訂を構成したものです。自然な探索担当が自発的に発見した経緯として扱いません。対象の改訂をhistoryの祖先案およびsourcesの実施記録と比較し、何が解決し何が変わらなかったかと、次にこの固定状態の13点を調べる価値を分けて評価してください。\n'
(OUT/'objective.txt').write_text(objective)
manifest={'created_at':NOW,'fixture_author':AUTHOR,'sessions':{},'root_code_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['src/svdeck/discovery.py','src/svdeck/discovery_read.py','src/svdeck/discovery_sources.py']}}

for name in ('a','b'):
 folder=OUT/name;session=folder/'session'
 conn=sqlite3.connect(folder/'cards.db');conn.row_factory=sqlite3.Row
 cards={r['card_id']:dict(r) for r in conn.execute('SELECT card_id,name,cost,type_category,skill_text FROM card ORDER BY card_id')};conn.close()
 start=cli('start',session,'--db',folder/'cards.db','--class','ウィッチ','--format','rotation','--objective',objective)
 save(folder/'start-result.json',start)
 provenance={'title':'この開発用入力と履歴の由来','kind':'入力担当による作成記録','location':str(ROOT/f'evals/discovery/role-chain/input-{name}.sql'),'observed_at':NOW,
  'content':'この入力は保存済みの仮想9枚カードのSQLを再使用したもの。初版と改訂は入力担当 /root/continuation_eval_audit が意図的に構成する。カード本文・指定初期手札は変更しない。実際の検査実施結果は別資料として付ける。探索担当が自発的に発見した経緯ではない。',
  'limitations':['実在カードではない。公式URL風の欄があっても実在公式カードとして照合しない。','実戦の勝率、Tier、独自の実デッキ発見、方式間の優位はこの入力で評価しない。','過去の評価ラベルは資料に含めない。']}
 save(folder/'provenance-source.json',{'sources':[provenance]});cli('attach',session,folder/'provenance-source.json')
 initial=cli('packet',session);save(folder/'develop-packet-0.json',initial)
 cost=cards[94070005]['cost']
 seed={
  'packet_hash':initial['sha256'],'parent_revision':0,'author':AUTHOR,
  'title':'守護の生成物を手札条件へ使う初版',
  'hypothesis':('守衛庫で生成した番兵を紙梯子で手札へ戻し、金環の対句の13点条件へ転用する。生成4＋戻し2＋対句4は10PPで、指定9PPに1足りない。軽減の使い方を調べる。' if name=='a' else '守衛庫の番兵を紙梯子で手札へ戻し、金環の対句で13点へつなぐ余地を調べる。番兵の元コストは9で12以上という条件に足りず、生成4＋戻し2＋対句4も10PPになる。固定カード内で条件を解く働きがあるか未確認とする。'),
  'change':'入力担当が構成した初版。カード探索担当が自然に到達した履歴とは数えない。',
  'roles':[role(94070001,'手札の元コスト12以上を参照する条件付き13点札。'),role(94070002,'通常の守護展開を、手札へ移す素材の入口として使う。'),role(94070003,'場の番兵を手札へ移す。'),role(94070005,f'元コスト{cost}の生成専用フォロワー。守護として残す用途から手札条件の素材へ変える候補。',True)],
  'steps':[
   step('指定初期手札8枚・9PPから守衛庫を4PPで使用。','PP9→5、手札8→7、場0→番兵1体。進化権/超進化権0、相手体力13のまま。','番兵の生成先は場であり、まだ手札条件へ入らない。',[ref(cards,94070002),ref(cards,94070005)]),
   step('紙梯子を2PPで使用し番兵を手札へ戻す。','PP5→3、手札7→6（使用）→7（番兵加入）、場1→0。相手体力13。',f'元コスト{cost}の番兵が手札に入る。PP回復はない。',[ref(cards,94070003),ref(cards,94070001)]),
   step('次に対句を4PPで使う計画を点検する。','残PP3なので4PPを払えず、この順序はここで停止する。仮想の13点を実際の発生ダメージへ加えない。',('元コスト12条件は満たしたが、総額10PPのため1PP不足。' if name=='a' else '元コスト9では12条件も満たさない。PPだけ軽くしても13点になるとは示せない。'),[ref(cards,94070001)])],
  'plan':{'early':'指定された第9ターン・固定初期手札からだけを扱う。序盤や取得頻度は検査しない。','transition':'場への守護生成を手札条件へ読み替えるため紙梯子を使う。','finish':'目標は現在のターンに相手残体力13を削ること。今の手順では実現していない。','without_core':'条件なし対句4点と採寸4点なら8PPで合計8点。','allocation':'守衛庫と紙梯子を条件の準備へ回し、番兵を守護として場に残す働きを手放す。40枚の採用配分は今回の入力外。','comparison':'通常2枚8PPの8点を越えて13点を目指す。未解決の条件やPPを解いたことにしない。'},
  'questions':([srch('全支出を含めて10PPを9PP以内へ変える手段はあるか。','手順の1PP不足を解ければ指定状態で13点へ届く。','コスト減少(手札スペル)')] if name=='a' else [srch('この固定8枚と生成先だけで、元コスト12以上の手札条件を満たして13点を出す手段はあるか。','番兵の元コスト9が障害。軽減だけで解決したことにはしない。','存在(手札高コストフォロワー)')]),
  'uncertainties':['この初版は検査用に意図的に構成した途中案。自然な発見の証拠ではない。','実戦の取得頻度、生存、勝率、Tier、新規性は検査しない。']}
 save(folder/'proposal-1.json',seed);cli('submit',session,folder/'proposal-1.json')
 # Real execution: finite enumerator results were created by prepare.py before this attachment.
 enumeration=json.loads((folder/'independent-enumeration.json').read_text())
 rows='\n'.join(f"- {c['card_id']} {c['name']}：元コスト{c['cost']}、{c['type_category']}。本文『{c['skill_text']}』" for c in cards.values())
 if name=='a':
  content='今回実施した確認：初版の不足1PPについて、全9枚の本文と費用を再確認した。余白のしるしは1PPを支払い、手札スペル1枚を2軽くする。紙梯子を対象にすれば1＋4＋0＋4＝9PP。手札8枚からしるし→守衛庫→紙梯子→対句で手札は8→7→6→5→6→5、場は0→0→1→0→0、PPは9→8→4→4→0。番兵の元コスト12は手札へ戻した後も12で、対句は通常4に加算せず13点へ置き換わる。\n\n'+rows+'\n\n独立の有限列挙でも、初期8枚各1枚・9PPから到達した最大ダメージは13だった。訪問した異なる状態は'+str(enumeration['states'])+'件、検査した遷移は'+str(enumeration['transitions'])+'件。守護の当日攻撃や進化権を使っていない。'
 else:
  content='今回実施した確認：固定した全9枚の本文・元コスト・生成先を1件ずつ点検した。初期手札のフォロワーは乾いた番帳の元コスト2と凪の観測者の元コスト3。生成できるフォロワーは青磁の番兵の元コスト9だけ。紙梯子は場から手札へ戻すが元コストを増やさない。しるしの対象はスペルであり、支払コストを減らすだけなので、元コスト12以上のフォロワーを作らない。\n\n'+rows+'\n\n本文からの上限：直接リーダーダメージは初期手札に各1枚の金環の対句と火花の採寸だけ。元コスト12以上が初期手札にも全生成先にもなく、金環は4点。追加ドロー、スペル回収・複製・再使用、当日リーダー攻撃を可能にする効果は、この全9枚にない。回復を相手ダメージに数えない。したがって相手へのダメージ上限は4＋4＝8。対句4PP→採寸4PPを実行すれば9→5→1PPで8点に達するため、上限は到達可能。\n\n独立の有限列挙も最大ダメージ8、訪問した異なる状態'+str(enumeration['states'])+'件・遷移'+str(enumeration['transitions'])+'件だった。これは初版が残した手札条件の問いに対して実施した結果であり、未実施の検索予定ではない。'
 obs={'title':'固定初期状態で実施した本文確認と資源検算','kind':'検査入力担当による実施記録','location':str(folder/'independent-enumeration.json'),'observed_at':NOW,'content':content,
  'limitations':['この有限列挙は全カードゲームの対戦シミュレータではなく、この仮想9枚の印刷効果だけを実装した検算。','初期手札8種類各1枚、9PP、場は双方空、進化権・超進化権0、追加PP使用済み。山札、追加取得、相手の協力を使わない。','指定状態外の構築やカード全般の有用性、実戦勝率、Tierはこの結果から判断しない。','入力担当による観測であり、過去reviewの採否評価は含めない。カード本文と計算は別評価担当も照合できる。']}
 save(folder/'observation-source.json',{'sources':[obs]});attached=cli('attach',session,folder/'observation-source.json');source_hash=attached['added'][0]
 developed=cli('packet',session);save(folder/'develop-packet-1.json',developed)
 if name=='a':
  revision=copy.deepcopy(seed)
  revision.update(packet_hash=developed['sha256'],parent_revision=1,title='紙梯子の支払いを軽くして9PPへ接続する',hypothesis='守護生成物を手札へ戻す役割変更に、余白のしるしの支出1PPと軽減2PPを組み込む。紙梯子を0PPにして、1＋4＋0＋4＝9PPで元コスト12の番兵を手札に置き対句13点へつなぐ。',change='初版の生成→手札戻し→条件打点は10PPだった。全9枚を確認した結果、しるしを紙梯子へ使うと支出込みで正味1PP節約でき、指定PP不足が解けた。これは入力担当が構成した改訂。')
  revision['roles'].insert(3,role(94070004,'1PP支出して紙梯子を2PP軽減し、手順全体の1PP不足を解消する。'))
  revision['steps']=[
    step('余白のしるしを1PPで使い、手札の紙梯子を対象にする。','PP9→8。手札8→7、場0。相手体力13。進化権/超進化権0。','紙梯子のこのターンの支払い2→0。軽減の支出1PPも計上する。',[ref(cards,94070004),{'source_hash':source_hash,'quote':'紙梯子を対象にすれば1＋4＋0＋4＝9PP。'}]),
    step('守衛庫を4PPで使い、番兵を場に出す。','PP8→4。手札7→6、場0→番兵1。相手体力13。','番兵は元コスト12。生成先は場でまだ手札条件には使えない。',[ref(cards,94070002),ref(cards,94070005)]),
    step('軽減済み紙梯子を0PPで使い、番兵を手札へ戻す。','PP4→4。手札6→5（使用）→6（番兵加入）、場1→0。相手体力13。','元コスト12のフォロワーが手札に存在する。番兵の12PP支払いは不要だが、場の守護を失う。',[ref(cards,94070003),ref(cards,94070001)]),
    step('番兵を手札に残したまま金環の対句を4PPで使う。','PP4→0。手札6→5、場0。相手体力13→0。','通常4点ではなく13点を一度与える。使用4枚、生成1枚、手札上限9と場上限5以内。相手の協力・当日攻撃・追加取得はない。',[ref(cards,94070001)])]
  revision['plan']['transition']='しるしを先に紙梯子へ使い、生成物を場から手札へ移して条件を満たす。'
  revision['plan']['finish']='指定9PPで相手13を削る。通常4点を条件13点に加えない。'
  revision['plan']['without_core']='しるしがない元手順は10PPで1不足。生成か手札戻しがなければ対句4と採寸4の8点。'
  revision['plan']['allocation']='指定初期手札のうち生成・手札戻し・軽減を条件準備に充て、番兵を場へ守護として残す働きを手放す。40枚化はしない。'
  revision['plan']['comparison']='通常の対句4＋採寸4は2枚8PPで8点。本手順は4枚9PPで13点。追加2枚と1PPを払う利益は指定残体力13の達成にあり、実戦での組みやすさは未測定。'
  revision['questions']=[]
 else:
  revision=copy.deepcopy(seed)
  revision.update(packet_hash=developed['sha256'],parent_revision=1,title='手札条件の接続余地をもう一度調べる',hypothesis='守衛庫から得る番兵を手札へ移した後、対句で13点に達する接続を引き続き検討する。番兵が元コスト9という障害と10PPの支払いを越える手段が、この固定8枚と生成先にあるかを確かめたい。',change='元の問いの説明を整理して再提示した。今回の札・使い方・資源・条件を新しく変更する指定はない。入力担当が構成した改訂。')
  revision['questions']=[srch('初期手札8枚と本文の生成物を使って、対句の元コスト12以上の手札条件へ到達し13点にする経路を、さらに確認できるか。','番兵を戻す利用を続け、固定状態の13点へのつながりを確かめる。','存在(手札高コストフォロワー)')]
 save(folder/'proposal-2.json',revision);submit=cli('submit',session,folder/'proposal-2.json')
 final=cli('packet',session,'--stage','review');save(folder/'review-packet.json',final)
 summary=cli('packet',session,'--stage','review','--summary');save(folder/'review-summary.json',summary)
 history=cli('read',session,final['sha256'],'history');save(folder/'read-history.json',history)
 sources=cli('read',session,final['sha256'],'sources');save(folder/'read-sources.json',sources)
 assert final['data']['revision']==2 and final['data']['proposal']['parent_revision']==1
 assert len(final['data']['history'])==1 and final['data']['history'][0]['proposal']['revision']==1
 assert final['data']['history'][0]['input_search']==[]
 assert len(final['data']['history'][0]['input_source_hashes'])==1
 assert len(final['data']['sources'])==2 and final['data']['previous_reviews']==[]
 assert len(final['data']['search'])==(0 if name=='a' else 1)
 assert source_hash in {s['source_hash'] for s in final['data']['sources']}
 assert source_hash not in final['data']['history'][0]['input_source_hashes']
 manifest['sessions'][name]={'session':str(session),'review_packet':str(folder/'review-packet.json'),'review_packet_hash':final['sha256'],'revision':2,'history_revisions':[1],'source_count':2,'observation_source_hash':source_hash,'submit_result':submit}
manifest['files_sha256']={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ('manifest.json',)}
save(OUT/'manifest.json',manifest)
print(json.dumps(manifest['sessions'],ensure_ascii=False,indent=2))
