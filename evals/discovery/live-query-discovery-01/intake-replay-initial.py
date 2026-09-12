from pathlib import Path
from datetime import datetime,timezone
import json, subprocess, os, time, hashlib
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');e=root/'evals/discovery/live-query-discovery-01';out=Path('/tmp/game8-leading-replay');out.mkdir(exist_ok=False)
started=datetime.now(timezone.utc).isoformat();tick=time.monotonic()
program=r'''
from pathlib import Path
from dataclasses import asdict
from urllib.parse import urlparse
from svdeck import meta
import json,hashlib
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker'); db=root/'data/cards.db';urls=json.loads((root/'evals/discovery/live-query-discovery-01/protocol.json').read_text())['articles'];records=[]
for url in urls:
    name=urlparse(url).hostname+'-'+urlparse(url).path.rsplit('/',1)[-1]+'.html';text=Path('/tmp/live-query-article-diagnosis',name).read_text()
    try:
        details=meta.parse_game8_decks(text) if urlparse(url).hostname=='game8.jp' else [meta.parse_gamewith_deck(text)]
        meta._get_html=lambda supplied, body=text: body
        answer=meta.article_sources(db,url,'rotation',with_text=True)
        records.append({'url':url,'status':'passed','details':[asdict(x) for x in details],'source_count':len(answer['sources']),'html_sha256':hashlib.sha256(text.encode()).hexdigest()})
    except ValueError as exc:records.append({'url':url,'status':'failed','error':str(exc),'html_sha256':hashlib.sha256(text.encode()).hexdigest()})
print(json.dumps(records,ensure_ascii=False))
'''
r={}
for side,runtime in [('before','/tmp/sv-live-query-discovery-01-a-launch/runtime'),('after','/tmp/sv-game8-leading-recipe-01-worktree/src')]:
    p=subprocess.run(['/tmp/sv-system-venv/bin/python','-B','-c',program],capture_output=True,text=True,check=True,env={**os.environ,'PYTHONPATH':runtime})
    r[side]=json.loads(p.stdout);(out/(side+'.json')).write_text(p.stdout)
assert len(r['before'])==len(r['after'])==8
same=[];fixed=[]
for old,new in zip(r['before'],r['after'],strict=True):
    assert old['url']==new['url'] and old['html_sha256']==new['html_sha256'];assert new['status']=='passed' and new['source_count']==3
    if old['status']=='passed': assert old['details']==new['details'];same.append(new['url'])
    else: assert old['error']=='Game8の主レシピ節から独立したデッキレシピを読めません';fixed.append(new['url'])
assert len(same)==7 and fixed==['https://game8.jp/shadowverse-beyond/734194']
assert hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest()=='11aef89fae292ce671781ce31da124d695b15b28f64d7813c6e0c9ad720e1414'
proof={'started_at':started,'ended_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-tick,'total':8,'fixed':fixed,'unchanged':same,'all_40_card_db_resolution_succeeded':True,'main_db_unchanged':True,'sources_each':3,'limits':'保存した同じ実HTTP応答を修正前後の公開取得関数へ渡した再現確認。今回はネットワーク再取得をしていない。実記事の強さ・一般普及は未確認。'};(out/'verification.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n');print(proof)
