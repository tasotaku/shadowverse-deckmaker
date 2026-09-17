from pathlib import Path
import json,copy,urllib.request,time
from svdeck.battle import Battle
from svdeck.battle_combat import analyze
out=Path('docs/evidence/combat-grouped-tests')
def write(n,x): (out/n).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
fixtures=json.loads((out/'fixtures-v1.json').read_text(encoding='utf-8')); original=copy.deepcopy(fixtures)
results=json.loads((out/'raw-combat.json').read_text(encoding='utf-8')); replays={}; summaries={};client=urllib.request.build_opener()
for key,row in results.items():
 summaries[key]=[]
 for i,c in enumerate(row['response']['candidates']):
  record=copy.deepcopy(row['response']['record']); record['actions']=copy.deepcopy(c['actions']);record['frames']=[]
  req={'record':record,'cursor':len(c['actions'])};t=time.perf_counter()
  try:
   response=client.open(urllib.request.Request('http://127.0.0.1:8767/api/replay',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'}),timeout=45)
   payload=json.load(response);p,q=payload['state']['players']; boards=[]
   for player in (p,q): boards.append([{k:v for k,v in x.items() if k in ['id','name','attack','health','max_health','evolved']} for x in player['board']])
   match=(boards[0]==c['own_board'] and boards[1]==c['enemy_board'] and q['health']==c['enemy_health'] and p['ep']==c['ep'] and p['sep']==c['sep'] and p['health']==20 and q['ep']==0 and q['sep']==0)
   result={'request':req,'status':response.status,'response':payload,'matches_advertised':match,'seconds':time.perf_counter()-t}
   summaries[key].append({'index':i,'actions':c['actions'],'own_board':p['board'],'enemy_board':q['board'],'own_health':p['health'],'enemy_health':q['health'],'ep':p['ep'],'sep':p['sep'],'matches_advertised':match})
  except Exception as e: result={'request':req,'error':str(e),'seconds':time.perf_counter()-t}
  replays[key+':'+str(i)]=result;write('raw-replays.json',replays)
 print(key,len(row['response']['candidates']),'replayed')
write('candidate-evidence.json',summaries)
comparisons={}
for strategy in ('grouped','exhaustive'):
 f=fixtures['F3'];b=Battle(f['record']['initial'],f['record']['cards']);before=copy.deepcopy(b.state);before_export=copy.deepcopy(b.export())
 if strategy=='grouped': result=analyze(b,mode='attack',max_states=50000)
 else: result=analyze(b,mode='attack',max_states=50000,strategy='exhaustive')
 comparisons[strategy]={'max_states':50000,'response':result,'input_state_unchanged':before==b.state,'input_export_unchanged':before_export==b.export()}
 print(strategy,result['stats'])
write('raw-comparison.json',comparisons)
write('immutability.json',{'records_and_cursors_unchanged':fixtures==original,'snapshot_reconstruction_unchanged':all(Battle(f['record']['initial'],f['record']['cards']).state==f['snapshot'] for f in fixtures.values())})
print('replay_count',len(replays),'all_match',all(x.get('matches_advertised') for x in replays.values()))
print(json.dumps(summaries,ensure_ascii=True))
