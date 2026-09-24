"""Complete differential traversal for the local transition cache experiment."""
from __future__ import annotations

from fractions import Fraction

import pytest

from svdeck.battle import Battle, Json
from svdeck.battle_frontier_cache import CachedKernel
from svdeck.battle_frontier_fast import Kernel
from test_battle_frontier import CASES, check_graph
from test_battle_frontier_fast import scenario


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_independent_small_graph(case: Json, monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 公開グラフの独立oracle検証をcache差し替えでも実施し、非対応入力の汎用経路を残す。
    monkeypatch.setattr('svdeck.battle_frontier_fast.Kernel', CachedKernel)
    check_graph(case)


@pytest.mark.parametrize('seed', range(96))
def test_complete_cached_transitions(seed: int) -> None:
    # AI_NOTE: 同じ局所値が異なる全体状態へ現れるまで全探索し、cacheヒット後も全遷移を比較する。
    battle = scenario(seed)
    reference, actual = Kernel(battle), CachedKernel(battle)
    seen = {reference.initial}
    pending = [reference.initial]
    edges = 0
    while pending:
        state = pending.pop()
        actions = reference.actions(state)
        assert actual.actions(state) == actions
        for action in actions:
            expected = reference.outcomes(state, action)
            branches = actual.outcomes(state, action)
            assert branches == expected, (seed, action, state, branches, expected)
            assert sum((p for _, p, _ in branches), Fraction()) == 1
            edges += len(branches)
            for child, _, _ in branches:
                if child not in seen:
                    seen.add(child)
                    pending.append(child)
        assert len(seen) < 100000, 'Generated complete test exceeded intended size'
    assert actual.patch_hits + actual.patch_misses == edges


def test_unsupported_effect_rejected() -> None:
    # AI_NOTE: cacheの対象範囲を既存kernelより広げず、複合効果を勝手に省略しない。
    battle = scenario(0)
    cid = battle.state['players'][0]['hand'][0]['card_id']
    battle.cards[cid]['effects'].append({'op': 'grant', 'target': 'all_ally', 'keywords': ['疾走']})
    with pytest.raises(ValueError, match='対象外'):
        CachedKernel(Battle(battle.state, battle.cards))
