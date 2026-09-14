"""2026-09-14のTier1二デッキ本文・公式用語集から独立に期待値を固定する。

資料: docs/battle-development.md（実装時の調査記録を参照）。
各例の開始盤面と数値は固定し、実行結果から期待値を生成しない。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from svdeck.battle import Battle, catalog, replay

Json = dict[str, Any]


@pytest.fixture
def cards() -> dict[str, Json]:
    result = catalog()
    required = {'10644120', '10842120', '10642310', '90044330', '10753310',
                '10951120', '10952110', '10954110', '10844120', '10452130',
                '10654120', '90051130', '90051140', '10444120'}
    assert required <= result.keys(), f'環境デッキの未対応カード: {sorted(required-result.keys())}'
    return result


def entity(cid: str, ident: str, **values: Any) -> Json:
    return {'card_id': cid, 'id': ident, **values}


def start(cards: dict[str, Json], own: Json | None = None, enemy: Json | None = None,
          record: bool = True) -> Battle:
    return Battle({'players': [{'pp': 10, 'max_pp': 10, **(own or {})}, enemy or {}]},
                  cards=cards, record=record)


def play(battle: Battle, ident: str, **selection: Any) -> Json:
    candidates = [a for a in battle.legal_actions() if a['type'] == 'play' and a['card'] == ident
                  and all(a.get(k) == v for k, v in selection.items())]
    assert len(candidates) == 1, f'一意の合法手が必要: {selection}, {candidates}'
    return battle.step(candidates[0])


@pytest.mark.parametrize('attack,barrier', [(0, False), (0, True), (1, True), (1, False)])
def test_lethal_works_even_at_zero_attack_or_prevented_damage(cards: dict[str, Json], attack: int, barrier: bool) -> None:
    b = start(cards, {'board': [entity('10644120', 'knife', attack=attack)]},
              {'board': [entity('test-body', 'enemy', attack=0, health=8, keywords=['バリア'] if barrier else [])]})
    b.step({'type': 'attack', 'source': 'knife', 'target': 'enemy'})
    assert b.state['players'][1]['board'] == []
    assert b.state['players'][1]['destroyed'] == ['test-body']
    assert b.state['players'][0]['board'][0]['health'] == 2


def test_lethal_does_not_override_super_evolution_protection(cards: dict[str, Json]) -> None:
    b = start(cards, {'board': [entity('test-body', 'super', evolved=2, attack=1, health=8)]},
              {'board': [entity('10644120', 'knife', attack=0)]})
    b.step({'type': 'attack', 'source': 'super', 'target': 'knife'})
    assert b.state['players'][0]['board'][0]['id'] == 'super'
    assert b.state['players'][0]['board'][0]['health'] == 8


@pytest.mark.parametrize('healths,barriers,expected,amounts', [
    ([2, 5], [], [1], [2, 4]),
    ([2, 1], [], [], [2, 4]),
    ([2, 5], [0], [2, 1], [2, 4]),
    ([2, 1], [1], [1], [2, 4]),
])
def test_split_damage_uses_order_and_gives_excess_to_last(cards: dict[str, Json], healths: list[int], barriers: list[int], expected: list[int], amounts: list[int]) -> None:
    board = [entity('test-body', f'e{i}', health=h, keywords=['バリア'] if i in barriers else []) for i, h in enumerate(healths)]
    b = start(cards, {'hand': [entity('10753310', 'live')]}, {'board': board})
    play(b, 'live')
    assert [e['health'] for e in b.state['players'][1]['board']] == expected
    # 終了盤面だけでは捨てられた余剰ダメージを検出できないため、作用量も確認。
    damage = [e for e in b.events if e['kind'] in ('damage', 'barrier') and e.get('target', '').startswith('e')]
    assert [e.get('amount') for e in damage if e['kind'] == 'damage'] == [n for i, n in enumerate(amounts) if i not in barriers]
    assert b.state['players'][1]['health'] == 20


@pytest.mark.parametrize('graveyard,health', [(5, 20), (6, 18), (7, 18)])
def test_live_necromancy_threshold_even_without_enemy_followers(cards: dict[str, Json], graveyard: int, health: int) -> None:
    b = start(cards, {'graveyard': graveyard, 'hand': [entity('10753310', 'live')]})
    play(b, 'live')
    assert b.state['players'][1]['health'] == health
    assert b.state['players'][0]['graveyard'] == graveyard + 1 - (6 if graveyard >= 6 else 0)


@pytest.mark.parametrize('discarded,own_health,enemy_health,summoned', [
    ('test-body', 11, 20, False), ('10644120', 11, 20, True), ('90044330', 12, 19, False),
])
def test_kimika_discard_trigger_is_distinct_from_play(cards: dict[str, Json], discarded: str, own_health: int, enemy_health: int, summoned: bool) -> None:
    b = start(cards, {'health': 10, 'hand': [entity('10842120', 'kimika'), entity(discarded, 'discard')],
                      'deck': [entity('test-body', 'draw')]})
    play(b, 'kimika', choices={'hand': 'discard'})
    p, q = b.state['players']
    assert p['health'] == own_health and q['health'] == enemy_health
    assert [e['id'] for e in p['hand']] == ['draw']
    assert [e['card_id'] for e in p['board']] == ['10842120'] + (['10644120'] if summoned else [])
    assert p['graveyard'] == 1 and p['destroyed'] == [] and p['combo'] == 1


def test_discard_summon_does_not_overfill_board(cards: dict[str, Json]) -> None:
    b = start(cards, {'board': [entity('test-body', f'b{i}') for i in range(4)],
                      'hand': [entity('10842120', 'k'), entity('10644120', 'd')],
                      'deck': [entity('test-body', 'draw')]})
    play(b, 'k', choices={'hand': 'd'})
    assert len(b.state['players'][0]['board']) == 5
    assert b.state['players'][0]['graveyard'] == 1
    assert b.state['players'][0]['destroyed'] == []


@pytest.mark.parametrize('hand,board', [(False, True), (True, False), (False, False)])
def test_redflow_requires_both_selected_cards(cards: dict[str, Json], hand: bool, board: bool) -> None:
    b = start(cards, {'hand': [entity('10642310', 'red')] + ([entity('test-body', 'discard')] if hand else [])},
              {'board': [entity('test-body', 'enemy')] if board else []})
    assert not any(a['type'] == 'play' and a['card'] == 'red' for a in b.legal_actions())


def test_redflow_uses_separate_hand_and_enemy_selection(cards: dict[str, Json]) -> None:
    b = start(cards, {'hand': [entity('10642310', 'red'), entity('10644120', 'knife')]},
              {'board': [entity('test-body', 'enemy')]})
    play(b, 'red', choices={'hand': 'knife', 'enemy': 'enemy'})
    p, q = b.state['players']
    assert [e['card_id'] for e in p['board']] == ['10644120']
    assert p['hand'] == [] and p['graveyard'] == 2
    assert q['board'] == [] and q['destroyed'] == ['test-body']


@pytest.mark.parametrize('count', [0, 1, 2])
def test_lumior_discards_as_many_as_possible_then_deals_damage(cards: dict[str, Json], count: int) -> None:
    b = start(cards, {'hand': [entity('10844120', 'lumior')] + [entity('test-body', f'h{i}') for i in range(count)]},
              {'board': [entity('test-body', 'enemy', health=5)]})
    play(b, 'lumior')
    p, q = b.state['players']
    assert p['hand'] == [] and p['graveyard'] == count and p['pp'] == 2
    assert q['health'] == 16 and q['board'][0]['health'] == 1


def test_duplicate_hand_choice_is_rejected_atomically(cards: dict[str, Json]) -> None:
    b = start(cards, {'hand': [entity('10844120', 'lumior'), entity('test-body', 'h1'), entity('test-body', 'h2')]})
    before = deepcopy(b.state)
    with pytest.raises(ValueError):
        b.step({'type': 'play', 'card': 'lumior', 'choices': {'hand': ['h1', 'h1']}})
    assert b.state == before


@pytest.mark.parametrize('pp,form,cost,board_size,ramp', [(2, None, 0, 0, 0), (3, 'accelerate', 3, 0, 1), (7, 'accelerate', 3, 0, 1), (8, None, 8, 1, 0)])
def test_accelerate_is_automatic_below_body_cost(cards: dict[str, Json], pp: int, form: str | None, cost: int, board_size: int, ramp: int) -> None:
    b = start(cards, {'pp': pp, 'max_pp': pp, 'hand': [entity('10844120', 'lumior')]})
    actions = [a for a in b.legal_actions() if a['type'] == 'play' and a['card'] == 'lumior']
    if pp == 2:
        assert actions == []
        return
    assert len(actions) == 1 and actions[0].get('form') == form
    b.step(actions[0])
    p = b.state['players'][0]
    assert p['pp'] == pp-cost and p['max_pp'] == pp+ramp
    assert len(p['board']) == board_size
    assert p['graveyard'] == (1 if form else 0)


@pytest.mark.parametrize('pp,form,cost,countdown', [(1, None, 0, None), (2, 'crystallize', 2, 4), (5, 'crystallize', 2, 4), (6, None, 6, None)])
def test_crystallize_is_automatic_below_body_cost(cards: dict[str, Json], pp: int, form: str | None, cost: int, countdown: int | None) -> None:
    b = start(cards, {'pp': pp, 'max_pp': pp, 'hand': [entity('10952110', 'colonel')]})
    actions = [a for a in b.legal_actions() if a['type'] == 'play' and a['card'] == 'colonel']
    if pp == 1:
        assert actions == []
        return
    assert len(actions) == 1 and actions[0].get('form') == form
    b.step(actions[0])
    p = b.state['players'][0]
    assert p['pp'] == pp-cost and p['board'][0]['countdown'] == countdown
    assert p['board'][0].get('form') == form
    assert not any(a['type'] == 'attack' for a in b.legal_actions())


def test_crystal_last_word_summons_original_follower(cards: dict[str, Json]) -> None:
    cards['advance'] = {'name': '検証用カウント短縮', 'kind': 'spell', 'cost': 0,
                        'effects': [{'op': 'countdown', 'target': 'chosen_ally_card', 'amount': 4}]}
    b = start(cards, {'pp': 2, 'max_pp': 2, 'hand': [entity('10952110', 'colonel'), entity('advance', 'advance')]})
    play(b, 'colonel')
    play(b, 'advance', target='colonel')
    p = b.state['players'][0]
    assert len(p['board']) == 1
    e = p['board'][0]
    assert e['card_id'] == '10952110' and not e.get('form')
    assert e['attack'] == 4 and e['health'] == 6 and '守護' in e['keywords']
    assert p['graveyard'] == 2 and p['destroyed'] == []


@pytest.mark.parametrize('mode,enemy_health,self_attack', [(0, 5, 3), (1, 2, 2)])
def test_baal_mode_only_runs_selected_effect(cards: dict[str, Json], mode: int, enemy_health: int, self_attack: int) -> None:
    b = start(cards, {'hand': [entity('10452130', 'baal')], 'board': [entity('test-body', 'ally')]},
              {'board': [entity('test-body', 'enemy', health=5)]})
    play(b, 'baal', mode=mode)
    p, q = b.state['players']
    assert q['board'][0]['health'] == enemy_health
    assert next(e for e in p['board'] if e['id'] == 'baal')['attack'] == self_attack
    assert next(e for e in p['board'] if e['id'] == 'ally')['attack'] == (3 if mode == 0 else 2)


def test_baal_random_enemy_mode_is_legal_without_enemy(cards: dict[str, Json]) -> None:
    b = start(cards, {'hand': [entity('10452130', 'baal')]})
    play(b, 'baal', mode=1)
    assert b.state['players'][0]['board'][0]['attack'] == 2


def test_lieutenant_respawn_loses_last_words_only_on_new_entity(cards: dict[str, Json]) -> None:
    b = start(cards, {'board': [entity('10951120', 'lieutenant', keywords=['突進'])]},
              {'board': [entity('test-body', 'enemy', health=20)]})
    b.step({'type': 'attack', 'source': 'lieutenant', 'target': 'enemy'})
    p = b.state['players'][0]
    assert len(p['board']) == 1
    child = p['board'][0]
    assert child['id'] != 'lieutenant' and child['card_id'] == '10951120'
    assert child['attack'] == 2 and child['health'] == 1 and '突進' in child['keywords']
    assert child['lost_last_words'] is True
    b.step({'type': 'attack', 'source': child['id'], 'target': 'enemy'})
    assert b.state['players'][0]['board'] == []
    assert b.state['players'][0]['destroyed'] == ['10951120', '10951120']


def test_reanimate_restores_card_and_adds_dead_type(cards: dict[str, Json]) -> None:
    b = start(cards, {'destroyed': ['10052110', '10951120', '10952110'],
                      'hand': [entity('10954110', 'reanimate')]})
    play(b, 'reanimate')
    p = b.state['players'][0]
    assert [e['card_id'] for e in p['board']] == ['10954110', '10951120', '10951120', '10951120']
    assert all(6 in e['tribes'] and not e.get('lost_last_words') for e in p['board'][1:])
    assert p['destroyed'] == ['10052110', '10951120', '10952110']


def test_reanimate_does_not_overfill_board(cards: dict[str, Json]) -> None:
    b = start(cards, {'destroyed': ['10951120'], 'hand': [entity('10954110', 'reanimate')],
                      'board': [entity('test-body', f'b{i}') for i in range(3)]})
    play(b, 'reanimate')
    p = b.state['players'][0]
    assert len(p['board']) == 5
    assert sum(e['card_id'] == '10951120' for e in p['board']) == 1
    assert p['graveyard'] == 0


@pytest.mark.parametrize('route', ['combat', 'bounce', 'destroy', 'end_turn'])
def test_ghost_leaving_replaces_destruction_and_bounce_with_banish(cards: dict[str, Json], route: str) -> None:
    own: Json = {'board': [entity('90051130', 'ghost')], 'deck': [entity('test-body', 'own_draw')]}
    enemy: Json = {'board': [entity('test-body', 'enemy')], 'deck': [entity('test-body', 'enemy_draw')]}
    if route in ('bounce', 'destroy'):
        cards['remove'] = {'name': '検証用離場', 'kind': 'spell', 'cost': 0, 'effects': [{'op': route, 'target': 'chosen_ally'}]}
        own['hand'] = [entity('remove', 'remove')]
    b = start(cards, own, enemy)
    if route == 'combat':
        b.step({'type': 'attack', 'source': 'ghost', 'target': 'enemy'})
    elif route == 'end_turn':
        b.step({'type': 'end_turn'})
    else:
        play(b, 'remove', target='ghost')
    p = b.state['players'][0]
    assert p['board'] == [] and p['destroyed'] == []
    assert not any(e['card_id'] == '90051130' for e in p['hand'])
    assert p['graveyard'] == (1 if route in ('bounce', 'destroy') else 0)


@pytest.mark.parametrize('graveyard,evolved,generated', [(3, 0, 0), (4, 1, 1), (5, 1, 1)])
def test_bibaty_evolution_event_runs_for_effect_evolution(cards: dict[str, Json], graveyard: int, evolved: int, generated: int) -> None:
    b = start(cards, {'graveyard': graveyard, 'hand': [entity('10654120', 'eye')]})
    play(b, 'eye')
    p = b.state['players'][0]
    assert p['board'][0]['evolved'] == evolved
    assert len(p['hand']) == generated
    assert all(e['card_id'] == '90054330' for e in p['hand'])
    assert p['ep'] == 2 and p['evolved_this_turn'] is False
    assert p['graveyard'] == graveyard - (4 if evolved else 0)


def test_headless_and_recorded_discard_chain_are_identical(cards: dict[str, Json]) -> None:
    own = {'health': 10, 'hand': [entity('10842120', 'kimika'), entity('90044330', 'discard')], 'deck': [entity('test-body', 'draw')]}
    headless, recorded = start(cards, own, record=False), start(cards, own)
    for b in (headless, recorded):
        play(b, 'kimika', choices={'hand': 'discard'})
    assert headless.state == recorded.state
    assert headless.state['players'][0]['health'] == 12
    assert headless.state['players'][1]['health'] == 19
    assert headless.events == []
    assert replay(recorded.export()).state == recorded.state


def test_same_end_turn_triggers_finish_before_zombie_last_words(cards: dict[str, Json]) -> None:
    # 公式腐臭のゾンビQA: 同じターン終了に予約された全体3ダメージ2回の後に再召喚。
    cards['ending'] = {'name': '検証用終了時3ダメージ', 'kind': 'follower', 'cost': 1,
                       'attack': 1, 'health': 4,
                       'end_turn': [{'op': 'damage', 'target': 'all_enemy', 'amount': 3}]}
    b = Battle({'active_player': 1, 'players': [
        {'board': [entity('90051140', 'zombie')], 'deck': [entity('test-body', 'draw')]},
        {'board': [entity('ending', 'end1'), entity('ending', 'end2')]},
    ]}, cards=cards)
    b.step({'type': 'end_turn'})
    p = b.state['players'][0]
    assert len(p['board']) == 1
    assert p['board'][0]['card_id'] == '90051140'
    assert p['board'][0]['health'] == 2 and p['board'][0]['lost_last_words'] is True
    assert p['graveyard'] == 1 and p['destroyed'] == ['90051140']


def test_zoey_shield_covers_opponent_end_turn_and_expires_after(cards: dict[str, Json]) -> None:
    # 公式ゾーイQA: 相手のターン終了時に起こるダメージもまだ無効。
    cards['ending'] = {'name': '検証用終了時リーダー1ダメージ', 'kind': 'follower', 'cost': 1,
                       'attack': 1, 'health': 4,
                       'end_turn': [{'op': 'damage', 'target': 'enemy_leader', 'amount': 1}]}
    b = start(cards, {'hand': [entity('10444120', 'zoey')], 'deck': [entity('test-body', 'draw')]},
              {'board': [entity('ending', 'end')], 'deck': [entity('test-body', 'draw2'), entity('test-body', 'draw3')]})
    play(b, 'zoey')
    assert b.state['players'][0]['health'] == 1
    assert b.state['players'][0]['max_health'] == 1
    assert '疾走' in b.state['players'][0]['board'][0]['keywords']
    b.step({'type': 'end_turn'})
    b.step({'type': 'end_turn'})
    assert b.state['players'][0]['health'] == 1 and b.state['winner'] is None
    b.step({'type': 'end_turn'})
    b.step({'type': 'attack', 'source': 'end', 'target': 'leader:0'})
    assert b.state['players'][0]['health'] == 0 and b.state['winner'] == 1


def test_zoey_below_enhance_only_ramps(cards: dict[str, Json]) -> None:
    b = start(cards, {'pp': 5, 'max_pp': 5, 'health': 10, 'hand': [entity('10444120', 'zoey')]})
    play(b, 'zoey')
    p = b.state['players'][0]
    assert p['max_pp'] == 6 and p['pp'] == 0
    assert p['max_health'] == 20 and p['health'] == 10
    assert not p.get('damage_shield') and '疾走' not in p['board'][0]['keywords']


def test_copy_preserves_damage_and_buffs_but_resets_attack_use(cards: dict[str, Json]) -> None:
    b = start(cards, {'hand': [entity('10652310', 'copy')]},
              {'board': [entity('10951120', 'enemy', attack=5, health=2, max_health=7,
                               evolved=1, attacks=1, lost_last_words=True, keywords=['守護'])]})
    play(b, 'copy', target='enemy')
    p, q = b.state['players']
    assert q['board'] == [] and q['graveyard'] == 0 and q['destroyed'] == []
    assert len(p['board']) == 1
    e = p['board'][0]
    assert e['id'] != 'enemy' and e['card_id'] == '10951120'
    assert (e['attack'], e['health'], e['max_health'], e['evolved'], e['attacks']) == (5, 2, 7, 1, 0)
    assert e['lost_last_words'] is True and e['keywords'] == ['守護']
    assert p['graveyard'] == 1


@pytest.mark.parametrize('own_healths,enemy_healths,expected_own,expected_enemy', [
    ([3, 4], [5, 6], [], [1, 2]),
    ([], [3], [], [2]),
    ([], [], [], []),
])
def test_prominence_damage_snapshots_board_count(cards: dict[str, Json], own_healths: list[int], enemy_healths: list[int], expected_own: list[int], expected_enemy: list[int]) -> None:
    b = start(cards, {'hand': [entity('10542310', 'roar')],
                      'board': [entity('test-body', f'a{i}', health=h) for i, h in enumerate(own_healths)]},
              {'board': [entity('test-body', f'b{i}', health=h) for i, h in enumerate(enemy_healths)]})
    play(b, 'roar')
    assert [e['health'] for e in b.state['players'][0]['board']] == expected_own
    assert [e['health'] for e in b.state['players'][1]['board']] == expected_enemy
    assert b.state['players'][0]['health'] == b.state['players'][1]['health'] == 20


@pytest.mark.parametrize('health,reduction', [(12, 1), (13, 0), (1, 1)])
def test_hand_end_turn_cost_reduction_threshold(cards: dict[str, Json], health: int, reduction: int) -> None:
    b = start(cards, {'health': health, 'hand': [entity('10954120', 'garodart')]},
              {'deck': [entity('test-body', 'draw')]})
    b.step({'type': 'end_turn'})
    assert b.state['players'][0]['hand'][0]['cost'] == 8-reduction


@pytest.mark.parametrize('count,legal', [(0, False), (1, False), (2, True)])
def test_spell_cannot_choose_fewer_than_required_hand_cards(cards: dict[str, Json], count: int, legal: bool) -> None:
    cards['discard-two'] = {'name': '検証用手札2枚破棄', 'kind': 'spell', 'cost': 0,
        'effects': [{'op': 'discard', 'target': 'chosen_hand', 'choice': 'hand', 'select_count': 2}]}
    b = start(cards, {'hand': [entity('discard-two', 'spell')] + [entity('test-body', f'h{i}') for i in range(count)]})
    actions = [a for a in b.legal_actions() if a['type'] == 'play' and a['card'] == 'spell']
    assert bool(actions) is legal
    if legal:
        b.step(actions[0])
        assert b.state['players'][0]['hand'] == []
        assert b.state['players'][0]['graveyard'] == 3


def test_nested_incompatible_targets_rejected_without_explicit_slots(cards: dict[str, Json]) -> None:
    cards['bad-nested'] = {'name': '検証用不正選択定義', 'kind': 'spell', 'cost': 0,
        'effects': [{'op': 'if', 'effects': [
            {'op': 'damage', 'target': 'chosen_enemy', 'amount': 1},
            {'op': 'heal', 'target': 'chosen_ally', 'amount': 1}]}]}
    with pytest.raises(ValueError):
        start(cards, {'hand': [entity('bad-nested', 'spell')]})


@pytest.mark.parametrize('overflow_card', ['10644120', '90044330'])
def test_overdraw_never_enters_hand_and_is_not_discard(cards: dict[str, Json], overflow_card: str) -> None:
    # 公式「引く」は手札に加えられず墓場増加。「捨てる」の手札からの除去とは別。
    b = Battle({'active_player': 1, 'players': [
        {'health': 10, 'hand': [entity('test-body', f'h{i}') for i in range(9)],
         'deck': [entity(overflow_card, 'overflow')]}, {}]}, cards=cards)
    b.step({'type': 'end_turn'})
    p, q = b.state['players']
    assert len(p['hand']) == 9 and p['deck'] == []
    assert p['graveyard'] == 1 and p['destroyed'] == []
    assert p['board'] == [] and p['health'] == 10 and q['health'] == 20


def test_generated_abyss_overflow_is_not_discard(cards: dict[str, Json]) -> None:
    b = start(cards, {'turn': 7, 'health': 10, 'board': [entity('10644120', 'knife')],
                      'hand': [entity('test-body', f'h{i}') for i in range(9)]})
    b.step({'type': 'super_evolve', 'source': 'knife'})
    p, q = b.state['players']
    assert len(p['hand']) == 9 and p['graveyard'] == 3
    assert p['health'] == 10 and q['health'] == 20


def test_burndknight_crest_drain_counts_once_each_own_turn_and_replays(cards: dict[str, Json]) -> None:
    b = Battle({'active_player': 1, 'players': [
        {'health': 10, 'board': [entity('90051120', 'bat1'), entity('90051120', 'bat2')],
         'deck': [entity('test-body', 'draw1'), entity('test-body', 'draw2')]},
        {'turn': 6, 'board': [entity('10744110', 'burn')], 'deck': [entity('test-body', 'draw3')]},
    ]}, cards=cards)
    b.step({'type': 'super_evolve', 'source': 'burn'})
    b.step({'type': 'end_turn'})
    assert b.state['players'][0]['health'] == 8
    b.step({'type': 'attack', 'source': 'bat1', 'target': 'leader:1'})
    assert b.state['players'][0]['health'] == 8
    b.step({'type': 'attack', 'source': 'bat2', 'target': 'leader:1'})
    assert b.state['players'][0]['health'] == 9
    # 発動済みクレストを含む途中状態を保存/復元しても意味が変わらない。
    assert Battle(b.state, cards).state == b.state
    assert replay(b.export()).state == b.state
    b.step({'type': 'end_turn'})
    b.step({'type': 'end_turn'})
    assert b.state['players'][0]['health'] == 7
    b.step({'type': 'attack', 'source': 'bat1', 'target': 'leader:1'})
    assert b.state['players'][0]['health'] == 7
    assert replay(b.export()).state == b.state


def test_macmillan_summon_trigger_buffs_all_three_and_deals_three(cards: dict[str, Json]) -> None:
    b = start(cards, {'graveyard': 10, 'hand': [entity('10754120', 'macmillan')]})
    play(b, 'macmillan')
    p, q = b.state['players']
    assert [e['card_id'] for e in p['board']] == ['10754120', '90051140', '90051140', '90051140']
    assert all(e['attack'] == 3 and e['health'] == 2 and {'突進', '守護'} <= set(e['keywords']) for e in p['board'][1:])
    assert p['graveyard'] == 0 and q['health'] == 17
    assert replay(b.export()).state == b.state


def test_nomagdala_evolution_mode_reduces_health_through_damage_protection(cards: dict[str, Json]) -> None:
    b = start(cards, {'turn': 5, 'board': [entity('10944120', 'nomagdala')]},
              {'board': [entity('test-body', 'barrier', health=4, keywords=['バリア'])]})
    b.step({'type': 'evolve', 'source': 'nomagdala', 'mode': 1})
    assert b.state['players'][1]['board'] == []
    assert b.state['players'][1]['destroyed'] == ['test-body']
    assert b.state['players'][0]['ep'] == 1


def test_itsurugi_fanfare_and_evolution_have_separate_modes(cards: dict[str, Json]) -> None:
    b = start(cards, {'turn': 7, 'ep': 0, 'hand': [entity('10854110', 'itsurugi')]},
              {'board': [entity('test-body', 'enemy', health=6)]})
    play(b, 'itsurugi', mode=1)
    assert b.state['players'][1]['board'][0]['health'] == 1
    assert b.state['players'][0]['ep'] == 1 and b.state['players'][0]['pp'] == 2
    b.step({'type': 'evolve', 'source': 'itsurugi', 'mode': 1})
    assert b.state['players'][0]['pp'] == 4 and b.state['players'][0]['ep'] == 0
    assert b.state['players'][1]['board'][0]['health'] == 1


@pytest.mark.parametrize('evolved,own_health,enemy_health,damaged_count', [(0, 18, 20, 2), (1, 10, 12, 0)])
def test_ilantha_end_turn_uses_evolution_state_and_distinct_targets(cards: dict[str, Json], evolved: int, own_health: int, enemy_health: int, damaged_count: int) -> None:
    b = start(cards, {'health': 10, 'board': [entity('10544110', 'ilantha', evolved=evolved)]},
              {'board': [entity('test-body', f'e{i}', health=9) for i in range(3)], 'deck': [entity('test-body', 'draw')]})
    b.step({'type': 'end_turn'})
    p, q = b.state['players']
    assert p['health'] == own_health and q['health'] == enemy_health
    assert sum(e['health'] == 1 for e in q['board']) == damaged_count
    assert len(q['board']) == 3


def test_tohime_deck_summon_is_two_names_and_enter_trigger_grants_rush(cards: dict[str, Json]) -> None:
    b = start(cards, {'hand': [entity('10754110', 'tohime')],
                      'deck': [entity('10951120', 'a'), entity('10951120', 'b'), entity('10851120', 'c'), entity('test-body', 'neutral')]})
    play(b, 'tohime')
    p = b.state['players'][0]
    summoned = p['board'][1:]
    assert {e['card_id'] for e in summoned} == {'10951120', '10851120'}
    assert all('突進' in e['keywords'] for e in summoned)
    assert len(p['deck']) == 2 and any(e['id'] == 'neutral' for e in p['deck'])
    assert p['combo'] == 1 and p['pp'] == 4
    assert replay(b.export()).state == b.state
