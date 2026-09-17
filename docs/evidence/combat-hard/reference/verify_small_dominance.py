"""Independent factorial matching checks for the reference's subset matcher."""
import json
import random
import sys
from itertools import permutations
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'scripts'))
import combat_reference as reference


def brute_covers(larger, smaller):
    return any(all(x[3] == y[3] and all(x[k] >= y[k] for k in range(3))
                   for x, y in zip(order, smaller))
               for order in permutations(larger, len(smaller)))


def dominates(a, b):
    if a == ('WIN',) or b == ('WIN',):
        return a == ('WIN',)
    return (a[2] <= b[2] and a[3] >= b[3] and a[4] >= b[4]
            and brute_covers(a[0], b[0]) and brute_covers(b[1], a[1]))

rng = random.Random(9172026)
rows = []
for i in range(35):
    case = dict(id=f'heldout-{i}', mode=['attack','evolve','super'][i % 3],
                own=[dict(attack=rng.randrange(4), health=rng.randrange(1,5), max_health=6,
                          entered_turn=7 if rng.randrange(3)==0 else 0,
                          attacks=1 if rng.randrange(5)==0 else 0) for _ in range(2)],
                enemy=[[rng.randrange(4), rng.randrange(1,5)] for _ in range(2)],
                face=rng.choice([2,5,100]), ep=1, sep=1)
    states, _ = reference.enumerate_assignments(case)
    engine = reference.engine_states(case)
    assert states.keys() == engine.keys(), (i, 'endpoint sets')
    brute = {b for b in engine if not any(a != b and dominates(a,b) for a in engine)}
    actual = set(reference.frontier(states))
    assert actual == brute, (i, 'frontier')
    rows.append(dict(id=case['id'], endpoints=len(states), candidates=len(actual)))
print(json.dumps(dict(status='PASS', cases=rows), indent=2))
