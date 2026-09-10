import os,sys,subprocess,json,shutil,hashlib,gzip,tarfile
from pathlib import Path
from typing import Any
from datetime import datetime,timezone
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');base=Path('/tmp/sv-burden-revision-01');a=root/'evals/discovery/burden-revision-01';py='/tmp/sv-system-venv/bin/python';env={**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONDONTWRITEBYTECODE':'1'}
arm,handle,exit_code=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]);assert arm in ('a','b');rb=base/arm/'review';w=rb/'work';s=w/'session';out=a/arm/'review';assert not (out/'collection.json').exists();started=datetime.now(timezone.utc).isoformat()
def save(p: Path,d: Any) -> None:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p: Path) -> str:return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(src: Path,dst: Path) -> None:
 if dst.exists():assert src.read_bytes()==dst.read_bytes(),dst
 else:dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
run=json.loads((rb/'run/run.json').read_text());assert run['status']!='running' and run['runner_returncode']==exit_code
initial=json.loads((a/arm/'review/initial-files.json').read_text());manifest_equal=json.loads((w/'initial-files.json').read_text())==initial;assert all(sha(s/name)==digest for name,digest in initial.items())
reviews=sorted(p for p in s.glob('review-*.json') if p.name not in initial)
assert not [p for p in s.glob('revision-*.json') if p.name not in initial],'reviewer wrote a proposal'
assert len(reviews)<=1,'more than one new independent review'
save(out/'run.json',run);save(out/'terminal.json',{'session_id':handle,'exit_code':exit_code,'confirmed_via':'write_stdin','collected_at':started})
ops=[]
for p in (w/'operations').glob('operation-*.json'):
 d=json.loads(p.read_text());f=Path(d['output']);ops.append({**d,'stdout':f.read_text() if f.exists() else None})
ops.sort(key=lambda d:d['started_at']);(out/'public-operations.json.gz').write_bytes(gzip.compress((json.dumps(ops,ensure_ascii=False,indent=2)+'\n').encode()))
for name in ('review.json','evaluation.md','web-checks.json','submission-verification.json','resource-check.json','evidence-use.json','review-verification.json'):
 if (w/name).exists():copy(w/name,out/name)
durable=root/'data/discovery'/f'burden-revision-01-{arm}'
for p in s.rglob('*'):
 if p.is_file():copy(p,durable/p.relative_to(s))
for p in reviews:copy(p,out/p.name)
report=json.loads(subprocess.check_output([py,'-m','svdeck.discovery','report',str(durable)],env=env));save(out/'report.json',report)
fields=[];decisions=[];draft_equal=None;draft_error=None
if reviews:
 formal=json.loads(reviews[0].read_text())['data'];matching=[v for r in report['revisions'] for v in r['reviews'] if all(v.get(k)==z for k,z in formal.items())];assert len(matching)==1
 fields=list(formal);decisions=[{k:formal[k] for k in ('procedure','value','novelty')}]
 if (w/'review.json').exists():
  try:
   submitted=json.loads((w/'review.json').read_text())
  except (OSError,json.JSONDecodeError) as error:
   draft_error=str(error)
  else:
   if not isinstance(submitted,dict):draft_error='下書きがJSONオブジェクトでない'
   else:
    draft_equal=submitted=={k:v for k,v in formal.items() if k not in ('revision','proposal_hash')}
archive=root/'data/discovery-archives/burden-revision-01'/f'final-{arm}.tar.gz';assert not archive.exists();files={p.relative_to(durable).as_posix():p for p in durable.rglob('*') if p.is_file()}
with tarfile.open(archive,'w:gz') as t:
 for name,p in sorted(files.items()):t.add(p,arcname=name,recursive=False)
with tarfile.open(archive,'r:gz') as t:
 assert {m.name for m in t if m.isfile()}==set(files)
 for name,p in files.items():
  member=t.extractfile(name);assert member is not None;assert member.read()==p.read_bytes()
mainhash=sha(root/'data/cards.db');assert mainhash==json.loads((a/'protocol.json').read_text())['main_db_sha256']
result={'collection_started_at':started,'collection_ended_at':datetime.now(timezone.utc).isoformat(),'arm':arm,'worker_status':run['status'],'exit_code':exit_code,'started_at':run['started_at'],'ended_at':run['ended_at'],'elapsed_seconds':run['elapsed_seconds'],'utc_elapsed_seconds':(datetime.fromisoformat(run['ended_at'])-datetime.fromisoformat(run['started_at'])).total_seconds(),'initial_files_unchanged':len(initial),'public_calls':len(ops),'failed_calls':[{'command':o['command'],'exit_code':o.get('exit_code')} for o in ops if o.get('exit_code') not in (0,None)],'new_formal_reviews':len(reviews),'total_formal_reviews':len(list(s.glob('review-*.json'))),'working_manifest_equal_frozen':manifest_equal,'latest_draft_equal_formal':draft_equal,'latest_draft_read_error':draft_error,'formal_fields_equal_public_report':fields,'decisions':decisions,'durable_session':str(durable),'archive':{'path':str(archive.relative_to(root)),'sha256':sha(archive),'verified_files':len(files)},'main_db_sha256':mainhash};save(out/'collection.json',result);print(json.dumps(result,ensure_ascii=False))
