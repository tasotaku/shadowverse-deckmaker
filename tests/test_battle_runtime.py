"""公開入口のデッキ開始・探索・検証記録を検査する。"""
from __future__ import annotations

from copy import deepcopy
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from svdeck.battle import Battle, catalog, demo_state, new_game, replay, run_case, search
from svdeck.battle_cards import load_catalog


def test_new_game_deals_and_replays() -> None:
    # AI_NOTE: 両者4枚配布の後、先攻だけ通常ドローし、後攻の初ターンが飛ばない。
    battle = Battle(demo_state())
    first, second = battle.state['players']
    assert (first['turn'], first['pp'], len(first['hand']), len(first['deck'])) == (1, 1, 5, 35)
    assert (second['turn'], second['pp'], len(second['hand']), len(second['deck'])) == (0, 0, 4, 36)
    battle.step({'type': 'end_turn'})
    assert (second['turn'], second['pp'], len(second['hand']), len(second['deck'])) == (1, 1, 5, 35)
    assert replay(battle.export()).state == battle.state


def deck() -> list[str]:
    # AI_NOTE: 配布例の40枚を利用し、テスト専用の架空カードを通常対戦へ混ぜない。
    p = demo_state()['players'][0]
    return [e['card_id'] for e in p['hand'] + p['deck']]


def test_mulligan_does_not_redraw_returned_instances() -> None:
    # AI_NOTE: 選択した同一個体を引き直さず、枚数と乱数再現を保つ。
    cards = deck()
    original = new_game([cards,cards], seed=88, format='unlimited')
    replaced = new_game([cards,cards], seed=88, mulligans=[[0,1,2,3],[0,1,2,3]],format='unlimited')
    for i in range(2):
        old_ids = {e['id'] for e in original.state['players'][i]['hand'][:4]}
        new_ids = {e['id'] for e in replaced.state['players'][i]['hand'][:4]}
        assert old_ids.isdisjoint(new_ids)
        assert len(replaced.state['players'][i]['hand']+replaced.state['players'][i]['deck']) == 40
    assert new_game([cards,cards],seed=88,format='unlimited').state == original.state


@pytest.mark.parametrize('bad', ['size','copies','mixed','unsupported','token'])
def test_deck_constraints(bad: str) -> None:
    # AI_NOTE: 合法40枚の対戦と自由な条件配置を混同させない。
    cards = deck()
    if bad == 'size': cards.pop()
    elif bad == 'copies': cards = ['10001110']*40
    elif bad == 'mixed': cards[0] = '10021110'
    elif bad == 'unsupported': cards[0] = 'not-supported'
    else: cards[0] = '90011110'
    with pytest.raises(ValueError):
        new_game([cards,deck()],format='unlimited')


def test_real_game_finishes_and_replays() -> None:
    # AI_NOTE: 単一局面だけでなく、40枚デッキを勝敗まで実際に進めて検査する。
    battle = Battle(demo_state())
    for _ in range(250):
        legal = battle.legal_actions()
        if not legal: break
        face = [a for a in legal if a['type']=='attack' and a['target'].startswith('leader:')]
        active = [a for a in legal if a['type'] in ('play','attack','evolve','super_evolve')]
        battle.step((face or active or legal)[0])
        for p in battle.state['players']:
            assert 0 <= p['health'] <= p['max_health']
            assert 0 <= p['pp'] <= p['max_pp'] + 1
            assert len(p['hand']) <= 9 and len(p['board']) <= 5
    assert battle.state['winner'] in (0,1,-1)
    assert replay(json.loads(json.dumps(battle.export()))).state == battle.state


def test_search_returns_replayable_witness() -> None:
    # AI_NOTE: 手順発見だけでなく、返却した手順の再実行が目的の状態に届くことを確かめる。
    initial = {'players':[{'pp':2,'max_pp':2,'hand':[{'id':'h','card_id':'test-damage-5'}]}, {'board':[{'id':'e','card_id':'test-body'}]}]}
    result = search(initial, {'players':[{}, {'board':[]}]}, max_depth=2, max_nodes=30)
    assert result['status'] == 'found'
    assert result['actions'] == [{'type':'play','card':'h','target':'e'}]
    assert replay(result['record']).state['players'][1]['board'] == []
    limited = search(initial, {'players':[{'health':99}, {}]},max_depth=0,max_nodes=1)
    assert limited['status']=='limit'


def test_replay_rejects_changed_cards_and_results() -> None:
    # AI_NOTE: 保存した効果や結果が変更された記録を正常な再現として通さない。
    b=Battle({'players':[{'board':[{'id':'a','card_id':'test-body'}]}, {}]})
    b.step({'type':'attack','source':'a','target':'leader:1'})
    record=b.export()
    altered=deepcopy(record);altered['cards']['test-body']['attack']=100
    with pytest.raises(ValueError): replay(altered)
    altered=deepcopy(record);altered['frames'][0]['state']['players'][1]['health']=19
    with pytest.raises(ValueError): replay(altered)


def test_catalog_detects_changed_card_source(tmp_path: Path) -> None:
    # AI_NOTE: DBの能力変更時に、旧コードを新しい能力へ適用しない。
    from svdeck.db import DB_PATH
    source=sqlite3.connect(DB_PATH)
    target=sqlite3.connect(tmp_path/'cards.db')
    source.backup(target); source.close()
    target.execute("update card set skill_text='未知の新しい能力' where card_id=10011110")
    target.commit();target.close()
    assert '10011110' not in load_catalog(tmp_path/'cards.db')
    assert '10001130' in load_catalog(tmp_path/'cards.db')


def test_incomplete_expectation_cannot_pass() -> None:
    # AI_NOTE: 期待値未入力を全一致として扱わない。
    with pytest.raises(ValueError):
        run_case({'initial':{},'actions':[],'expected':{}})


def test_catalog_has_87_real_cards() -> None:
    # AI_NOTE: 対応数を実際のDBと照合し、未対応をカウントへ混ぜない。
    assert sum(not c.get('synthetic',False) for c in catalog().values()) == 87


def test_super_evolution_attack_trigger_destroy() -> None:
    # AI_NOTE: 攻撃時能力で倒した場合も超進化の追加1点が発生する。
    cards={'trigger':{'name':'攻撃時破壊の検証用','kind':'follower','cost':1,'attack':2,'health':3,
        'attack_effects':[{'op':'destroy','target':'all_enemy'}]}}
    b=Battle({'players':[{'board':[{'id':'a','card_id':'trigger','evolved':2}]},
                         {'board':[{'id':'b','card_id':'test-body'}]}]},cards)
    b.step({'type':'attack','source':'a','target':'b'})
    assert b.state['players'][1]['health']==19
    assert b.state['players'][1]['board']==[]


def test_effect_cannot_silently_ignore_unsupported_owner() -> None:
    # AI_NOTE: 相手に引かせる定義を自分のドローとして誤実行しない。
    cards={'bad':{'name':'相手ドロー','kind':'spell','cost':0,'effects':[{'op':'draw','target':'enemy_leader','count':1}]}}
    with pytest.raises(ValueError): Battle({},cards)


def test_spawn_cannot_put_spell_on_board() -> None:
    # AI_NOTE: 宣言形式の誤りも盤面のルール違反として入力時に拒否する。
    cards={'bad':{'name':'不正な召喚','kind':'spell','cost':0,'effects':[{'op':'summon','card_id':'test-damage-5'}]}}
    with pytest.raises(ValueError): Battle({},cards)
