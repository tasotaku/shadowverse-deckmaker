from client import *
def load(n):return json.loads((D/(n+'.response.json')).read_text(encoding='utf-8'))
checks=[]
def check(ok,why):checks.append({'pass':bool(ok),'check':why})
r=load('half');root=r['policy'][0];check(r['recommended_action']=={'type':'play','card':'r'},'half pre-outcome action is play r')
for e in root['actions'][root['best_action']]['outcomes']:
 n=r['policy'][e['node']];b=n['state']['players'][1]['board'];check(e['probability']=='1/2','half each uniform draw is1/2');check(len(b)==(1 if e['draws']==[0] else 2),'half ward death only draw0')
r=load('adaptive');root=r['policy'][0]
for e in root['actions'][root['best_action']]['outcomes']:
 n=r['policy'][e['node']];survivor=n['state']['players'][1]['board'][0]['id'];act=n['actions'][n['best_action']]['action'];check(act['type']=='attack' and act['target']==survivor,'adaptive observed survivor determines target '+survivor)
r=load('split');root=r['policy'][0]
for a in root['actions']:
 if a['action']=={'type':'play','card':'split'}:
  st=r['policy'][a['outcomes'][0]['node']]['state'];b=st['players'][1]['board'];check([(x['id'],x['health'],x['keywords']) for x in b]==[('old',3,['守護']),('new',3,[])],'split consumes all3 on old barrier no carry; identity lexical new before old does not change chronology')
for name,p in [('half','1/2'),('adaptive','1'),('slot','1'),('split','1'),('objective-lethal','1'),('objective-value','0'),('recovery','0')]:
 r=load(name);check(r['win_probability_exact']==p and r['complete'] and r['optimal'],name+' exact hand-derived optimum and complete')
r=load('limited');check(not r['complete'] and not r['optimal'] and any('states' in str(x) for x in r['cutoffs']),'limit explicit states cutoff')
check(json.loads((D/'invalid.meta.json').read_text())['status']==400 and 'max_states' in load('invalid')['error'],'400 identifies invalid field')
check(load('legacy')['complete'] and len(load('legacy')['candidates'])==858,'documented legacy complete858')
save('anchors-checks.json',checks);print(json.dumps(checks,ensure_ascii=False,indent=2))
