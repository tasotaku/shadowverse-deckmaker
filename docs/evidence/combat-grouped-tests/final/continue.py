import json,copy,urllib.request,datetime
from pathlib import Path
from svdeck.battle import Battle
from svdeck.battle_combat import analyze
P=Path('docs/evidence/combat-grouped-tests/final')
def save(n,x): (P/n).write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf8')
fixtures=json.loads((P/'fixtures.json').read_text(encoding='utf8')); original=copy.deepcopy(fixtures)
raw=json.loads((P/'combat.json').read_text(encoding='utf8')); replays=[]
opener=urllib.request.build_opener()
for x in raw:
 r=x.get('response',{})
 for idx,c in enumerate(r.get('candidates',[])):
  rec={**r['record'],'actions':c['actions'],'frames':[]}; req={'record':rec,'cursor':len(c['actions'])}
  row={'fixture':x['fixture'],'mode':x['mode'],'index':idx,'candidate':c,'request':req}
  try:
   res=opener.open(urllib.request.Request('http://127.0.0.1:8767/api/replay',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'}),timeout=30)
   row.update(status=res.status,response=json.load(res))
  except Exception as e: row['error']=str(e)
  replays.append(row); save('replays.json',replays)
comparisons=[]
f=fixtures['F3']
for strategy in [None,'exhaustive']:
 b=Battle(copy.deepcopy(f['record']['initial']),copy.deepcopy(f['record']['cards']))
 before=copy.deepcopy(b.state); exported=copy.deepcopy(b.export())
 args={'mode':'attack','max_states':50000}
 if strategy: args['strategy']=strategy
 r=analyze(b,**args)
 comparisons.append({'strategy':strategy or 'default','max_states':50000,'response':r,'state_unchanged':b.state==before,'export_unchanged':b.export()==exported,'before':before,'after':copy.deepcopy(b.state)})
 save('comparisons.json',comparisons)
save('immutability.json',{'records_cursors_snapshots_equal':fixtures==original==json.loads((P/'fixtures.json').read_text(encoding='utf8'))})
save('stopped.json',{'stopped_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cleanup':'Dedicated HTTP opener released; immutable artifacts preserved; shared service left running.'})
for x in replays: print(x['fixture'],x['mode'],x['index'],x.get('status'),list(x.get('response',{})))
print('sample state',json.dumps(replays[0]['response']['state']))
for x in comparisons: print(x['strategy'],x['response']['stats'],x['response']['complete'],x['state_unchanged'],x['export_unchanged'])
