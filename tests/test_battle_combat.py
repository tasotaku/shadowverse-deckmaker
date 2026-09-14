"""Ability-free combat: independent engine enumeration and fixed rule oracles."""
from __future__ import annotations

from copy import deepcopy
from random import Random
from typing import Any

import pytest

from svdeck.battle import Battle, Json, replay
from svdeck.battle_combat import analyze, project

CARDS: dict[str, Json] = {'v': {'kind': 'follower', 'name': '検証体', 'cost': 1, 'attack': 1, 'health': 1}}


def body(ident: str, attack: int, health: int, **values: Any) -> Json:
    return {'id': ident, 'card_id': 'v', 'attack': attack, 'health': health, **values}


def game(own: list[Json], enemy: list[Json], *, owner: int = 0, turn: int = 7,
         face: int = 20, **values: Any) -> Battle:
    players = [{'board': own, 'turn': turn, **values}, {'board': enemy, 'health': face}]
    if owner:
        players.reverse()
    return Battle({'players': players, 'active_player': owner}, CARDS)


def summary(battle: Battle) -> Json:
    owner = battle.state['active_player']
    own, enemy = (battle.state['players'][i] for i in (owner, 1-owner))
    boards = [[{k: b[k] for k in ('id', 'name', 'attack', 'health', 'max_health', 'evolved')}
               for b in p['board']] for p in (own, enemy)]
    return {'own_board': boards[0], 'enemy_board': boards[1], 'enemy_health': enemy['health'],
            'ep': own['ep'], 'sep': own['sep'], 'win': battle.state['winner'] == owner}


def key(value: Json) -> tuple[Any, ...]:
    return tuple(tuple(tuple(b[k] for k in ('id', 'attack', 'health', 'max_health', 'evolved'))
                       for b in value[z]) for z in ('own_board', 'enemy_board')) + (
                           value['enemy_health'], value['ep'], value['sep'], value['win'])


def no_worse(a: Json, b: Json) -> bool:
    # Independent dictionary/vector formulation of the documented endpoint criteria.
    if a['win'] or b['win']:
        return bool(a['win'])
    if not (a['enemy_health'] <= b['enemy_health'] and a['ep'] >= b['ep'] and a['sep'] >= b['sep']):
        return False
    for zone, favorable, unfavorable in [('own_board', a, b), ('enemy_board', b, a)]:
        larger = {e['id']: e for e in favorable[zone]}
        for smaller in unfavorable[zone]:
            match = larger.get(smaller['id'])
            if match is None or match['evolved'] != smaller['evolved']:
                return False
            if any(match[k] < smaller[k] for k in ('attack', 'health', 'max_health')):
                return False
    return True


def exhaustive(battle: Battle, mode: str) -> list[Json]:
    # Enumerate EVERY action sequence with the real engine, no state dedup and no beam score.
    allowed = {'attack'} | ({'evolve'} if mode != 'attack' else set()) | ({'super_evolve'} if mode == 'super' else set())
    results = [summary(battle)]
    for action in battle.legal_actions():
        if action['type'] not in allowed:
            continue
        branch = Battle(battle.state, battle.cards, record=False)
        branch.step(action)
        results.extend(exhaustive(branch, mode))
    return results


def checked(battle: Battle, mode: str = 'super') -> Json:
    before = deepcopy(battle.export())
    result = analyze(battle, mode)
    assert result['complete']
    assert battle.export() == before
    for candidate in result['candidates']:
        record = {**result['record'], 'actions': candidate['actions'], 'frames': []}
        assert key(summary(replay(record))) == key(candidate)
    return result


@pytest.mark.parametrize('mode', ['attack', 'evolve', 'super'])
def test_all_small_board_paths_match_independent_engine(mode: str) -> None:
    rng = Random(621)
    for n in range(12):
        battle = game([body('a', rng.randrange(5), rng.randrange(1, 6), entered_turn=7 if n % 3 == 0 else 0),
                       body('b', rng.randrange(5), rng.randrange(1, 6))],
                      [body('x', rng.randrange(5), rng.randrange(1, 6)),
                       body('y', rng.randrange(5), rng.randrange(1, 6), evolved=2 if n % 4 == 0 else 0)],
                      owner=n % 2, face=20)
        result = checked(battle, mode)
        raw = exhaustive(project(battle), mode)
        unique = {key(r): r for r in raw}
        expected = {k for k, b in unique.items() if not any(k != j and no_worse(a, b) for j, a in unique.items())}
        assert {key(c) for c in result['candidates']} == expected
        assert result['stats']['endpoints'] == len(unique)


def test_new_follower_super_ping_lethal_and_sickness() -> None:
    battle = game([body('a', 1, 1, entered_turn=7)], [body('x', 4, 3)], face=1)
    result = checked(battle)
    assert len(result['candidates']) == 1
    winner = result['candidates'][0]
    assert winner['actions'] == [{'type': 'super_evolve', 'source': 'a'}, {'type': 'attack', 'source': 'a', 'target': 'x'}]
    assert winner['own_board'][0]['health'] == 4 and winner['win']
    assert all(not c['win'] for c in checked(battle, 'evolve')['candidates'])


def test_combined_sacrifice_survives_bad_intermediate_score() -> None:
    result = checked(game([body('a', 1, 1), body('b', 3, 3)], [body('x', 4, 4)]), 'attack')
    assert any(c['own_board'] == c['enemy_board'] == [] and len(c['actions']) == 2 for c in result['candidates'])
    assert any(c['enemy_health'] == 16 and len(c['own_board']) == 2 for c in result['candidates'])
    assert result['stats']['duplicates'] > 0


def test_enemy_super_takes_damage_and_has_no_ping() -> None:
    result = checked(game([body('a', 3, 4)], [body('x', 3, 3, evolved=2)]), 'attack')
    trade = next(c for c in result['candidates'] if not c['enemy_board'])
    assert trade['own_board'][0]['health'] == 1
    assert trade['enemy_health'] == 20


def test_resource_choices_and_attack_before_evolve() -> None:
    result = checked(game([body('a', 1, 4)], [body('x', 2, 1)], ep=1, sep=1))
    trades = [c for c in result['candidates'] if not c['enemy_board']]
    assert {(c['ep'], c['sep']) for c in trades} == {(1, 1), (0, 1), (1, 0)}
    assert all(len([a for a in c['actions'] if a['type'] == 'attack']) <= 1 for c in result['candidates'])
    # Directly compare all sequence endpoints, including attack THEN evolve even if dominated.
    raw = exhaustive(project(game([body('a', 3, 5)], [body('x', 1, 2)])), 'super')
    assert any(c['own_board'] and c['own_board'][0]['attack'] == 5 and c['own_board'][0]['health'] == 6
               and not c['enemy_board'] for c in raw)


@pytest.mark.parametrize('owner,turn,normal,super_', [(0, 4, False, False), (0, 5, True, False),
    (0, 6, True, False), (0, 7, True, True), (1, 3, False, False), (1, 4, True, False),
    (1, 5, True, False), (1, 6, True, True)])
def test_evolution_thresholds(owner: int, turn: int, normal: bool, super_: bool) -> None:
    result = checked(game([body('a', 1, 1, attacks=1)], [], owner=owner, turn=turn))
    kinds = {a['type'] for c in result['candidates'] for a in c['actions']}
    assert ('evolve' in kinds) == normal
    assert ('super_evolve' in kinds) == super_
    assert 'attack' not in kinds


@pytest.mark.parametrize('changes', [{'evolved_this_turn': True}, {'ep': 0, 'sep': 0}])
def test_no_evolution_right(changes: Json) -> None:
    result = checked(game([body('a', 1, 1)], [], **changes))
    assert all(a['type'] == 'attack' for c in result['candidates'] for a in c['actions'])


def test_abilities_and_hand_removed_without_affecting_original() -> None:
    cards = {**CARDS, 'effect': {'kind': 'follower', 'name': '効果体', 'cost': 1, 'attack': 1, 'health': 1,
                               'keywords': ['守護', '必殺', 'バリア', '疾走'],
                               'last_words': [{'op': 'damage', 'target': 'enemy_leader', 'amount': 9}],
                               'evolve': [{'op': 'buff', 'target': 'self', 'attack': 9}]},
             'amulet': {'kind': 'amulet', 'name': '置物', 'cost': 1}}
    battle = Battle({'players': [{'board': [dict(body('a', 1, 1), card_id='effect'), {'card_id': 'amulet'}],
                                 'hand': ['effect'], 'turn': 7}, {'board': [dict(body('x', 1, 1), card_id='effect')]}]}, cards)
    result = checked(battle, 'attack')
    assert len(result['record']['initial']['players'][0]['board']) == 1
    assert result['record']['initial']['players'][0]['hand'] == []
    assert any(c['enemy_health'] == 19 and c['enemy_board'] for c in result['candidates'])
    assert all(c['enemy_health'] >= 19 for c in result['candidates'])


def test_empty_board_and_budget_and_bad_inputs() -> None:
    battle = game([], [])
    result = checked(battle)
    assert len(result['candidates']) == 1 and result['candidates'][0]['actions'] == []
    assert analyze(battle, max_states=1)['complete']
    limited = analyze(game([body('a', 1, 1)], []), max_states=1)
    assert not limited['complete'] and limited['stats']['states'] == 1
    with pytest.raises(ValueError):
        analyze(battle, 'wrong')
    for limit in (0, True, 200001):
        with pytest.raises(ValueError):
            analyze(battle, max_states=limit)
    ended = game([], [])
    ended.state['winner'] = 0
    with pytest.raises(ValueError):
        analyze(ended)
