"""Cross-check compact transitions and exact solutions against the public engine."""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from time import perf_counter

import pytest

from svdeck.battle.battle import Battle, Json
from svdeck.battle.battle_compact import Compact, eligible
from svdeck.battle.battle_practical import ChanceBattle, WEIGHTS, analyze, validate_scope, value, verify_policy

ROOT = Path(__file__).resolve().parents[1]
STRESS: Json = json.loads((ROOT/'docs/evidence/combat-practical/stress/input.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('seed', range(12))
def test_compact_matches_general_and_engine(seed: int) -> None:
    # AI_NOTE: 勝ち・召喚酔い・0攻撃・能力・進化・後攻PPを組み替え、独立した通常エンジンと全到達辺を照合する。
    rng = random.Random(seed)
    case = copy.deepcopy(STRESS)
    state = case['state']
    owner = seed % 2
    state['active_player'] = owner
    if owner:
        state['players'].reverse()
    own, enemy = state['players'][owner], state['players'][1-owner]
    own['board'] = own['board'][:2]
    enemy['board'] = enemy['board'][:2]
    enemy['health'] = 1+seed % 8
    own['evolved_this_turn'] = seed % 3 == 0
    own['extra_pp_used'] = seed % 3 == 1
    own['hand'] = own['hand'][:1] if seed % 2 else own['hand'][1:]
    for player in (own, enemy):
        for entity in player['board']:
            entity['attack'], entity['health'] = rng.randrange(4), rng.randrange(1, 5)
            entity['keywords'] = rng.sample(['バリア', '必殺', '疾走', '突進', '守護'], rng.randrange(4))
            entity['entered_turn'] = 7 if rng.randrange(2) else 0
            entity['attacks'] = rng.randrange(2)
            entity['evolved'] = rng.randrange(3)
    battle = Battle(state, case['cards'])
    validate_scope(battle)
    assert eligible(battle)
    weights = dict(WEIGHTS) | {'own_board_health': seed % 3}
    objective = 'lethal' if seed % 2 else 'value'
    solver = Compact(battle, weights, objective, 100000, 64, 4096, perf_counter()+10)
    pair = solver.solve(solver.initial)
    general = analyze(battle, weights=weights, objective=objective, max_states=50000)
    assert general['complete']
    assert str(pair[0]) == general['win_probability_exact']
    assert str(pair[1]) == general['expected_value_exact']
    pending = [(ChanceBattle(battle.state, battle.cards, record=False), solver.initial)]
    visited = set()
    while pending:
        current, compact = pending.pop()
        if compact in visited:
            continue
        visited.add(compact)
        assert solver.score(compact) == value(current, weights)
        if current.state['winner'] is not None:
            continue
        actions = solver.actions(compact)
        assert [solver.public_action(a) for a in actions] == [a for a in current.legal_actions() if a['type'] != 'end_turn']
        for action in actions:
            children = solver.children(compact, action)
            for number, child_state in enumerate(children):
                has_enemy = any(compact[i] > 0 for i in range(solver.n, solver.count))
                draws = (number,) if action[0] == 0 and action[2] == -1 and has_enemy else ()
                child = current.branch(solver.public_action(action), draws)
                encoded = list(solver.encode(child))
                encoded[solver.count+2] = child_state[solver.count+2]
                assert tuple(encoded) == child_state
                assert solver.score(child_state) == value(child, weights)
                pending.append((child, child_state))


def test_unchanged_stress_completes_and_attains_independent_optimum() -> None:
    # AI_NOTE: 旧上限に当たった入力を変更せず、別担当の通常エンジン総当たり値-4と公開方策再生を固定する。
    result = analyze(Battle(STRESS['state'], STRESS['cards']))
    assert result['complete'] and result['optimal']
    assert result['win_probability_exact'] == '0' and result['expected_value_exact'] == '-4'
    assert result['stats']['states'] <= result['stats']['max_states']
    assert result['stats']['policy_nodes'] == len(result['policy'])
    assert verify_policy(result)['status'] == 'PASS'


@pytest.mark.parametrize('limits', [{'max_states': 1}, {'max_depth': 1}, {'seconds': 1e-9}])
def test_compact_cutoff_is_honest(limits: Json) -> None:
    # AI_NOTE: 高速側でも途中結果を最適解扱いせず、公開データの再生を保つ。
    result = analyze(Battle(STRESS['state'], STRESS['cards']), **limits)
    assert not result['complete'] and not result['optimal'] and result['cutoffs']
    assert result['stats']['states'] <= result['stats']['max_states']
    assert verify_policy(result)['status'] == 'PASS'


def test_conditional_spell_keeps_general_solver() -> None:
    # AI_NOTE: 墓場条件など整数kernelが追跡しない機能を、黙って最適化対象へ含めない。
    case = copy.deepcopy(STRESS)
    case['cards']['ping']['effects'][0]['condition'] = {'player': 'graveyard', 'gte': 2}
    battle = Battle(case['state'], case['cards'])
    assert not eligible(battle)
    assert analyze(battle, max_states=1)['strategy'] == 'practical-expectimax'


def test_zero_enhance_keeps_general_solver() -> None:
    # AI_NOTE: 0も有効なエンハンス閾値なので、追加抽選を無視する高速経路へ入れない。
    case = copy.deepcopy(STRESS)
    case['cards']['ping']['enhance'] = 0
    case['cards']['ping']['enhance_effects'] = [{'op': 'damage', 'target': 'random_enemy', 'amount': 1}]
    battle = Battle(case['state'], case['cards'])
    assert not eligible(battle)
    assert analyze(battle, max_states=1)['strategy'] == 'practical-expectimax'


def test_many_random_paths_merge_without_losing_probability() -> None:
    # AI_NOTE: 同じ盤面になる抽選順の組合せを共有し、5回の4択を木のまま出力して膨張させない。
    case = copy.deepcopy(STRESS)
    own, enemy = case['state']['players']
    own['ep'] = own['sep'] = 0
    own['hand'] = ['random']*5
    own['board'] = own['board'][:3]
    enemy['board'] = enemy['board'][:4]
    for entity in own['board']+enemy['board']:
        entity.update(attack=0, health=1000, max_health=1000, keywords=[], attacks=1)
    case['cards']['random']['cost'] = 0
    case['cards']['random']['effects'][0]['amount'] = 1
    result = analyze(Battle(case['state'], case['cards']), weights={'hand': 0})
    assert result['complete']
    assert result['stats']['policy_nodes'] < 200
    assert verify_policy(result)['status'] == 'PASS'


def test_export_deadline_cannot_report_optimal(monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 探索終了後に期限を越えた場合も、欠けた方策を完全として返さない。
    import svdeck.battle.battle_practical as practical
    calls = 0
    def clock() -> float:
        # AI_NOTE: 開始時だけ実時間を返し、次の出力検査で確実に期限超過へ進める。
        nonlocal calls
        calls += 1
        return perf_counter() if calls == 1 else perf_counter()+100
    monkeypatch.setattr(practical, 'perf_counter', clock)
    result = analyze(Battle(STRESS['state'], STRESS['cards']))
    assert not result['complete'] and result['cutoffs'] == ['time']
    assert len(result['policy']) == 1
    assert verify_policy(result)['status'] == 'PASS'
