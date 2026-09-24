import json,hashlib,os,subprocess,sys,time,platform
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path.cwd(); HERE=ROOT/'docs/evidence/turn-search-speed/acceptance'; OUT=ROOT/'output/turn-search-speed-acceptance'; PY=ROOT/'.venv/Scripts/python.exe'; PRE=ROOT.parent/'shadowverse-speed-predecessor'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
manifest=json.loads((HERE.parent/'fixture-manifest.v1.json').read_text())
checks=[]
for x in manifest['fixtures']+manifest['supporting_historical_artifacts']:
 p=ROOT/x['path']; got=sha(p); checks.append(dict(x,actual_sha256=got,match=got==x['sha256']))
assert all(x['match'] for x in checks)
inputs=[HERE.parent/'spec.v1.json',HERE.parent/'spec.v1.lock.json',HERE.parent/'fixture-manifest.v1.json',ROOT/'docs/battle-frontier.md',ROOT/'docs/battle-frontier-compare.md',ROOT/'docs/evidence/turn-search-compare/acceptance-t1/consume.py',ROOT/'docs/evidence/turn-search-compare/acceptance-t1/public-followup.py']
roles={'executor_id':'fresh-speed-acceptance','role':'Fresh independent executor; no production source/diff or prior verdict read','inputs':[{'path':str(p),'sha256':sha(p)} for p in inputs],'pinned_checks':checks,'started_at':datetime.now(timezone.utc).isoformat(),'host_release':'Explicit root host release; no competing benchmark/oracle/compile workers','budget_minutes':45,'ordinary_product_invocations':[{'command':str(PY)+' -X utf8 -m svdeck.battle_frontier_compare --help','observed':'CLI help read; exit 0'}]}
for label,checkout in [('delivered',ROOT),('predecessor',PRE)]:
 env=dict(os.environ,PYTHONPATH=str(checkout/'src'))
 code='import json,svdeck.battle_frontier_compare as x,sys;print(json.dumps({"module_file":x.__file__,"python":sys.version,"executable":sys.executable}))'
 r=subprocess.run([str(PY),'-X','utf8','-c',code],env=env,cwd=checkout,capture_output=True,text=True,check=True)
 roles[label]={'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip(),'import':json.loads(r.stdout),'source_hashes':{str(p.relative_to(checkout)):sha(p) for p in sorted((checkout/'src/svdeck').glob('*.py'))},'cache_before': [{'path':str(p),'size':p.stat().st_size} for p in (checkout/'src/svdeck/__pycache__').glob('*.nb*')]}
save(HERE/'role-input-manifest.json',roles)
cmd=[str(PY),'-X','utf8','-m','svdeck.battle_frontier_compare','--cases',str(ROOT/'docs/evidence/turn-search-compare/independent-small-cases.v1.json'),'--output',str(OUT/'small'),'--algorithms','native','--trials','1','--seconds','3600','--max-states','100000000','--debug-threshold','1000000','--witness-samples','100','--load-note','Reserved host; fresh independent executor; no competing benchmark/oracle/compile']
start=time.perf_counter()
with (HERE/'small.stdout.txt').open('w',encoding='utf8') as o,(HERE/'small.stderr.txt').open('w',encoding='utf8') as e:r=subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,PYTHONPATH=str(ROOT/'src')),stdout=o,stderr=e)
roles['ordinary_product_invocations'].append({'command':subprocess.list2cmdline(cmd),'returncode':r.returncode,'external_wall_seconds':time.perf_counter()-start});save(HERE/'role-input-manifest.json',roles)
print('small finished',r.returncode,flush=True)
