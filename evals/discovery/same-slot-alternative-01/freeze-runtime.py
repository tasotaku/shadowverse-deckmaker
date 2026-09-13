from pathlib import Path
from datetime import datetime, timezone
import hashlib, io, json, subprocess, tarfile
from svdeck.discovery_run import manifest
from svdeck.journal_store import Journal
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');e=root/'evals/discovery/same-slot-alternative-01'
implementation=json.loads((e/'implementation.json').read_text());protocol=json.loads((e/'protocol.json').read_text());assert implementation['verdict']=='PASS'
started=datetime.now(timezone.utc).isoformat();result={}
for side,commit in [('a',protocol['base_commit']),('b',implementation['commit'])]:
 destination=Path('/tmp/sv-same-slot-alternative-01-'+side+'-launch');destination.mkdir(exist_ok=False);runtime=destination/'runtime';runtime.mkdir()
 data=subprocess.check_output(['git','archive',commit,'src'],cwd=root)
 with tarfile.open(fileobj=io.BytesIO(data)) as tar:
  for member in tar.getmembers():
   assert not member.issym() and not member.islnk();relative=Path(member.name);assert '..' not in relative.parts and relative.parts[0]=='src'
   if member.isfile():
    out=runtime.joinpath(*relative.parts[1:]);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(tar.extractfile(member).read())
 result[side]={'runtime':str(runtime),'commit':commit,'manifest':manifest(runtime)}
 (e/(side+'-runtime.json')).write_text(json.dumps(result[side],ensure_ascii=False,indent=2)+'\n')
a,b=result['a']['manifest'],result['b']['manifest'];assert a.keys()==b.keys();differences=[n for n in a if a[n]!=b[n]];assert differences==['svdeck/discovery.py'];source=Path(json.loads((e/'preparation.json').read_text())['source']);assert manifest(source)==json.loads((e/'preparation.json').read_text())['manifest']
proof={'started_at':started,'ended_at':datetime.now(timezone.utc).isoformat(),'only_runtime_differences':differences,'common_input_unchanged':True,'source':str(source),'develop_seconds':900,'review_seconds':600,'revision':1,'repeat_count':1,'explicit_finish':True,'model_override':None,'journal_root':str(root),'experiment_id':e.name,'runtime_files':['a-runtime.json','b-runtime.json']}
(e/'launch-settings.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n');print(proof)
