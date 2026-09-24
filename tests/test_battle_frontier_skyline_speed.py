"""Exact skyline optimization boundaries and insertion-order invariants."""
from __future__ import annotations

from itertools import permutations

import pytest

pytest.importorskip('numpy')
pytest.importorskip('numba')

import numpy as np

from svdeck.battle import Battle
from svdeck.battle_frontier_fast import Kernel
from svdeck.battle_frontier_packed import frontier as reference
from svdeck.battle_frontier_skyline import _packed_relation, frontier
from test_battle_frontier_skyline import packed


def test_guarded_lane_boundaries() -> None:
    # AI_NOTE: Each guard must isolate low/high neighboring lanes, including zero, 128, 255 and unequal hands.
    rng = np.random.default_rng(90712)
    values = [0, 1, 127, 128, 254, 255]
    for trial in range(1000):
        left = rng.choice(values, size=14)
        right = rng.choice(values, size=14)
        left_hand, right_hand = map(int, rng.integers(0, 1024, size=2))
        if trial % 3 == 1:
            left, right = np.maximum(left, right), np.minimum(left, right)
            left_hand = 1023
        elif trial % 3 == 2:
            left, right = np.minimum(left, right), np.maximum(left, right)
            right_hand = 1023
        a, b = np.zeros(3, dtype=np.uint64), np.zeros(3, dtype=np.uint64)
        for index in range(14):
            a[index//7] |= np.uint64(left[index]) << np.uint64(9*(index % 7))
            b[index//7] |= np.uint64(right[index]) << np.uint64(9*(index % 7))
        a[-1], b[-1] = left_hand, right_hand
        ad = left_hand & right_hand == right_hand and bool(np.all(left >= right))
        bd = right_hand & left_hand == left_hand and bool(np.all(right >= left))
        assert _packed_relation(a, b) == (-1 if ad else 1 if bd else 0)
        assert _packed_relation(a, a) == -1


@pytest.mark.parametrize('order', list(permutations(range(5))))
def test_insertion_order_and_resource_tradeoffs(order: tuple[int, ...]) -> None:
    # AI_NOTE: All arrival orders include equal endpoints, hand/resource tradeoffs and a later dominating endpoint.
    cards = {'f': {'name': 'F', 'kind': 'follower', 'cost': 1, 'attack': 2, 'health': 5},
             's': {'name': 'S', 'kind': 'spell', 'cost': 1, 'effects': [{'op': 'damage', 'amount': 1, 'target': 'chosen_enemy'}]}}
    battle = Battle({'players': [{'pp': 4, 'max_pp': 4, 'hand': ['s', 's', 's'], 'board': [{'id': 'a', 'card_id': 'f'}]}, {}]}, cards)
    kernel = Kernel(battle)
    states = []
    for health, hand, pp in ((2, 3, 3), (3, 5, 2), (4, 7, 3), (4, 7, 3), (5, 1, 1)):
        state = list(kernel.initial)
        state[0], state[kernel.tail+2], state[kernel.tail+3] = health, hand, pp
        states.append(tuple(state))
    ordered = [states[index] for index in order]
    keys, layout = packed(ordered)
    expected, complete = reference(kernel, ordered, float('inf'))
    actual, finished = frontier(kernel, keys, layout, float('inf'), batch_size=2)
    assert complete and finished and actual == expected
