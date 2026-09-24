import subprocess,time,json,datetime,pathlib,ctypes
root=pathlib.Path.cwd(); out=root/'docs/evidence/battle-lookahead/user-tests/final-t1'
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
start=time.perf_counter(); started=utc()
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(PMC),ctypes.c_ulong]
def run(name,args,output=None):
 if output and pathlib.Path(output).exists(): raise RuntimeError('Existing output '+output)
 begin=time.perf_counter(); peak=0; timeout=False
 with (out/(name+'.stdout.txt')).open('w',encoding='utf-8') as so,(out/(name+'.stderr.txt')).open('w',encoding='utf-8') as se:
  p=subprocess.Popen(args,stdout=so,stderr=se)
  while p.poll() is None:
   pm=PMC(); pm.cb=ctypes.sizeof(pm)
   if ctypes.windll.psapi.GetProcessMemoryInfo(int(p._handle),ctypes.byref(pm),pm.cb): peak=max(peak,pm.PeakWorkingSetSize)
   if time.perf_counter()-begin>30: timeout=True; p.kill(); break
   time.sleep(.005)
  p.wait()
 elapsed=time.perf_counter()-begin
 rec=dict(id=name,argv=args,pid=p.pid,exit_code=p.returncode,elapsed_seconds=elapsed,peak_working_set_bytes_observed=peak,timeout=timeout,output_exists=pathlib.Path(output,'report.json').exists() if output else None,process_exited=True)
 print(json.dumps(rec),flush=True); return rec
records=[run('help',['.venv/Scripts/python.exe','-X','utf8','-m','svdeck.battle_lookahead','--help'])]
manifest=json.load(open('docs/evidence/battle-lookahead/acceptance-inputs/manifest.json',encoding='utf-8'))
for call in manifest['T1']['cli']:
 records.append(run(call['id'],[a.replace('NEW','final-t1') for a in call['argv']],call['output'].replace('NEW','final-t1')))
raw=dict(started_at=started,analysis_finished_at=utc(),journey_start_perf=start,analysis_elapsed_seconds=time.perf_counter()-start,records=records,analysis_calls=4,manual_surface_switches=0,clicks=0,scrolls=0,method='Dedicated subprocesses; perf_counter; Windows GetProcessMemoryInfo sampled 5ms; only owned process killed on timeout')
(out/'raw.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
