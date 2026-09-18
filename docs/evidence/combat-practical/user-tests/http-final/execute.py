import json,sys,time,platform,ctypes,urllib.request,urllib.error,datetime
from pathlib import Path
from fractions import Fraction
from svdeck.battle import Battle
from svdeck import combat_benchmark as bench
out=Path('docs/evidence/combat-practical/user-tests/http-final')
def save(name,data):
 (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
oracle={
'random-half-anchor':{'win':'1/2','derivation':'Only r first can win: uniform target g removes ward allowing a to hit face, target d leaves ward and sole attack cannot both clear ward and hit face. Each branch has probability 1/2. Attacking ward first spends a and cannot win.','first':{'type':'play','card':'r'}},
'random-two-ward-adaptive-anchor':{'win':'1','derivation':'r uniformly kills left or right (1/2 each); a1 or a2 must attack observed surviving ward; other hits face. No random outcome exceeds 1 and this achieves 1. An attack before r can also guarantee victory; whichever policy is returned must obey observed state.'},
'slot-pp-evolve':{'win':'1','derivation':'Full board blocks runner; expensive costs2 with1PP; idle attackers spent. Small attacks guard and both die, opening slot. Runner costs1, base attack2 plus normal evolve2 plus effect1 =5; storm permits face lethal. Evolving small first retains full board after defeating guard, preventing runner, so cannot reach 5 face damage.','first':{'type':'attack','source':'small','target':'g'}},
'split-oldest-first':{'win':'1','derivation':'Board chronology is old then new although lexical new comes first. Split3 first allocates all3 to old barrier: neither damaged, barrier removed, remaining ping1 cannot kill old3. Ping old first removes barrier then split3 kills old; a hits face4.','first':{'type':'play','card':'ping','target':'old'}},
'objective-preserve-versus-win-lethal':{'win':'1','value':'20','derivation':'Only attacks available; either ally kills ward but dies to20 retaliation. Sacrificing face leaves big health20 and1 face lethal. Sacrificing big leaves health1. With own_board_health1 and all others0, lethal optimum (1,20).','first':{'type':'attack','source':'face','target':'guard'}},
'objective-preserve-versus-win-value':{'win':'0','value':'21','derivation':'Stop preserves20+1=21 health. Any attack loses at least1 health body, maximum afterwards20. Value optimum21 by stopping; enemy leader remains1 so win0.','first':None},
'bounded':{'derivation':'max_states1 cannot finish half fixture: complete and optimal must be false, cutoff reason states.'},
'invalid':{'derivation':'max_states0 outside documented1..50000 range; HTTP400 error should name max_states.'},
'recovery':{'win':'0','derivation':'No own board or hand or evolution resources; stop only; both leaders alive.'},
'legacy':{'derivation':'cheap-trade own2/1+3/1 versus enemy1/2. Sacrifice2/1 trades and leaves3/1; sacrificing3/1 leaves2/1 and is dominated. Required clear survivor3/1.'}}
save('independent-oracles.json',oracle)
save('runtime.json',{'python':sys.executable,'version':sys.version,'platform':platform.platform(),'pid_serving':16500,'started_before_discovery':'2026-09-18T01:06:28Z'})
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(x,ctypes.c_size_t) for x in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];k.OpenProcess.restype=ctypes.c_void_p
k.CloseHandle.argtypes=[ctypes.c_void_p];p.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(PMC),ctypes.c_ulong]
h=k.OpenProcess(0x410,False,16500)
def mem():
 c=PMC();c.cb=ctypes.sizeof(c)
 if not p.GetProcessMemoryInfo(h,ctypes.byref(c),c.cb): return {'error':ctypes.get_last_error()}
 return {'peak_rss_bytes':c.PeakWorkingSetSize,'memory_scope':'serving process lifetime peak including earlier requests','memory_method':'Windows GetProcessMemoryInfo PeakWorkingSetSize'}
log=[]
def call(name,route,payload=None):
 start=time.perf_counter(); raw=None
 if payload is not None: save(name+'.request.json',payload)
 req=urllib.request.Request('http://127.0.0.1:8767'+route,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=60) as resp: status=resp.status;raw=resp.read();headers=dict(resp.headers)
 except urllib.error.HTTPError as e: status=e.code;raw=e.read();headers=dict(e.headers)
 elapsed=time.perf_counter()-start
 (out/(name+'.response.txt')).write_bytes(raw)
 try: data=json.loads(raw)
 except ValueError:data={'text':raw.decode('utf-8')}
 entry={'name':name,'route':route,'status':status,'elapsed_seconds':elapsed,'memory':mem(),'headers':headers}
 if isinstance(data,dict):entry.update({x:data.get(x) for x in ['objective','complete','optimal','cutoffs','stats','win_probability_exact','expected_value_exact','recommended_action']})
 log.append(entry);save('requests.json',log)
 return status,data
status,ready=call('readiness','/')
cs={c['id']:c for c in json.loads(Path('tests/fixtures/combat_practical_cases.json').read_text(encoding='utf-8'))}
weights=dict.fromkeys(['leader','attack','health','body','hand','pp','ep','sep','keyword','win','own_board_health'],0);weights['own_board_health']=1
results={}
configs=[(x,x,{'objective':'lethal'}) for x in ['random-half-anchor','random-two-ward-adaptive-anchor','slot-pp-evolve','split-oldest-first']]+[('objective-preserve-versus-win-'+o,'objective-preserve-versus-win',{'objective':o,'weights':weights}) for o in ['lethal','value']]+[('bounded','random-half-anchor',{'max_states':1}),('invalid','random-half-anchor',{'max_states':0})]
for name,cid,opt in configs:
 c=cs[cid];save(name+'.fixture.json',c)
 record=Battle(c['state'],c['cards']).export()
 status,data=call(name,'/api/combat-practical',{'record':record,'options':opt})
 results[name]={'status':status,'result':data}
 print(name,status,{x:data.get(x) for x in ['win_probability_exact','expected_value_exact','recommended_action','complete','cutoffs']},flush=True)
trivial=Battle({'players':[{'turn':7,'ep':0,'sep':0},{}]},{}).export()
status,data=call('recovery','/api/combat-practical',{'record':trivial});results['recovery']={'status':status,'result':data}
legacy=json.loads(Path('src/svdeck/data/combat_benchmark_cases.json').read_text(encoding='utf-8'))[0];save('legacy.fixture.json',legacy)
status,data=call('legacy','/api/combat',{'record':bench.make_battle(legacy).export(),'cursor':0,'mode':legacy['mode']});results['legacy']={'status':status,'result':data}
save('search-results.json',results)
checks=[]
for name,entry in results.items():
 d=entry['result'];o=oracle[name]
 ck={'name':name,'checks':[],'edges_checked':0,'failures':[]}
 def check(label,truth):
  ck['checks'].append({'label':label,'pass':bool(truth)})
  if not truth:ck['failures'].append(label)
 if name=='invalid':check('HTTP400 actionable max_states',entry['status']==400 and 'max_states' in d.get('error',''))
 elif name=='legacy':
  check('HTTP200 complete',entry['status']==200 and d.get('complete') is True)
  check('required clear survivor3/1',any(not x['enemy_board'] and [(f['attack'],f['health']) for f in x['own_board']]==[(3,1)] for x in d['candidates']))
 else:
  check('HTTP200',entry['status']==200)
  check('complete/optimal',d['complete']==(name!='bounded') and d['optimal']==(name!='bounded'))
  if 'win' in o:check('independent win probability',Fraction(d['win_probability_exact'])==Fraction(o['win']))
  if 'value' in o:check('independent heuristic value',Fraction(d['expected_value_exact'])==Fraction(o['value']))
  if 'first' in o:check('independent first decision',d['recommended_action']==o['first'])
  if name=='bounded':check('states cutoff',any('states' in str(x) for x in d['cutoffs']))
  for node in d['policy']:
   for ai,choice in enumerate(node['actions']):
    total=Fraction(0);wv=Fraction(0);hv=Fraction(0)
    for ei,edge in enumerate(choice['outcomes']):
     pr=Fraction(edge['probability'])
     if pr<=0:continue
     local=dict(d['record'],initial=node['state'],actions=[],frames=[])
     rn=f'{name}.replay-{node["id"]}-{ai}-{ei}'
     rs,rd=call(rn,'/api/combat-practical-replay',{'record':local,'steps':[{'action':choice['action'],'draws':edge['draws']}]})
     target=d['policy'][edge['node']]
     no_rng=lambda state:{k:v for k,v in state.items() if k!='rng'}
     check(rn+' legal/state/probability',rs==200 and no_rng(rd['state'])==no_rng(target['state']) and Fraction(rd['probability'])==pr)
     total+=pr;wv+=pr*Fraction(target['value']['win_probability_exact']);hv+=pr*Fraction(target['value']['expected_value_exact']);ck['edges_checked']+=1
    check(f'node{node["id"]}choice{ai} probability/expectation',total==1 and wv==Fraction(choice['win_probability_exact']) and hv==Fraction(choice['expected_value_exact']))
 checks.append(ck);save('checks.json',checks)
 print('checked',name,ck['edges_checked'],'failures',ck['failures'],flush=True)
k.CloseHandle(h)
save('completed.json',{'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'request_count':len(log),'edges':sum(c['edges_checked'] for c in checks),'failures':[c for c in checks if c['failures']],'cleanup':'HTTP responses closed after each call; process observer handle closed; no server changes; client exiting'})
