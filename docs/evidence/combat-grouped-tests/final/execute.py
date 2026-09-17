import json,copy,urllib.request,time,datetime
from pathlib import Path
from svdeck.battle import Battle
P=Path('docs/evidence/combat-grouped-tests/final')
def save(n,x): (P/n).write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf8')
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
fixtures={}
cards={'test-body':{'name':'Body','kind':'follower','cost':1,'attack':2,'health':3,'keywords':[],'synthetic':True}}
for name,friendly,enemy in [('F1',[('A',2,1),('B',3,1)],[('X',1,2)]),('F2',[('A',4,2),('B',2,4)],[('X',5,2)]),('F3',[('T',4,1),('S1',2,1),('S2',2,1)],[('X',4,4)]),('F4',[('A',1,1)],[])]:
 def player(board): return {'health':20,'turn':10,'ep':1 if name=='F4' else 0,'sep':1 if name=='F4' else 0,'hand':[],'deck':['test-body']*10,'board':[{'id':i,'card_id':'test-body','attack':a,'health':h,'max_health':h,'entered_turn':0,'attacks':0,'evolved':0} for i,a,h in board]}
 b=Battle({'players':[player(friendly),player(enemy)]},cards)
 fixtures[name]={'record':b.export(),'cursor':0,'snapshot':copy.deepcopy(b.state)}
save('fixtures.json',fixtures); save('start.json',{'started_at':start})
opener=urllib.request.build_opener()
raw=[]
for f,m in [('F1','attack'),('F2','attack'),('F3','attack'),('F4','attack'),('F4','evolve'),('F4','super')]:
 req={'record':fixtures[f]['record'],'cursor':0,'mode':m}
 row={'fixture':f,'mode':m,'request':req}
 try:
  r=opener.open(urllib.request.Request('http://127.0.0.1:8767/api/combat',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'}),timeout=30)
  row.update(status=r.status,response=json.load(r))
 except Exception as e: row['error']=str(e)
 raw.append(row); save('combat.json',raw)
save('records-unchanged.json',{'equal':fixtures==json.loads((P/'fixtures.json').read_text(encoding='utf8'))})
for x in raw:
 r=x.get('response',{}); print(x['fixture'],x['mode'],x.get('status'),list(r),r.get('stats'),len(r.get('candidates',[])))
print(json.dumps(raw[0].get('response',{}).get('candidates',[None])[0],ensure_ascii=False))
