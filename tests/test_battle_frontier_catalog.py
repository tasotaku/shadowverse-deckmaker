"""Public training catalogue, including fallback and conditional random actions."""
from fractions import Fraction
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip('numba')

from svdeck.battle_frontier_catalog import Catalog, analyze_catalog
from svdeck.battle_frontier import endpoint_key, freeze
from svdeck.battle import Battle
from svdeck.battle_practical import replay_branch
from test_battle_frontier_fast import scenario, semantic


def signature(catalog: Catalog, node: int) -> tuple[Any, ...]:
    # AI_NOTE: 探索順に依存しない候補の盤面・手札の意味を比較する。
    state = catalog.state_at(node)
    current = Battle(state, catalog.record['cards'])
    hand = state['players'][state['active_player']]['hand']
    return endpoint_key(current), tuple(sorted(freeze(e) for e in hand))


@pytest.mark.parametrize('seed', [0, 1, 5, 12, 38, 69])
def test_public_candidate_states_and_conditional_decisions(seed: int) -> None:
    # AI_NOTE: 公開入口で全候補一致・到達例・全出目確率を確認し、代表経路を選べる運と取り違えない。
    battle = scenario(seed)
    native = analyze_catalog(battle, seconds=30)
    reference = analyze_catalog(battle, backend='reference', seconds=30)
    cached = analyze_catalog(battle, backend='cache', seconds=30)
    assert native.complete and reference.complete
    assert {signature(native, n) for n in native.candidates} == {signature(reference, n) for n in reference.candidates}
    assert cached.complete and cached.stats['backend'] == 'cache'
    assert {signature(cached, n) for n in cached.candidates} == {signature(reference, n) for n in reference.candidates}
    for node in range(native.stats['states']):
        replayed = replay_branch(native.record, native.witness_steps(node))
        assert semantic(replayed['state']) == semantic(native.state_at(node))
        for choice in native.expand(node):
            assert sum(Fraction(o['probability']) for o in choice['outcomes']) == 1


def test_fallback_and_incomplete_are_explicit() -> None:
    # AI_NOTE: 複合効果は省略せず汎用処理へ戻し、小さい予算は完了と表示しない。
    battle = scenario(0)
    cid = battle.state['players'][0]['hand'][0]['card_id']
    battle.cards[cid]['effects'].append({'op': 'grant', 'target': 'all_ally', 'keywords': ['疾走']})
    result = analyze_catalog(battle, seconds=30)
    assert result.complete and result.native is None and result.stats['fallback_reason']
    assert result.expand(0)
    with pytest.raises(ValueError, match='generic'):
        analyze_catalog(battle, backend='native')
    tiny = analyze_catalog(scenario(0), max_states=1)
    assert not tiny.complete and 'states' in tiny.cutoffs
    with pytest.raises(ValueError, match='node'):
        tiny.state_at(-1)
    with pytest.raises(ValueError, match='seconds'):
        analyze_catalog(battle, seconds=0)


def test_invalid_values_and_native_bound_fallback() -> None:
    # AI_NOTE: ゲーム自体で不正な値は拒否し、正しいがnative表現外の入力は参照処理へ戻す。
    battle = scenario(0)
    battle.state['players'][0]['board'][0]['max_health'] = 2**70
    with pytest.raises(ValueError, match='max_health'):
        analyze_catalog(battle, seconds=30)
    with patch('svdeck.battle_frontier_native.prepare', side_effect=ValueError('native integer bounds exceeded')):
        result = analyze_catalog(scenario(0), seconds=30)
    assert result.complete and result.native is None
    assert 'bounds' in result.stats['fallback_reason']


def test_missing_optional_runtime_uses_reference() -> None:
    # AI_NOTE: 任意依存を入れていない通常環境でも、既存の解析を使い続けられる。
    with patch.dict('sys.modules', {'svdeck.battle_frontier_native': None}):
        result = analyze_catalog(scenario(0), seconds=30)
    assert result.complete and result.native is None and 'dependencies' in result.stats['fallback_reason']
