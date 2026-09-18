from client import *
from svdeck import combat_benchmark as bench
allcases=json.loads(Path('tests/fixtures/combat_hard_cases.json').read_text(encoding='utf-8'))
c=next(c for c in allcases if c['id']=='timing-finisher-5v5');save('legacy-case.json',c)
r=post('legacy','/api/combat',{'record':bench.make_battle(c).export(),'cursor':0,'mode':c['mode']})
print(json.dumps({k:v for k,v in r.items() if k not in ['candidates','record']},ensure_ascii=False));print('candidates',len(r.get('candidates',[])))
save('legacy-check.json',{'public_doc':'docs/combat-benchmark.md','documented_expected_candidates':858,'actual_candidates':len(r.get('candidates',[])),'complete':r.get('complete')})
