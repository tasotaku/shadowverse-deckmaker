"""Single fixed-spec execution through the documented public CLI only."""
from pathlib import Path
import os,sys,json,hashlib,subprocess,time,datetime,platform
ROOT=Path(r'C:/Users/tasog/source/shadowverse-deckmaker')
OLD=ROOT/'output/max-baseline-worktree'
HERE=ROOT/'docs/evidence/turn-search-max/acceptance'
OUT=ROOT/'output/turn-search-max-acceptance'
PY=ROOT/'.venv/Scripts/python.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def env(version):
 e=os.environ.copy();e['PYTHONPATH']=str((OLD if version=='predecessor' else ROOT)/'src');return e
def remaining():return read(HERE/'journey.json')['deadline_monotonic']-time.monotonic()
def run(label,args,version='delivered'):
 if remaining()<=0:raise TimeoutError('journey deadline before '+label)
 start=now();t=time.monotonic();cwd=OLD if version=='predecessor' else ROOT
 cmd=[str(PY),'-X','utf8','-m','svdeck.battle_frontier_compare',*map(str,args)]
 with (HERE/(label+'.stdout.txt')).open('w',encoding='utf8') as out,(HERE/(label+'.stderr.txt')).open('w',encoding='utf8') as err:
  p=subprocess.Popen(cmd,cwd=cwd,env=env(version),stdout=out,stderr=err)
  evt={'label':label,'version':version,'command':cmd,'cwd':str(cwd),'PYTHONPATH':env(version)['PYTHONPATH'],'pid':p.pid,'start':start,'start_monotonic':t}
  with (HERE/'commands.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(evt)+'\n')
  try:
   if label.startswith(('medium-','hard-','small-','tiny')):
    from process_observer import wait
    code=wait(p,max(.001,remaining()),HERE/(label+'.processes.json'))
   else:code=p.wait(timeout=max(.001,remaining()))
  except (subprocess.TimeoutExpired,TimeoutError):
   # p is our still-owned launch handle; /T targets only this exact process tree.
   if p.poll() is None:subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
   code='budget'
  evt.update(end=now(),end_monotonic=time.monotonic(),external_monotonic_wall_seconds=time.monotonic()-t,exit_code=code)
  with (HERE/'commands.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(evt)+'\n')
 print(label,code,round(evt['external_monotonic_wall_seconds'],3),flush=True)
 if code=='budget':raise TimeoutError('journey deadline '+label)
 return evt
BASE=['--algorithms','native','--witness-samples','100','--max-states','100000000','--seconds','3600']
def preflight():
 assert not OUT.exists(), 'Output must be unused'
 pins=read(ROOT/'docs/evidence/turn-search-max/input-manifest.v1.json');checked=[]
 for entry in pins['inputs']+pins['fixtures']+pins['independent_oracle_inputs']+pins['historical_candidate_inputs']:
  actual=sha(ROOT/entry['path']);checked.append({**entry,'actual_sha256':actual,'matches':actual==entry['sha256']})
 save(HERE/'pinned-inputs.json',checked);assert all(x['matches'] for x in checked), 'Pinned input mismatch'
 versions={}
 for version,cwd in [('delivered',ROOT),('predecessor',OLD)]:
  provenance=subprocess.check_output([str(PY),'-X','utf8','-c',"import svdeck.battle_frontier_compare as m,sys,importlib.metadata,json;print(json.dumps({'module_file':m.__file__,'python':sys.version,'executable':sys.executable,'dependencies':{x:importlib.metadata.version(x) for x in ['numpy','numba','llvmlite']}}))"],cwd=cwd,env=env(version),text=True)
  versions[version]={'revision':subprocess.check_output(['git','-c','safe.directory='+str(cwd),'rev-parse','HEAD'],cwd=cwd,text=True).strip(),'provenance':json.loads(provenance),'source_hashes':{str(p.relative_to(cwd)):sha(p) for p in sorted((cwd/'src').rglob('*.py'))},'preexisting_jit_cache':[{'path':str(p.relative_to(cwd)),'size':p.stat().st_size,'mtime':p.stat().st_mtime} for p in sorted((cwd/'src').rglob('*.nb*'))]}
  assert Path(versions[version]['provenance']['module_file']).resolve().is_relative_to((cwd/'src').resolve())
 assert versions['predecessor']['revision']==pins['baseline_revision']
 save(HERE/'input-manifest.json',{'platform':platform.platform(),'processor':platform.processor(),'machine':platform.machine(),'versions':versions,'fixed_manifest_sha256':sha(ROOT/'docs/evidence/turn-search-max/input-manifest.v1.json'),'warmup_policy':'Existing disk caches preserved and recorded; exactly one automatic one-state warmup per case/version invocation; warmups excluded.','frozen_score':'Sum of two hard per-case medians from all three complete trials; delivered must be strictly lower; historical timing excluded.'})
 print('preflight complete',flush=True)
if __name__=='__main__':
 phase=sys.argv[1]
 if phase=='preflight':preflight()
 elif phase=='small':
  assert not OUT.exists();OUT.mkdir();t=time.monotonic();save(HERE/'journey.json',{'start':now(),'start_monotonic':t,'deadline_monotonic':t+3600,'deadline_minutes':60,'executor':'fresh-max-acceptance','competing_load':'Root reserved host after READY; no other benchmark/oracle/compile work. Root only reads/writes small metadata.'})
  run('help',['--help'])
  for version in ['delivered','predecessor']:
   run('small-'+version,['--cases',ROOT/'docs/evidence/turn-search-compare/independent-small-cases.v1.json','--output',OUT/('small-'+version),*BASE,'--trials','1','--debug-threshold','1000000','--load-note','Fresh max acceptance; host reserved; no other benchmark/oracle/compile work'],version)
 elif phase=='timings':
  subsets=[]
  for suite in ['medium','hard']:
   src=ROOT/f'docs/evidence/turn-search-compare/independent-{suite}-cases.v1.json';cases=read(src)
   for idx,case in enumerate(cases):
    casepath=HERE/f'{suite}-{idx}.json';save(casepath,[case]);subsets.append({'original':str(src),'original_sha256':sha(src),'index':idx,'case':case['id'],'subset':str(casepath),'subset_sha256':sha(casepath),'all_case_values_equal':read(casepath)==[case]});save(HERE/'subsets.json',subsets)
    order=(['predecessor','delivered'] if idx%2==0 else ['delivered','predecessor']) if suite=='medium' else (['delivered','predecessor'] if idx==0 else ['predecessor','delivered'])
    for version in order:
     run(f'{suite}-{idx}-{version}',['--cases',casepath,'--output',OUT/f'{suite}-{idx}-{version}',*BASE,'--trials','3','--debug-threshold','0','--load-note','Exclusive reserved host; fixed case-level version alternation; no concurrent workers'],version)
