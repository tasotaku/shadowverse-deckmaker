from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,hashlib,gzip
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');base=Path('/tmp/sv-pp-comparison-01');archive=root/'evals/discovery/pp-comparison-01';code=Path('/tmp/sv-pp-comparison-prototype');env={**os.environ,'PYTHONPATH':str(code/'src'),'PYTHONDONTWRITEBYTECODE':'1'}
proto=json.loads((base/'protocol.json').read_text());changed=[p for p,h in proto['frozen_files'].items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h];assert not changed,changed
records=[];readbacks=[]
for arm in ['a','b']:
 session=base/arm/'session';work=base/arm/'work';commands=[]
 def call(*args):
  before=datetime.now(timezone.utc).isoformat();r=subprocess.run(['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery',*map(str,args)],env=env,cwd=code,capture_output=True,text=True);commands.append({'args':list(map(str,args)),'started_at':before,'ended_at':datetime.now(timezone.utc).isoformat(),'exit_code':r.returncode});r.check_returncode();return json.loads(r.stdout)
 packet=call('packet',session,'--summary');read=call('read',session,packet['sha256'],'sources','--offset',0,'--limit',10000);assert read['next_offset'] is None
 sources=json.loads(''.join(read['content']));report=call('report',session);checks=[]
 for source in sources:
  content=source['content'];content=''.join(content) if isinstance(content,list) else content
  location=source.get('location','')
  if location==str(work/'report.md'):assert content==(work/'report.md').read_text();checks.append('report.md exact saved content')
  if source.get('source_hash') in proto.get('source_hashes',[]):pass
  if source.get('title','').startswith('PP比較:'):
   saved=json.loads(content);original=json.loads((work/'pp-output.json').read_text());assert all(original[k]==v for k,v in saved.items());checks.append('PP output exact saved content')
 assert 'report.md exact saved content' in checks
 if arm=='b':assert 'PP output exact saved content' in checks
 (work/'root-public-readback.json').write_text(json.dumps({'packet_hash':packet['sha256'],'source_count':len(sources),'source_hashes':[s['source_hash'] for s in sources],'checks':checks,'commands':commands},ensure_ascii=False,indent=2)+'\n');readbacks.append({'arm':arm,'source_count':len(sources),'checks':checks})
 for src in sorted(work.rglob('*')):
  if not src.is_file():continue
  raw=src.read_bytes();out=archive/arm/src.relative_to(work)
  if len(raw)>20000:out=out.with_name(out.name+'.gz')
  out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(gzip.compress(raw,mtime=0) if out.suffix=='.gz' else raw);assert (gzip.decompress(out.read_bytes()) if out.suffix=='.gz' else out.read_bytes())==raw
  records.append({'source':str(src),'archive':str(out.relative_to(root)),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
a=json.loads((base/'a/work/calc-output.json').read_text());b=json.loads((base/'b/work/pp-output.json').read_text());expected=[[9,4,4,2,0,9,9,9,7,5],[8,8,0,7,0,9,9,7,5,3]];row_checks=[]
for i,values in enumerate(expected):
 ar=a['plans'][i]['rows'];br=b['plans'][i]['rows'];assert len(ar)==len(br)==10
 for j,value in enumerate(values):
  extra=0 if i==0 else 1
  assert ar[j]['current_after']==br[j]['after']['pp']==value
  assert ar[j]['extra_after']==extra
  assert br[j]['after']['extra_pp']==('used' if extra==0 else 'available')
  assert ar[j]['available_after']==br[j]['after']['available_pp']==value+extra
  assert br[j]['issue'] is None
  row_checks.append({'plan':i,'step':j+1,'current_pp':value,'unused_extra':extra,'available':value+extra,'both_match':True})
assert b['input']==json.loads((base/'b/work/pp-input.json').read_text())
result={'verified_at':datetime.now(timezone.utc).isoformat(),'workers_terminal':{'a':'native final received','b':{'process_session_id':5342,'exit_code':0}},'frozen_files_unchanged':len(proto['frozen_files']),'readbacks':readbacks,'row_checks':row_checks,'criteria_scope':'Exact 20 rows per method against source sequence. T9 start 9 is the internally consistent assumption explicitly qualified in both reports; same-start symbolic differences are also given. No hand/board/card effect/strength inference is approved.','archive_files':records}
(archive/'comparison-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print({'archived':len(records),'rows_per_arm':20,'readbacks':readbacks,'frozen':len(proto['frozen_files'])})
