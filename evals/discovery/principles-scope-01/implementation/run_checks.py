import json, os, subprocess, sys
from datetime import datetime,timezone
from pathlib import Path
root=Path('/tmp/sv-principles-scope-prototype')
out=Path('/tmp/sv-principles-scope-implementation')
commands=[('mypy-strict',[sys.executable,'-m','mypy','--strict','--follow-imports=silent',*[f'src/svdeck/{s}.py' for s in ['discovery','discovery_principles','discovery_evidence','discovery_read','discovery_sources','discovery_compare']]]),
 ('pytest-discovery',[sys.executable,'-m','pytest','-q',*[f'tests/{s}' for s in ['test_discovery.py','test_discovery_read.py','test_discovery_history.py','test_discovery_sources.py','test_discovery_compare.py','test_discovery_review_contexts.py']], 'tests/temp/test_discovery_principles_scope_temp.py','--basetemp',str(out/'pytest-temp')])]
records=[]
for name,cmd in commands:
 begin=datetime.now(timezone.utc).isoformat()
 result=subprocess.run(cmd,cwd=root,env=dict(os.environ,PYTHONPATH='src:tests'),text=True,capture_output=True)
 (out/(name+'.log')).write_text(result.stdout+result.stderr)
 records.append({'name':name,'command':cmd,'started_at_utc':begin,'ended_at_utc':datetime.now(timezone.utc).isoformat(),'returncode':result.returncode,'log':name+'.log'})
 print(json.dumps(records[-1]))
 print(result.stdout+result.stderr)
 (out/'check-commands.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
 if result.returncode: raise SystemExit(result.returncode)
