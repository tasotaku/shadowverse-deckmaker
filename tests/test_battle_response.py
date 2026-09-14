"""相手の返しと、見えない手札の枚数制約を検査する固定課題。"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from svdeck.battle import Battle
from svdeck.battle_ai import BASE_WEIGHTS, Player, sample_world
from svdeck.battle_response import best_reply, finish

Json = dict[str, Any]
CARDS: dict[str,Json] = {
    'filler':{'name':'検証用高コスト','kind':'follower','cost':10,'attack':1,'health':1,'synthetic':True},
    'bad':{'name':'小回復の遺言','kind':'follower','cost':3,'attack':4,'health':4,'synthetic':True,
           'last_words':[{'op':'heal','target':'own_leader','amount':1}]},
    'good':{'name':'後続を残す遺言','kind':'follower','cost':3,'attack':4,'health':4,'synthetic':True,
            'last_words':[{'op':'summon','card_id':'token','count':1}]},
    'token':{'name':'検証用後続','kind':'follower','cost':5,'attack':5,'health':5,'synthetic':True,'token':True},
    'clear':{'name':'検証用全除去','kind':'spell','cost':3,'synthetic':True,
             'effects':[{'op':'destroy','target':'all_enemy'}]},
}


def observed() -> tuple[Battle,Json]:
    # AI_NOTE: 同じ4/4・同じ遺言加点でも、相手の全除去後に残る内容が異なる課題。
    battle = Battle({'players':[{'pp':3,'max_pp':3,'hand':[{'id':'bad','card_id':'bad'},{'id':'good','card_id':'good'}],
                                  'deck':['filler']*3},
                                 {'max_pp':2,'deck':['clear']*3}]},CARDS)
    view = battle.observation(0)
    view['deck_knowledge'] = [
        {'deck_list':{'bad':1,'good':1,'filler':3},'revealed':{},'known_hand':[]},
        {'deck_list':{'clear':3},'revealed':{},'known_hand':[]}]
    view['own_hand_originals'] = {'bad':'bad','good':'good'}
    return battle,view


def test_reply_distinguishes_last_words_contents() -> None:
    # AI_NOTE: 残存能力の一律点では同点だが、全除去を受ける小回復札より後続を残す札を選ぶ。
    battle,view = observed()
    assert Player(battle.cards,policy='turn').choose(view)['action']=={'type':'play','card':'bad'}
    decision = Player(battle.cards,policy='reply').choose(view)
    assert decision['action']=={'type':'play','card':'good'}
    assert decision['response_search']['available']
    assert not decision['proven_win']


def test_reply_resolves_last_words_and_respects_pp() -> None:
    # AI_NOTE: 3PPあれば全除去で盤面を消せるが、2PPではその同じ手を使えない。
    battle,view = observed()
    world = sample_world(view,battle.cards,0).branch({'type':'play','card':'bad'})
    response = finish(world,0)
    _,plan,_,_ = best_reply(response,0,BASE_WEIGHTS)
    assert any(action['type']=='play' for action in plan)
    for action in plan:
        assert action in response.legal_actions()
        response = response.branch(action)
    assert response.state['players'][0]['board']==[]
    poor = finish(world,0)
    poor.state['players'][1]['pp']=2
    poor.state['players'][1]['extra_pp_used']=True
    _,plan,_,_ = best_reply(poor,0,BASE_WEIGHTS)
    assert all(action['type']!='play' for action in plan)


def test_sampling_uses_copies_and_joint_hand_availability() -> None:
    # AI_NOTE: 9枚から3枚なら特定1枚は約1/3、特定3枚が全部揃うのは約1/84。独立なカード確率の積にしない。
    battle,view = observed()
    view['players'][1]['hand']={'count':3}
    view['players'][1]['deck']={'count':6}
    pool = {'bad':1,'good':1,'clear':1,'filler':6}
    view['deck_knowledge'][1]['deck_list']=pool
    singles = combos = 0
    for seed in range(1000):
        sampled = sample_world(view,battle.cards,seed).state['players'][1]
        hand = Counter(e['card_id'] for e in sampled['hand'])
        assert hand+Counter(e['card_id'] for e in sampled['deck'])==pool
        singles += bool(hand['clear'])
        combos += all(hand[cid] for cid in ('bad','good','clear'))
    assert .28 < singles/1000 < .39
    assert .003 < combos/1000 < .025
    assert combos < singles/10


def test_public_used_copies_and_own_hand_are_removed_once() -> None:
    # AI_NOTE: 公開済みの使用札・バウンス札と、見えている自分の元札を二重計上しない。
    battle,view = observed()
    view['deck_knowledge'][1].update(revealed={'used':'clear','returned':'clear'},known_hand=[{'id':'returned-now','card_id':'clear','cost':2}])
    view['players'][1]['hand']={'count':1}
    view['players'][1]['deck']={'count':1}
    sampled = sample_world(view,battle.cards,9)
    assert [e['card_id'] for e in sampled.state['players'][0]['deck']]==['filler']*3
    assert sampled.state['players'][1]['hand'][0]['id']=='returned-now'
    assert sampled.state['players'][1]['hand'][0]['cost']==2
    assert len(sampled.state['players'][1]['deck'])==1


def test_reply_choice_only_depends_on_public_observation() -> None:
    # AI_NOTE: 判断入力に本物の非公開状態は入れず、同じ観測なら返しの候補まで再現する。
    battle,view = observed()
    before = deepcopy(view)
    a = Player(battle.cards,policy='reply',seed=4).choose(view)
    battle.state['players'][1]['deck'].reverse()
    battle.state['rng']=98765
    b = Player(battle.cards,policy='reply',seed=4).choose(deepcopy(view))
    assert view==before
    assert {k:v for k,v in a.items() if k!='elapsed_ms'}=={k:v for k,v in b.items() if k!='elapsed_ms'}
