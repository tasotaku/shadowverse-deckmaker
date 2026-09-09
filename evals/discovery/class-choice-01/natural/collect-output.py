"""Collect a terminal worker's selected public session; root verifies the agent handle first."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,subprocess,os,hashlib,gzip
parser=argparse.ArgumentParser();parser.add_argument('arm',choices=['a','b']);parser.add_argument('round',type=int);parser.add_argument('session',type=Path);parser.add_argument('--phase',choices=['generation','review'],required=True);args=parser.parse_args()
base=Path('/tmp/sv-class-choice-01');code=Path('/tmp/sv-class-choice-prototype');root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');out=base/(args.arm+'-work')/f'round-{args.round}';out.mkdir(parents=True,exist_ok=True)
index=json.loads((base/(args.arm+'-session-index.json')).read_text());assert str(args.session) in [v['session'] for v in index.values()]
manifest=json.loads((base/'manifest.json').read_text());changed=[p for p,h in manifest['files'].items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h];assert not changed,changed
cmd=['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery'];env={**os.environ,'PYTHONPATH':str(code/'src')}
result=subprocess.run(cmd+['report',str(args.session)],cwd=code,env=env,capture_output=True,text=True,check=True);report=json.loads(result.stdout);(out/('root-'+args.phase+'-report.json')).write_text(result.stdout)
context=json.loads((args.session/'context.json').read_text());checks=[]
for revision in report['revisions']:
 for review in revision['reviews']:
  packet=json.loads((args.session/'packets'/(review['packet_hash']+'.json')).read_text());assert packet['data']['context_hash']==context['sha256'];assert packet['data']['context']==context['data'];assert packet['data']['stage']=='review'
  checks.append({'revision':revision['revision'],'review_hash':hashlib.sha256(json.dumps(review,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'packet_hash':review['packet_hash']})
summary={'collected_at':datetime.now(timezone.utc).isoformat(),'arm':args.arm,'round':args.round,'phase':args.phase,'session':str(args.session),'fixed_files_unchanged':len(manifest['files']),'formal_count':len(report['revisions']),'review_count':len(checks),'source_count':len(report['sources']),'review_context_checks':checks,'limits':'Identity and public report collection only. Root verifies terminal agent status and assesses semantic evidence separately.'}
(out/('collection-'+args.phase+'.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))
