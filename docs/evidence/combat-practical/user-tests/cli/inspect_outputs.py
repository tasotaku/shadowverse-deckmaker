from pathlib import Path
import json
from fractions import Fraction as F
from functools import lru_cache
p=Path('docs/evidence/combat-practical/user-tests/cli')
refs={c['id']:c for c in json.loads((p/'reference.json').read_text(encoding='utf-8'))['cases']}
findings=[];summaries=[]
def check(cond,desc):
 if not cond:findings.append(desc)
def score(state,w):
 o,e=state['players']; v=w['leader']*(o['health']-e['health'])
 for who,sgn in [(o,1),(e,-1)]:
  for b in who['board']:
   v+=sgn*(w['attack']*b['attack']+w['health']*b['health']+w['body']+w['keyword']*len(b['keywords']))
 v+=w['hand']*len(o['hand'])+sum(w[k]*o[k] for k in ['pp','ep','sep'])
 v+=w['own_board_health']*sum(b['health'] for b in o['board'])
 if state['winner']==0:v+=w['win']
 return (F(state['winner']==0),F(v))
for f in p.glob('*/report.json'):
 r=json.loads(f.read_text(encoding='utf-8'))
 if 'policy' not in r:continue
 name=f.parent.name;nodes=r['policy'];edges=0;terminal_paths=[];checks=0
 for n in nodes:
  st=n['state'];o,e=st['players'];mine={b['id']:b for b in o['board']};enemy={b['id']:b for b in e['board']};hand={b['id']:b for b in o['hand']}
  check(len(mine)<=5,name+' full board capacity')
  check(score(st,r['weights'])==(F(n['stop']['win_probability_exact']),F(n['stop']['expected_value_exact'])),name+' stop score '+str(n['id']))
  for a in n['actions']:
   ac=a['action'];kind=ac['type'];checks+=1
   if kind=='play':
    c=hand.get(ac['card']);check(c is not None,name+' play hand membership')
    check(c['cost']<=o['pp'],name+' PP affordability')
    if r['record']['cards'][c['card_id']]['kind']=='follower':check(len(mine)<5,name+' full board play forbidden')
   elif kind=='attack':
    b=mine[ac['source']];target=ac['target'];check(b['attacks']==0,name+' spent attack forbidden')
    fresh=b['entered_turn']==o['turn'];ward=[x['id'] for x in enemy.values() if '守護'in x['keywords']]
    check(not ward or target in ward,name+' ward target')
    if target=='leader:1':check(not fresh or '疾走'in b['keywords'],name+' fresh face restriction')
    else:
     check(target in enemy,name+' valid follower target')
     check(not fresh or b['evolved'] or any(k in b['keywords'] for k in ['突進','疾走']),name+' summon sickness')
   elif kind in ('evolve','super_evolve'):
    b=mine[ac['source']];k='ep' if kind=='evolve' else 'sep';threshold=5 if kind=='evolve' else 7
    check(o[k]>0 and not o['evolved_this_turn'] and not b['evolved'] and o['turn']>=threshold,name+' evolution legality')
   else:findings.append(name+' unknown action '+kind)
   check(sum(F(x['probability']) for x in a['outcomes'])==1,name+' branch sum')
   for edge in a['outcomes']:
    edges+=1;check(F(edge['probability'])>0,name+' positive probability');child=nodes[edge['node']]['state'];co=child['players'][0]
    if kind=='play':
     check(co['pp']==o['pp']-hand[ac['card']]['cost'],name+' PP consumed once')
     check(ac['card'] not in [x['id'] for x in co['hand']],name+' hand consumed once')
    elif kind in ('evolve','super_evolve'):
     k='ep' if kind=='evolve' else 'sep';check(co[k]==o[k]-1 and co['evolved_this_turn'],name+' evolution resource once')
    elif kind=='attack':
     survivors=[b for b in co['board'] if b['id']==ac['source']]
     check(not survivors or survivors[0]['attacks']==mine[ac['source']]['attacks']+1,name+' attack spent once')
  checks+=len(n['actions'])
 @lru_cache(None)
 def calc(i):
  n=nodes[i];values=[score(n['state'],r['weights'])]
  for a in n['actions']:
   v=tuple(sum(F(x['probability'])*calc(x['node'])[k] for x in a['outcomes']) for k in [0,1]);values.append(v)
   check(v==(F(a['win_probability_exact']),F(a['expected_value_exact'])),name+' weighted action '+str(i))
  best=max(values,key=lambda v:v if r['objective']=='lethal' else (v[1],v[0]))
  chosen=values[0 if n['best_action'] is None else n['best_action']+1]
  check(chosen==best,name+' best decision '+str(i))
  check(chosen==(F(n['value']['win_probability_exact']),F(n['value']['expected_value_exact'])),name+' reported node value')
  return chosen
 root=calc(r['root'])
 check(root==(F(r['win_probability_exact']),F(r['expected_value_exact'])),name+' root aggregate')
 check(r['replay']['status']=='PASS' and r['replay']['edges_checked']==edges,name+' public CLI replay all edges')
 if r['complete'] and r['objective']=='lethal':check(root[0]==F(refs[r['case_id']]['win_probability']),name+' independent exhaustive oracle')
 def paths(i,prob,steps):
  n=nodes[i]
  if n['best_action'] is None:
   terminal_paths.append({'probability':str(prob),'node':i,'win':n['state']['winner']==0,'expected_value':str(score(n['state'],r['weights'])[1]),'steps':steps});return
  a=n['actions'][n['best_action']]
  for edge in a['outcomes']:paths(edge['node'],prob*F(edge['probability']),steps+[{'node':i,'action':a['action'],'draws':edge['draws'],'next_node':edge['node']}])
 paths(r['root'],F(1),[])
 summary=dict(case=name,objective=r['objective'],complete=r['complete'],optimal=r['optimal'],cutoffs=r['cutoffs'],recommended_action=r['recommended_action'],win=str(root[0]),value=str(root[1]),edges_checked=edges,stats=r['stats'],terminal_paths=terminal_paths)
 summaries.append(summary)
(p/'independent-checks.json').write_text(json.dumps(dict(findings=findings,cases=summaries),ensure_ascii=False,indent=2),encoding='utf-8')
print('findings',findings);print('cases',len(summaries),'edges',sum(s['edges_checked'] for s in summaries))

