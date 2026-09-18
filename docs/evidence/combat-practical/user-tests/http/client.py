from pathlib import Path
import json,sys,time,urllib.request,urllib.error,datetime,platform
from svdeck.battle import Battle
D=Path('docs/evidence/combat-practical/user-tests/http')
def save(name,obj):
 (D/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def post(name,route,payload):
 save(name+'.request.json',payload)
 start=time.perf_counter()
 req=urllib.request.Request('http://127.0.0.1:8767'+route,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=60) as r: status=r.status; raw=r.read()
 except urllib.error.HTTPError as e: status=e.code; raw=e.read()
 elapsed=time.perf_counter()-start
 (D/(name+'.response.json')).write_bytes(raw)
 save(name+'.meta.json',{'status':status,'elapsed_seconds':elapsed,'route':route})
 return json.loads(raw)
cases={c['id']:c for c in json.loads(Path('tests/fixtures/combat_practical_cases.json').read_text(encoding='utf-8'))}
if __name__=='__main__':
 save('environment.json',{'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':sys.executable,'version':sys.version,'platform':platform.platform(),'server_pid':25220,'server_command':'python -X utf8 -m svdeck.battle_server --port 8767','readiness':'Get-NetTCPConnection: 127.0.0.1:8767 LISTEN PID25220'})
 save('oracle-before-requests.json',{
 'half':'Random hit g (1/2) clears ward then a attacks face => win; hit d (1/2) leaves ward and only a must spend attack clearing => no win. Attack g before random spends sole attacker => no win. Max=1/2.',
 'adaptive':'Play r: each of left/right dies with 1/2; one ally clears observed other ward, second goes face, value=1. Attack one ward first then r against sole remaining ward also guarantees 1; all such ties are valid and do not require future RNG knowledge. In post-r branch attack target must be surviving ward.',
 'slot':'Five occupied slots prohibit runner. small1/1 trades guard1/1 to free fifth slot and remove ward; PP1 buys runner2/2 storm; evolve consumes EP1 and gives +2/+2 plus +1 attack effect =>5 attack lethal. Evolving small or idle spends unique evolve without enough remaining face damage. expensive cost2 unaffordable. Max=1.',
 'split':'Oldest old3-health barrier ward precedes new3-health by input array. Split3 first consumes all3 on old barrier leaving both health3, old barrier removed. Ping1 old then split3 kills old; a4 hits leader4. Max=1, ping old first.',
 'objectives':'Own-health-only weights all0 except own_board_health1. Stop:21 HP, win0. Sacrifice face1 to guard20/1: both die then big1/20 hits leader1 => win1 and value20. Sacrifice big yields win1,value1. Thus lethal chooses face->guard and big->leader; value chooses stop,21.',
 'limited':'max_states1 cannot expand random-half actions; must explicitly incomplete with states reason.',
 'invalid':'max_states0 outside documented1..50000 gives400 field constraint.',
 'recovery':'Empty boards, no resources, leader20 each => no actions, lethal0 complete.'})
 c=cases['random-half-anchor']; r=post('half','/api/combat-practical',{'record':Battle(c['state'],c['cards']).export(),'options':{'objective':'lethal'}})
 print(json.dumps({k:v for k,v in r.items() if k not in ('policy','record')},ensure_ascii=False)); print(json.dumps(r['policy'][0],ensure_ascii=False))
