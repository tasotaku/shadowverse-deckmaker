"""Ability-free combat: independent engine enumeration and fixed rule oracles."""
from __future__ import annotations

from copy import deepcopy
from itertools import permutations
from random import Random
from typing import Any

import pytest

from svdeck.battle_env.battle import Battle, Json, replay
from svdeck.battle_env.battle_combat import analyze, project

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
    return tuple(tuple(sorted(tuple(b[k] for k in ('attack', 'health', 'max_health', 'evolved'))
                       for b in value[z])) for z in ('own_board', 'enemy_board')) + (
                           value['enemy_health'], value['ep'], value['sep'], value['win'])


def no_worse(a: Json, b: Json) -> bool:
    # Independent dictionary/vector formulation of the documented endpoint criteria.
    if a['win'] or b['win']:
        return bool(a['win'])
    if not (a['enemy_health'] <= b['enemy_health'] and a['ep'] >= b['ep'] and a['sep'] >= b['sep']):
        return False
    for zone, favorable, unfavorable in [('own_board', a, b), ('enemy_board', b, a)]:
        larger, smaller = favorable[zone], unfavorable[zone]
        if len(larger) < len(smaller):
            return False
        matches = False
        for arrangement in permutations(larger, len(smaller)):
            if all(x['evolved'] == y['evolved'] and all(x[k] >= y[k] for k in ('attack', 'health', 'max_health'))
                   for x, y in zip(arrangement, smaller)):
                matches = True
                break
        if not matches:
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
        actual = summary(replay(record))
        assert actual == {k: v for k, v in candidate.items() if k != 'actions'}
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
        # AI_NOTE: 組合せ方式は劣位の途中結果を作らない。結果集合は独立総当たりと一致することを要求する。
        reference = analyze(battle, mode, strategy='exhaustive')
        assert reference['stats']['endpoints'] == len(unique)
        assert {key(c) for c in reference['candidates']} == expected
        assert result['stats']['endpoints'] <= len(unique)


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
    # AI_NOTE: 攻撃順の重複を最初から作らないため、重複検出件数そのものは要求しない。
    assert result['strategy'] == 'grouped'


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


def test_matching_is_not_greedy_and_separate_stats_are_not_sufficient() -> None:
    from svdeck.battle_env.battle_combat import Body, Position, board_dominates, canonical, frontier
    def b(a: int, h: int) -> Body:
        return Body(a, h, h, 0, 0, False)
    assert board_dominates((b(3, 3), b(3, 1)), (b(3, 1), b(1, 3)))
    assert not board_dominates((b(4, 1), b(1, 4)), (b(3, 3),))
    x = canonical(Position((b(4, 1), b(1, 4)), (), 20, 1, 1, False, False))
    y = canonical(Position((b(3, 3),), (), 20, 1, 1, False, False))
    assert frontier([x, y]) == [0, 1]


def test_five_identical_bodies_merge_symmetry_with_replay_witnesses() -> None:
    result = checked(game([body(f'a{i}', 2, 3) for i in range(5)],
                          [body(f'x{i}', 2, 3) for i in range(5)], face=20))
    assert result['stats']['states'] < 1000
    assert len(result['candidates']) == len({key(c) for c in result['candidates']})


def test_equal_winning_lines_keep_one_representative() -> None:
    result = checked(game([body('a', 3, 3), body('b', 2, 2)], [], face=1))
    assert len(result['candidates']) == 1 and result['candidates'][0]['win']


@pytest.mark.parametrize('units,required,excluded', [
    ([(1, 1), (2, 2), (2, 3)], [((2, 3),)], [((2, 2),)]),
    ([(1, 1), (2, 2), (3, 3)], [((3, 3),), ((1, 1), (2, 2))], []),
    ([(2, 3), (3, 2)], [((2, 3),), ((3, 2),)], []),
])
def test_grouped_sacrifices_keep_incomparable_survivors(
        units: list[tuple[int, int]], required: list[tuple[tuple[int, int], ...]],
        excluded: list[tuple[tuple[int, int], ...]]) -> None:
    # AI_NOTE: 合計スタッツで比較せず、安い犠牲・攻防差・単体と横展開を別々に確認する。
    target = (3, 2) if len(units) == 2 else (4, 3)
    result = checked(game([body(str(i), *v) for i, v in enumerate(units)], [body('x', *target)]), 'attack')
    survivors = {tuple(sorted((b['attack'], b['health']) for b in c['own_board']))
                 for c in result['candidates'] if not c['enemy_board']}
    assert all(value in survivors for value in required)
    assert all(value not in survivors for value in excluded)


def test_grouped_partial_damage_and_search_reduction() -> None:
    # AI_NOTE: 倒せない敵を削る選択も残し、同条件の全探索より操作数が減ることを確認する。
    partial = checked(game([body('a', 2, 2)], [body('x', 5, 5)]), 'attack')
    assert any(not c['own_board'] and c['enemy_board'][0]['health'] == 3 for c in partial['candidates'])
    battle = game([body('a', 4, 1), body('b', 2, 1), body('c', 2, 1)], [body('x', 4, 4)])
    grouped = checked(battle, 'attack')
    full = analyze(battle, 'attack', strategy='exhaustive')
    assert {key(c) for c in grouped['candidates']} == {key(c) for c in full['candidates']}
    assert grouped['stats']['transitions'] < full['stats']['transitions']
    with pytest.raises(ValueError):
        analyze(battle, strategy='wrong')


def test_continuation_matching_keeps_attack_and_face_rights() -> None:
    # AI_NOTE: 次の敵を処理する前は、同じ数値でも攻撃済み・顔へ攻撃不可を同一視しない。
    from svdeck.battle_env.battle_combat import Body, Position, canonical, dominates, frontier
    small = Body(2, 2, 2, 0, 0, True)
    base = canonical(Position((small,), (), 20, 1, 1, False, False))
    spent = base._replace(own=(small._replace(attacks=1),))
    sick = base._replace(own=(small._replace(ready=False),))
    assert dominates(base, spent, True) and not dominates(spent, base, True)
    assert dominates(base, sick, True) and not dominates(sick, base, True)
    assert frontier([base, spent, sick], continuation=True) == [0]
    strong_spent = base._replace(own=(small._replace(attack=3, health=3, max_health=3, attacks=1),))
    assert frontier([base, strong_spent], continuation=True) == [0, 1]


def test_lower_attack_can_preserve_super_finishing_blow() -> None:
    # AI_NOTE: 大きい攻撃力が先に敵を倒すと、召喚酔いの超進化による顔1点を失うため両方残す。
    from svdeck.battle_env.battle_combat import Body, Position, canonical, frontier
    normal = Body(1, 4, 4, 0, 0, True)
    super_body = Body(1, 4, 4, 2, 0, False)
    target = Body(0, 2, 2, 0, 0, False)
    low = canonical(Position((normal, super_body), (target,), 20, 0, 0, True, False))
    high = canonical(low._replace(own=(normal._replace(attack=2), super_body)))
    assert frontier([low, high], continuation=True) == [0, 1]
    battle = game([body('a', 2, 1), body('b', 3, 1), body('s', 1, 4, evolved=2, entered_turn=7)],
                  [body('x', 4, 2), body('y', 0, 3)], ep=0, sep=0, evolved_this_turn=True)
    result = checked(battle, 'attack')
    reference = analyze(battle, 'attack', strategy='exhaustive')
    assert {key(c) for c in result['candidates']} == {key(c) for c in reference['candidates']}
    assert any(not c['enemy_board'] and c['enemy_health'] == 19 for c in result['candidates'])


def test_evolve_after_attack_preserves_another_super_ping() -> None:
    # AI_NOTE: 進化前の小打点で削って超進化に最後を任せた後、削った個体を進化する正解を固定する。
    battle = game([body('a', 1, 4), body('s', 1, 4, evolved=2, entered_turn=7)],
                  [body('x', 0, 2)], ep=1, sep=0)
    result = checked(battle, 'evolve')
    raw = exhaustive(project(battle), 'evolve')
    unique = {key(c): c for c in raw}
    expected = {k for k, b in unique.items() if not any(k != j and no_worse(a, b) for j, a in unique.items())}
    assert {key(c) for c in result['candidates']} == expected
    assert any(not c['enemy_board'] and c['enemy_health'] == 19 and c['ep'] == 0 and
               sorted((b['attack'], b['health'], b['evolved']) for b in c['own_board']) == [(1, 4, 2), (3, 6, 1)]
               for c in result['candidates'])
