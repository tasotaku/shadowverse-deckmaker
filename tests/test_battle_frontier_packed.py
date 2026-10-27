"""Compact endpoint vectors preserve exact candidate comparisons."""
from __future__ import annotations

import pytest

from svdeck.battle_env.battle import Battle, Json
from svdeck.battle_env.battle_frontier_fast import Kernel
from svdeck.battle_env import battle_frontier_packed as packed


def bounded_battle(change: Json) -> Battle:
    # AI_NOTE: byteの正負境界と進化の上限を、公開Battleへ渡せる小さい盤面で固定する。
    cards: dict[str, Json] = {
        'own': {'name': 'own', 'kind': 'follower', 'cost': 1, 'attack': change.get('attack', 124), 'health': 4},
        'enemy': {'name': 'enemy', 'kind': 'follower', 'cost': 1, 'attack': change.get('enemy_attack', 128), 'health': 4}}
    own: Json = {'turn': 7, 'health': change.get('own_health', 127), 'max_health': change.get('own_health', 127),
                 'ep': change.get('ep', 0), 'sep': change.get('sep', 1),
                 'board': [{'id': 'ours', 'card_id': 'own', 'evolved': change.get('evolved', 0),
                            'max_health': change.get('max_health', 4)}], 'hand': []}
    enemy: Json = {'health': change.get('enemy_health', 128), 'max_health': change.get('enemy_health', 128),
                   'board': [{'id': 'theirs', 'card_id': 'enemy'}]}
    if 'token_health' in change:
        cards['token'] = {'name': 'token', 'kind': 'follower', 'cost': 1, 'attack': 0,
                          'health': change['token_health'], 'keywords': ['疾走']}
        cards['summon'] = {'name': 'summon', 'kind': 'spell', 'cost': 0,
                           'effects': [{'op': 'summon', 'card_id': 'token'}]}
        own['hand'] = [{'id': 'summon', 'card_id': 'summon'}]
    owner = change.get('owner', 0)
    if owner:
        own.update(pp=11, max_pp=10, extra_pp_used=False)
    return Battle({'active_player': owner, 'players': [enemy, own] if owner else [own, enemy]}, cards)


@pytest.mark.parametrize(('change', 'compact'), [
    ({}, True), ({'attack': 125}, False),
    ({'attack': 127, 'sep': 0}, True), ({'attack': 128, 'sep': 0}, False),
    ({'attack': 127, 'evolved': 1}, True),
    ({'own_health': 128}, False), ({'enemy_health': 129}, False),
    ({'enemy_attack': 129}, False), ({'max_health': 125}, False),
    ({'ep': 127}, True), ({'ep': 128}, False),
    ({'token_health': 124}, True), ({'token_health': 125}, False),
    ({'owner': 1}, True),
])
def test_vector_bounds_and_candidates(change: Json, compact: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 境界をまたぐ全小状態を実際に列挙し、圧縮と非圧縮の候補番号まで同一であることを確認する。
    kernel = Kernel(bounded_battle(change))
    assert packed._byte_vectors(kernel) is compact
    states = [kernel.initial]
    seen = {kernel.initial}
    for state in states:
        for action in kernel.actions(state):
            for child, _, _ in kernel.outcomes(state, action):
                if child not in seen:
                    seen.add(child)
                    states.append(child)
    if compact:
        assert all(-128 <= value <= 127 for state in states for value in kernel.endpoint(state)[1])
    selected, complete = packed.frontier(kernel, states, float('inf'))
    monkeypatch.setattr(packed, '_byte_vectors', lambda _: False)
    reference, reference_complete = packed.frontier(kernel, states, float('inf'))
    assert complete and reference_complete
    assert selected == reference


def test_bytes_keep_component_and_lexicographic_order() -> None:
    # AI_NOTE: 負数と境界値を跨いでも辞書順・成分優越・等価が変わらないことを全組合せで検査する。
    points = (-128, -127, -1, 0, 1, 126, 127)
    vectors = [(first, second) for first in points for second in points]
    def encode(vector: tuple[int, ...]) -> bytes:
        # AI_NOTE: 1成分を1byteへ写す同じ単調変換で、大小関係の保存を検査する。
        return bytes(value+128 for value in vector)
    for first in vectors:
        for second in vectors:
            assert (first < second) == (encode(first) < encode(second))
            assert all(a >= b for a, b in zip(first, second)) == all(a >= b for a, b in zip(encode(first), encode(second)))
