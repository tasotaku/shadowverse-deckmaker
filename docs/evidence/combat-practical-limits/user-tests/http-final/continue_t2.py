from pathlib import Path
exec(Path('docs/evidence/combat-practical-limits/user-tests/http-final/run_t2.py').read_text('utf-8-sig').split('\nresults={}')[0])
LOG=json.loads((OUT/'requests.json').read_text('utf-8'));counter=len(LOG)
CHECKS=json.loads((OUT/'checks-initial.json').read_text('utf-8'))
results={x['label']:json.loads((OUT/x['response_file']).read_text('utf-8')) for x in LOG}
without_rng=lambda s:{k:v for k,v in s.items() if k!='rng'}
paths=[]
for c in CASES:
 if 'adaptive_after_action' not in c['expected']:continue
 label=c['id']; r=results[label];root=r['policy'][r['root']]
 first=next(x for x in root['actions'] if x['action']==c['expected']['adaptive_after_action'])
 def walk(node,choice,steps,probability):
  check(label+' branch sum node '+str(node['id']),sum(Fraction(e['probability']) for e in choice['outcomes'])==1,choice['outcomes'])
  for e in choice['outcomes']:
   p=Fraction(e['probability']); target=r['policy'][e['node']]
   steps2=steps+[{'action':choice['action'],'draws':e['draws']}]
   replay=post(label+'-edge-'+str(node['id'])+'-'+str(e['node']),'/api/combat-practical-replay',{'record':dict(r['record'],initial=node['state'],actions=[],frames=[]),'steps':[steps2[-1]]})
   check(label+' replay '+str(node['id'])+'-'+str(e['node']),p>0 and Fraction(replay.get('probability','0'))==p and without_rng(replay.get('state',{}))==without_rng(target['state']),dict(probability=replay.get('probability'),expected=e['probability']))
   if target['best_action'] is None:
    check(label+' terminal '+str(target['id']),target['state']['winner']==0 and target['value']['win_probability_exact']=='1',target['value'])
    paths.append(dict(case=label,probability=str(probability*p),steps=steps2,terminal=target['id']))
   else:walk(target,target['actions'][target['best_action']],steps2,probability*p)
 walk(root,first,[],Fraction(1))
for c in CASES:
 for i,a in enumerate(c['expected'].get('replay_anchors',[])):
  r=post(c['id']+'-anchor-'+str(i),'/api/combat-practical-replay',{'record':record(c),'steps':[{'action':x,'draws':[]} for x in a['actions']]})
  enemy=r.get('state',{}).get('players',[{},{}])[1];board=enemy.get('board',[])
  check(c['id']+' anchor IDs',[x['id'] for x in board]==a['enemy_board_ids'],[x['id'] for x in board])
  if 'enemy_health' in a:check(c['id']+' anchor health',{x['id']:x['health'] for x in board}==a['enemy_health'],{x['id']:x['health'] for x in board})
  for k,v in a.get('enemy_keywords',{}).items():check(c['id']+' anchor keywords '+k,next(x['keywords'] for x in board if x['id']==k)==v,next(x['keywords'] for x in board if x['id']==k))
  if 'enemy_leader_health' in a:check(c['id']+' anchor leader',enemy.get('health')==a['enemy_leader_health'],enemy.get('health'))
c=copy.deepcopy(next(c for c in CASES if c['id']=='split-oldest-first'))
for x in c['state']['players'][1]['board']:x['id']={'old':'z_old','new':'a_new'}[x['id']]
for reverse in [False,True]:
 if reverse:c['state']['players'][1]['board'].reverse()
 r=post('chronology-'+str(reverse),'/api/combat-practical-replay',{'record':record(c),'steps':[{'action':{'type':'play','card':'split'},'draws':[]}]})
 b=r.get('state',{}).get('players',[{},{}])[1].get('board',[])
 obs=[(x['id'],x['health'],x['keywords']) for x in b]
 expected=[('z_old',3,['守護','バリア'])] if reverse else [('z_old',3,['守護']),('a_new',3,[])]
 check('chronology '+str(reverse),obs==expected,obs)
c=next(c for c in CASES if c['id']=='objective-preserve-versus-win')
weights=dict.fromkeys(['leader','attack','health','body','hand','pp','ep','sep','keyword','win','own_board_health'],0);weights['own_board_health']=1
for obj,win,value in [('lethal','1','20'),('value','0','21')]:
 r=solve('own-health-'+obj,c,{'objective':obj,'weights':weights})
 check('own-health '+obj,r.get('complete') is True and r.get('optimal') is True and r.get('win_probability_exact')==win and r.get('expected_value_exact')==value and (obj!='value' or r.get('recommended_action') is None),{k:r.get(k) for k in ['complete','optimal','win_probability_exact','expected_value_exact','recommended_action']})
 if obj=='value':check('no implicit end turn',r['policy'][r['root']]['state']['players'][0]['turn']==c['state']['players'][0]['turn'],r['policy'][r['root']]['state']['players'][0]['turn'])
c=next(c for c in CASES if c['id']=='random-half-anchor')
r=solve('tiny-budget',c,{'max_states':1});check('tiny budget honest',r.get('complete') is False and r.get('optimal') is False and 'states' in r.get('cutoffs',[]),{k:r.get(k) for k in ['complete','optimal','cutoffs','win_probability_exact']})
save('adaptive-paths.json',paths);save('checks.json',CHECKS)
save('completed.json',{'stopped_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'requests':len(LOG),'checks':len(CHECKS),'failed':[x for x in CHECKS if not x['passed']]})
print(json.dumps({'requests':len(LOG),'checks':len(CHECKS),'paths':paths,'failed':[x for x in CHECKS if not x['passed']]},ensure_ascii=False))
