from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,tarfile
from svdeck import discovery
from svdeck.discovery_run import manifest,copy_session,check_unchanged
from svdeck.journal_store import Journal
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');e=root/'evals/discovery/remaining-question-01';p=json.loads((e/'protocol.json').read_text());started=datetime.now(timezone.utc).isoformat();source=Path(p['source']);destination=root/'data/discovery/remaining-question-01-input';j=Journal(root)
check_unchanged(source,p['source_manifest'],exact=True);assert not destination.exists();copy_session(source,destination);check_unchanged(destination,p['source_manifest'],exact=True);r=discovery.report(destination);assert len(r['revisions'])==2 and sum(len(x['reviews']) for x in r['revisions'])==1 and len(r['revisions'][-1]['reviews'])==1;assert len(list((destination/'sources').glob('*.json')))==26;assert hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest()=='11aef89fae292ce671781ce31da124d695b15b28f64d7813c6e0c9ad720e1414';ended=datetime.now(timezone.utc).isoformat()
proof={'started_at':started,'ended_at':ended,'source':str(destination),'copied_from':str(source),'manifest':manifest(destination),'formal_revisions':2,'formal_reviews':1,'sources':26,'main_db_unchanged':True,'original_source_unchanged':True,'limits':'保存済みの現行案・評価・資料を再利用した改訂比較。初見ではない。'};(e/'preparation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
with tarfile.open(e/'input.tar.gz','w:gz') as tar:tar.add(destination,arcname='session')
c=j.get(e.name);record=c['record'];next(s for s in record['stages'] if s['id']=='prepare').update(title='共通の旧案・別評価・資料を固定',status='completed',started_at=started,ended_at=ended,note='現行版の結果36ファイルを一致確認。改訂2・評価1・資料26、元入力と主DB保持。');record['evidence_paths']+=['evals/discovery/remaining-question-01/'+n for n in ['prepare-input.py','preparation.json','input.tar.gz']];j.save(record,c['revision'],'codex-root','両方式へ渡す旧案と評価を固定');(e/'journal-record.json').write_text(json.dumps(j.get(e.name),ensure_ascii=False,indent=2)+'\n');print({k:v for k,v in proof.items() if k!='manifest'})
