"""Documented replay/conditional consumption, without private imports."""
from run import *
from consume_small import statekey,replay
from svdeck.battle_practical import replay_branch
from fractions import Fraction
checks=[]
for idx in range(9):
 r=read(OUT/f'small-delivered/case-{idx:03d}/native/trial-1/result.json')
 nodes=r['debug_nodes'];candidate_states={statekey(n['state']) for n in nodes if n['candidate']}
 samples=r['witness_samples'];observed=[]
 for w in samples:
  target=replay_branch(r['record'],w['steps'])['state']
  expected=replay(r['record']['initial'],r['record']['cards'],w['steps'])
  observed.append({'witness':w,'public_replay_equals_oracle':statekey(target)==statekey(expected),'reaches_candidate':statekey(target) in candidate_states,'target':target})
 checks.append({'case_index':idx,'backend':r['actual_backend'],'cutoffs':r['cutoffs'],'sample_count':len(samples),'all_replayed':all(w['public_replay_equals_oracle'] and w['reaches_candidate'] for w in observed),'observations':observed})
save(HERE/'public-witnesses.json',checks)
path=OUT/'small-delivered/case-008/native/trial-1/result.json';r=read(path)
run('adaptive-root',['--expand',path,'--output',OUT/'adaptive-root.json'])
root=read(OUT/'adaptive-root.json');choice=next(c for c in root['choices'] if c['action']=={'type':'play','card':'random'})
branches=[]
for i,o in enumerate(choice['outcomes']):
 save(OUT/f'adaptive-observed-{i}.json',o['state'])
 run(f'adaptive-continuation-{i}',['--expand',path,'--state',OUT/f'adaptive-observed-{i}.json','--output',OUT/f'adaptive-continuation-{i}.json'])
 continuation=read(OUT/f'adaptive-continuation-{i}.json');target='exposed' if i==0 else 'protected'
 follow=next(c for c in continuation['choices'] if c['action'].get('target')==target)
 steps=[{'action':choice['action'],'draws':o['draws']},{'action':follow['action'],'draws':follow['outcomes'][0]['draws']}]
 save(OUT/f'adaptive-steps-{i}.json',steps)
 run(f'adaptive-replay-{i}',['--expand',path,'--steps',OUT/f'adaptive-steps-{i}.json','--output',OUT/f'adaptive-replay-{i}.json'])
 actual=read(OUT/f'adaptive-replay-{i}.json')['state'];expected=replay(r['record']['initial'],r['record']['cards'],steps)
 branches.append({'observed_probability':o['probability'],'observed_draws':o['draws'],'chosen_action':follow['action'],'steps':steps,'final_state':actual,'exact_replay':statekey(actual)==statekey(expected)==statekey(follow['outcomes'][0]['state'])})
save(HERE/'adaptive.json',{'root_random_mass':str(sum(Fraction(o['probability']) for o in choice['outcomes'])),'branches':branches})
items=[]
for idx in [4,7,8]:
 r=read(OUT/f'small-delivered/case-{idx:03d}/native/trial-1/result.json');groups=[]
 for ni,n in enumerate(r['debug_nodes']):
  for c in n['conditional']:
   if len(c['outcomes'])>1 or any(o['draws'] for o in c['outcomes']):
    mass=sum((Fraction(o['probability']) for o in c['outcomes']),Fraction())
    groups.append({'node_index':ni,'action':c['action'],'mass':str(mass),'outcomes':[{'probability':o['probability'],'draws':o['draws'],'state':o['state']} for o in c['outcomes']]})
 items.append({'case_index':idx,'all_random_groups_mass_one':all(g['mass']=='1' for g in groups),'groups':groups})
save(HERE/'random-probabilities.json',items)
case=read(ROOT/'docs/evidence/turn-search-compare/independent-hard-cases.v1.json')[0];save(HERE/'tiny-case.json',[case])
run('tiny',['--cases',HERE/'tiny-case.json','--output',OUT/'tiny','--algorithms','native','--trials','1','--max-states','1','--seconds','3600','--debug-threshold','0'])
tiny=read(OUT/'tiny/case-000/native/trial-1/result.json');save(HERE/'tiny.json',{k:tiny[k] for k in ('complete','enumeration_complete','frontier_complete','cutoffs','candidate_count','actual_backend')})
print(json.dumps({'public_witnesses':sum(c['sample_count'] for c in checks),'all_replayed':all(c['all_replayed'] for c in checks),'adaptive_branches':len(branches),'all_adaptive_replays':all(b['exact_replay'] for b in branches),'tiny_explicit_incomplete':tiny['complete'] is False and bool(tiny['cutoffs'])}))
