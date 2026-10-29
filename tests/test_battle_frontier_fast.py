"""Differential transitions for the closed integer kernel."""
from __future__ import annotations

import copy
import json
import random
from fractions import Fraction

import pytest

from svdeck.battle.battle import Battle, Json
from svdeck.battle.battle_frontier import analyze, state_at
from svdeck.battle.battle_frontier_fast import Kernel, eligible
from svdeck.battle.battle_practical import ChanceBattle, Chance


def semantic(state: Json) -> str:
    # AI_NOTE: 一般探索と同じく破壊順・能力順・乱数seedだけを意味比較から外す。
    value = copy.deepcopy(state)
    value.pop('rng', None)
    for player in value['players']:
        player['destroyed'].sort()
        for entity in player['board']+player['hand']:
            entity['keywords'].sort()
    return json.dumps(value, sort_keys=True)


def scenario(seed: int) -> Battle:
    # AI_NOTE: 固定ケース名で高速化せず、5能力・進化・生成ID・0コストを組み合わせた入力を作る。
    rng = random.Random(seed)
    keywords = ['バリア', '必殺', '疾走', '突進', '守護']
    cards: dict[str, Json] = {
        f'f{i}': {'name': f'Body{i}', 'kind': 'follower', 'cost': 1, 'attack': rng.randrange(5),
                  'health': rng.randint(1, 6), 'keywords': rng.sample(keywords, rng.randrange(4))}
        for i in range(5)}
    effects = [{'op': 'damage', 'target': 'chosen_enemy', 'amount': rng.randrange(5)},
               {'op': 'damage', 'target': 'random_enemy', 'amount': rng.randrange(5)},
               {'op': 'destroy', 'target': 'chosen_enemy'},
               {'op': 'split_damage', 'amount': rng.randrange(9)},
               {'op': 'grant', 'target': 'chosen_ally', 'keywords': rng.sample(keywords, rng.randrange(1, 6))},
               {'op': 'summon', 'card_id': 'f4'}]
    for index in range(2):
        effect = effects[(seed+index) % len(effects)]
        cards[f's{index}'] = {'name': f'Spell{index}', 'kind': 'spell', 'cost': rng.randrange(3), 'effects': [effect]}
    players: list[Json] = []
    for owner in range(2):
        board = [{'id': f'e{owner*2+i+1}', 'card_id': f'f{owner*2+i}', 'evolved': rng.randrange(3),
                  'entered_turn': rng.choice([0, 7]), 'attacks': rng.randrange(3)} for i in range(2)]
        players.append({'health': rng.randint(1, 20), 'turn': 7, 'ep': 1, 'sep': 1,
                        'max_pp': 3, 'pp': 3, 'board': board, 'graveyard': rng.randrange(3),
                        'destroyed': ['f0'], 'combo': rng.randrange(4), 'extra_pp_used': bool(seed % 3)})
    active = seed % 2
    players[active]['hand'] = [{'id': f'h{i}', 'card_id': f's{i}'} for i in range(2)]
    return Battle({'players': players, 'active_player': active}, cards)


@pytest.mark.parametrize('seed', range(96))
def test_kernel_transitions_against_public_battle(seed: int) -> None:
    # AI_NOTE: 各訪問点の全合法手・全抽選枝を公開Battleへ再生し、途中からも一致することを確かめる。
    battle = scenario(seed)
    assert eligible(battle)
    kernel = Kernel(battle)
    state = kernel.initial
    rng = random.Random(seed)
    for _ in range(10):
        current = ChanceBattle(kernel.state(state), battle.cards, record=False)
        legal = [a for a in current.legal_actions() if a['type'] != 'end_turn']
        actual = list(kernel.actions(state))
        assert sorted(map(lambda a: json.dumps(a, sort_keys=True), actual)) == sorted(map(lambda a: json.dumps(a, sort_keys=True), legal))
        choices = []
        for action in actual:
            branches = kernel.outcomes(state, action)
            observed = set()
            for child, probability, draws in branches:
                reference = current.branch(action, tuple(draws))
                assert semantic(kernel.state(child)) == semantic(reference.state), (seed, action, draws)
                numerator = 1
                for size in reference.sizes:
                    numerator *= size
                assert probability == Fraction(1, numerator)
                observed.add(tuple(draws))
                choices.append(child)
            work: list[tuple[int, ...]] = [()]
            expected = set()
            while work:
                tape = work.pop()
                try:
                    current.branch(action, tape)
                except Chance as chance:
                    work.extend(tape+(i,) for i in range(chance.size))
                else:
                    expected.add(tape)
            assert observed == expected
        if not choices:
            break
        state = rng.choice(choices)


def test_complex_effect_uses_generic_backend() -> None:
    # AI_NOTE: 高速条件から外れる能力は黙って省かず、完全な汎用処理へ戻す。
    battle = scenario(0)
    cid = battle.state['players'][0]['hand'][0]['card_id']
    battle.cards[cid]['effects'].append({'op': 'grant', 'target': 'all_ally', 'keywords': ['疾走']})
    assert not eligible(battle)
    result = analyze(battle, max_states=1000, seconds=5)
    assert result.get('encoding') != 'fixed-slots-v1'
    with pytest.raises(ValueError, match='対象外'):
        analyze(battle, backend='fixed-slots')


def test_existing_record_starts_at_current_position() -> None:
    # AI_NOTE: APIが途中記録を解析するとき、初期局面へ戻らずその時点をrootにする。
    battle = scenario(1)
    action = next(a for a in battle.legal_actions() if a['type'] != 'end_turn')
    battle.step(action)
    result = analyze(battle, seconds=5, max_states=10000)
    assert semantic(state_at(result, 0)) == semantic(battle.state)
