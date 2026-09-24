from run import *
from consume_small import statekey,replay
from svdeck.battle_practical import replay_branch
from fractions import Fraction
checks=[]
for idx in range(9):
 r=read(OUT/f'small/case-{idx:03d}/native/trial-1/result.json')
 nodes=r['debug_nodes'];candidate_states={statekey(n['state']) for n in nodes if n['candidate']}
 samples=r['witness_samples']
 checks.append({'case_index':idx,'backend':r['actual_backend'],'cutoffs':r['cutoffs'],'sample_structure':type(samples).__name__,'sample_count':len(samples)})
 for w in samples:
  target=replay_branch(r['record'],w['steps'])['state']
  expected=replay(r['record']['initial'],r['record']['cards'],w['steps'])
  assert statekey(target)==statekey(expected) and statekey(target) in candidate_states
checks_file=HERE/'public-witnesses.json';save(checks_file,checks)
path=OUT/'small/case-008/native/trial-1/result.json'
run('adaptive-root',['--expand',path,'--output',OUT/'adaptive-root.json'])
root=read(OUT/'adaptive-root.json')
print(json.dumps({'choices':root['choices']},ensure_ascii=False)[:12000])
