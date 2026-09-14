"""実際に指摘された局面を固定し、途中で方針が崩れる判断の再発を防ぐ。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from svdeck.battle import Battle
from svdeck.battle_ai import BASE_WEIGHTS, Player, sample_world, turn_value
from svdeck.battle_training import save_model

FIXTURE = json.loads((Path(__file__).parents[1]/'docs/evidence/ai-play-feedback.json').read_text())


def position(name: str) -> Battle:
    # AI_NOTE: 元の保存対戦を更新しても、ユーザーが指摘した開始状態を固定して検査する。
    case = next(case for case in FIXTURE['cases'] if case['id']==name)
    return Battle(case['initial'], FIXTURE['cards'])


def finish_turn(battle: Battle) -> list[dict[str, Any]]:
    # AI_NOTE: 実際の対戦入口と同じく、各手の実行後に新しい公開観測で選び直す。
    owner = battle.state['active_player']
    player = Player(battle.cards)
    actions = []
    for _ in range(12):
        decision = player.choose(battle.observation(owner))
        assert decision['action'] in battle.legal_actions()
        actions.append(decision['action'])
        battle.step(decision['action'])
        if battle.state['active_player'] != owner or battle.state['winner'] is not None:
            return actions
    pytest.fail('手番を終了できませんでした')


def test_ramp_unlocks_held_zoey_next_turn() -> None:
    # AI_NOTE: 攻めないルリアの展開より、手札の5コストにつながるPP加速を選べる。
    battle = position('ramp-before-luria')
    actions = finish_turn(battle)
    own = battle.state['players'][0]
    assert actions[0] == {'type':'play','card':'e15'}
    assert own['max_pp']==4
    assert any(card['id']=='e3' for card in own['hand'])


def test_luria_trades_into_drain_and_still_ramps() -> None:
    # AI_NOTE: 回復される顔1点より、バリアを使ったドレイン除去を選び、PP加速も完遂する。
    battle = position('luria-board-trade')
    actions = finish_turn(battle)
    assert any(action.get('source')=='e3' and action.get('target') in ('e81','e82') for action in actions)
    own, enemy = battle.state['players']
    assert own['max_pp']==5
    assert sum(card['id'] in ('e81','e82') for card in enemy['board'])==1
    luria = next(card for card in own['board'] if card['id']=='e3')
    assert luria['health']==1 and 'バリア' not in luria['keywords']


def test_zoey_removal_is_completed() -> None:
    # AI_NOTE: ダメージだけ残す自滅で終わらず、選んだ除去方針をゾーイの破壊まで進める。
    battle = position('finish-zoey-removal')
    finish_turn(battle)
    assert all(card['id']!='e25' for card in battle.state['players'][0]['board'])


def test_pass_instead_of_futile_rush_sacrifice() -> None:
    # AI_NOTE: 既に倒し切れない局面では2/1を残し、無意味な突進攻撃をしない。
    battle = position('avoid-futile-attack')
    before = battle.state['players'][1]['board']
    assert finish_turn(battle)==[{'type':'end_turn'}]
    assert battle.state['players'][1]['board']==before


def test_pass_and_partial_path_use_same_evaluation_time() -> None:
    # AI_NOTE: 相手の通常ドローとPP増加が「ターン終了」だけの不利益にならない。
    battle = position('avoid-futile-attack')
    owner = battle.state['active_player']
    world = sample_world(battle.observation(owner),battle.cards,0)
    assert turn_value(world,owner,BASE_WEIGHTS)==turn_value(world.branch({'type':'end_turn'}),owner,BASE_WEIGHTS)


@pytest.mark.parametrize('version',[None,2])
def test_saved_model_preserves_training_algorithm(tmp_path: Path, version: int | None) -> None:
    # AI_NOTE: 旧学習履歴を保存し直しても、新しい評価方式で学習したと誤表示しない。
    report: dict[str, Any] = dict(version=1,method='test',weights=BASE_WEIGHTS,base_weights=BASE_WEIGHTS,
                                  scope='test',training_games=0,generations=[],policy='search')
    if version is not None:
        report['policy_version']=version
    output = tmp_path/'model.json'
    save_model(report,output)
    assert json.loads(output.read_text())['policy_version']==(version or 1)
