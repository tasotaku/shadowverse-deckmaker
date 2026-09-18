from client import *
from fractions import Fraction as F
checks=[]
def verify(ok,label):
 checks.append({'pass':bool(ok),'check':label})
def score(s,w):
 p=s['active_player'];a,b=s['players'][p],s['players'][1-p]
 val=w['leader']*(a['health']-b['health'])
 for term,key in [('attack','attack'),('health','health')]: val+=w[term]*(sum(c[key] for c in a['board'])-sum(c[key] for c in b['board']))
 val+=w['body']*(len(a['board'])-len(b['board']))+w['keyword']*(sum(len(c['keywords']) for c in a['board'])-sum(len(c['keywords']) for c in b['board']))
 val+=sum(w[x]*a[x] for x in ['pp','ep','sep'])+w['hand']*len(a['hand'])+w['own_board_health']*sum(c['health'] for c in a['board'])
 return val+w['win']*(s['winner']==p)
def legal(s,act,t):
 a,b=s['players'][s['active_player']],s['players'][1-s['active_player']];aa,bb=t['players'][t['active_player']],t['players'][1-t['active_player']]
 kind=act['type']
 if kind=='attack':
  c=next(c for c in a['board'] if c['id']==act['source']); target=act['target']; wards=[c['id'] for c in b['board'] if '守護' in c['keywords']]
  verify(c['attacks']==0 and c['attack']>0,'attack unused and positive')
  verify(not wards or target in wards,'ward blocks other targets')
  verify(c['entered_turn']<a['turn'] or '疾走' in c['keywords'] or ('突進' in c['keywords'] and target!='enemy_leader') or(c['evolved'] and target!='enemy_leader'),'summoning legality')
  verify(aa['pp']==a['pp'] and aa['ep']==a['ep'],'attack preserves pp/ep')
  for survivor in aa['board']:
   if survivor['id']==c['id']: verify(survivor['attacks']==c['attacks']+1,'attack consumed once')
 elif kind=='play':
  c=next(c for c in a['hand'] if c['id']==act['card']);definition=cards[c['card_id']]
  verify(a['pp']>=c['cost'] and aa['pp']==a['pp']-c['cost'],'play affordable exact cost')
  verify(definition['kind']!='follower' or len(a['board'])<5,'play board capacity')
  verify(c['id'] not in [x['id'] for x in aa['hand']],'played card leaves hand')
 elif kind=='evolve':
  c=next(c for c in a['board'] if c['id']==act['source'])
  verify(a['ep']>0 and not a['evolved_this_turn'] and not c['evolved'] and a['turn']>=5,'evolve legality')
  verify(aa['ep']==a['ep']-1 and aa['evolved_this_turn'],'evolve resource once')
 else: verify(False,'unexpected action '+str(act))
for name in ['half','adaptive','slot','split','objective-lethal','objective-value','limited','recovery']:
 r=json.loads((D/(name+'.response.json')).read_text(encoding='utf-8')); cards=r['record']['cards']; edges=0; policy=r['policy']
 for node in policy:
  verify(F(node['stop']['expected_value_exact'])==score(node['state'],r['weights']),name+' independent state heuristic')
  for ai,choice in enumerate(node['actions']):
   ps=F(0);ev=F(0);ew=F(0)
   for ei,edge in enumerate(choice['outcomes']):
    payload={'record':dict(r['record'],initial=node['state'],actions=[],frames=[]),'steps':[{'action':choice['action'],'draws':edge['draws']}]}
    replayed=post(f'{name}-edge-{node["id"]}-{ai}-{ei}','/api/combat-practical-replay',payload)
    target=policy[edge['node']]; without_rng=lambda st:{k:v for k,v in st.items() if k!='rng'}
    verify(without_rng(replayed['state'])==without_rng(target['state']),name+' exact replay state')
    probability=F(edge['probability']); verify(F(replayed['probability'])==probability,name+' replay probability')
    legal(node['state'],choice['action'],target['state']); ps+=probability;ev+=probability*F(target['value']['expected_value_exact']);ew+=probability*F(target['value']['win_probability_exact']);edges+=1
   verify(ps==1,name+' branch sum1'); verify(ev==F(choice['expected_value_exact']) and ew==F(choice['win_probability_exact']),name+' chance aggregation')
 def follow(n):
  node=policy[n]
  if node['best_action'] is None: return (F(node['state']['winner']==node['state']['active_player']),F(score(node['state'],r['weights'])))
  outcomes=node['actions'][node['best_action']]['outcomes'];sub=[(F(e['probability']),follow(e['node'])) for e in outcomes]
  return tuple(sum(p*v[i] for p,v in sub) for i in [0,1])
 win,value=follow(r['root']);verify(win==F(r['win_probability_exact']) and value==F(r['expected_value_exact']),name+' independent terminal-weight aggregation')
 save(name+'.checks.json',{'edges':edges,'independent_terminal_win':str(win),'independent_terminal_value':str(value)})
 print(name,'replayed edges',edges,'win/value',str(win),str(value),flush=True)
save('all-checks.json',checks);print('FAILURES',[c for c in checks if not c['pass']],flush=True)
