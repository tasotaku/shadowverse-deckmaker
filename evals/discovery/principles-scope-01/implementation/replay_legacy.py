import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
root=Path('/tmp/sv-principles-scope-prototype')
out=Path('/tmp/sv-principles-scope-implementation')
folder=out/'legacy-before'
key=json.load(open(out/'baseline-develop.json'))['sha256']
checks=[('baseline-develop',['packet',str(folder),'--revision','0']),('baseline-summary',['packet',str(folder),'--revision','0','--summary']),('baseline-principles-read',['read',str(folder),key,'principles','--limit','2000']),('baseline-review-packet',['packet',str(folder),'--revision','1','--stage','review']),('baseline-report',['report',str(folder)])]
records=[]
for label,args in checks:
 begin=datetime.now(timezone.utc).isoformat()
 cmd=[sys.executable,'-m','svdeck.discovery',*args]
 r=subprocess.run(cmd,cwd=root,env=dict(os.environ,PYTHONPATH='src'),text=True,capture_output=True)
 match=r.stdout==(out/(label+'.json')).read_text()
 records.append({'command':cmd,'started_at_utc':begin,'ended_at_utc':datetime.now(timezone.utc).isoformat(),'returncode':r.returncode,'stdout_bytes_identical_to_baseline':match,'baseline':label+'.json'})
 assert r.returncode==0 and match,(label,r.stderr)
current={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
assert current==json.load(open(out/'legacy-before-manifest.json'))
result={'commands':records,'success_count':len(records),'legacy_stdout_identical':True,'legacy_session_files_unchanged':True,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
(out/'legacy-compatibility.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='commands'},ensure_ascii=False))
