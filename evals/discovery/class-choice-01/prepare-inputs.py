from pathlib import Path
from datetime import datetime, timezone
import os, json, subprocess, hashlib
ROOT=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker')
CODE=Path('/tmp/sv-class-choice-prototype')
RUN=Path('/tmp/sv-class-choice-01')
SOURCE=Path('/tmp/sv-sketch-first-01/cards-reference-refresh.db')
ENV={**os.environ,'PYTHONPATH':str(CODE/'src')}
COMMAND=['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery']
CLASSES=['エルフ','ロイヤル','ウィッチ','ドラゴン','ナイトメア','ビショップ','ネメシス']
OBJECTIVE='ニュートラルのカードの別用途や役割から出発し、それが活きるクラスと構築配分・勝ち方まで発展させて、独自でそこそこ戦えるデッキの種を考える。既知の標準用法との差、条件が揃わない時の勝ち方、採用負担に見合う可能性を根拠で説明する。特定カードやクラスを最初から指定しない。'

def digest(value):
 return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def public(args,out):
 result=subprocess.run(COMMAND+args,cwd=CODE,env=ENV,text=True,capture_output=True)
 with (RUN/'preparation-commands.jsonl').open('a') as f:f.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'args':args,'returncode':result.returncode,'stderr':result.stderr},ensure_ascii=False)+'\n')
 assert result.returncode==0,result.stderr
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(result.stdout)
 return json.loads(result.stdout)

assert not subprocess.check_output(['git','status','--porcelain'],cwd=CODE).strip(),'prototype must be clean before creating natural inputs'
assert not (RUN/'input-check.json').exists(),'completed input must not be regenerated'
RUN.mkdir(exist_ok=True)
started=json.loads((RUN/'preparation-commands.jsonl').read_text().splitlines()[0])['at'] if (RUN/'preparation-commands.jsonl').exists() else datetime.now(timezone.utc).isoformat()
contexts={};indices={}
for label,cls in [('a-'+str(i+1),c) for i,c in enumerate(CLASSES)]+[('b','all')]:
 directory=RUN/label;directory.mkdir(exist_ok=True);session=directory/'session'
 result=json.loads((directory/'start.json').read_text()) if (directory/'start.json').exists() else public(['start',str(session),'--db',str(SOURCE),'--class',cls,'--format','rotation','--objective',OBJECTIVE],directory/'start.json')
 context=json.loads((session/'context.json').read_text())['data'];contexts[label]=context
 indices[label]={'class_name':cls,'session':str(session),'context_hash':result['context_sha256'],'eligible_cards':result['eligible_cards'],'related_cards':result['related_cards']}
all_context=contexts['b'];cards={};decks={}
for label,c in contexts.items():
 if label=='b':continue
 for row in c['cards']:
  old=cards.setdefault(row['card_id'],{**row,'deck_eligible':False})
  assert {k:v for k,v in old.items() if k!='deck_eligible'}=={k:v for k,v in row.items() if k!='deck_eligible'}
  old['deck_eligible']=old['deck_eligible'] or row['deck_eligible']
 for row in c['known_decks']:
  assert row['id'] not in decks or decks[row['id']]==row
  decks[row['id']]=row
 for key in ('rules','principles','ability_keywords','card_sets','fulfillment_map','objective','format','related_coverage','freshness','snapshot_sha256'):
  assert c[key]==all_context[key],(label,key)
assert cards=={c['card_id']:c for c in all_context['cards']},'card union differs'
assert decks=={d['id']:d for d in all_context['known_decks']},'reference union differs'
assert sum(c['deck_eligible'] for c in cards.values())==516
sources=[]
for d in all_context['known_decks']:
 assert sum(c['count'] for c in d['cards'])==40 and d['currently_legal_list']
 sources.append({'title':d['name']+' 全40枚（保存した公開構築）','kind':'公開記事から取得済みの比較用構築リスト','location':d['url'],'observed_at':d['fetched_at'],'content':json.dumps([{k:c[k] for k in ('card_id','name','count')} for c in d['cards']],ensure_ascii=False,indent=2),'limitations':['保存済みの表示表またはコピー対象。今回Webを再取得したこと、実戦評価、独自性・勝率を証明しない。','取得来歴: '+json.dumps(d['source'],ensure_ascii=False),'能力・合法性は固定したカードDB時点。表示とコピー対象が違う例は来歴に残す。']})
sourcepath=RUN/'reference-sources.json';sourcepath.write_text(json.dumps({'sources':sources},ensure_ascii=False,indent=2)+'\n')
for label,index in indices.items():
 directory=RUN/label;session=index['session']
 public(['attach',session,str(sourcepath)],directory/'attach.json')
 packet=public(['packet',session,'--stage','develop','--revision','0'],directory/'initial-packet.json')
 index['initial_packet_hash']=packet['sha256'];index['packet']=str(directory/'initial-packet.json')
 index['context_characters']=len(json.dumps(contexts[label],ensure_ascii=False))
 index['source_count']=len(packet['data']['sources'])
proof={'started_at':started,'completed_at':datetime.now(timezone.utc).isoformat(),'prototype_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=CODE,text=True).strip(),'source_db_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'objective':OBJECTIVE,'sessions':indices,'checks':{'eligible_card_union':516,'all_context_card_count':len(cards),'reference_union':len(decks),'same_shared_metadata':True,'same_source_corpus_each_session':len(sources),'single_class_restriction_not_imposed':True},'limits':['This is input preparation, not natural exploration or useful output.','Per-class contexts differ in eligibility, class, scope and capture time; union equality is checked.','No historical gameplay or current web recheck is claimed.']}
(RUN/'input-check.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
(RUN/'operator-readme.md').write_bytes((CODE/'README.md').read_bytes())
print(json.dumps(proof,ensure_ascii=False))
