"""Independent tiny-case oracle; imports only the public Battle engine.

Enumerates legal current-turn actions and every uniform random-index outcome.
The Fraction Bellman recurrence maximizes AFTER observing each completed action.
No production practical solver, heuristic, search key, or pruning is reused.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterator
import copy
from fractions import Fraction
import json
from pathlib import Path
import sys
import time
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from svdeck.battle_env.battle import Battle


class NeedRandom(Exception):
    def __init__(self, length: int) -> None:
        self.length = length


class ReplayBattle(Battle):
    tape: tuple[int, ...]
    cursor: int

    def random_index(self, length: int) -> int:
        if self.cursor == len(self.tape):
            raise NeedRandom(length)
        value = self.tape[self.cursor]
        self.cursor += 1
        assert 0 <= value < length
        # Keep the public engine's RNG state transition, substitute only outcome.
        super().random_index(length)
        return value


def replay(battle: Battle, action: dict[str, Any], tape: tuple[int, ...]) -> ReplayBattle:
    copied = copy.deepcopy(battle)
    copied.__class__ = ReplayBattle
    result = cast(ReplayBattle, copied)
    result.tape, result.cursor = tape, 0
    result.step(action)
    assert result.cursor == len(tape)
    return result


def branches(battle: Battle, action: dict[str, Any]) -> Iterator[tuple[Fraction, tuple[int, ...], ReplayBattle]]:
    pending: list[tuple[tuple[int, ...], Fraction]] = [((), Fraction(1))]
    while pending:
        tape, mass = pending.pop()
        try:
            after = replay(battle, action, tape)
        except NeedRandom as need:
            pending.extend((tape + (i,), mass / need.length) for i in range(need.length))
            continue
        # Independently replay every emitted branch through public step again.
        assert replay(battle, action, tape).state == after.state
        yield mass, tape, after


def state_key(battle: Battle) -> str:
    state = copy.deepcopy(battle.state)
    state.pop('rng')  # future random choices are uniform, never seed predictions
    return json.dumps(state, ensure_ascii=False, sort_keys=True)


def solve_case(case: dict[str, Any], seed: int | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    state = copy.deepcopy(case['state'])
    if seed is not None:
        state['rng'] = seed
    root = Battle(state, case['cards'], record=False)
    owner = root.state['active_player']
    memo: dict[str, Fraction] = {}
    rows: dict[str, list[dict[str, Any]]] = {}
    stats = {'states': 0, 'actions': 0, 'random_branches': 0, 'replayed_branches': 0}

    def visit(battle: Battle) -> Fraction:
        if battle.state['winner'] is not None:
            return Fraction(battle.state['winner'] == owner)
        key = state_key(battle)
        if key in memo:
            return memo[key]
        stats['states'] += 1
        best = Fraction(0)  # stopping is allowed; do not execute end_turn/draw
        values = []
        for action in battle.legal_actions():
            if action['type'] == 'end_turn':
                continue
            stats['actions'] += 1
            value = Fraction(0)
            outcomes = []
            total = Fraction(0)
            for mass, tape, after in branches(battle, action):
                total += mass
                stats['replayed_branches'] += 1
                stats['random_branches'] += bool(tape)
                continuation = visit(after)
                value += mass * continuation
                outcomes.append({'probability': str(mass), 'random_indices': list(tape),
                                 'continuation_value': str(continuation),
                                 'state': after.state,
                                 'best_next_actions': [r['action'] for r in rows.get(state_key(after), [])
                                                       if Fraction(r['win_probability']) == continuation]})
            assert total == 1
            values.append({'action': action, 'win_probability': str(value), 'outcomes': outcomes})
            best = max(best, value)
        memo[key] = best
        rows[key] = values
        return best

    value = visit(root)
    root_rows = rows.get(state_key(root), [])
    result = {'id': case['id'], 'win_probability': str(value),
              'best_first_actions': [r['action'] for r in root_rows if Fraction(r['win_probability']) == value],
              'action_values': root_rows, 'stats': stats, 'elapsed_seconds': time.perf_counter() - started}
    expected = case['expected']
    assert value == Fraction(expected['win_probability']), (case['id'], result)
    if 'unique_best_first_action' in expected:
        assert result['best_first_actions'] == [expected['unique_best_first_action']], (case['id'], result['best_first_actions'])
    for anchor in expected.get('action_values', []):
        assert next(r['win_probability'] for r in root_rows if r['action'] == anchor['action']) == anchor['win_probability']
    counterexample = expected.get('fixed_rng_counterexample')
    if counterexample:
        # Demonstrate the concrete bad choice made by predicting one seed.
        for label, should_win in [('losing_higher_probability_action', False),
                                  ('winning_lower_probability_action', True)]:
            fixed_state = copy.deepcopy(case['state'])
            fixed_state['rng'] = counterexample['seed']
            fixed = Battle(fixed_state, case['cards'], record=False)
            fixed.step(counterexample[label])
            face = {'type': 'attack', 'source': 'a', 'target': f'leader:{1-owner}'}
            if face in fixed.legal_actions():
                fixed.step(face)
            assert (fixed.state['winner'] == owner) == should_win
    for anchor in expected.get('replay_anchors', []):
        b = copy.deepcopy(root)
        for action in anchor['actions']:
            b.step(action)
        enemy = b.state['players'][1-owner]['board']
        if 'enemy_leader_health' in anchor:
            assert b.state['players'][1-owner]['health'] == anchor['enemy_leader_health']
        assert [e['id'] for e in enemy] == anchor['enemy_board_ids']
        for e in enemy:
            if e['id'] in anchor.get('enemy_health', {}):
                assert e['health'] == anchor['enemy_health'][e['id']]
            if e['id'] in anchor.get('enemy_keywords', {}):
                assert e['keywords'] == anchor['enemy_keywords'][e['id']]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=Path(__file__).resolve().parents[1] / 'tests/fixtures/combat_practical_cases.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; independent reference evidence must never be overwritten')
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    results = []
    for case in cases:
        result = solve_case(case)
        result['seed_checks'] = []
        for seed in case['expected'].get('seed_independence', []):
            seeded = solve_case(case, seed)
            assert seeded['win_probability'] == result['win_probability']
            assert seeded['best_first_actions'] == result['best_first_actions']
            result['seed_checks'].append(seed)
        results.append(result)
        print(case['id'], result['win_probability'], result['stats'], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump({'method': 'independent public Battle exhaustive uniform-outcome Fraction recurrence', 'cases': results}, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
