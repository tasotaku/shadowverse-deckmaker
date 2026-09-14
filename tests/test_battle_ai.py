"""対戦AIの固定課題。期待値はカード本文・戦闘規則から先に決める。

盤面の自由配置を使うため、合法40枚からの到達証明や人間との強さ比較ではない。
実カードの定義根拠は docs/battle-development.md。第三の課題のみ検証カードを使う。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from svdeck.battle import Battle, catalog
from svdeck.battle_ai import Player, execute_plan, sample_world

Json = dict[str, Any]


def entity(cid: str, ident: str, **values: Any) -> Json:
    return {'card_id': cid, 'id': ident, **values}


def player(**values: Any) -> Json:
    # 隠し山札の仮定を空配列にして人工的な山札切れ勝ちを生まない。
    return {'deck': ['90051110'] * 5, **values}


CASES = [
    ('direct', [player(board=[entity('90051130', 'a')]), player(health=1)]),
    ('guard', [player(pp=1, max_pp=1, hand=[entity('10642310', 'r'), entity('10042310', 'd')],
                      board=[entity('90051130', 'a')]),
               player(health=1, board=[entity('10944120', 'g')])]),
    ('barrier-order', [player(board=[entity('90051110', 'a'), entity('90051110', 'b'), entity('10752110', 'c')]),
                       player(health=4, board=[entity('test-barrier', 'g', health=1, attack=0,
                                                     keywords=['守護', 'バリア'])])]),
    ('evolve-first', [player(turn=5, ep=1, board=[entity('90051110', 'a')]), player(health=3)]),
    ('super-evolution-chip', [player(turn=7, sep=1, board=[entity('90051110', 'a', entered_turn=7)]),
                              player(health=1, board=[entity('10001130', 'g', health=1)])]),
    ('drain-before-self-damage', [player(health=1, board=[entity('90051120', 'bat'), entity('10851120', 'lilim')]),
                                 player(health=2)]),
    ('end-turn-lethal', [player(board=[entity('10544110', 'ilan', evolved=1, attacks=1)]), player(health=8)]),
    ('discard-burn', [player(pp=1, max_pp=1, hand=[entity('10642310', 'r'), entity('90044330', 'sky')]),
                      player(health=1, board=[entity('10944120', 'g')])]),
]


@pytest.fixture(scope='module')
def cards() -> dict[str, Json]:
    result = catalog()
    required = {'90051130', '10642310', '10042310', '10944120', '90051110', '10752110',
                '10001130', '90051120', '10851120', '10544110', '90044330', '10954120'}
    assert required <= result.keys(), f'AI課題の未対応カード: {sorted(required-result.keys())}'
    return result


@pytest.mark.parametrize('name,players', CASES, ids=[item[0] for item in CASES])
def test_search_replans_each_action_and_wins(cards: dict[str, Json], name: str, players: list[Json]) -> None:
    battle = Battle({'players': players}, cards)
    ai = Player(cards, policy='search', max_nodes=160, width=6, depth=6, seed=0)
    for _ in range(6):
        if battle.state['winner'] is not None:
            break
        assert battle.state['active_player'] == 0, f'{name}: 今ターンの勝ちを逃した'
        decision = ai.choose(battle.observation(0))
        assert decision['action'] in battle.legal_actions()
        battle.step(decision['action'])
    assert battle.state['winner'] == 0, name


@pytest.mark.parametrize('name,players', CASES, ids=[item[0] for item in CASES])
def test_proven_plan_is_executable_without_replanning(cards: dict[str, Json], name: str, players: list[Json]) -> None:
    battle = Battle({'players': players}, cards)
    decision = Player(cards).choose(battle.observation(0))
    assert decision['proven_win'], f'{name}: 公開情報のみの勝ち手順を発見できていない'
    assert not decision['uncertain']
    assert decision['plan'][0] == decision['action']
    for action in decision['plan']:
        battle.step(action)
    assert battle.state['winner'] == 0, name


def test_choose_survival_mode_over_immediate_self_defeat(cards: dict[str, Json]) -> None:
    battle = Battle({'players': [player(health=2, pp=8, max_pp=8, hand=[entity('10954120', 'garo')]),
                                  player(health=8, board=[entity('10752110', 'enemy')])]}, cards)
    decision = Player(cards).choose(battle.observation(0))
    assert decision['action'] == {'type': 'play', 'card': 'garo', 'mode': 1}
    battle.step(decision['action'])
    assert battle.state['winner'] is None
    assert battle.state['players'][0]['health'] == 2
    assert battle.state['players'][1]['board'] == []


def test_negative_oracles_really_lose(cards: dict[str, Json]) -> None:
    # 誤手が単なる別解ではなく負けになることを、本文の自傷値で確認する。
    drain = Battle({'players': CASES[5][1]}, cards)
    drain.step({'type': 'attack', 'source': 'lilim', 'target': 'leader:1'})
    assert drain.state['winner'] == 1
    assert [p['health'] for p in drain.state['players']] == [0, 1]
    suicide = Battle({'players': [player(health=2, pp=8, max_pp=8, hand=[entity('10954120', 'garo')]),
                                   player(health=8)]}, cards)
    suicide.step({'type': 'play', 'card': 'garo', 'mode': 0})
    assert suicide.state['winner'] == 1


@pytest.mark.parametrize('policy', ['random', 'greedy', 'search'])
def test_hidden_state_cannot_change_observation_or_choice(cards: dict[str, Json], policy: str) -> None:
    first = Battle({'players': [player(pp=3, max_pp=3, hand=[entity('10042310', 'ramp')],
                                      board=[entity('90051130', 'ghost')]),
                               player(hand=[entity('10954120', 'secret')])]}, cards)
    changed = deepcopy(first.state)
    changed['rng'] = 387425
    changed['next_id'] = 80000
    for owner in (0, 1):
        changed['players'][owner]['deck'] = [entity('10544110' if i % 2 else '90044330', f'hidden-{owner}-{i}')
                                             for i in range(5)]
    changed['players'][1]['hand'] = [entity('10042310', 'different-secret')]
    second = Battle(changed, cards)
    a, b = first.observation(0), second.observation(0)
    assert a == b
    one = Player(cards, policy=policy, seed=17).choose(a)
    two = Player(cards, policy=policy, seed=17).choose(b)
    assert {k: v for k, v in one.items() if k != 'elapsed_ms'} == {
        k: v for k, v in two.items() if k != 'elapsed_ms'}


def test_choice_does_not_mutate_engine_observation_or_catalog(cards: dict[str, Json]) -> None:
    battle = Battle({'players': CASES[1][1]}, cards)
    observation = battle.observation(0)
    before = deepcopy((battle.export(), observation, cards))
    Player(cards).choose(observation)
    assert (battle.export(), observation, cards) == before


def test_full_state_and_unmasked_hand_are_rejected(cards: dict[str, Json]) -> None:
    battle = Battle({'players': CASES[0][1]}, cards)
    with pytest.raises(ValueError):
        Player(cards).choose({**battle.state, 'legal_actions': battle.legal_actions()})
    view = battle.observation(0)
    view['players'][1]['hand'] = []
    with pytest.raises(ValueError):
        Player(cards).choose(view)


def test_unknown_draw_ends_plan_without_certifying_win(cards: dict[str, Json]) -> None:
    battle = Battle({'players': [player(pp=3, max_pp=9, hand=[entity('10042310', 'ramp')]), player()]}, cards)
    world = sample_world(battle.observation(0), cards, seed=0)
    drawn = world.branch({'type': 'play', 'card': 'ramp'})
    assert drawn.uncertain, '最大PP10で未知カードを引くため、以降を確定手順に含められない'
    assert len(drawn.state['players'][0]['deck']) == 4
    assert not world.uncertain, '子の不確実フラグを親に漏らさない'


def test_reanimate_marks_random_choice_even_without_random_event(cards: dict[str, Json]) -> None:
    battle = Battle({'players': [player(pp=10, max_pp=10, hand=[entity('10954110', 'reanimate')],
                                       destroyed=['10052110', '10851120']), player()]}, cards)
    world = sample_world(battle.observation(0), cards, seed=0)
    result = world.branch({'type': 'play', 'card': 'reanimate'})
    assert result.uncertain, 'リアニメイトの直接乱数呼出しも確定手順に含められない'


@pytest.mark.parametrize('execution', ['replan', 'resolve-plan'])
def test_generated_follower_uses_observed_real_id(cards: dict[str, Json], execution: str) -> None:
    # next_idは非公開なので、探索中に生成されたe1を実環境のIDと決めつけられない。
    battle = Battle({'next_id': 700, 'players': [player(pp=3, max_pp=3,
                     hand=[entity('10552110', 'trouble')]), player(health=1)]}, cards)
    decision = Player(cards).choose(battle.observation(0))
    assert decision['proven_win']
    ghost_id = decision['plan'][1]['source']
    assert decision['plan_entities'][ghost_id] == cards['90051130']['name']
    assert decision['action'] == {'type': 'play', 'card': 'trouble'}
    if execution == 'resolve-plan':
        actual_actions = execute_plan(battle, decision)
        assert actual_actions[0] == decision['action']
        assert actual_actions[1]['source'] != ghost_id
        assert battle.state['winner'] == 0
        return
    battle.step(decision['action'])
    actual_ghost = next(e for e in battle.state['players'][0]['board'] if e['card_id'] == '90051130')
    assert actual_ghost['id'] != ghost_id, 'この回帰条件は仮IDと実IDが異なる必要がある'
    next_decision = Player(cards).choose(battle.observation(0))
    assert next_decision['action'] == {'type': 'attack', 'source': actual_ghost['id'], 'target': 'leader:1'}
    battle.step(next_decision['action'])
    assert battle.state['winner'] == 0


def test_uncertain_plan_is_rejected_without_advancing_game(cards: dict[str, Json]) -> None:
    battle = Battle({'players': [player(pp=3, max_pp=9, hand=[entity('10042310', 'ramp')]), player()]}, cards)
    decision = Player(cards).choose(battle.observation(0))
    assert decision['uncertain']
    before = battle.export()
    with pytest.raises(ValueError):
        execute_plan(battle, decision)
    assert battle.export() == before


def test_hidden_deck_count_is_preserved_when_sampling(cards: dict[str, Json]) -> None:
    battle = Battle({'players': [player(), player()]}, cards)
    world = sample_world(battle.observation(0), cards, seed=9)
    assert [len(p['deck']) for p in world.state['players']] == [5, 5]
    ended = world.branch({'type': 'end_turn'})
    assert ended.state['winner'] is None
    assert len(ended.state['players'][1]['deck']) == 4


def test_search_limit_and_returned_action_remain_valid(cards: dict[str, Json]) -> None:
    battle = Battle({'players': CASES[2][1]}, cards)
    decision = Player(cards, max_nodes=1).choose(battle.observation(0))
    assert decision['nodes'] <= 1
    assert decision['limited']
    assert decision['action'] in battle.legal_actions()
