from pathlib import Path
import json,hashlib,sqlite3,subprocess,datetime,copy
ROOT=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');OUT=Path('/tmp/sv-mazel-role-eval')
DB=ROOT/'data/cards.db';PYTHON='/tmp/sv-system-venv/bin/python';AUTHOR='/root/continuation_eval_audit'
NOW=datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,value):
 with path.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def cli(*args):
 r=subprocess.run([PYTHON,'-m','svdeck.discovery',*map(str,args)],cwd=ROOT,capture_output=True,text=True)
 with (OUT/'cli-log.jsonl').open('a') as f:f.write(json.dumps({'args':list(map(str,args)),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},ensure_ascii=False)+'\n')
 if r.returncode:raise RuntimeError(r.stderr)
 return json.loads(r.stdout)

scope={
 'fixed_at':NOW,'format':'unlimited','class_name':'エルフ','source_database':str(DB),'source_database_sha256_before':sha(DB),
 'purpose':'既知ユーザーフィードバックと保存カード本文を読んで、構築の前半と後半の役割分担を認めつつ、山札置換後の取得についての誤りを区別できるかを検査する。',
 'fixture_origin':'入力担当が意図的に構成する2つの検査用seed。自然な探索担当による発見履歴ではない。',
 'not_tested':['過去のマゼルテンポエルフの完全な40枚・当時環境・勝率・Tierの再現','最新の公式能力・ルールへの外部再照合','未知デッキの発見能力、方式比較、実戦での採用優先度','ベイル軽減の最速達成、初期手札の取得頻度、序盤ダメージの保証','置換先の全76枚の確定と抽選確率'],
 'known_source_limit':'DB ability_keyword はマゼルベインデッキを絶傑の継承者から1枚ずつの76枚と定義するが、保存card_set_id10003の非token行は77件。この相違から除外される1枚を推定しない。ベイル10113130はcard_set_id10001で、同パック内にベイルの行はない。単純な通常6ドローを元デッキの任意札取得へ転用できないことは、この相違と分離して判定する。',
 'cards_in_seed':[10304110,10113130,90004320],
 'notes':'主役・相方のcard_noteをstartの固定資料にそのまま保持する。ベイルは現DB noteなし。無い注記を生成しない。',
 'shared_conditional_state':'意味確認の例として、現在PP/最大PP8/8、通常進化権1、手札3枚はマゼル1枚とベイル2枚、場は自分0・選べる相手フォロワーありとする。ベイル2枚を手札に持っている間に自分のフォロワーが合計4回場を離れたという条件を与える。両ベイルは8→4PP。マゼル未使用・クレスト未取得。元デッキにはベイル3枚目が残っているとする。到達済みの実測ではなく、最速・安定達成も主張しない。',
 'reviewer_access':'別評価者へはa/bのreview-packet.jsonのみ。expected.json・scope.json・入力生成コード・旧レポート・今回の採点結果は渡さない。packet内sourcesは出典・条件・データの限界であり採否結論は含めない。'}
save(OUT/'scope.json',scope)
expected={
 'fixed_at':NOW,'purpose':scope['purpose'],
 'a':{'label_scope':'正例という名称は役割変更の意味を認めるべき例という意味。現構築を試す優先度の正解ラベルではない。',
   'value_scoring':'特定値を強制しない。develop/unknown等を許容し、条件付きの優先度判断と意味の成立を分離する。直接打点0・置換後元札を引けない・単体コンボにならないという理由だけの一律棄却は不可。',
   'required_findings':['前半を元デッキの手札消費・攻撃・ベイル軽減へ寄せ、後半の補充を置換先へ任せるという構築上の役割分担を認める。','この方針は置換後に元デッキの任意札を取得する必要がない。','指定例でベイル4＋マゼル4＝8PPと通常進化権1を払う。ベイル4回離脱は与えた条件で、8回/最速/毎試合の達成ではない。','マゼルのクレストを持った時点で山札が置換され、手札はこの瞬間に全交換されない。終了時には絶大の証明以外の残り手札を捨てる。','指定例の終了前の手札は残したベイル1＋証明1の2枚。ベイル1を捨て6枚引き、証明1＋置換先6の7枚で終了直前からの純増は5。一般には捨てる枚数と手札上限も関わる。','正確な初期40枚と取得頻度等がなく、実際の採用優先度・勝率を断定しない。'],
   'hard_errors':['置換後に任意の元デッキ札を引けないことを理由に、この前半/後半の役割分担まで不成立にする。','ベイルはマゼル補充後まで保持できるとする。','6枚取得をこの指定例で純増6枚とする。','手札で持つ前の離脱を当然ベイル軽減へ遡及する。','直接打点0のみで役割変更を無価値とする。']},
 'b':{'procedure_target':'元デッキに残したベイル3枚目が、マゼル置換後も通常6ドローの取得候補として残るという具体的な主張。',
   'required_findings':['クレストを持った時点で山札が固定された別の山札になるという本文とkeywordを根拠に、この通常ドローの主張を否定する。','ベイルは保存DBで絶傑の継承者ではない。元デッキに3枚目があったという前提は置換後の候補を保存しない。','元札を新しく引く誤りと、既に手札にある元札を置換した同じターンに使える時間帯を区別する。','手札の残りベイルは終了時に捨てるため翌ターンへ当然保持できない。','誤った取得を必要としない前半/後半の役割分担まで否定せず、カード全般を禁止しない。'],
   'value_scoring':'元札の通常取得を根拠に現案を試行推薦しない。具体的取得主張をrefutedとする説明が必要。drop/develop/unknownという優先度ラベル自体は固定しない。',
   'hard_errors':['元山札の残りベイルを置換後の通常ドローで取得可能と認定する。','存在しない外部カード・元山札の維持効果を勝手に追加して元案を救う。','置換は手札も即時全交換すると誤る。','マゼルと元デッキの構築上の役割分担をすべて不成立とする。']},
 'common':['アンリミとして評価し、ローテ落ちをアンリミでの禁止にしない。','両側のnoteを読み、マゼルの古い任意カードコンボ不可という注記を2026-09-06補足の範囲で解釈する。','ユーザーの過去tier3〜4評価はユーザーが既存デッキについて述べた経験であり、今回の入力のTierや勝率には移植しない。','76枚定義と77行の相違をもとに特定の除外札・抽選率・全構成を捏造しない。','新規性・最新公式再確認を認定しない。'],
 'grading':'各caseの必要な意味判断と資源処理を満たし重大誤りがなければ、そのcaseは意味解釈の検査PASS。実戦の採用優先度がunknownでもこの検査自体は未達としない。原文不足で個別項目を判断できなければ、その範囲と理由を記録し勝手に補完しない。固定条件を後から変更しない。'}
save(OUT/'expected.json',expected)

objective='エルフ・unlimitedのローカルDB保存版を使い、提出する検査用の案の意味・行動順・構築上の役割分担を評価してください。入力担当が既知カードとユーザーフィードバックから構成したseedであり、新しいデッキ探索ではありません。正確な40枚は提示されていないので、配分方針までを扱います。前半に使う元の札と、後半に使う補充の供給元を区別し、山札置換・手札破棄・取得のタイミングをカード本文、keyword、両側のnoteで確認してください。特定の優先度ラベルや試行推薦は要求しません。構造の意味、指定した条件での成立、実戦の採用優先度、新規性を分け、未確認は未確認として示してください。新しい相方を探したり40枚を作ったりせず、提出案の主張を評価してください。最新の外部再照合、当時の完全再現、勝率やTierの予測は今回行いません。'
(OUT/'objective.txt').write_text(objective)
manifest={'fixed_at':NOW,'source_db_sha256_before':scope['source_database_sha256_before'],'expected_sha256':sha(OUT/'expected.json'),'sessions':{}}
for name in ('a','b'):
 folder=OUT/name;folder.mkdir();session=folder/'session'
 save(folder/'start-result.json',cli('start',session,'--db',DB,'--class','エルフ','--format','unlimited','--objective',objective))
 provenance={'title':'検査用seedの由来・条件・資料の限界','kind':'入力担当による範囲の記録','location':str(DB),'observed_at':NOW,
  'content':'このseedは入力担当が意図的に構成した。主役はマゼル10304110、前半の役割例はベイル10113130、生成専用の証明90004320。両側のnoteは保存版を保持している。\n\n'+scope['shared_conditional_state']+'\n\n元の40枚、序盤の具体的な攻撃打点、ここまでに手札を揃える頻度は与えていない。前半の低い費用の札を増やし、後半の補充を置換先に任せる配分方針の例として扱う。\n\n'+scope['known_source_limit'],
  'limitations':scope['not_tested']+['外部Web再取得なし。DBの保存時刻と現在有効な公式能力の確認時点を混同しない。','条件付きの資源例であり、実際に試合で観測したものではない。','正確な初期40枚が不明なので、抜いた札の特定や枚数の優劣を保証しない。']}
 save(folder/'source-input.json',{'sources':[provenance]});cli('attach',session,folder/'source-input.json')
 packet=cli('packet',session);save(folder/'develop-packet.json',packet)
 data=packet['data'];cards={c['card_id']:c for c in data['context']['cards']}
 def ref(cid,field='skill_text'):return {'card_id':cid,'field':field,'quote':cards[cid][field]}
 def st(action,resources,result,ev):return {'action':action,'resources':resources,'result':result,'evidence':ev}
 kw={'keyword':'マゼルベインデッキ','quote':data['context']['ability_keywords']['マゼルベインデッキ']}
 assert cards[10304110]['deck_eligible'] and cards[10113130]['deck_eligible']
 assert cards[10113130]['note']==''
 common={
  'packet_hash':packet['sha256'],'parent_revision':0,'author':AUTHOR,
  'title':'元の構築の前半とマゼルの補充で役割を分ける',
  'hypothesis':'マゼルを特殊勝利だけでなく後半の補充源として見る。元の構築は早い段階の手札消費と攻撃へ寄せ、ベイルを手札に持っている間の味方離脱による軽減をその前半に使う。切替時にはマゼル4PPと進化権を払い、以後の後半は置換先からの補充へ任せる。元デッキの任意札を置換後に新しく取得することや、終了時に残りの元札を保持することを前提にしない。',
  'change':'入力担当が構成した単独の検査用seed。自然な探索による新発見、歴史デッキの完全再現とは扱わない。',
  'roles':[{'card_id':10304110,'role':'4PPと進化権を使い、山札の供給元を置換して後半の補充を担う。','access':'deck'}, {'card_id':10113130,'role':'前半に手札を使って戦う中で、手札保持中の味方離脱を軽減に変え、切替より前または同じターンの前半で使う役。','access':'deck'}, {'card_id':90004320,'role':'マゼルのFFで手札に加わり、クレストの終了時全捨ての例外として残る生成物。この例ではプレイしない。','access':'effect','via':[10304110]}],
  'steps':[
   st('前半の配分方針と、ここから検算する条件を区別する。','序盤の具体的打点・最速ターン・正確な40枚は未提示。指定例では現在8PP、通常進化権1、手札はマゼル1＋ベイル2。ベイル2枚を持っている間に味方が4回離れた条件なので、それぞれ8→4PP。','前半に安い札を使い攻撃する方針は、ここまでに何点出るかを保証する主張ではない。8回離脱や0PPのベイルを当然の前提にしない。',[ref(10113130),ref(10304110,'note')]),
   st('手札のベイル1枚を4PPでプレイし、選べる相手フォロワー1枚に4ダメージ。','PP8→4。手札3→2［マゼル1・ベイル1］。自分の場0→ベイル1。通常進化権1を保持。','ベイルの4ダメージは相手フォロワーへの効果であり、相手リーダーへの4点ではない。相手の体力によらず撃破したことにしない。',[ref(10113130)]),
   st('マゼルを4PPでプレイし、ファンファーレで絶大の証明を加える。通常進化権1を使いクレストを得る。','PP4→0。手札2→1［残りベイル］→2［残りベイル・証明］。場1→2。通常進化権1→0。','クレストを持った時点で元の山札はマゼルベインデッキに置換され、山札下の死神は勝利のカードへ変身する。この時点では残りベイルはまだ手札にある。',[ref(10304110),ref(10304110,'ref_effect_text'),kw]),
   st('このターンを終了する。証明を使わず、残りベイルが手札にある指定例として処理する。','終了時の直前手札2［ベイル1・証明1］→ベイル1を捨て1［証明］→置換先から6枚取得し7枚。終了直前との比較で純増5。手札上限9を超えない。','6枚を得るが、この例では純増6ではない。残りベイルは翌ターンに保持されず、元デッキに残した3枚目も通常ドローの供給元として温存されない。取得した6枚の具体的な札・順番・勝ち方は保証しない。',[ref(10304110,'ref_effect_text'),ref(90004320),kw])],
  'plan':{'early':'前半用の元の構築は、手札を使って相手体力を減らす役割へ寄せる方針。手札のベイルに離脱が発生した分だけ軽減を得る。実際の40枚と序盤打点は未確定。','transition':'ベイル等を使う前半から、4PPと進化権をマゼルへ使う切替へ移る。指定例はベイル4＋マゼル4の8PPで、切替が無料とはしない。','finish':'後半の供給は固定された別の山札に任せる。新しい6枚で相手の残体力に対応する方針で、何を引き何ターンで勝つかや特殊勝利の達成を保証しない。','without_core':'マゼルを引けなければ後半の補充へ切り替わらない。元の構築を前半へ寄せるほど手札切れの危険があり、ベイルを早く持てなければ離脱軽減も間に合わない。','allocation':'後半に元札を引く前提を置かず、元の構築の枠を前半の攻撃と手札消費へ寄せる方針。その分、マゼルを引けない時の後半や4PP・進化権の準備に負担がある。枚数の具体的増減は40枚不明のため決めない。','comparison':'前半用と後半用の札を元の構築に両方抱える考え方に対し、後半の供給をマゼルへ任せることで前半用の配分を増やす余地を考える。直接打点を足す単体コンボの優位ではなく、手札を使う段階と補充する段階の役割分担。利益の頻度や実戦優位は未測定。'},
  'questions':[{'question':'実際の採用優先度を判断するには、元の40枚、切替までの攻撃と取得頻度、マゼルを引けない場合の手札切れの程度をどこまで確認する必要があるか。','tag':None,'why':'配分方針が意味を持つことと、具体的構築が試す価値を持つことを分離する。今回は新カード探索や実戦の追加実施を依頼していない。'}],
  'uncertainties':['ローカル保存版の本文だけで確認する。最新の公式情報は外部再照合していない。','前半の40枚、序盤の攻撃打点、ベイルを持つ時点、4回離脱の頻度、マゼル取得率は未測定。','マゼルデッキの76枚定義とパック77行の相違から除外札を推測しない。後半の特定札の取得や完全な76枚リストは確定しない。','2026-09-06のユーザーのTier経験は過去のデッキに関する注記。このseedの実戦強度や新規性へ転用しない。']}
 if name=='b':
  proposal=copy.deepcopy(common)
  proposal['title']='マゼルの補充から元のベイルも引き直す'
  proposal['hypothesis']='前半の攻撃とベイル軽減を使い、マゼル4PPと進化で後半の補充へ切り替える。切替後も元デッキに残した3枚目のベイルは通常6ドローの取得候補として残るので、新しくベイルを引き直す後半を組み込めるとする。現在手札の残りベイルは終了時に捨てるが、元デッキの未取得ベイルから補えるという案。'
  proposal['steps'][3]['result']='このターンの残りベイルは捨てるが、元デッキに残した3枚目は置換後も通常6ドローの取得候補として残るので、その6枚から新しくベイルを引けるとする。実際に引いたベイルの軽減は、引く前の離脱回数を引き継がず元コスト8から始める。'
  proposal['plan']['finish']='通常6ドローの中から元デッキに残したベイルを新しく取得し、後半の選択肢へ使う。残りは置換先の札で戦う方針。'
  proposal['plan']['allocation']='元の構築にベイル3枚を入れ、指定時点で2枚が手札・3枚目が元山札にあるとする。置換後も元山札の3枚目を通常補充で拾えると考えて、後半の選択肢に含める。完全な40枚は決めない。'
  proposal['plan']['comparison']='元の構築へ入れたベイルを、マゼルの継続6枚補充で後半にも取得できるという供給の兼用を狙う。'
  proposal['questions']=[{'question':'山札置換後の通常6ドローでも、元デッキに残したベイルは取得候補として残るという読みでよいか。','tag':None,'why':'後半のベイル取得を構築方針に算入する根拠としている。'}]
 else:proposal=common
 save(folder/'proposal.json',proposal);save(folder/'submit-result.json',cli('submit',session,folder/'proposal.json'))
 final=cli('packet',session,'--stage','review');save(folder/'review-packet.json',final)
 save(folder/'review-summary.json',cli('packet',session,'--stage','review','--summary'))
 ctx=final['data']['context'];fcards={c['card_id']:c for c in ctx['cards']}
 assert all(cid in fcards for cid in (10304110,10113130,90004320))
 assert fcards[10304110]['note']==cards[10304110]['note'] and fcards[10113130]['note']==''
 set_members=[c for c in ctx['cards'] if c['card_set_id']==10003]
 assert len(set_members)==77 and all(c['card_id']!=10113130 for c in set_members)
 assert len(final['data']['history'])==0 and final['data']['previous_reviews']==[]
 manifest['sessions'][name]={'session':str(session),'review_packet':str(folder/'review-packet.json'),'review_packet_hash':final['sha256'],'revision':1,'source_count':len(final['data']['sources']),'card_count':len(ctx['cards']),'collection_rows':len(set_members),'mazel_note_preserved':True,'bail_note_present':bool(fcards[10113130]['note'])}
manifest['source_db_sha256_after']=sha(DB)
assert manifest['source_db_sha256_before']==manifest['source_db_sha256_after']
manifest['files_sha256']={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'}
save(OUT/'manifest.json',manifest)
print(json.dumps({'sessions':manifest['sessions'],'source_db_unchanged':True},ensure_ascii=False,indent=2))
