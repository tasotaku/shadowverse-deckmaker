"""実カード本文と確定ルールから先に期待結果を定めた連鎖例。

カードDBがない配布環境では実カード検証を明示的にskipする。合成カードの
基本効果検証は test_battle.py でDBなしでも実行できる。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from svdeck.battle import Battle, catalog, replay


@pytest.fixture
def cards() -> dict[str, Any]:
    # AI_NOTE: 公式本文の照合済み実カードがある環境でのみ、実カードとしての連鎖を検証する。
    values = catalog()
    needed = {'10001120', '10022110', '10011110', '10011120', '10011130',
              '10012110', '90011110', '90021110'}
    if not needed <= values.keys():
        pytest.skip('照合済み実カードDBがないため実カード連鎖検証は未実施')
    return values


def test_bell_destruction_draws(cards: dict[str, Any]) -> None:
    # AI_NOTE: 守護ベルの体力2を攻撃2で破壊すると、所有者だけが1枚引く。
    battle = Battle({'active_player': 1, 'players': [
        {'board': [{'id': 'bell', 'card_id': '10001120'}],
         'deck': [{'id': 'draw', 'card_id': 'test-body'}]},
        {'board': [{'id': 'attacker', 'card_id': 'test-body'}]},
    ]}, cards=cards)
    battle.step({'type': 'attack', 'source': 'attacker', 'target': 'bell'})
    own, other = battle.state['players']
    assert own['board'] == []
    assert [c['id'] for c in own['hand']] == ['draw']
    assert own['deck'] == []
    assert own['graveyard'] == 1
    assert own['destroyed'] == ['10001120']
    assert other['board'][0]['health'] == 3
    assert other['hand'] == []
    assert replay(battle.export()).state == battle.state


def test_bell_banish_does_not_draw(cards: dict[str, Any]) -> None:
    # AI_NOTE: 同じベルでも消滅ではラストワード・墓場増加・破壊履歴が発生しない。
    cards['banish'] = {'card_id': 'banish', 'name': '検証用消滅', 'kind': 'spell', 'cost': 0,
                       'effects': [{'op': 'banish', 'target': 'chosen_enemy'}]}
    battle = Battle({'active_player': 1, 'players': [
        {'board': [{'id': 'bell', 'card_id': '10001120'}],
         'deck': [{'id': 'draw', 'card_id': 'test-body'}]},
        {'hand': [{'id': 'h', 'card_id': 'banish'}]},
    ]}, cards=cards)
    battle.step({'type': 'play', 'card': 'h', 'target': 'bell'})
    own = battle.state['players'][0]
    assert own['board'] == [] and own['hand'] == []
    assert [c['id'] for c in own['deck']] == ['draw']
    assert own['graveyard'] == 0 and own['destroyed'] == []


def test_bell_ep_evolution_draws(cards: dict[str, Any]) -> None:
    # AI_NOTE: ベルの【進化時】はEP使用で発動し、+2/+2と1枚ドローが両方起きる。
    battle = Battle({'players': [{'turn': 5,
        'board': [{'id': 'bell', 'card_id': '10001120'}],
        'deck': [{'id': 'draw', 'card_id': 'test-body'}]}, {}]}, cards=cards)
    battle.step({'type': 'evolve', 'source': 'bell'})
    own = battle.state['players'][0]
    assert own['ep'] == 1
    assert [c['id'] for c in own['hand']] == ['draw']
    assert own['board'][0]['attack'] == 2 and own['board'][0]['health'] == 4


def test_bell_effect_evolution_does_not_draw(cards: dict[str, Any]) -> None:
    # AI_NOTE: 効果進化はEPを消費せず【進化時】を発動しない（rules.mdの確定区別）。
    cards['auto-evolve'] = {'card_id': 'auto-evolve', 'name': '検証用効果進化',
        'kind': 'spell', 'cost': 0, 'effects': [{'op': 'evolve', 'target': 'chosen_ally'}]}
    battle = Battle({'players': [{'turn': 1,
        'hand': [{'id': 'h', 'card_id': 'auto-evolve'}],
        'board': [{'id': 'bell', 'card_id': '10001120'}],
        'deck': [{'id': 'draw', 'card_id': 'test-body'}]}, {}]}, cards=cards)
    battle.step({'type': 'play', 'card': 'h', 'target': 'bell'})
    own = battle.state['players'][0]
    assert own['ep'] == 2 and not own['evolved_this_turn']
    assert own['hand'] == []
    assert [c['id'] for c in own['deck']] == ['draw']
    assert own['board'][0]['attack'] == 2 and own['board'][0]['health'] == 4


def test_coach_death_summons_knight(cards: dict[str, Any]) -> None:
    # AI_NOTE: 王家の御者の破壊後にナイトが出るが、カード使用数やPP消費は増えない。
    battle = Battle({'active_player': 1, 'players': [
        {'combo': 2, 'pp': 3, 'max_pp': 3,
         'board': [{'id': 'coach', 'card_id': '10022110'}]},
        {'board': [{'id': 'attacker', 'card_id': 'test-body'}]},
    ]}, cards=cards)
    battle.step({'type': 'attack', 'source': 'attacker', 'target': 'coach'})
    own = battle.state['players'][0]
    assert [c['card_id'] for c in own['board']] == ['90021110']
    assert own['board'][0]['attack'] == 1 and own['board'][0]['health'] == 1
    assert own['combo'] == 2 and own['pp'] == 3
    assert own['graveyard'] == 1 and own['destroyed'] == ['10022110']
    assert battle.state['players'][1]['board'][0]['health'] == 2


def test_tamer_fairy_mei_sequence(cards: dict[str, Any]) -> None:
    # AI_NOTE: テイマー→生成フェアリー→メイが3枚目となり、3ダメージの条件を満たす。
    battle = Battle({'players': [{'pp': 4, 'max_pp': 4,
        'hand': [{'id': 'tamer', 'card_id': '10011110'}, {'id': 'mei', 'card_id': '10012110'}]},
        {'board': [{'id': 'enemy', 'card_id': 'test-body', 'health': 5, 'max_health': 5}]},
    ]}, cards=cards)
    battle.step({'type': 'play', 'card': 'tamer'})
    own = battle.state['players'][0]
    fairies = [c['id'] for c in own['hand'] if c['card_id'] == '90011110']
    assert len(fairies) == 2 and own['combo'] == 1 and own['pp'] == 2
    battle.step({'type': 'play', 'card': fairies[0]})
    battle.step({'type': 'play', 'card': 'mei', 'target': 'enemy'})
    own, other = battle.state['players']
    assert own['combo'] == 3 and own['pp'] == 0
    assert [c['card_id'] for c in own['board']] == ['10011110', '90011110', '10012110']
    assert [c['card_id'] for c in own['hand']] == ['90011110']
    assert other['board'][0]['health'] == 2 and other['graveyard'] == 0
    assert replay(battle.export()).state == battle.state


def test_mei_below_combo_threshold(cards: dict[str, Any]) -> None:
    # AI_NOTE: メイ自身を含めても2枚なら、敵がいても対象選択なしでダメージは発生しない。
    battle = Battle({'players': [{'pp': 1, 'max_pp': 1, 'combo': 1,
        'hand': [{'id': 'mei', 'card_id': '10012110'}]},
        {'board': [{'id': 'enemy', 'card_id': 'test-body'}]}]}, cards=cards)
    enemy_before = deepcopy(battle.state['players'][1])
    battle.step({'type': 'play', 'card': 'mei'})
    assert battle.state['players'][0]['combo'] == 2
    assert battle.state['players'][1] == enemy_before


def test_beastman_adds_combo_before_mei(cards: dict[str, Any]) -> None:
    # AI_NOTE: ビーストマンの使用1と追加コンボ1により、次のメイでコンボ3へ到達する。
    battle = Battle({'players': [{'pp': 3, 'max_pp': 3,
        'hand': [{'id': 'beast', 'card_id': '10011120'}, {'id': 'mei', 'card_id': '10012110'}]},
        {'board': [{'id': 'enemy', 'card_id': 'test-body'}]}]}, cards=cards)
    battle.step({'type': 'play', 'card': 'beast'})
    assert battle.state['players'][0]['combo'] == 2
    battle.step({'type': 'play', 'card': 'mei', 'target': 'enemy'})
    assert battle.state['players'][0]['combo'] == 3
    assert battle.state['players'][0]['pp'] == 0
    assert battle.state['players'][1]['board'] == []
    assert battle.state['players'][1]['destroyed'] == ['test-body']


def test_summoned_tamer_does_not_generate(cards: dict[str, Any]) -> None:
    # AI_NOTE: 同じ実カードでも場に出すだけならファンファーレによるフェアリー生成は起きない。
    cards['summon-tamer'] = {'card_id': 'summon-tamer', 'name': '検証用テイマー召喚',
        'kind': 'spell', 'cost': 0,
        'effects': [{'op': 'summon', 'card_id': '10011110', 'count': 1}]}
    battle = Battle({'players': [{'hand': [{'id': 'h', 'card_id': 'summon-tamer'}]}, {}]}, cards=cards)
    battle.step({'type': 'play', 'card': 'h'})
    own = battle.state['players'][0]
    assert [c['card_id'] for c in own['board']] == ['10011110']
    assert own['hand'] == [] and own['combo'] == 1 and own['graveyard'] == 1


def test_treant_combo_evolves_without_ep(cards: dict[str, Any]) -> None:
    # AI_NOTE: コンボ3のトレントは早いターンでも効果で進化し、EPの操作権を消費しない。
    battle = Battle({'players': [{'turn': 3, 'combo': 2, 'pp': 4, 'max_pp': 4,
        'hand': [{'id': 'treant', 'card_id': '10011130'}]}, {}]}, cards=cards)
    battle.step({'type': 'play', 'card': 'treant'})
    own = battle.state['players'][0]
    assert own['combo'] == 3 and own['pp'] == 0
    assert own['ep'] == 2 and not own['evolved_this_turn']
    assert own['board'][0]['evolved'] == 1
    assert own['board'][0]['attack'] == 6 and own['board'][0]['health'] == 6
