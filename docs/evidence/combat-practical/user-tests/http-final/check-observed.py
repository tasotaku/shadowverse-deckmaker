import json
from pathlib import Path
from fractions import Fraction
p=Path('docs/evidence/combat-practical/user-tests/http-final');rs=json.loads((p/'search-results.json').read_text(encoding='utf-8'));checks=[]
def add(n,c):
 checks.append({'check':n,'pass':bool(c)})
for name,item in rs.items():
 if name in ('invalid','legacy','bounded'):continue
 d=item['result'];cards=d['record']['cards'];w=d['weights']
 for n in d['policy']:
  s=n['state'];me=s['active_player'];own=s['players'][me];enemy=s['players'][1-me]
  for ch in n['actions']:
   a=ch['action'];typ=a['type'];tag=f'{name} node{n["id"]} {a}'
   if typ=='attack':
    src=next(f for f in own['board'] if f['id']==a['source']);wards=[f['id'] for f in enemy['board'] if '守護' in f['keywords']]
    face=a['target']==f'leader:{1-me}'
    add(tag+' attacks/ward/sickness',src['attacks']==0 and src['attack']>0 and (not wards or a['target'] in wards) and (src['entered_turn']<own['turn'] or '疾走' in src['keywords'] or (not face and ('突進' in src['keywords'] or src['evolved']>0))))
   elif typ=='play':
    src=next(f for f in own['hand'] if f['id']==a['card']);card=cards[src['card_id']]
    add(tag+' pp/capacity',src['cost']<=own['pp'] and (card['kind']!='follower' or len(own['board'])<5))
    if 'target' in a:add(tag+' enemy target',any(f['id']==a['target'] for f in enemy['board']))
   elif typ=='evolve':
    src=next(f for f in own['board'] if f['id']==a['source'])
    add(tag+' evolution legal',own['ep']>0 and not own['evolved_this_turn'] and src['evolved']==0 and own['turn']>=5)
   else:add(tag+' recognized action',False)
   for e in ch['outcomes']:
    nex=d['policy'][e['node']]['state']['players'][me]
    if typ=='play':add(tag+' pp spent once',nex['pp']==own['pp']-src['cost'] and not any(f['id']==src['id'] for f in nex['hand']))
    if typ=='evolve':add(tag+' ep spent once',nex['ep']==own['ep']-1 and nex['evolved_this_turn'])
 def term(n):
  s=n['state'];me=s['active_player'];a,b=s['players'][me],s['players'][1-me]
  win=int(s['winner']==me)
  score=w['leader']*(a['health']-b['health'])
  for label,key in [('attack','attack'),('health','health')]:score+=w[label]*(sum(f[key] for f in a['board'])-sum(f[key] for f in b['board']))
  score+=w['body']*(len(a['board'])-len(b['board']))+w['keyword']*(sum(len(f['keywords']) for f in a['board'])-sum(len(f['keywords']) for f in b['board']))
  score+=w['hand']*len(a['hand'])+sum(w[k]*a[k] for k in ['pp','ep','sep'])+w['win']*win+w['own_board_health']*sum(f['health'] for f in a['board'])
  return Fraction(win),Fraction(score)
 def aggregate(i):
  n=d['policy'][i]
  if n['best_action'] is None:return term(n)
  edges=n['actions'][n['best_action']]['outcomes'];v=[(Fraction(e['probability']),aggregate(e['node'])) for e in edges]
  return tuple(sum(pr*x[k] for pr,x in v) for k in [0,1])
 actual=aggregate(d['root']);add(name+' independent terminal aggregation',actual==(Fraction(d['win_probability_exact']),Fraction(d['expected_value_exact'])))
 if name=='random-two-ward-adaptive-anchor':
  root=d['policy'][d['root']];edge=root['actions'][root['best_action']]['outcomes'];observed=[]
  for e in edge:
   n=d['policy'][e['node']];action=n['actions'][n['best_action']]['action'];survivor=n['state']['players'][1]['board'][0]['id'];observed.append(action['target']);add('adaptive target follows observed survivor '+survivor,action['target']==survivor)
  add('adaptive branches distinct targets',len(set(observed))==2)
 if name=='split-oldest-first':
  root=d['policy'][d['root']];split=next(ch for ch in root['actions'] if ch['action']=={'type':'play','card':'split'});n=d['policy'][split['outcomes'][0]['node']];board=n['state']['players'][1]['board'];add('split barrier consumes assigned3 leaves both3 no barrier',[(f['id'],f['health']) for f in board]==[('old',3),('new',3)] and 'バリア' not in board[0]['keywords'])
(p/'independent-rule-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print('Independent checks',len(checks),'failures',[x for x in checks if not x['pass']])
