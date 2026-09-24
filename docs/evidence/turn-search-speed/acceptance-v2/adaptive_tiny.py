from run import *
from consume_small import statekey,replay
from fractions import Fraction
path=OUT/'small/case-008/native/trial-1/result.json';r=read(path);root=read(OUT/'adaptive-root.json');choice=next(c for c in root['choices'] if c['action']=={'type':'play','card':'random'})
assert sum(Fraction(o['probability']) for o in choice['outcomes'])==1
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
 assert statekey(actual)==statekey(expected)==statekey(follow['outcomes'][0]['state'])
 branches.append({'observed_probability':o['probability'],'observed_draws':o['draws'],'chosen_action':follow['action'],'steps':steps,'final_state':actual,'exact_replay':True})
save(HERE/'adaptive.json',branches)
cases=read(ROOT/'docs/evidence/turn-search-compare/independent-small-cases.v1.json');save(HERE/'tiny-case.json',[cases[0]])
run('tiny',['--cases',HERE/'tiny-case.json','--output',OUT/'tiny','--algorithms','native','--trials','1','--max-states','1','--seconds','0.001','--debug-threshold','1000000'])
tiny=read(OUT/'tiny/case-000/native/trial-1/result.json');save(HERE/'tiny.json',{k:tiny[k] for k in ('complete','enumeration_complete','frontier_complete','cutoffs','candidate_count','actual_backend')})
assert tiny['complete'] is False and tiny['cutoffs']
