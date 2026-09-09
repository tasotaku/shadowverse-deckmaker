"""Collect a worker only after root has observed its terminal tool result."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, subprocess, os, hashlib
p=argparse.ArgumentParser();p.add_argument('case',choices=['elf','nightmare']);p.add_argument('arm',choices=['a','b']);p.add_argument('--round',type=int,default=1);p.add_argument('--phase',choices=['generation','review'],required=True);p.add_argument('--terminal-evidence',type=Path,required=True);a=p.parse_args()
base=Path('/tmp/sv-principles-scope-01');code=Path('/tmp/sv-principles-scope-prototype');session=base/a.case/a.arm/'session';out=base/a.case/a.arm/'work'/f'round-{a.round}'
terminal=json.loads(a.terminal_evidence.read_text());assert terminal['case']==a.case and terminal['arm']==a.arm and terminal['phase']==a.phase and terminal['round']==a.round
assert terminal['terminal'] is True
manifest=json.loads((base/'manifest.json').read_text());changed=[s for s,h in manifest['files'].items() if hashlib.sha256(Path(s).read_bytes()).hexdigest()!=h];assert not changed,changed
cmd=['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery','report',str(session)]
result=subprocess.run(cmd,cwd=code,env={**os.environ,'PYTHONPATH':str(code/'src'),'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,check=True)
report=json.loads(result.stdout);(out/f'root-{a.phase}-report.json').write_text(result.stdout)
context=json.loads((session/'context.json').read_text());checks=[]
for revision in report['revisions']:
 for review in revision['reviews']:
  packet=json.loads((session/'packets'/(review['packet_hash']+'.json')).read_text())
  assert packet['data']['context_hash']==context['sha256'] and packet['data']['context']==context['data'] and packet['data']['stage']=='review'
  checks.append({'revision':revision['revision'],'packet_hash':review['packet_hash']})
summary={'collected_at':datetime.now(timezone.utc).isoformat(),'case':a.case,'arm':a.arm,'round':a.round,'phase':a.phase,'terminal_evidence':str(a.terminal_evidence),'fixed_files_unchanged':len(manifest['files']),'formal_count':len(report['revisions']),'review_count':len(checks),'source_count':len(report['sources']),'review_context_checks':checks,'limits':'Public report and input identity verification only; semantic evaluation is separate.'}
(out/f'collection-{a.phase}.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))
