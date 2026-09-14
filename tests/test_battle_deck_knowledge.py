"""Public deck accounting must survive replay and never reveal hidden identities."""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from svdeck import battle_rules as rules
from svdeck.battle import Battle, new_game, replay

Json = dict[str, Any]
CARDS: dict[str, Json] = {
    'body': {'name': 'Body', 'kind': 'follower', 'cost': 0, 'attack': 1, 'health': 3},
    'other': {'name': 'Other', 'kind': 'follower', 'cost': 0, 'attack': 2, 'health': 2},
}


def initial(record: bool = True) -> Battle:
    battle = Battle({'players': [
        {'hand': [{'id': 'own-card', 'card_id': 'body'}], 'deck': ['body'] * 19 + ['other'] * 20},
        {'hand': [{'id': 'enemy-card', 'card_id': 'other'}], 'deck': ['body'] * 20 + ['other'] * 19},
    ]}, CARDS, record=record)
    battle.enable_deck_knowledge()
    return battle


def test_recipe_public_but_hidden_identity_and_order_private() -> None:
    battle = initial()
    view = battle.observation(0)
    assert view['deck_knowledge'] == [{'deck_list': {'body': 20, 'other': 20}, 'revealed': {}, 'known_hand': []}] * 2
    assert view['own_hand_originals'] == {'own-card': 'own-card'}
    assert 'deck_origins' not in view
    assert 'enemy-card' not in json.dumps(view)
    changed = copy.deepcopy(battle.state)
    changed['players'][1]['deck'].reverse()
    changed['players'][1]['hand'][0], changed['players'][1]['deck'][0] = changed['players'][1]['deck'][0], changed['players'][1]['hand'][0]
    changed['rng'] += 77
    assert Battle(changed, CARDS).observation(0) == view
    assert battle.observation(1)['own_hand_originals'] == {'enemy-card': 'enemy-card'}


@pytest.mark.parametrize('operation', ['play', 'discard', 'overflow', 'deck_summon'])
def test_original_is_counted_when_public(operation: str) -> None:
    battle = initial(record=False)
    p = battle.state['players'][0]
    if operation == 'play':
        entity = p['hand'][0]
        battle.step({'type': 'play', 'card': entity['id']})
    elif operation == 'discard':
        entity = p['hand'][0]
        battle.resolve([{'op': 'discard', 'target': 'chosen_hand'}], 0, {'id': 'effect', 'name': 'Effect'}, entity['id'])
    elif operation == 'overflow':
        p['hand'] += [battle.fresh('other') for _ in range(8)]
        entity = p['deck'][0]
        battle.resolve([{'op': 'draw', 'count': 1}], 0, {'id': 'effect', 'name': 'Effect'})
    else:
        battle.resolve([{'op': 'deck_summon', 'count': 1}], 0, {'id': 'effect', 'name': 'Effect'})
        entity = p['board'][0]
    assert battle.state['deck_knowledge'][0]['revealed'] == {entity['id']: entity['card_id']}
    assert battle.state['deck_knowledge'][0]['known_hand'] == []
    assert battle.frames == []


def test_draw_keeps_new_original_hidden() -> None:
    battle = initial()
    battle.resolve([{'op': 'draw', 'count': 1}], 0, {'id': 'effect', 'name': 'Effect'})
    assert len(battle.state['players'][0]['hand']) == 2
    assert battle.observation(1)['deck_knowledge'][0]['revealed'] == {}
    assert battle.observation(1)['deck_knowledge'][0]['known_hand'] == []


def test_bounce_replay_does_not_count_original_twice() -> None:
    battle = initial()
    battle.step({'type': 'play', 'card': 'own-card'})
    for _ in range(2):
        entity = battle.state['players'][0]['board'][0]
        battle.remove(entity['id'], 'bounce')
        returned = battle.state['players'][0]['hand'][0]
        known = battle.observation(1)['deck_knowledge'][0]
        assert known['revealed'] == {'own-card': 'body'}
        assert known['known_hand'] == [{'id': returned['id'], 'card_id': 'body'}]
        assert battle.observation(0)['own_hand_originals'] == {returned['id']: 'own-card'}
        battle = Battle(battle.state, CARDS)
        battle.step({'type': 'play', 'card': returned['id']})
        assert battle.state['deck_knowledge'][0]['known_hand'] == []
        assert battle.state['deck_knowledge'][0]['revealed'] == {'own-card': 'body'}


def test_generated_same_card_and_summoned_copy_do_not_consume_originals() -> None:
    battle = initial()
    battle.resolve([{'op': 'generate', 'card_id': 'body'}], 0, {'id': 'effect', 'name': 'Effect'})
    generated = battle.state['players'][0]['hand'][-1]
    assert battle.observation(0)['own_hand_originals'] == {'own-card': 'own-card'}
    assert battle.observation(1)['deck_knowledge'][0]['known_hand'] == [{'id': generated['id'], 'card_id': 'body'}]
    battle.step({'type': 'play', 'card': generated['id']})
    rules.summon(battle, 0, battle.fresh('body'))
    assert battle.state['deck_knowledge'][0]['revealed'] == {}
    assert battle.state['deck_knowledge'][0]['known_hand'] == []


def test_replay_and_nonrecording_keep_same_public_history() -> None:
    recorded, fast = initial(), initial(record=False)
    earliest = copy.deepcopy(recorded.initial)
    for action in [{'type': 'play', 'card': 'own-card'}, {'type': 'end_turn'}, {'type': 'play', 'card': 'enemy-card'}]:
        recorded.step(action)
        fast.step(action)
        assert recorded.state == fast.state
    assert replay(recorded.export()).state == recorded.state
    assert Battle(earliest, CARDS).observation(0)['deck_knowledge'][1]['revealed'] == {}
    assert recorded.observation(0)['deck_knowledge'][1]['revealed'] == {'enemy-card': 'other'}
    assert recorded.initial == earliest


def test_new_game_registers_recipe_before_hidden_shuffle() -> None:
    recipes = json.loads((Path(__file__).parents[1] / 'src/svdeck/data/battle_decks.json').read_text())
    decks = [[cid for cid, count in recipe['cards'].items() for _ in range(count)] for recipe in recipes[:2]]
    battle = new_game(decks, seed=29)
    assert [entry['deck_list'] for entry in battle.observation(0)['deck_knowledge']] == [dict(Counter(deck)) for deck in decks]
    assert battle.initial == battle.state
    assert Battle(battle.state, battle.cards).observation(0) == battle.observation(0)


def test_old_state_stays_identical_without_opt_in() -> None:
    battle = Battle({'players': [{'hand': ['body']}, {}]}, CARDS)
    assert 'deck_knowledge' not in battle.state
    assert 'own_hand_originals' not in battle.observation(0)
    battle.step({'type': 'play', 'card': battle.state['players'][0]['hand'][0]['id']})
    assert 'deck_knowledge' not in replay(battle.export()).state
    with pytest.raises(ValueError, match='初期40枚'):
        battle.enable_deck_knowledge()


@pytest.mark.parametrize('invalid', [
    [],
    [{'deck_list': {}, 'revealed': {}, 'known_hand': []}],
    [{'deck_list': {'body': 1}, 'revealed': {'a': 'body', 'b': 'body'}, 'known_hand': []}] * 2,
    [{'deck_list': {'missing': 40}, 'revealed': {}, 'known_hand': []}] * 2,
])
def test_invalid_public_metadata_rejected(invalid: Any) -> None:
    with pytest.raises(ValueError):
        Battle({'deck_knowledge': invalid}, CARDS)


@pytest.mark.parametrize('generated', [False, True], ids=['bounced-original', 'generated-copy'])
def test_public_garo_discount_keeps_cost_and_original_accounting(generated: bool) -> None:
    # AI_NOTE: 公開済みガロダートの自分ターン終了時の軽減は、相手にも分かる手札情報。
    battle = Battle({'players': [
        {'health': 12, 'hand': [{'id': 'original-garo', 'card_id': '10954120'}], 'deck': ['test-body'] * 39},
        {'deck': ['test-body'] * 40},
    ]}, record=False)
    battle.enable_deck_knowledge()
    p = battle.state['players'][0]
    if generated:
        battle.resolve([{'op': 'generate', 'card_id': '10954120'}], 0, {'id': 'effect', 'name': 'Effect'})
    else:
        original = p['hand'].pop(0)
        rules.summon(battle, 0, original)
        battle.remove(original['id'], 'bounce')
    public_id = p['hand'][-1]['id']
    before = battle.observation(1)
    battle.step({'type': 'end_turn'})
    view = battle.observation(1)
    knowledge = view['deck_knowledge'][0]
    assert knowledge['known_hand'] == [{'id': public_id, 'card_id': '10954120', 'cost': 7}]
    assert 'cost' not in before['deck_knowledge'][0]['known_hand'][0]
    assert knowledge['revealed'] == ({} if generated else {'original-garo': '10954120'})
    assert Battle(battle.state, battle.cards).observation(1) == view
    # Returning the same physical card again resets its cost and still consumes no extra original.
    returned = next(e for e in p['hand'] if e['id'] == public_id)
    p['hand'].remove(returned)
    rules.summon(battle, 0, returned)
    battle.remove(returned['id'], 'bounce')
    public_id = p['hand'][-1]['id']
    after = battle.observation(1)['deck_knowledge'][0]
    assert after['known_hand'] == [{'id': public_id, 'card_id': '10954120'}]
    assert after['revealed'] == knowledge['revealed']
    assert p['hand'][-1]['cost'] == 8


def test_spellboost_only_updates_already_known_cards() -> None:
    cards = CARDS | {
        'boost': {'name': 'Boost', 'kind': 'follower', 'cost': 2, 'attack': 1, 'health': 1, 'spellboost': True},
        'spell': {'name': 'Spell', 'kind': 'spell', 'cost': 0},
    }
    battle = Battle({'players': [
        {'hand': [{'id': 'hidden-boost', 'card_id': 'boost'}, {'id': 'spell', 'card_id': 'spell'}], 'deck': ['body'] * 38},
        {'deck': ['body'] * 40},
    ]}, cards, record=False)
    battle.enable_deck_knowledge()
    battle.resolve([{'op': 'generate', 'card_id': 'boost'}], 0, {'id': 'effect', 'name': 'Effect'})
    public_id = battle.state['players'][0]['hand'][-1]['id']
    battle.step({'type': 'play', 'card': 'spell'})
    view = battle.observation(1)
    assert view['deck_knowledge'][0]['known_hand'] == [{'id': public_id, 'card_id': 'boost', 'cost': 1}]
    assert view['deck_knowledge'][0]['revealed'] == {'spell': 'spell'}
    assert 'hidden-boost' not in json.dumps(view)
    assert all(e['cost'] == 1 for e in battle.state['players'][0]['hand'])


@pytest.mark.parametrize('cost', [-1, True, 1.5])
def test_invalid_known_hand_cost_rejected(cost: Any) -> None:
    battle = initial()
    state = copy.deepcopy(battle.state)
    state['deck_knowledge'][0]['known_hand'] = [{'id': 'own-card', 'card_id': 'body', 'cost': cost}]
    with pytest.raises(ValueError, match='known hand cost'):
        Battle(state, CARDS)
