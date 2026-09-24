"""Exhaustive independent oracle comparison for current-turn candidates."""
from __future__ import annotations

import copy
import json
import random
import sys
import threading
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from svdeck.battle import Battle, Json
from svdeck.battle_frontier import analyze, endpoint_key, state_at, witness_steps
from svdeck.battle_practical import replay_branch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from turn_frontier_reference import enumerate_turn, verify_case, action_signature  # type: ignore[import-not-found]  # noqa: E402

CASES = json.loads((Path(__file__).parent/'fixtures/turn_frontier_cases.json').read_text(encoding='utf-8'))


def signature(state: Json) -> str:
    # AI_NOTE: current-turn契約で意味が同じ破壊順・能力順と乱数seedだけを比較から外す。
    state = copy.deepcopy(state)
    state.pop('rng', None)
    for player in state['players']:
        player['destroyed'].sort()
        for entity in player['board']+player['hand']:
            entity['keywords'].sort()
    return json.dumps(state, sort_keys=True)


def check_graph(case: Json) -> Json:
    # AI_NOTE: 新実装に依存しない全列挙の状態集合・合法手・確率・抽選テープと照合する。
    battle = Battle(case['state'], case['cards'])
    before = copy.deepcopy(battle.state)
    reference = enumerate_turn(case['state'], case['cards'])
    verify_case(case, reference)
    result = analyze(battle, max_states=100000, seconds=30)
    assert result['complete'], result['cutoffs']
    assert battle.state == before
    states = [state_at(result, i) for i in range(len(result['positions']))]
    keys = [signature(s) for s in states]
    expected = {key: signature(state) for key, state in reference.states.items()}
    assert set(keys) == set(expected.values())
    observed = set()
    for parent, action, start, end in result['choices']:
        total = Fraction()
        for target, probability, draws in result['outcomes'][start:end]:
            chance = Fraction(result['probabilities'][probability])
            total += chance
            observed.add((keys[parent], action_signature(result['actions'][action]), keys[target],
                          tuple(result['draws'][draws]), chance))
        assert total == 1
    assert observed == {(expected[e.source], e.action, expected[e.target], e.choices, e.probability)
                        for e in reference.edges}
    for index, state in enumerate(states):
        actual = replay_branch(result['record'], witness_steps(result, index))
        assert signature(actual['state']) == signature(state)
        assert state['active_player'] == before['active_player']
        assert [p['turn'] for p in state['players']] == [p['turn'] for p in before['players']]
    # Independent quadratic skyline reference, including equivalent endpoint coalescing.
    endpoints = [endpoint_key(Battle(s, case['cards'], record=False)) for s in states]
    hands = [frozenset(json.dumps(e, sort_keys=True) for e in s['players'][s['active_player']]['hand']) for s in states]
    compared = [(shape, vector, hand) for (shape, vector), hand in zip(endpoints, hands)]
    expected_frontier = {(shape, vector, hand) for shape, vector, hand in compared
                         if not any(s == shape and (v != vector or h != hand) and h >= hand and
                                    all(x >= y for x, y in zip(v, vector)) for s, v, h in compared)}
    assert {compared[i] for i in result['candidates']} == expected_frontier
    return result


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_hand_authored_complete_graph(case: Json) -> None:
    # AI_NOTE: 固定された独立fixture全件を公開解析入口から検査する。
    check_graph(case)


@pytest.mark.parametrize('seed', range(24))
def test_generated_small_graphs(seed: int) -> None:
    # AI_NOTE: 実装と別のBattle全列挙へ、小盤面の能力・順序・資源の組合せを追加する。
    rng = random.Random(seed)
    keywords = [[], ['バリア'], ['必殺'], ['守護'], ['疾走'], ['突進']]
    cards: dict[str, Any] = {
        f'f{i}': {'name': f'f{i}', 'kind': 'follower', 'cost': 1, 'attack': rng.randint(1, 3),
                  'health': rng.randint(1, 4), 'keywords': rng.choice(keywords)} for i in range(4)}
    effects = [{'op': 'damage', 'target': 'random_enemy', 'amount': 2},
               {'op': 'split_damage', 'amount': 3},
               {'op': 'destroy', 'target': 'chosen_enemy'},
               {'op': 'grant', 'target': 'chosen_ally', 'keywords': ['必殺']},
               {'op': 'summon', 'card_id': 'f0'},
               {'op': 'buff', 'target': 'chosen_ally', 'health': 2, 'attack': 1}]
    for i in range(2):
        cards[f's{i}'] = {'name': f's{i}', 'kind': 'spell', 'cost': 1, 'effects': [rng.choice(effects)]}
    players = [{'turn': 1, 'health': 8, 'pp': 2, 'max_pp': 2, 'ep': 0, 'sep': 0,
                'extra_pp_used': True, 'board': [{'id': f'e{p}-{i}', 'card_id': f'f{p*2+i}'} for i in range(2)]}
               for p in range(2)]
    players[0]['hand'] = [{'id': f'h{i}', 'card_id': f's{i}'} for i in range(2)]
    check_graph({'id': f'seed-{seed}', 'state': {'players': players}, 'cards': cards})


def test_caps_and_random_mass() -> None:
    # AI_NOTE: 打切りを完了と偽らず、部分的な確率分布を返さない。
    case = next(c for c in CASES if any('random' in str(card) for card in c['cards'].values()))
    for options in ({'max_states': 1}, {'seconds': 0.000001}, {'max_outcomes': 1}):
        result = analyze(Battle(case['state'], case['cards']), **options)
        assert not result['complete']
        assert result['cutoffs']
        for _, _, start, end in result['choices']:
            assert sum(Fraction(result['probabilities'][p]) for _, p, _ in result['outcomes'][start:end]) == 1


@pytest.mark.parametrize('options', [{'seconds': True}, {'seconds': float('nan')}, {'max_states': 0}, {'max_outcomes': 0}])
def test_invalid_budget(options: Json) -> None:
    # AI_NOTE: 曖昧なbudgetを既定値へ黙って置き換えない。
    with pytest.raises(ValueError):
        analyze(Battle(CASES[0]['state'], CASES[0]['cards']), **options)


@pytest.mark.parametrize('backend', ['generic', 'fixed-slots'])
def test_large_budget_preserves_small_complete_result(backend: str) -> None:
    # AI_NOTE: 許容予算だけを広げても小ケースの全状態・全辺・候補が変わらず、既定値も変わらない。
    battle = Battle(CASES[0]['state'], CASES[0]['cards'])
    reference = analyze(battle, backend=backend)
    result = analyze(battle, backend=backend, max_states=100000000, seconds=3600)
    assert result['complete'] and reference['complete']
    assert reference['stats']['max_states'] == 100000
    assert reference['stats']['seconds'] == 10
    for field in ('positions', 'choices', 'outcomes', 'witnesses', 'actions', 'probabilities', 'draws', 'expanded', 'candidates'):
        assert list(result[field]) == list(reference[field]), field


@pytest.mark.parametrize('backend', ['generic', 'fixed-slots'])
@pytest.mark.parametrize('options', [{'max_states': 100000001}, {'seconds': 3601}])
def test_large_budget_upper_boundary_is_rejected(backend: str, options: Json) -> None:
    # AI_NOTE: 許容上限の直後を両backendで拒否し、無制限探索へ変わっていないことを検査する。
    with pytest.raises(ValueError):
        analyze(Battle(CASES[0]['state'], CASES[0]['cards']), backend=backend, **options)


def test_weakest_sufficient_mutual_trade_survives_frontier() -> None:
    # AI_NOTE: 大小が決まる二つの相打ちは、残る3/3を残し2/2だけ残る下位互換を除く。
    cards = {cid: {'name': cid, 'kind': 'follower', 'cost': 1, 'attack': attack, 'health': health,
                   'keywords': keywords} for cid, attack, health, keywords in
             [('small', 2, 2, []), ('large', 3, 3, []), ('enemy', 3, 2, ['守護'])]}
    battle = Battle({'players': [{'turn': 1, 'ep': 0, 'sep': 0, 'board': ['small', 'large']},
                                {'board': ['enemy']}]}, cards)
    result = analyze(battle)
    cleared = [state_at(result, i) for i in result['candidates']
               if not state_at(result, i)['players'][1]['board']]
    assert cleared
    assert all([(e['attack'], e['health']) for e in s['players'][0]['board']] == [(3, 3)] for s in cleared)


def test_api_frontier_and_http_budget() -> None:
    # AI_NOTE: サーバー実入口からJSON共有表を読み戻し、HTTP固有budgetと未対応optionsも検査する。
    from http.client import HTTPConnection
    from svdeck.battle_server import create_server
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        record = Battle(CASES[0]['state'], CASES[0]['cards']).export()
        for options, status in (({}, 200), ({'seconds': 61}, 400), ({'turns': 3}, 400)):
            connection.request('POST', '/api/turn-frontier', json.dumps({'record': record, 'options': options}),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            result = json.loads(response.read())
            assert response.status == status
            if status == 200:
                assert result['complete']
                assert state_at(result, 0)['active_player'] == record['initial']['active_player']
            else:
                assert result['error']
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_public_history_and_hand_metadata_are_isolated() -> None:
    # AI_NOTE: revealと手札への能力付与は可変共有禁止。入力と兄弟分岐を汚さず全列挙へ一致させる。
    case = copy.deepcopy(CASES[0])
    own = case['state']['players'][0]
    case['state']['deck_knowledge'] = [
        {'deck_list': {e['card_id']: 1 for e in own['hand']}, 'revealed': {}, 'known_hand': []},
        {'deck_list': {}, 'revealed': {}, 'known_hand': []}]
    case['state']['deck_origins'] = [{e['id']: e['id'] for e in own['hand']}, {}]
    check_graph(case)


def test_state_cap_exact_boundary_can_finish() -> None:
    # AI_NOTE: 最終状態への重複辺しか残っていない時に、上限到達だけを理由に未完としない。
    case = CASES[0]
    battle = Battle(case['state'], case['cards'])
    baseline = analyze(battle)
    limited = analyze(battle, max_states=baseline['stats']['states'])
    assert limited['complete']
    assert limited['positions'] == baseline['positions']


def test_useless_ping_does_not_survive_pareto_but_random_edges_do() -> None:
    # AI_NOTE: 同じ相打ちならpingとPPを残せる結果を選ぶ。グラフ自体には浪費経路も残す。
    case = next(c for c in CASES if c['id'] == 'barrier_bane_low_stack_trade')
    result = analyze(Battle(case['state'], case['cards']))
    cleared = [state_at(result, i) for i in result['candidates']
               if all(not p['board'] for p in state_at(result, i)['players'])]
    assert cleared
    assert all([e['id'] for e in s['players'][0]['hand']] == ['ping'] for s in cleared)
    assert any(not state_at(result, i)['players'][0]['hand'] for i in range(len(result['positions'])))


@pytest.mark.parametrize('case', [c for c in json.loads((Path(__file__).parent/'fixtures/battle_lookahead_hard.json')
                                                     .read_text(encoding='utf-8')) if c['classification'] == 'exact'],
                         ids=lambda c: c['id'])
def test_existing_hard_cases_one_turn(case: Json) -> None:
    # AI_NOTE: 既存の複合能力fixtureも境界を現在ターン停止へ変えて独立全列挙と照合する。
    check_graph(case)


@pytest.mark.parametrize('variant', ['second_player', 'super_evolve'])
def test_other_owner_and_super_evolution(variant: str) -> None:
    # AI_NOTE: 手番側の添字と超進化の攻撃権・反撃無効・追加打点を全分岐で照合する。
    case = copy.deepcopy(CASES[0 if variant == 'second_player' else 1])
    case.pop('witnesses', None)
    case.pop('relations', None)
    if variant == 'second_player':
        case['state']['players'].reverse()
        case['state']['active_player'] = 1
    else:
        case['state']['players'][0].update(turn=7, sep=1)
    result = check_graph(case)
    if variant == 'super_evolve':
        assert any(a['type'] == 'super_evolve' for a in result['actions'])


def test_unspent_attack_is_not_dominated_by_face_damage() -> None:
    # AI_NOTE: 独立受入で検出。敵の体力を減らしても攻撃権を使った結果は、未攻撃状態の上位互換でない。
    case = next(c for c in CASES if c['id'] == 'summon_storm_grant_order')
    result = analyze(Battle(case['state'], case['cards']))
    observed = {(p['players'][1]['health'], tuple(e['attacks'] for e in p['players'][0]['board']))
                for i in result['candidates'] for p in [state_at(result, i)]
                if not p['players'][0]['hand']}
    assert (20, (0,)) in observed
    assert (17, (1,)) in observed
