"""Compiled skyline must preserve the complete existing endpoint semantics."""
from __future__ import annotations

from time import perf_counter

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('numba')

from svdeck.battle import Battle
from svdeck.battle_frontier_fast import Kernel
from svdeck.battle_frontier_packed import frontier as reference
from svdeck.battle_frontier_skyline import frontier
from test_battle_frontier_fast import scenario


def packed(states):
    # AI_NOTE: 探索実装と独立に列ごとの厳密範囲を詰め、decoderと負の進化値を検査する。
    layout = []
    word, shift = 0, 0
    for values in zip(*states):
        bias = max(0, -min(values))
        bits = max(1, (max(values)+bias).bit_length())
        if shift+bits > 64:
            word, shift = word+1, 0
        assert word < 3
        layout.append((word, shift, (1 << bits)-1, bias))
        shift += bits
    keys = np.zeros((len(states), 3), dtype=np.uint64)
    for index, state in enumerate(states):
        for value, (word, shift, mask, bias) in zip(state, layout):
            keys[index, word] |= np.uint64(value+bias) << np.uint64(shift)
    return keys, np.asarray(layout, dtype=np.int64)


def reachable(kernel):
    # AI_NOTE: 枝刈りなしで全停止点を列挙し、途中状態を選別する実装への循環依存を避ける。
    states = [kernel.initial]
    seen = set(states)
    for state in states:
        for action in kernel.actions(state):
            for child, _, _ in kernel.outcomes(state, action):
                if child not in seen:
                    seen.add(child)
                    states.append(child)
    return states


@pytest.mark.parametrize('seed', range(96))
def test_complete_candidate_equality(seed):
    # AI_NOTE: 異なる手札・5能力・進化・生成順を持つ全状態について、等価代表を含め完全一致を求める。
    kernel = Kernel(scenario(seed))
    states = reachable(kernel)
    keys, layout = packed(states)
    before = keys.copy()
    expected, complete = reference(kernel, states, float('inf'))
    actual, finished = frontier(kernel, keys, layout, float('inf'), batch_size=7)
    assert complete and finished
    assert actual == expected
    assert np.array_equal(keys, before)


def test_identity_equivalence_and_later_dominance():
    # AI_NOTE: 異なるslotの同能力フォロワーは同形状になる。後から来る上位候補への置換を確かめる。
    cards = {'f': {'name': 'F', 'kind': 'follower', 'cost': 1, 'attack': 2, 'health': 3}}
    battle = Battle({'players': [{'board': [{'id': 'a', 'card_id': 'f'}, {'id': 'b', 'card_id': 'f'}]}, {}]}, cards)
    kernel = Kernel(battle)
    states = []
    for health in (1, 2, 3, 2, 1):
        for alive in (0, 1):
            state = list(kernel.initial)
            state[alive], state[1-alive] = health, 0
            states.append(tuple(state))
    keys, layout = packed(states)
    expected, _ = reference(kernel, states, float('inf'))
    actual, complete = frontier(kernel, keys, layout, float('inf'))
    assert complete and actual == expected and len(actual) == 1


def test_large_values_and_timeout():
    # AI_NOTE: 8bit外の値を切り詰めない。期限切れを完全なPareto候補と表示しない。
    battle = scenario(0)
    battle.state['players'][0]['board'][0].update(health=50000, max_health=50000, attack=60000)
    kernel = Kernel(battle)
    states = reachable(kernel)
    keys, layout = packed(states)
    actual, complete = frontier(kernel, keys, layout, float('inf'))
    assert complete and actual == reference(kernel, states, float('inf'))[0]
    actual, complete = frontier(kernel, keys, layout, perf_counter()-1)
    assert not complete and actual == list(range(len(states)))
    with pytest.raises(ValueError, match='positive'):
        frontier(kernel, keys, layout, float('inf'), batch_size=0)
