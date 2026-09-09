import json, os, subprocess, sys
from datetime import datetime,timezone
from pathlib import Path
root=Path('/tmp/sv-principles-scope-prototype')
out=Path('/tmp/sv-principles-scope-implementation')
sys.path[:0]=[str(root/'src'),str(root/'tests')]
from test_discovery import make_db,proposal,assessment
base=out/'legacy-before'
db=out/'synthetic.db'
make_db(db)
env=dict(os.environ,PYTHONPATH=str(root/'src'))
records=[]
def run(name,args):
 begin=datetime.now(timezone.utc).isoformat()
 cmd=[sys.executable,'-m','svdeck.discovery',*args]
 r=subprocess.run(cmd,cwd=root,env=env,text=True,capture_output=True)
 (out/(name+'.json')).write_text(r.stdout)
 records.append({'phase':'baseline','command':cmd,'started_at_utc':begin,'ended_at_utc':datetime.now(timezone.utc).isoformat(),'returncode':r.returncode,'output_file':name+'.json','stderr':r.stderr})
 (out/'baseline-commands.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
 assert r.returncode==0,r.stderr
 return json.loads(r.stdout)
run('baseline-start',['start',str(base),'--db',str(db),'--class','ウィッチ','--objective','合成資料の保存互換性を検査'])
p=run('baseline-develop',['packet',str(base),'--revision','0'])
run('baseline-summary',['packet',str(base),'--revision','0','--summary'])
run('baseline-principles-read',['read',str(base),p['sha256'],'principles','--limit','2000'])
answer=out/'baseline-proposal.json'
answer.write_text(json.dumps(proposal(p),ensure_ascii=False))
run('baseline-submit',['submit',str(base),str(answer)])
p=run('baseline-review-packet',['packet',str(base),'--revision','1','--stage','review'])
answer=out/'baseline-review.json'
answer.write_text(json.dumps(assessment(p),ensure_ascii=False))
run('baseline-review-result',['review',str(base),str(answer)])
run('baseline-report',['report',str(base)])
manifest={str(p.relative_to(base)):__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in base.rglob('*') if p.is_file()}
(out/'legacy-before-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'public_commands':len(records),'successes':sum(r['returncode']==0 for r in records),'saved_session_files':len(manifest),'completed_at_utc':datetime.now(timezone.utc).isoformat()}))
