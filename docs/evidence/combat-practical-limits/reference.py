"""Independent stress-only exhaustive oracle through production Battle semantics.
Run from repository root with PYTHONPATH=src. No fast-kernel implementation used.
"""
import json
import time
from fractions import Fraction
from pathlib import Path
from svdeck.battle import Battle
from svdeck.battle_practical import ChanceBattle, Chance

case = json.loads(Path('docs/evidence/combat-practical/stress/input.json').read_text(encoding='utf-8'))
root = ChanceBattle(Battle(case['state'], case['cards']).state, case['cards'], record=False)
started = time.perf_counter()
cache = {}
transitions = 0

def key(battle):
    state = battle.state
    return (state['winner'], tuple((
        p['health'], p['pp'], p['ep'], p['sep'], p['evolved_this_turn'],
        tuple(e['id'] for e in p['hand']),
        tuple((e['id'], e['attack'], e['health'], e['evolved'], e['attacks'], tuple(e['keywords'])) for e in p['board'])
    ) for p in state['players']))

def value(battle):
    own, enemy = battle.state['players']
    score = own['health']-enemy['health']+3*len(own['hand'])+own['pp']+3*own['ep']+5*own['sep']
    for sign, player in ((1, own), (-1, enemy)):
        score += sign*sum(2+2*e['attack']+e['health']+2*len(e['keywords']) for e in player['board'])
    return Fraction(score)

def visit(battle):
    global transitions
    marker = key(battle)
    if marker in cache:
        return cache[marker]
    if time.perf_counter()-started > 180:
        raise TimeoutError
    best = value(battle)
    for action in battle.legal_actions():
        if action['type'] == 'end_turn':
            continue
        pending = [((), Fraction(1))]
        total = Fraction(0)
        while pending:
            draws, probability = pending.pop()
            try:
                child = battle.branch(action, draws)
            except Chance as chance:
                pending.extend((draws+(i,), probability/chance.size) for i in range(chance.size))
            else:
                total += probability*visit(child)
                transitions += 1
        best = max(best, total)
    cache[marker] = best
    if len(cache)%100000 == 0:
        print('progress', len(cache), transitions, time.perf_counter()-started, flush=True)
    return best

if __name__ == '__main__':
    print('RESULT', visit(root), 'nodes', len(cache), 'transitions', transitions, 'seconds', time.perf_counter()-started, flush=True)
