"""Frozen independent mixed-ability oracles and the comparison failure paths."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.lookahead_generated_cases import generate_cases
from scripts.lookahead_reference import solve
from scripts.lookahead_stress import compare
from svdeck.battle import Battle, Json
from svdeck.battle_ai import Player
from svdeck.battle_lookahead import analyze, verify_policy

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures'
GENERATED: list[Json] = json.loads((FIXTURES/'battle_lookahead_generated.json').read_text(encoding='utf-8'))
EXPECTED: dict[str, Json] = json.loads((FIXTURES/'battle_lookahead_generated_expected.json').read_text(encoding='utf-8'))
HARD: list[Json] = json.loads((FIXTURES/'battle_lookahead_hard.json').read_text(encoding='utf-8'))
EXACT = [case for case in HARD if case['classification'] == 'exact']
STRESS = [case for case in HARD if case['classification'] == 'stress']


def test_generated_population_is_frozen_and_reproducible() -> None:
    # AI_NOTE: 成功したseedだけ残す選別を防ぎ、同じ128入力を将来も再生する。
    assert GENERATED == generate_cases()
    assert [case['seed'] for case in GENERATED] == list(range(128))
    assert set(EXPECTED) == {case['id'] for case in GENERATED}
    assert sum(case['n_turns'] == 3 for case in GENERATED) == 80


@pytest.mark.parametrize('case', GENERATED, ids=[case['id'] for case in GENERATED])
def test_generated_all_initial_actions_match_independent_oracle(case: Json) -> None:
    # AI_NOTE: 正解は別プロセスの公開Battle総当たりで保存済み。製品の推奨だけでなく全初手を検査する。
    battle = Battle(case['state'], case['cards'])
    before = battle.export()
    result = analyze(battle, turns=case['n_turns'])
    result['verification'] = verify_policy(result)
    checked = compare(result, EXPECTED[case['id']])
    assert checked['status'] == 'PASS', checked
    assert battle.export() == before


def test_comparison_detects_wrong_values_missing_actions_and_incomplete_results() -> None:
    # AI_NOTE: 壊れた出力を正解と扱わないことを、独立正解のある実局面の出力から故障を注入して確認する。
    case = GENERATED[1]
    original = analyze(Battle(case['state'], case['cards']), turns=case['n_turns'])
    original['verification'] = verify_policy(original)
    reference = EXPECTED[case['id']]
    assert compare(original, reference)['status'] == 'PASS'
    wrong = copy.deepcopy(original)
    wrong['candidates'][0]['win_probability_exact'] = '123/7'
    assert compare(wrong, reference)['status'] == 'FAIL'
    missing = copy.deepcopy(original)
    missing['candidates'].pop()
    assert compare(missing, reference)['status'] == 'FAIL'
    partial = original | {'complete': False, 'cutoffs': ['states']}
    assert compare(partial, reference)['status'] == 'INCOMPLETE'


@pytest.mark.parametrize('case', EXACT, ids=[case['id'] for case in EXACT])
def test_hand_designed_mixed_abilities_and_order(case: Json) -> None:
    # AI_NOTE: 新たな手作り難問の全初手と手計算の8手順を固定し、共有エンジンの同じ誤解だけで通さない。
    result = analyze(Battle(case['state'], case['cards']), turns=3)
    result['verification'] = verify_policy(result)
    expected = case['expectations']
    reference = {'value': expected['value'], 'optimal_first_actions': expected['optimal_first_actions'],
                 'actions': expected['action_values']}
    assert compare(result, reference)['status'] == 'PASS'
    for trace in case.get('replays', []):
        battle = Battle(case['state'] | trace.get('state_overrides', {}), case['cards'])
        for action in trace['actions']:
            battle.step(action)
        for path, expected_value in trace['expected_paths'].items():
            actual = battle.state
            for part in path.split('.'):
                actual = actual[int(part)] if isinstance(actual, list) else actual[part]
            assert actual == expected_value, (case['id'], path)


@pytest.mark.parametrize('case', EXACT, ids=[case['id'] for case in EXACT])
@pytest.mark.parametrize('turns', [1, 2])
def test_shorter_horizons_do_not_borrow_later_wins(case: Json, turns: int) -> None:
    # AI_NOTE: 3ターン後の勝利を1/2ターンの確定勝利へ混ぜず、深さごとに独立参照で全初手を再計算する。
    reference = solve(case | {'n_turns': turns})
    assert reference['value'] == case['metadata']['horizon_values'][str(turns)]
    result = analyze(Battle(case['state'], case['cards']), turns=turns)
    result['verification'] = verify_policy(result)
    assert compare(result, reference)['status'] == 'PASS'


@pytest.mark.parametrize('case', STRESS, ids=[case['id'] for case in STRESS])
def test_full_boards_are_active_and_limited_player_is_honest(case: Json) -> None:
    # AI_NOTE: 置物で水増しした5対5でないことを検査し、厳しい予算でも合法手と不完全性を保つ。
    for side in (0, 1):
        battle = Battle(case['state'] | {'active_player': side}, case['cards'])
        assert len(battle.state['players'][side]['board']) == 5
        assert len(battle.state['players'][side]['hand']) == 6
        assert len({a['source'] for a in battle.legal_actions() if a['type'] == 'attack'}) == 5
    battle = Battle(case['state'], case['cards'])
    result = Player(battle.cards, policy='lookahead', max_nodes=128).choose(battle.observation(battle.state['active_player']))
    assert result['nodes'] <= 128
    assert result['action'] in battle.legal_actions()
    assert not result['optimal'] and not result['proven_win']
    assert result['complete'] == (result['depth'] == result['turns_requested'])
    if not result['complete']:
        assert result['limited'] and result['cutoffs']
