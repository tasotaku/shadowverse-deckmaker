import json,time,subprocess,sys,urllib.request,datetime,ctypes,ctypes.wintypes as wt
from pathlib import Path
from svdeck.battle import Battle
D=Path('docs/evidence/battle-lookahead/user-tests/final-t2'); RAW=D/'raw';RAW.mkdir()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
manifest=json.loads(Path('docs/evidence/battle-lookahead/acceptance-inputs/manifest.json').read_text(encoding='utf-8-sig'))['T2']
log={'started_at':now(),'start_monotonic':time.monotonic(),'calls':[],'manual_surface_switches':0,'clicks':0,'keys':0,'scrolls':0,'channel':'PowerShell public CLI/HTTP; no foreground UI interactions'}
save(D/'trial.json',log)
a,b=[json.loads(Path('docs/evidence/battle-lookahead/acceptance-inputs/api-'+c+'.json').read_text(encoding='utf-8-sig')) for c in 'ab']
ba,bb=[Battle(p['record']['initial'],p['record']['cards']) for p in [a,b]]
sa,sb=ba.state,bb.state
checks={'same_public_observation':ba.observation(0)==bb.observation(0),'options_equal':a['options']==b['options'],'enemy_hand_different':sa['players'][1]['hand']!=sb['players'][1]['hand'],'both_deck_orders_different':[sa['players'][i]['deck']!=sb['players'][i]['deck'] for i in range(2)],'rng_different':sa['rng']!=sb['rng'],'observation':ba.observation(0)}
save(D/'input-checks.json',checks)
assert checks['same_public_observation'] and checks['options_equal']
class PMC(ctypes.Structure):
 _fields_=[('cb',wt.DWORD),('PageFaultCount',wt.DWORD)]+[(n,ctypes.c_size_t) for n in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
getmem=ctypes.windll.psapi.GetProcessMemoryInfo
getmem.argtypes=[wt.HANDLE,ctypes.POINTER(PMC),wt.DWORD]
def cli(entry):
 argv=[v.replace('NEW','final-t2') for v in entry['argv']];begin=time.monotonic();r={'id':entry['id'],'argv':argv,'started_at':now()};peak=0
 with (RAW/(entry['id']+'.stdout')).open('w',encoding='utf-8') as out,(RAW/(entry['id']+'.stderr')).open('w',encoding='utf-8') as err:
  p=subprocess.Popen(argv,stdout=out,stderr=err)
  while p.poll() is None:
   mem=PMC();mem.cb=ctypes.sizeof(mem)
   if getmem(wt.HANDLE(int(p._handle)),ctypes.byref(mem),mem.cb):peak=max(peak,mem.PeakWorkingSetSize)
   if time.monotonic()-begin>=30:p.kill();r['timeout']=True;break
   time.sleep(.01)
  p.wait()
 r.update(elapsed_seconds=time.monotonic()-begin,returncode=p.returncode,peak_working_set_bytes=peak,output=entry['output'].replace('NEW','final-t2'));log['calls'].append(r);save(D/'trial.json',log);print(r,flush=True)
def api(entry):
 begin=time.monotonic();r={'id':entry['id'],'started_at':now(),'url':entry['url'],'payload':entry['payload']}
 try:
  req=urllib.request.Request(entry['url'],data=Path(entry['payload']).read_bytes(),headers={'Content-Type':'application/json'},method='POST')
  with urllib.request.urlopen(req,timeout=30) as response:r['http_status']=response.status;data=response.read()
  (RAW/(entry['id']+'.json')).write_bytes(data)
 except Exception as exc:r['error']=str(exc)
 r['elapsed_seconds']=time.monotonic()-begin;log['calls'].append(r);save(D/'trial.json',log);print(r,flush=True)
cli(manifest['cli'][0])
for entry in manifest['api']:api(entry)
for entry in manifest['cli'][1:]:cli(entry)
log['calls_finished_at']=now();log['call_phase_seconds']=time.monotonic()-log['start_monotonic'];save(D/'trial.json',log)
