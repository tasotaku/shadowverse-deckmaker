"""Exact state-set and per-transition checks for the optional compiled kernel."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

pytest.importorskip('numba')
import numpy as np

from svdeck.battle.battle import Battle, Json
from svdeck.battle.battle_frontier_fast import Kernel, eligible
from svdeck.battle.battle_frontier_native import NativeSearch, _numeric_id, enumerate_native, prepare
from svdeck.battle.battle_frontier_native_core import _actions, _pack, _transition, _unpack
from svdeck.battle.battle_frontier_native_delta import _combat_key, _spell_key
from svdeck.battle.battle_practical import ChanceBattle
from test_battle_frontier_fast import scenario, semantic


@pytest.mark.parametrize('seed', range(96))
def test_native_all_transitions(seed: int) -> None:
    # AI_NOTE: Compare every native legal action and chance branch at ten generated states against the reference kernel.
    kernel = Kernel(scenario(seed))
    layout, prototypes, spells, config, static, hand_ids = prepare(kernel)
    state = kernel.initial
    rng = random.Random(seed)
    actions = np.empty((128, 3), dtype=np.int64)
    for _ in range(10):
        packed = tuple(np.uint64(value) for value in _pack(np.array(state, dtype=np.int64), layout))
        assert tuple(map(int, _unpack(packed, layout))) == state
        native_state = np.array(state, dtype=np.int64)
        count = _actions(native_state, prototypes, spells, config, actions)
        reference_actions = kernel.actions(state)
        assert count == len(reference_actions)
        adapter = NativeSearch(kernel, np.array([packed], dtype=np.uint64), layout,
                               np.zeros((1, 3), dtype=np.int32), 0, False, [], {})
        choices = []
        for native_action, action in zip(actions[:count], reference_actions):
            kind, source, target = map(int, native_action)
            code = kind*256+source*16+target+1
            assert adapter.action(0, code) == action
            enemies = [slot for slot in range(kernel.n, kernel.count) if state[slot] > 0]
            for child, _, draws in kernel.outcomes(state, action):
                random_target = enemies[draws[0]] if draws else -1
                result = _transition(native_state, kind, source, target, random_target,
                                     prototypes, spells, config, static, hand_ids)
                assert tuple(map(int, result)) == child, (seed, action, draws)
                if kind != 1:
                    delta_key = tuple(np.uint64(value) for value in
                                      _combat_key(native_state, packed, kind, source, target, layout, prototypes, config))
                    assert tuple(map(int, _unpack(delta_key, layout))) == child, (seed, action, draws)
                else:
                    delta_key = tuple(np.uint64(value) for value in
                                      _spell_key(native_state, packed, source, target, random_target, layout,
                                                 prototypes, spells, config, static, hand_ids))
                    assert tuple(map(int, _unpack(delta_key, layout))) == child, (seed, action, draws)
                choices.append(child)
        if not choices:
            break
        state = rng.choice(choices)


CASES = json.loads((Path(__file__).parent/'fixtures/turn_frontier_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_native_complete_reachable_set(case: Json) -> None:
    # AI_NOTE: Independently enumerate Kernel's full reachable closure, then replay every native witness through Battle.
    battle = Battle(case['state'], case['cards'])
    if not eligible(battle):
        pytest.skip('compound effect belongs to generic backend')
    reference = Kernel(battle)
    seen = {reference.initial}
    pending = [reference.initial]
    choices, outcomes = 0, 0
    while pending:
        state = pending.pop()
        for action in reference.actions(state):
            choices += 1
            for child, _, _ in reference.outcomes(state, action):
                outcomes += 1
                if child not in seen:
                    seen.add(child)
                    pending.append(child)
    result = enumerate_native(battle, max_states=max(1, len(seen)), seconds=10)
    assert result.complete
    assert set(result.states) == seen
    assert result.stats['choices'] == choices
    assert result.stats['outcomes'] == outcomes
    # AI_NOTE: Reusing budget lookups must still count repeated draws and previously seen children exactly once each.
    assert result.stats['duplicate_outcomes'] == outcomes-(len(seen)-1)
    for node, state in enumerate(result.states):
        current = ChanceBattle(battle.state, battle.cards, record=False)
        for step in result.witness_steps(node):
            current = current.branch(step['action'], tuple(step['draws']))
        assert semantic(current.state) == semantic(result.kernel.state(state))


def test_native_chance_and_state_budgets() -> None:
    # AI_NOTE: A random decision with several new results must be rejected as a whole when budgets cannot fit it.
    case = next(case for case in CASES if case['id'] == 'random_bad_outcome_retained')
    battle = Battle(case['state'], case['cards'])
    states = enumerate_native(battle, max_states=1)
    assert not states.complete and states.cutoffs == ['states'] and len(states.states) == 1
    chance = enumerate_native(battle, max_outcomes=1)
    assert not chance.complete and chance.cutoffs == ['chance outcomes'] and len(chance.states) == 1
    timed = enumerate_native(battle, seconds=0)
    assert not timed.complete and timed.cutoffs == ['time'] and len(timed.states) == 1


def test_native_rejects_oversized_packing() -> None:
    # AI_NOTE: Extreme imported numerical states fall back instead of silently colliding packed keys.
    battle = scenario(3)
    for player in battle.state['players']:
        for entity in player['board']:
            entity['health'] = 2**59
    with pytest.raises(ValueError, match='192 bits'):
        prepare(Kernel(battle))


@pytest.mark.parametrize('field', ['attack', 'max_health', 'entered_turn'])
def test_native_rejects_large_prototype_before_numpy(field: str) -> None:
    # AI_NOTE: Out-of-range Python integers must produce a fallback-compatible ValueError, never NumPy OverflowError.
    kernel = Kernel(scenario(3))
    kernel.prototypes[0][field] = 2**80
    with pytest.raises(ValueError, match='operands'):
        prepare(kernel)


def test_native_rejects_large_spell_before_numpy() -> None:
    # AI_NOTE: A large imported damage amount is checked before constructing a signed native array.
    kernel = Kernel(scenario(0))
    kernel.spells[0][1]['amount'] = 2**80
    with pytest.raises(ValueError, match='operands'):
        prepare(kernel)


def test_native_very_long_entity_id() -> None:
    # AI_NOTE: Arbitrary identifiers cannot collide with bounded fresh IDs and must not trigger Python's decimal digit guard.
    assert _numeric_id('e'+'9'*5000) == -1
    assert _numeric_id('e0001') == -1
    assert _numeric_id('e9223372036854775808') == -1
    assert _numeric_id('e123') == 123


@pytest.mark.parametrize('op', ['damage', 'split_damage'])
@pytest.mark.parametrize('amount', [-2**59, -1, 0])
def test_native_nonpositive_damage_matches_reference(op: str, amount: int) -> None:
    # AI_NOTE: Negative and zero amounts are supported by the existing kernel; they must not consume barriers differently.
    kernel = Kernel(scenario(0))
    effect: Json = {'op': op, 'amount': amount}
    if op == 'damage':
        effect['target'] = 'chosen_enemy'
    kernel.spells[0] = (0, effect)
    _, prototypes, spells, config, static, hand_ids = prepare(kernel)
    target = kernel.n if op == 'damage' else -1
    state = np.array(kernel.initial, dtype=np.int64)
    actual = _transition(state, 1, 0, target, -1, prototypes, spells, config, static, hand_ids)
    action: Json = {'type': 'play', 'card': kernel.hand[0]['id']}
    if target >= 0:
        action['target'] = kernel._id(kernel.initial, target)
    expected = kernel.outcomes(kernel.initial, action)[0][0]
    assert tuple(map(int, actual)) == expected
