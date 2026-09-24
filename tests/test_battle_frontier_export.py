"""The accelerated writer must preserve every old candidate row and SHA byte."""
from __future__ import annotations

import hashlib

import pytest

pytest.importorskip('numba')

from svdeck.battle import Battle
from svdeck.battle_frontier_compare import digest, kernel_key, semantic_key
from svdeck.battle_frontier_export import materialize
from svdeck.battle_frontier_fast import Kernel, _freeze
from svdeck.battle_frontier_native import enumerate_native
from test_battle_frontier_fast import scenario


@pytest.mark.parametrize('seed', range(96))
def test_all_reachable_rows_and_hashes(seed: int) -> None:
    # AI_NOTE: Compare the new batched writer against both old kernel keys and independent full Battle keys.
    search = enumerate_native(scenario(seed), max_states=100000, seconds=60)
    assert search.complete
    candidates = list(range(len(search.keys)))
    rows, hashes = materialize(search, candidates, batch_size=7)
    kernel = search.kernel
    shapes: dict[int, str] = {}
    hands = [digest(_freeze(dict(e, keywords=sorted(e['keywords'])))) for e in kernel.hand]
    for index, (row, actual) in enumerate(zip(rows, hashes)):
        assert row == search.states[index]
        assert actual.hex() == digest(kernel_key(kernel, row, shapes, hands))
        assert actual.hex() == digest(semantic_key(Battle(kernel.state(row), kernel.battle.cards)))


def test_large_integer_rows_and_empty_candidates() -> None:
    # AI_NOTE: The signed16 optimization must fall back without truncation, including empty output and owner 1.
    battle = Battle({'active_player': 1, 'players': [{}, {'health': 100000, 'max_health': 100000,
                    'board': [{'id': 'large', 'card_id': 'f', 'health': 40000, 'max_health': 40000}]}]},
                    {'f': {'name': 'F', 'kind': 'follower', 'cost': 1, 'attack': 1, 'health': 40000}})
    search = enumerate_native(battle, max_states=100, seconds=60)
    rows, hashes = materialize(search, [0])
    assert rows[0] == search.states[0]
    assert hashes[0].hex() == digest(semantic_key(Battle(search.kernel.state(rows[0]), battle.cards)))
    empty, empty_hashes = materialize(search, [])
    assert len(empty) == 0 and empty_hashes == []
    with pytest.raises(ValueError, match='batch_size'):
        materialize(search, [0], batch_size=0)
