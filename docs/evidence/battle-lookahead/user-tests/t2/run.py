import json,subprocess,time,datetime,copy,urllib.request
from pathlib import Path
from svdeck.battle import Battle
base=Path('docs/evidence/battle-lookahead/user-tests/t2')
cases=json.loads(Path('tests/fixtures/battle_lookahead_cases.json').read_text(encoding='utf-8'))
byid={c['id']:c for c in cases}
log=[]
def save(name,value): (base/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def cli(name,case,extra=(),input_path='tests/fixtures/battle_lookahead_cases.json'):
 cmd=['.venv/Scripts/python.exe','-X','utf8','-m','svdeck.battle_lookahead','--cases',input_path,'--case',case,'--turns','3','--output',str(base/name),*extra]
 t=time.monotonic()
 try:
  r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=30)
  item={'name':name,'command':cmd,'elapsed_seconds':time.monotonic()-t,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
 except subprocess.TimeoutExpired: item={'name':name,'elapsed_seconds':time.monotonic()-t,'timeout':True}
 log.append(item);save('operations.json',log)
cli('random','random_then_observe_and_adapt')
for name in ['incomparable_hand_burn','incomparable_hand_storm']:
 c=byid[name]; b=Battle(c['state'],c['cards']);record=b.export()
 save(name+'-request.json',{'record':record,'policy':'lookahead','options':{'turns':3,'max_nodes':4000,'seconds':2,'seed':0}})
 payload=(base/(name+'-request.json')).read_bytes()
 t=time.monotonic()
 try:
  with urllib.request.urlopen(urllib.request.Request('http://localhost:8767/api/ai-step',data=payload,headers={'Content-Type':'application/json'}),timeout=30) as response:
   data=response.read();status=response.status
  (base/(name+'-response.json')).write_bytes(data)
  item={'name':name,'http_status':status,'elapsed_seconds':time.monotonic()-t}
 except Exception as e:item={'name':name,'elapsed_seconds':time.monotonic()-t,'error':repr(e)}
 log.append(item);save('operations.json',log)
cli('budget','save_removal_for_next_turn',['--max-states','1'])
unsupported=copy.deepcopy(byid['save_removal_for_next_turn']);unsupported['id']='unsupported_effect';unsupported['cards']['remove']['effects']=[{'op':'unrecognized_effect','target':'chosen_enemy'}]
save('unsupported-input.json',[unsupported])
cli('unsupported','unsupported_effect',input_path=str(base/'unsupported-input.json'))
print(json.dumps(log,ensure_ascii=False,indent=2))
