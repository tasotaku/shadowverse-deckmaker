"""Role metadata preserves activation paths; availability counts physical hands once."""
from __future__ import annotations

import copy
from collections import Counter
from fractions import Fraction
from itertools import combinations
from typing import Any

import pytest

from svdeck.battle.battle_meta_cards import definitions
from svdeck.battle.battle_roles import card_roles, response_weights

Json = dict[str, Any]


def test_registered_heal_and_conditional_draw() -> None:
    # AI_NOTE: 実カードの回復と覚醒ドローを別経路として確認する。
    card = {'kind': 'spell', 'cost': 3, **definitions()['10742310']}
    profile = card_roles({'10742310': card})['10742310']
    assert {'heal', 'resource'} <= set(profile['roles'])
    healing = next(path for path in profile['paths'] if path['op'] == 'heal')
    drawing = next(path for path in profile['paths'] if path['op'] == 'draw')
    assert healing['conditions'] == []
    assert healing['target'] == 'own_leader'
    assert healing['amount'] == 3
    assert drawing['conditions'] == ['awakening']
    assert drawing['count'] == 1
    assert healing['phase'] == drawing['phase'] == 'effects'


def test_registered_end_turn_modes_and_ward_removal() -> None:
    # AI_NOTE: 進化前後の終了時能力と守護解除を同時に成立する能力へ潰さない。
    card = {'kind': 'follower', 'cost': 10, **definitions()['10544110']}
    profile = card_roles({'10544110': card})['10544110']
    assert {'defense', 'heal', 'remove_multi', 'damage', 'develop'} <= set(profile['roles'])
    removal = next(path for path in profile['paths'] if path['op'] == 'damage' and path['target'] == 'random_enemy')
    assert removal['phase'] == 'end_turn'
    assert removal['conditions'] == [{'source': 'evolved', 'eq': 0}]
    assert removal['count'] == 2 and removal['amount'] == 8
    healing = next(path for path in profile['paths'] if path['op'] == 'heal')
    assert healing['conditions'] == removal['conditions']
    damage = next(path for path in profile['paths'] if path['op'] == 'damage' and path['target'] == 'enemy_leader')
    assert damage['conditions'] == [{'source': 'evolved', 'gte': 1}]
    assert damage['phase'] == 'end_turn'
    removed = next(path for path in profile['paths'] if path['op'] == 'remove_keywords')
    assert removed['phase'] == 'evolve'
    assert removed['keywords'] == ['守護']
    assert 'defense' in removed['removes_roles']


def test_modes_forms_and_negative_health_keep_paths() -> None:
    # AI_NOTE: 同じカードの選択モードと別形態を独立させ、本体能力を結晶へ混ぜない。
    cards: dict[str, Json] = {'card': {'kind': 'follower', 'cost': 7, 'keywords': ['守護'],
        'modes': {'fanfare': [[{'op': 'heal', 'target': 'own_leader', 'amount': 3}],
                              [{'op': 'buff', 'target': 'all_enemy', 'health': -4}]]},
        'forms': {'crystallize': {'kind': 'amulet', 'cost': 2,
                                  'last_words': [{'op': 'draw', 'count': 1}]}}}}
    before = copy.deepcopy(cards)
    profile = card_roles(cards)['card']
    healing = next(path for path in profile['paths'] if path['op'] == 'heal')
    removal = next(path for path in profile['paths'] if path['op'] == 'buff')
    assert healing['mode'] == 0 and removal['mode'] == 1
    assert removal['roles'] == ['remove_all', 'support']
    alternate = [path for path in profile['paths'] if path['form'] == 'crystallize']
    assert len(alternate) == 1
    assert alternate[0]['phase'] == 'last_words'
    assert alternate[0]['conditions'] == [{'form': 'crystallize', 'cost': 2}]
    assert cards == before


def test_generated_roles_and_summon_cycles() -> None:
    # AI_NOTE: 生成後の打点は依存を残し、直接召喚でファンファーレを発動扱いにしない。
    cards: dict[str, Json] = {
        'maker': {'kind': 'follower', 'fanfare': [{'op': 'generate', 'card_id': 'burn', 'count': 1}]},
        'burn': {'kind': 'spell', 'effects': [{'op': 'damage', 'target': 'enemy_leader', 'amount': 4}]},
        'summoner': {'kind': 'spell', 'effects': [{'op': 'summon', 'card_id': 'body'}]},
        'body': {'kind': 'follower', 'fanfare': [{'op': 'damage', 'target': 'enemy_leader', 'amount': 8}],
                 'last_words': [{'op': 'summon', 'card_id': 'body'}]},
    }
    profiles = card_roles(cards)
    assert {'damage', 'resource', 'support'} <= set(profiles['maker']['roles'])
    generated = next(path for path in profiles['maker']['paths'] if path['op'] == 'damage')
    assert generated['phase'] == 'fanfare.generate.effects'
    assert generated['card_ids'] == ['burn']
    assert generated['conditions'] == [{'requires': 'generate', 'card_id': 'burn', 'count': 1}]
    assert 'damage' not in profiles['summoner']['roles']
    assert len(profiles['summoner']['paths']) < 10


def test_repeat_random_and_enemy_crest_orientation() -> None:
    # AI_NOTE: 同じ対象への繰返し射撃と、相手へ渡したクレストの打点方向を保持する。
    cards: dict[str, Json] = {
        'repeat': {'kind': 'spell', **definitions()['10543310']},
        'crest': {'kind': 'follower', **definitions()['10744110']},
    }
    profiles = card_roles(cards)
    random = next(path for path in profiles['repeat']['paths'] if path['op'] == 'damage' and path['target'] == 'random_enemy')
    assert random['repetitions'] == 2
    assert random['roles'] == ['remove_multi']
    damage = [path for path in profiles['crest']['paths'] if path['op'] == 'damage' and path['target'] == 'own_leader']
    assert damage and all(path['roles'] == ['damage'] for path in damage)
    assert all(path['reversed_owner'] for path in damage)


def test_roles_follow_structure_not_card_names() -> None:
    # AI_NOTE: 名称やIDを変えても能力構造が同じなら役割が変わらない。
    ability: Json = {'kind': 'follower', 'keywords': ['疾走', 'ドレイン'],
                     'fanfare': [{'op': 'pp', 'amount': 2}]}
    profiles = card_roles({'a': {**ability, 'name': 'A'}, 'b': {**ability, 'name': 'B'}})
    assert profiles['a']['roles'] == profiles['b']['roles']
    assert {'damage', 'heal', 'remove_one', 'resource', 'support', 'develop'} <= set(profiles['a']['roles'])
    assert card_roles({'unknown': {'effects': [{'op': 'new_effect'}]}})['unknown']['unknown']


def test_overlap_is_assigned_once_in_response_order() -> None:
    # AI_NOTE: AB・AC・BCの3手札を最良の返しへ一度だけ割り当てる。
    pool = Counter({'a': 1, 'b': 1, 'c': 1})
    assert response_weights(pool, 2, [{'a': 1}, {'b': 1}]) == [Fraction(2, 3), Fraction(1, 3), Fraction(0)]
    assert response_weights(pool, 2, [{'a': 1, 'b': 1}, {'a': 1}, {'b': 1}]) == [Fraction(1, 3)] * 3 + [Fraction(0)]
    assert response_weights(pool, 2, [{'a': 1}, {'a': 1}, {'a': 1, 'b': 1}]) == [Fraction(2, 3), Fraction(0), Fraction(0), Fraction(1, 3)]


def test_copies_empty_impossible_and_zero_size() -> None:
    # AI_NOTE: 枚数要求・中立札・不可能な要求と空条件の境界を正確に数える。
    pool = Counter({'a': 2, 'b': 1, 'c': 1})
    assert response_weights(pool, 2, [{'a': 2}]) == [Fraction(1, 6), Fraction(5, 6)]
    assert response_weights(pool, 2, [{'missing': 1}, {'a': 3}, {'a': 2, 'b': 1}]) == [Fraction(0)] * 3 + [Fraction(1)]
    assert response_weights(pool, 2, [{}, {'a': 1}]) == [Fraction(1), Fraction(0), Fraction(0)]
    assert response_weights(pool, 2, []) == [Fraction(1)]
    assert response_weights(Counter(), 0, [{'a': 1}, {'a': 0}]) == [Fraction(0), Fraction(1), Fraction(0)]


def test_weights_match_exhaustive_physical_hands() -> None:
    # AI_NOTE: 小さな全物理手札を直接列挙した独立の数え上げと照合する。
    pool = Counter({'a': 3, 'b': 2, 'c': 1, 'unused': 2})
    requirements = [{'a': 2, 'b': 1}, {'b': 2}, {'a': 1, 'c': 1}, {'c': 1}, {'a': 1}]
    physical = list(pool.elements())
    for size in range(9):
        expected = [0] * (len(requirements) + 1)
        for indices in combinations(range(len(physical)), size):
            hand = Counter(physical[i] for i in indices)
            chosen = next((i for i, requirement in enumerate(requirements) if all(hand[cid] >= n for cid, n in requirement.items())), len(requirements))
            expected[chosen] += 1
        actual = response_weights(pool, size, requirements)
        assert actual == [Fraction(n, sum(expected)) for n in expected]
        assert sum(actual) == 1 and all(weight >= 0 for weight in actual)


@pytest.mark.parametrize(('pool', 'size', 'requirements'), [
    (Counter({'a': -1}), 0, []), (Counter({'a': True}), 0, []),
    (Counter({'a': 2}), -1, []), (Counter({'a': 2}), True, []),
    (Counter({'a': 2}), 3, []), (Counter({'a': 2}), 1, [{'a': -1}]),
    (Counter({'a': 2}), 1, [{'a': True}]), (Counter({'a': 2}), 1, [{'a': 1.5}]),
])
def test_invalid_counts_are_rejected(pool: Counter[str], size: int,
                                     requirements: list[dict[str, int]]) -> None:
    # AI_NOTE: 負値・真偽値・非整数を確率へ黙って流さず入力境界で拒否する。
    with pytest.raises(ValueError):
        response_weights(pool, size, requirements)
