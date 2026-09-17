from pathlib import Path
import json,copy,urllib.request,time,datetime
from svdeck.battle import Battle
out=Path('docs/evidence/combat-grouped-tests'); started=datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(n,x): (out/n).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def body(t):
 n,a,h=t
 return {'id':n,'card_id':'test-body','attack':a,'health':h,'max_health':h,'entered_turn':1,'attacks':0,'evolved':0,'keywords':[]}
def player(board,e=0): return {'health':20,'max_health':20,'turn':8,'ep':e,'sep':e,'evolved_this_turn':False,'hand':[],'deck':['test-body']*20,'board':[body(x) for x in board]}
data={'F1':([('A',2,1),('B',3,1)],[('X',1,2)]),'F2':([('A',4,2),('B',2,4)],[('X',5,2)]),'F3':([('T',4,1),('S1',2,1),('S2',2,1)],[('X',4,4)]),'F4':([('A',1,1)],[])}
fixtures={}
for key,(own,enemy) in data.items():
 b=Battle({'players':[player(own,1 if key=='F4' else 0),player(enemy)]})
 fixtures[key]={'record':b.export(),'cursor':0,'snapshot':copy.deepcopy(b.state),'legal_actions':b.observation(0)['legal_actions']}
write('fixtures-v1.json',fixtures);write('execution-meta.json',{'started_at':started})
client=urllib.request.build_opener(); results={}
for key in data:
 for mode in (['attack','evolve','super'] if key=='F4' else ['attack']):
  name=key+'-'+mode; req={'record':fixtures[key]['record'],'cursor':0,'mode':mode}; t=time.perf_counter()
  try:
   response=client.open(urllib.request.Request('http://127.0.0.1:8767/api/combat',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'}),timeout=45)
   result={'request':req,'status':response.status,'response':json.load(response),'seconds':time.perf_counter()-t}
  except Exception as e: result={'request':req,'error':str(e),'seconds':time.perf_counter()-t}
  results[name]=result;write('raw-combat.json',results)
  print(name,json.dumps({k:v for k,v in result.items() if k not in ('request','response')}),list(result.get('response',{})))
print(json.dumps(results['F1-attack']['response'],ensure_ascii=False)[:6500])
