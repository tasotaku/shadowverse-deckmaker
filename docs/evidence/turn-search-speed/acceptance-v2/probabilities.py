from run import *
from fractions import Fraction
from collections import defaultdict
items=[]
for idx in [4,7,8]:
 r=read(OUT/f'small/case-{idx:03d}/native/trial-1/result.json');groups=[]
 for ni,n in enumerate(r['debug_nodes']):
  for c in n['conditional']:
   if len(c['outcomes'])>1 or any(o['draws'] for o in c['outcomes']):
    mass=sum((Fraction(o['probability']) for o in c['outcomes']),Fraction())
    groups.append({'node_index':ni,'action':c['action'],'mass':str(mass),'outcomes':[{'probability':o['probability'],'draws':o['draws'],'state':o['state']} for o in c['outcomes']]})
 items.append({'case_index':idx,'result_path':str(OUT/f'small/case-{idx:03d}/native/trial-1/result.json'),'all_random_groups_mass_one':all(g['mass']=='1' for g in groups),'groups':groups})
save(HERE/'random-probabilities.json',items)
