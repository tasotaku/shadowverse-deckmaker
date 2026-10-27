"""Exact small references and chance-policy regression tests."""
from __future__ import annotations

import copy
import importlib.util
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from svdeck.battle_env.battle import Battle, Json
from svdeck.battle_env.battle_practical import WEIGHTS, analyze, replay_branch, verify_policy

ROOT = Path(__file__).resolve().parents[1]
CASES: list[Json] = json.loads((ROOT/'tests/fixtures/combat_practical_cases.json').read_text(encoding='utf-8'))


def oracle() -> Any:
    # AI_NOTE: 生産探索から独立した合法操作列の総当たりを読み、同じ実装から期待値を作らない。
    spec = importlib.util.spec_from_file_location('practical_reference', ROOT/'scripts/practical_reference.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('case', CASES, ids=[case['id'] for case in CASES])
def test_exact_action_probabilities_and_every_branch(case: Json) -> None:
    # AI_NOTE: 最大確率だけでなく各初手の価値・全ての抽選辺・入力不変を検査する。
    battle = Battle(case['state'], case['cards'])
    original = battle.export()
    expected = oracle().solve_case(case)
    result = analyze(battle)
    assert result['complete'] and result['optimal']
    assert Fraction(result['win_probability_exact']) == Fraction(expected['win_probability'])
    root = result['policy'][result['root']]
    for choice in root['actions']:
        reference = next(row for row in expected['action_values'] if row['action'] == choice['action'])
        assert Fraction(choice['win_probability_exact']) == Fraction(reference['win_probability'])
    assert verify_policy(result)['status'] == 'PASS'
    assert result['stats']['elapsed_ms'] >= 0 and result['stats']['peak_rss_bytes'] > 0
    assert battle.export() == original


def test_objective_changes_decision_without_relabeling_value_as_probability() -> None:
    # AI_NOTE: 同一の評価重みでも、勝利優先と盤面保存優先が異なる決定になることを手計算で固定する。
    case = next(c for c in CASES if c['id'] == 'objective-preserve-versus-win')
    weights = dict.fromkeys(WEIGHTS, 0) | {'own_board_health': 1}
    battle = Battle(case['state'], case['cards'])
    lethal = analyze(battle, weights=weights)
    saved = analyze(battle, objective='value', weights=weights)
    assert lethal['win_probability_exact'] == '1' and lethal['expected_value_exact'] == '20'
    assert saved['recommended_action'] is None
    assert saved['win_probability_exact'] == '0' and saved['expected_value_exact'] == '21'


def test_rng_seed_cannot_change_probability_or_policy() -> None:
    # AI_NOTE: 固定seedでは成功する低確率手を、未知の抽選を知ったかのように優遇しない。
    case = next(c for c in CASES if c['id'] == 'rng-cheating-choice')
    results = [analyze(Battle({**case['state'], 'rng': seed}, case['cards'])) for seed in (1, 60, 999)]
    assert all(result['win_probability_exact'] == '2/3' for result in results)
    assert all(result['policy'] == results[0]['policy'] for result in results)


def test_budgets_never_report_partial_chance_as_optimal() -> None:
    # AI_NOTE: 不完全な抽選集合を100%へ正規化せず、状態・抽選・深さの打切りを明示する。
    case = next(c for c in CASES if c['id'] == 'random-two-ward-adaptive-anchor')
    battle = Battle(case['state'], case['cards'])
    for limits in ({'max_states': 1}, {'max_outcomes': 1}, {'max_depth': 1}, {'seconds': 1e-9}):
        result = analyze(battle, **limits)
        assert not result['complete'] and not result['optimal'] and result['cutoffs']
        assert result['stats']['states'] <= limits.get('max_states', 10000)
        assert verify_policy(result)['status'] == 'PASS'


def test_conditional_replay_rejects_illegal_or_incomplete_draws() -> None:
    # AI_NOTE: 抽選履歴は手で選べる攻略操作ではなく証拠なので、余分・不足・範囲外を拒否する。
    case = next(c for c in CASES if c['id'] == 'random-half-anchor')
    result = analyze(Battle(case['state'], case['cards']))
    random_choice = next(c for c in result['policy'][0]['actions'] if len(c['outcomes']) > 1)
    for draws in ([], [999], [0, 0]):
        with pytest.raises(ValueError):
            replay_branch(result['record'], [{'action': random_choice['action'], 'draws': draws}])
    with pytest.raises(ValueError):
        replay_branch(result['record'], [{'action': {'type': 'attack', 'source': 'missing', 'target': 'leader:1'}, 'draws': []}])


def test_unsupported_effects_and_invalid_options_fail_explicitly() -> None:
    # AI_NOTE: 能力を削除して成立する解を返す事故を防ぎ、不正設定も入口で拒否する。
    case = copy.deepcopy(CASES[0])
    first = next(card for card in case['cards'].values() if card['kind'] == 'spell')
    first['effects'] = [{'op': 'draw', 'amount': 1}]
    with pytest.raises(ValueError, match='対象外'):
        analyze(Battle(case['state'], case['cards']))
    battle = Battle(CASES[0]['state'], CASES[0]['cards'])
    for options in ({'objective': 'unknown'}, {'max_states': 0}, {'seconds': float('nan')}, {'weights': {'win': True}}):
        with pytest.raises(ValueError):
            analyze(battle, **options)


@pytest.mark.parametrize('alternate', [False, True])
def test_opponent_hand_triggers_cannot_bypass_scope_check(alternate: bool) -> None:
    # AI_NOTE: 相手の非公開手札にある未対応誘発が、完全探索の推奨手へ混ざる経路を拒否する。
    case = copy.deepcopy(CASES[0])
    case['cards']['reactive'] = {'name': 'Reactive', 'kind': 'follower', 'cost': 1, 'attack': 1, 'health': 1,
                                'hand_triggers': [{'event': 'enter', 'scope': 'enemy',
                                                   'effects': [{'op': 'damage', 'target': 'enemy_leader', 'amount': 20}]}]}
    case['state']['players'][1]['hand'] = ['reactive']
    if alternate:
        reactive = case['cards']['reactive']
        variant = {k: v for k, v in reactive.items() if k != 'card_id'}
        reactive.pop('hand_triggers')
        reactive['forms'] = {'accelerate': variant}
        case['state']['players'][1]['hand'] = [{'card_id': 'reactive', 'form': 'accelerate'}]
    with pytest.raises(ValueError, match='手札誘発'):
        analyze(Battle(case['state'], case['cards']))


def test_deadline_interrupts_inside_deterministic_repeat(monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 時計を制御して、1操作内の繰り返し中にもキャンセルを検査する。実機速度に依存しない。
    from svdeck.battle_env import battle_practical as practical
    effect: Json = {'op': 'damage', 'target': 'enemy_leader', 'amount': 0}
    for _ in range(2):
        effect = {'op': 'repeat', 'count': 100, 'effects': [effect]}
    battle = practical.ChanceBattle({'players': [{'pp': 1, 'max_pp': 1, 'hand': ['s']}, {}]},
                                   {'s': {'name': 'Repeat', 'kind': 'spell', 'cost': 1, 'effects': [effect]}}, record=False)
    battle.deadline = 1
    ticks = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(practical, 'perf_counter', lambda: next(ticks))
    with pytest.raises(practical.Limit, match='time'):
        battle.branch(next(a for a in battle.legal_actions() if a['type'] == 'play'), ())
