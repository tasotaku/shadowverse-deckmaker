"""Independent, exhaustive finite-assignment oracle for ability-free combat.

No production solver import. Each follower attacks at most once, so choose its
target and optional evolution timing. For each enemy the total assigned damage
determines survival; if lethal, enumerate every feasible last hitter (all other
damage must sum to strictly less than initial health). Other attack order cannot
affect an ability-free endpoint. Different target groups commute. This covers
every legal prefix, including deliberately unused attacks and post-attack evo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from functools import lru_cache
from itertools import product
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from svdeck.battle_env.battle import Battle  # noqa: E402


def build(case: dict[str, Any]) -> Battle:
    # AI_NOTE: Only public Battle input normalization is shared with verification.
    players = []
    for side, name in enumerate(('own', 'enemy')):
        board = [dict(({'attack': v[0], 'health': v[1]} if isinstance(v, list) else v),
                      card_id='body', id=f'{side}-{i}') for i, v in enumerate(case[name])]
        players.append(dict(board=board, health=case.get('face', 100), max_health=max(20, case.get('face', 100)),
                            turn=case.get('turn', 7), ep=case.get('ep', 2), sep=case.get('sep', 2),
                            evolved_this_turn=case.get('used', False)))
    owner = case.get('owner', 0)
    if owner:
        players.reverse()
    return Battle(dict(players=players, active_player=owner),
                  {'body': dict(kind='follower', name='Reference body', cost=1, attack=1, health=1)}, record=False)


def endpoint(battle: Battle) -> tuple[Any, ...]:
    # AI_NOTE: Endpoint equality intentionally omits identities and attack rights.
    owner = battle.state['active_player']
    if battle.state['winner'] == owner:
        return ('WIN',)
    own, enemy = (battle.state['players'][i] for i in (owner, 1-owner))
    boards = [tuple(sorted(tuple(b[k] for k in ('attack', 'health', 'max_health', 'evolved'))
                           for b in p['board'])) for p in (own, enemy)]
    return (*boards, enemy['health'], own['ep'], own['sep'])


def signature(value: tuple[Any, ...]) -> str:
    # AI_NOTE: This stable format matches the public benchmark output contract.
    return 'WIN' if value == ('WIN',) else json.dumps(value, separators=(',', ':'))


@lru_cache(maxsize=300000)
def covers(larger: tuple[Any, ...], smaller: tuple[Any, ...]) -> bool:
    # AI_NOTE: Independent bipartite subset matching compares all three stats.
    if len(larger) < len(smaller):
        return False
    masks = [sum(1 << i for i, x in enumerate(larger)
                 if x[3] == y[3] and all(x[k] >= y[k] for k in range(3))) for y in smaller]
    reachable = {0}
    for mask in sorted(masks, key=int.bit_count):
        reachable = {used | (1 << i) for used in reachable for i in range(len(larger))
                     if mask & (1 << i) and not used & (1 << i)}
        if not reachable:
            return False
    return True


def frontier(states: dict[tuple[Any, ...], list[dict[str, Any]]]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    # AI_NOTE: Strictly increasing utility under dominance allows a one-way scan;
    # it is only an ordering, never a top-k or approximate acceptance criterion.
    if ('WIN',) in states:
        return {('WIN',): states[('WIN',)]}
    def utility(s: tuple[Any, ...]) -> int:
        return int(sum(sum(b[:3])+1 for b in s[0])-sum(sum(b[:3])+1 for b in s[1])-s[2]+s[3]+s[4])
    ordered = sorted(states, key=utility, reverse=True)
    def necessary(s: tuple[Any, ...]) -> tuple[int, ...]:
        # AI_NOTE: Sums/counts only reject impossible dominance; exact matching remains mandatory.
        return (s[3], s[4], -s[2], *(sum(b[3] == e for b in s[0]) for e in range(3)),
                *(-sum(b[3] == e for b in s[1]) for e in range(3)),
                *(sum(b[k] for b in s[0]) for k in range(3)),
                *(-sum(b[k] for b in s[1]) for k in range(3)),
                *(v for k in range(3) for v in sorted([b[k] for b in s[0]]+[0]*5, reverse=True)[:5]),
                *(-v for k in range(3) for v in sorted([b[k] for b in s[1]]+[0]*5, reverse=True)[:5]))
    dimensions = [necessary(s) for s in ordered]
    indexes = []
    for dimension in zip(*dimensions):
        groups: dict[int, int] = {}
        for i, v in enumerate(dimension):
            groups[v] = groups.get(v, 0) | (1 << i)
        running = 0
        for v in sorted(groups, reverse=True):
            running |= groups[v]
            groups[v] = running
        indexes.append(groups)
    kept: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    kept_mask = 0
    for index, (b, dims) in enumerate(zip(ordered, dimensions)):
        candidates = kept_mask
        for axis, v in enumerate(dims):
            candidates &= indexes[axis][v]
            if not candidates:
                break
        dominated = False
        while candidates:
            bit = candidates & -candidates
            a = ordered[bit.bit_length()-1]
            if covers(a[0], b[0]) and covers(b[1], a[1]):
                dominated = True
                break
            candidates -= bit
        if not dominated:
            kept[b] = states[b]
            kept_mask |= 1 << index
    return kept


def enumerate_assignments(case: dict[str, Any]) -> tuple[dict[tuple[Any, ...], list[dict[str, Any]]], int]:
    # AI_NOTE: Enumerate target assignments and legal last hitters, not solver states.
    initial = build(case)
    owner = initial.state['active_player']
    p, q = (initial.state['players'][i] for i in (owner, 1-owner))
    own, enemy = p['board'], q['board']
    plans = [(-1, 0, False)]
    if not p['evolved_this_turn']:
        for i, b in enumerate(own):
            if b['evolved']:
                continue
            for level, resource, threshold in ((1, 'ep', 5-owner), (2, 'sep', 7-owner)):
                if p[resource] and p['turn'] >= threshold and (case['mode'] == 'super' or level == 1 and case['mode'] == 'evolve'):
                    plans.extend((i, level, after) for after in (False, True))
    states: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    assignments = 0
    for evolved, level, after in plans:
        amount = level+1 if level else 0
        bodies = [tuple(b[k] for k in ('attack', 'health', 'max_health', 'evolved')) for b in own]
        attack_bodies = bodies.copy()
        if evolved >= 0 and not after:
            a, h, m, _ = bodies[evolved]
            attack_bodies[evolved] = (a+amount, h+amount, m+amount, level)
        options = []
        for i, b in enumerate(own):
            ready = b['entered_turn'] < p['turn']
            choices = [-2]
            if not b['attacks']:
                if ready or attack_bodies[i][3]:
                    choices += list(range(len(enemy)))
                if ready:
                    choices.append(-1)
            options.append(choices)
        for targets in product(*options):
            assignments += 1
            survivors = list(attack_bodies)
            possible = True
            for i, target in enumerate(targets):
                a, h, m, e = survivors[i]
                if target >= 0 and e != 2:
                    h -= enemy[target]['attack']
                if i == evolved and after:
                    if h <= 0:
                        possible = False
                        break
                    a, h, m, e = a+amount, h+amount, m+amount, level
                survivors[i] = (a, h, m, e)
            if not possible:
                continue
            orders = []
            enemy_result = []
            for j, b in enumerate(enemy):
                group = tuple(i for i, target in enumerate(targets) if target == j)
                damage = sum(attack_bodies[i][0] for i in group)
                if damage < b['health']:
                    enemy_result.append((b['attack'], b['health']-damage, b['max_health'], b['evolved']))
                    orders.append([(group, 0)])
                else:
                    orders.append([(tuple(i for i in group if i != last)+(last,), int(attack_bodies[last][3] == 2))
                                   for last in group if damage-attack_bodies[last][0] < b['health']])
            for selected in product(*orders):
                actions = []
                def add_evolution() -> None:
                    actions.append(dict(type='evolve' if level == 1 else 'super_evolve', source=own[evolved]['id']))
                if evolved >= 0 and targets[evolved] == -2:
                    add_evolution()
                for group, _ in selected:
                    for i in group:
                        if i == evolved and not after:
                            add_evolution()
                        actions.append(dict(type='attack', source=own[i]['id'], target=enemy[targets[i]]['id']))
                        if i == evolved and after:
                            add_evolution()
                for i, target in enumerate(targets):
                    if target == -1:
                        if i == evolved and not after:
                            add_evolution()
                        actions.append(dict(type='attack', source=own[i]['id'], target=f'leader:{1-owner}'))
                        if i == evolved and after:
                            add_evolution()
                health = q['health']-sum(attack_bodies[i][0] for i, target in enumerate(targets) if target == -1)-sum(ping for _, ping in selected)
                result = (tuple(sorted(b for b in survivors if b[1] > 0)), tuple(sorted(enemy_result)), health,
                          p['ep']-int(level == 1), p['sep']-int(level == 2)) if health > 0 else ('WIN',)
                states.setdefault(result, actions)
    return states, assignments


def engine_states(case: dict[str, Any]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    # AI_NOTE: Small-case validation exhausts all public legal sequences with no pruning.
    pending: list[tuple[Battle, list[dict[str, Any]]]] = [(build(case), [])]
    states: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    allowed = {'attack'} | ({'evolve'} if case['mode'] != 'attack' else set()) | ({'super_evolve'} if case['mode'] == 'super' else set())
    while pending:
        battle, actions = pending.pop()
        states.setdefault(endpoint(battle), actions)
        for action in battle.legal_actions():
            if action['type'] in allowed:
                child = Battle(battle.state, battle.cards, record=False)
                child.step(action)
                pending.append((child, actions+[action]))
    return states


def certify(case: dict[str, Any], small: bool = False) -> dict[str, Any]:
    # AI_NOTE: Replay every retained witness; small checks compare every endpoint too.
    started = perf_counter()
    states, count = enumerate_assignments(case)
    if not small:
        print('ENUMERATED', case['id'], count, len(states), perf_counter()-started, flush=True)
    if small:
        actual = engine_states(case)
        assert states.keys() == actual.keys(), (case['id'], 'endpoint mismatch', len(states), len(actual),
                                                list(states.keys()-actual.keys())[:2], list(actual.keys()-states.keys())[:2])
    result = frontier(states)
    if not small:
        print('FRONTIER', case['id'], len(result), perf_counter()-started, flush=True)
    for expected, actions in result.items():
        battle = build(case)
        for action in actions:
            if battle.state['winner'] is not None:
                break
            battle.step(action)
        assert endpoint(battle) == expected, (case['id'], 'witness mismatch', expected, endpoint(battle), actions)
    signatures = sorted(signature(s) for s in result)
    return dict(id=case['id'], status='PASS', complete=True, expected=signatures,
                expected_sha256=hashlib.sha256(json.dumps(signatures).encode()).hexdigest(),
                case_sha256=hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest(),
                assignments=count, endpoints=len(states), candidate_count=len(result),
                witness_replay_checked=len(result), witnesses={signature(s): a for s, a in result.items()},
                elapsed_seconds=perf_counter()-started, engine_all_endpoints=small)


def main() -> None:
    # AI_NOTE: The fixture remains independent of all production solver answers.
    parser = argparse.ArgumentParser()
    parser.add_argument('--case')
    parser.add_argument('--small-only', action='store_true')
    args = parser.parse_args()
    cases_path = ROOT/'tests/fixtures/combat_hard_cases.json'
    cases = json.loads(cases_path.read_text(encoding='utf-8-sig'))
    small_cases = json.loads((ROOT/'src/svdeck/battle_env/data/combat_benchmark_cases.json').read_text(encoding='utf-8'))
    small_cases = [c for c in small_cases if c['oracle']]
    small_cases.append(dict(id='post-attack-evolution-super-finisher', own=[[1, 4],
                            dict(attack=1, health=4, evolved=2, entered_turn=7)], enemy=[[0, 2]],
                            turn=7, ep=1, sep=0, face=100, mode='evolve'))
    small_cases += [{**c, 'id': c['id']+'-small', 'own': c['own'][:2], 'enemy': c['enemy'][:2]} for c in cases]
    report: dict[str, Any] = dict(schema_version=1, status='RUNNING', complete=False, method='complete finite target assignments; all feasible last hitters; pre/post evolution; exact injective dominance',
                  independence='Production battle_combat.py was not read or imported. Expected values never use production solver output.',
                  generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  engine_sha256=hashlib.sha256((ROOT/'src/svdeck/battle_env/battle.py').read_bytes()).hexdigest(),
                  fixtures_sha256=hashlib.sha256(cases_path.read_bytes()).hexdigest(), small_validation=[], cases=[])
    output = ROOT/'tests/fixtures/combat_hard_answers.json'
    for case in small_cases if not args.case else []:
        result = certify(case, small=True)
        result.pop('witnesses')
        report['small_validation'].append(result)
        print(case['id'], result['endpoints'], result['candidate_count'], flush=True)
    if not args.small_only:
        for case in cases:
            if args.case and case['id'] != args.case:
                continue
            print('START', case['id'], flush=True)
            result = certify(case)
            report['cases'].append(result)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            print(case['id'], result['endpoints'], result['candidate_count'], result['elapsed_seconds'], flush=True)
    report['status'] = 'PASS'
    report['complete'] = True
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
