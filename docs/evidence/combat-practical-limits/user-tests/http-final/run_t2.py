import json, time, datetime, urllib.request, urllib.error, copy, hashlib, sys
from pathlib import Path
from fractions import Fraction
from svdeck.battle import Battle
OUT=Path('docs/evidence/combat-practical-limits/user-tests/http-final')
CASES=json.loads(Path('tests/fixtures/combat_practical_cases.json').read_text('utf-8'))
LOG=[]; CHECKS=[]; counter=0

def save(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def check(label,ok,observed): CHECKS.append(dict(label=label,passed=bool(ok),observed=observed))
def post(label,route,payload):
 global counter
 counter+=1; stem=f'{counter:03}-{label}'; save(stem+'-request.json',payload)
 t=time.perf_counter(); stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
 try:
  req=urllib.request.Request('http://localhost:8767'+route,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=60) as response:
   raw=response.read(); status=response.status
  result=json.loads(raw)
 except Exception as e:
  result={'client_error':str(e)}; status=getattr(e,'code',None); raw=json.dumps(result).encode()
 ms=(time.perf_counter()-t)*1000
 (OUT/(stem+'-response.json')).write_bytes(raw)
 LOG.append(dict(label=label,route=route,status=status,started_at=stamp,wall_ms=ms,response_file=stem+'-response.json',stats=result.get('stats')))
 save('requests.json',LOG)
 check(label+' HTTP',status==200 and ms<60000,dict(status=status,wall_ms=ms))
 return result

def record(c):return Battle(c['state'],c['cards']).export()
def solve(label,c,options=None):
 payload={'record':record(c)}
 if options is not None:payload['options']=options
 return post(label,'/api/combat-practical',payload)
def validate(label,c,r):
 exp=c['expected']; check(label+' completion',r.get('complete') is True and r.get('optimal') is True,[r.get('complete'),r.get('optimal'),r.get('cutoffs')])
 check(label+' probability',r.get('win_probability_exact')==exp['win_probability'],r.get('win_probability_exact'))
 if 'unique_best_first_action' in exp:check(label+' first action',r.get('recommended_action')==exp['unique_best_first_action'],r.get('recommended_action'))
 if 'policy' in r:
  root=r['policy'][r['root']]
  for av in exp.get('action_values',[]):
   cs=[a for a in root['actions'] if a['action']==av['action']]
   check(label+' candidate '+av['action']['card'],len(cs)==1 and cs[0]['win_probability_exact']==av['win_probability'],[(a['action'],a['win_probability_exact']) for a in cs])

results={}
for c in CASES:
 r=solve(c['id'],c);results[c['id']]=r;validate(c['id'],c,r)
c=next(c for c in CASES if c['id']=='rng-cheating-choice')
for seed in c['expected']['seed_independence']:
 if seed==c['state']['rng']:continue
 variant=copy.deepcopy(c);variant['state']['rng']=seed
 r=solve('rng-seed-'+str(seed),variant);validate('rng-seed-'+str(seed),variant,r)
save('checks-initial.json',CHECKS);save('results-index.json',{k:v.get('recommended_action') for k,v in results.items()})
print(json.dumps({'requests':len(LOG),'failed':[x for x in CHECKS if not x['passed']],'sample_keys':list(results['random-adaptive-target']),'adaptive_root':results['random-adaptive-target']['policy'][results['random-adaptive-target']['root']]}))
