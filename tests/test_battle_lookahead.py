"""Independent finite-turn oracles, privacy boundary, limits and public integration."""
from __future__ import annotations

import copy
import importlib.util
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from svdeck.battle.battle import Battle, Json, replay
from svdeck.battle.battle_ai import Player
from svdeck.battle.battle_lookahead import analyze, verify_policy, validate_work

ROOT = Path(__file__).resolve().parents[1]
CASES: list[Json] = json.loads((ROOT/'tests/fixtures/battle_lookahead_cases.json').read_text(encoding='utf-8'))
ACCEPTANCE: list[Json] = json.loads((ROOT/'tests/fixtures/battle_lookahead_acceptance.json').read_text(encoding='utf-8'))


def oracle() -> Any:
    # AI_NOTE: 別担当の公開Battle総当たりを読み、こちらの探索や盤面点から正解を作らない。
    spec = importlib.util.spec_from_file_location('lookahead_reference', ROOT/'scripts/lookahead_reference.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('case', CASES + ACCEPTANCE[:4], ids=[c['id'] for c in CASES + ACCEPTANCE[:4]])
def test_exact_all_initial_actions_and_policy(case: Json) -> None:
    # AI_NOTE: 選択手だけでなく全初手の勝敗確率を独立参照と照合し、ターン境界込みの全方策辺を再生する。
    expected = oracle().verify(case)
    battle = Battle(case['state'], case['cards'])
    before = battle.export()
    result = analyze(battle, turns=case['n_turns'])
    assert result['complete'] and result['optimal']
    assert result['recommended_action'] in expected['optimal_first_actions']
    assert [result['win_probability_exact'], str(-Fraction(result['loss_probability_exact']))] == expected['value']
    assert len(result['candidates']) == len(battle.legal_actions())
    for row in result['candidates']:
        reference = next(r for r in expected['actions'] if r['action'] == row['action'])
        assert [row['win_probability_exact'], str(-Fraction(row['loss_probability_exact']))] == reference['value']
    assert verify_policy(result)['status'] == 'PASS'
    assert battle.export() == before


def test_deeper_horizon_preserves_removal_and_all_hand_choices() -> None:
    # AI_NOTE: 即時点では除去を使うが、3ターンでは温存して勝つ反例で先読み深さが実際に効くことを検査する。
    case = next(c for c in CASES if c['id'] == 'save_removal_for_next_turn')
    battle = Battle(case['state'], case['cards'])
    shallow = analyze(battle, turns=1)
    deep = analyze(battle, turns=3)
    assert shallow['recommended_action']['type'] == 'play'
    assert deep['recommended_action'] == {'type': 'end_turn'}
    assert deep['win_probability_exact'] == '1'
    assert {tuple(p['used']) for p in deep['hand_patterns']} == {(), ('remove',)}


def test_random_result_selects_next_target_without_seed_peeking() -> None:
    # AI_NOTE: 異なるseedでも抽選結果の両方を1/2で保ち、生き残った対象へ後続の確定除去を変える。
    case = next(c for c in CASES if c['id'] == 'random_then_observe_and_adapt')
    results = [analyze(Battle(case['state'] | {'rng': seed}, case['cards']), turns=1) for seed in (1, 60)]
    for result in results:
        root = result['policy'][0]
        assert len(root['outcomes']) == 2
        assert {e['probability'] for e in root['outcomes']} == {'1/2'}
        targets = {result['policy'][e['node']]['action']['target'] for e in root['outcomes']}
        assert len(targets) == 2
        assert result['win_probability_exact'] == '1'
    assert results[0]['candidates'] == results[1]['candidates']


@pytest.mark.parametrize('options', [{'max_states': 1}, {'max_actions': 1}, {'seconds': 1e-9}, {'max_outcomes': 1}])
def test_limits_never_claim_complete(options: Json) -> None:
    # AI_NOTE: 半端な確率分布や途中ターンの値を、完了したnターンの解として提示しない。
    case = next(c for c in CASES if c['id'] == 'random_then_observe_and_adapt')
    result = analyze(Battle(case['state'], case['cards']), turns=1, **options)
    assert not result['complete'] and not result['optimal'] and result['cutoffs']
    assert result['stats']['states'] <= options.get('max_states', 10000)
    assert not result['policy']


def test_real_player_secret_state_invariance() -> None:
    # AI_NOTE: 実際の非公開手札・山札順・seedだけを変え、同じ公開観測から同じ判断が出ることを確認する。
    case = copy.deepcopy(next(c for c in CASES if c['id'] == 'incomparable_hand_burn'))
    first = Battle(case['state'], case['cards'])
    modified = copy.deepcopy(case['state'])
    modified['rng'] = 4321
    modified['players'][1]['hand'] = ['filler']*len(modified['players'][1]['hand'])
    modified['players'][1]['deck'].reverse()
    second = Battle(modified, case['cards'])
    a, b = first.observation(0), second.observation(0)
    assert a == b
    one = Player(first.cards, policy='lookahead', turns=2, seed=17).choose(a)
    two = Player(second.cards, policy='lookahead', turns=2, seed=17).choose(b)
    assert one['action'] == two['action'] and one['candidates'] == two['candidates']
    assert one['complete'] and not one['optimal'] and not one['proven_win']
    with pytest.raises(ValueError, match='observation'):
        Player(first.cards, policy='lookahead').choose(first.state | {'legal_actions': first.legal_actions()})


def test_distinct_hidden_deck_orders_hand_and_rng() -> None:
    # AI_NOTE: 同名カードのreverseで済ませず、独立fixtureの異なる山札順・相手手札・乱数を実際に照合する。
    inputs = ROOT/'docs/evidence/battle-lookahead/acceptance-inputs'
    payloads = [json.loads((inputs/f'api-{suffix}.json').read_text(encoding='utf-8')) for suffix in ('a', 'b')]
    first, second = [replay(p['record']) for p in payloads]
    assert first.state['rng'] != second.state['rng']
    assert first.state['players'][1]['hand'] != second.state['players'][1]['hand']
    for owner in (0, 1):
        assert first.state['players'][owner]['deck'] != second.state['players'][owner]['deck']
    assert first.observation(0) == second.observation(0)
    one, two = [Player(b.cards, policy='lookahead', **p['options']).choose(b.observation(0))
                for b, p in zip((first, second), payloads)]
    for key in ('action', 'candidates', 'depth', 'complete', 'optimal', 'proven_win'):
        assert one[key] == two[key]


def test_runtime_depth_and_legal_fallback() -> None:
    # AI_NOTE: 通常Playerで3ターン判断を使い、最小予算でも合法な一手を返し限界を記録する。
    case = next(c for c in CASES if c['id'] == 'save_removal_for_next_turn')
    battle = Battle(case['state'], case['cards'])
    observation = battle.observation(0)
    result = Player(battle.cards, policy='lookahead').choose(observation)
    assert result['action'] == {'type': 'end_turn'}
    assert result['depth'] == 3 and result['settings']['policy_version'] == 4
    limited = Player(battle.cards, policy='lookahead', max_nodes=1).choose(observation)
    assert limited['limited'] and limited['fallback'] and limited['depth'] == 0
    assert not limited['fallback_evaluated'] and '未評価の合法手' in limited['reason']
    assert limited['action'] in battle.legal_actions()
    battle.step(limited['action'])


@pytest.mark.parametrize('options', [{'turns': 0}, {'turns': True}, {'max_states': 0}, {'seconds': float('nan')}])
def test_invalid_settings_are_explicit(options: Json) -> None:
    # AI_NOTE: 入力不正を探索上限の到達や正常なパスへ置き換えない。
    with pytest.raises(ValueError):
        analyze(Battle(CASES[0]['state'], CASES[0]['cards']), **options)


def test_pathological_expansion_is_rejected_before_enumerating() -> None:
    # AI_NOTE: 合法手生成の直積と、効果のない巨大repeatも入力時に拒否し時間検査を迂回させない。
    card = {'name': 'Many targets', 'kind': 'spell', 'cost': 0,
            'effects': [{'op': 'damage', 'amount': 1, 'target': 'chosen_enemy', 'choice': str(i)} for i in range(8)]}
    with pytest.raises(ValueError, match='対象選択'):
        validate_work({'many': card})
    card['effects'] = [{'op': 'repeat', 'count': 100001, 'effects': []}]
    with pytest.raises(ValueError, match='効果展開'):
        validate_work({'many': card})
