from pathlib import Path
import os,sys,json,hashlib,subprocess,time,datetime,platform
ROOT=Path(r'C:/Users/tasog/source/shadowverse-deckmaker')
OLD=Path(r'C:/Users/tasog/source/shadowverse-speed-predecessor')
HERE=ROOT/'docs/evidence/turn-search-speed/acceptance-v2'
OUT=ROOT/'output/turn-search-speed-acceptance-v2'
PY=ROOT/'.venv/Scripts/python.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def env(version):
 e=os.environ.copy();e['PYTHONPATH']=str((OLD if version=='predecessor' else ROOT)/'src');return e
def run(label,args,version='delivered'):
 start=now();t=time.perf_counter();cwd=OLD if version=='predecessor' else ROOT
 cmd=[str(PY),'-X','utf8','-m','svdeck.battle_frontier_compare',*map(str,args)]
 with (HERE/(label+'.stdout.txt')).open('w',encoding='utf8') as out,(HERE/(label+'.stderr.txt')).open('w',encoding='utf8') as err:
  p=subprocess.Popen(cmd,cwd=cwd,env=env(version),stdout=out,stderr=err)
  evt={'label':label,'version':version,'command':cmd,'cwd':str(cwd),'PYTHONPATH':env(version)['PYTHONPATH'],'pid':p.pid,'start':start}
  with (HERE/'commands.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(evt)+'\n')
  try:
   if label.startswith(('medium-','hard-')):
    from process_observer import wait
    code=wait(p,max(1,2700-(time.time()-read(HERE/'journey.json')['epoch'])),HERE/(label+'.processes.json'))
   else:code=p.wait(timeout=max(1,2700-(time.time()-read(HERE/'journey.json')['epoch'])))
  except (subprocess.TimeoutExpired,TimeoutError):
   subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True);code='budget'
  evt.update(end=now(),external_monotonic_wall_seconds=time.perf_counter()-t,exit_code=code)
  with (HERE/'commands.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(evt)+'\n')
 print(label,code,round(evt['external_monotonic_wall_seconds'],3),flush=True)
 return evt
BASE=['--algorithms','native','--witness-samples','100','--max-states','100000000','--seconds','3600']
if __name__=='__main__':
 phase=sys.argv[1]
 if phase=='small':
  assert not OUT.exists();OUT.mkdir();save(HERE/'journey.json',{'start':now(),'epoch':time.time(),'deadline_minutes':45,'executor':'fresh-speed-acceptance-v2','competing_load':'Root reserved host; previous executor processes exited; root only reads/writes small metadata.'})
  pins=read(ROOT/'docs/evidence/turn-search-speed/fixture-manifest.v1.json');checked=[]
  for entry in pins['fixtures']+pins['supporting_historical_artifacts']:
   actual=sha(ROOT/entry['path']);checked.append({**entry,'actual_sha256':actual,'matches':actual==entry['sha256']})
  save(HERE/'pinned-inputs.json',checked);assert all(x['matches'] for x in checked)
  versions={}
  for version,cwd in [('delivered',ROOT),('predecessor',OLD)]:
   provenance=subprocess.check_output([str(PY),'-X','utf8','-c',"import svdeck.battle_frontier_compare as m,sys,importlib.metadata,json;print(json.dumps({'module_file':m.__file__,'python':sys.version,'executable':sys.executable,'dependencies':{x:importlib.metadata.version(x) for x in ['numpy','numba','llvmlite']}}))"],cwd=cwd,env=env(version),text=True)
   versions[version]={'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=cwd,text=True).strip(),'provenance':json.loads(provenance),'source_hashes':{str(p.relative_to(cwd)):sha(p) for p in sorted((cwd/'src').rglob('*.py'))},'preexisting_jit_cache':[{'path':str(p.relative_to(cwd)),'size':p.stat().st_size,'mtime':p.stat().st_mtime} for p in sorted((cwd/'src').rglob('*.nb*'))]}
  save(HERE/'input-manifest.json',{'platform':platform.platform(),'processor':platform.processor(),'machine':platform.machine(),'versions':versions,'fixture_manifest_sha256':sha(ROOT/'docs/evidence/turn-search-speed/fixture-manifest.v1.json'),'warmup_policy':'Existing disk caches preserved; exactly one automatic one-state warmup per case/version invocation; warmups excluded.'})
  run('help',['--help'])
  run('small',['--cases',ROOT/pins['fixtures'][0]['path'],'--output',OUT/'small',*BASE,'--trials','1','--debug-threshold','1000000','--load-note','Fresh v2; host reserved; no other benchmark/oracle/compile work'])
 elif phase=='timings':
  for suite,count,trials in [('medium',3,3),('hard',2,1)]:
   src=ROOT/f'docs/evidence/turn-search-compare/independent-{suite}-cases.v1.json';cases=read(src)
   for idx,case in enumerate(cases):
    casepath=HERE/f'{suite}-{idx}.json';save(casepath,[case])
    order=(['predecessor','delivered'] if idx%2==0 else ['delivered','predecessor']) if suite=='medium' else (['delivered','predecessor'] if idx==0 else ['predecessor','delivered'])
    for version in order:
     run(f'{suite}-{idx}-{version}',['--cases',casepath,'--output',OUT/f'{suite}-{idx}-{version}',*BASE,'--trials',str(trials),'--debug-threshold','0','--load-note','Exclusive reserved host; v2 fixed case-level version alternation; no concurrent workers'],version)
