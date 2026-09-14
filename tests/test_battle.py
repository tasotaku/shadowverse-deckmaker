"""Synthetic rule examples fix expectations before running the simulator.

These checks do not certify equivalence to the official game. Their fixtures are
also selectable in the visual debugger so a reported mismatch can be replayed.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from svdeck.battle import Battle, catalog, default_state, load_cases, replay, run_case

CASES = json.loads((Path(__file__).parents[1] / 'src/svdeck/data/battle_cases.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_rule_examples(case: dict[str, Any]) -> None:
    # AI_NOTE: 期待値は独立に書いた保存例で固定し、実装出力で更新しない。
    before = deepcopy(case)
    result = run_case(case)
    assert result['passed'], json.dumps(result.get('differences', result), ensure_ascii=False)
    assert case == before, 'ケースの入力・期待値を書き換えてはいけない'


def sample() -> dict[str, Any]:
    # AI_NOTE: 状態の不変性を確かめるため、ダメージだけで決まる最小局面を共用する。
    return {'players': [
        {'pp': 2, 'max_pp': 2, 'hand': [{'id': 'h', 'card_id': 'test-damage-5'}]},
        {'board': [{'id': 'enemy', 'card_id': 'test-body', 'health': 6, 'max_health': 6}]},
    ]}


@pytest.mark.parametrize('action', [
    {'type': 'play', 'card': 'missing', 'target': 'enemy'},
    {'type': 'play', 'card': 'h', 'target': 'leader:0'},
    {'type': 'play', 'card': 'h'},
    {'type': 'attack', 'source': 'enemy', 'target': 'leader:0'},
    {'type': 'unknown'},
])
def test_illegal_action_is_atomic(action: dict[str, Any]) -> None:
    # AI_NOTE: 操作拒否でPPだけ減るなどの部分更新や履歴への混入を検出する。
    battle = Battle(sample())
    before = deepcopy(battle.state)
    record = battle.export()
    with pytest.raises(ValueError):
        battle.step(action)
    assert battle.state == before
    assert battle.export() == record


def test_replay_and_branch() -> None:
    # AI_NOTE: 巻き戻しは元の履歴を壊さず、再実行すると同じ終了状態へ戻る必要がある。
    battle = Battle(sample())
    initial = deepcopy(battle.state)
    action = {'type': 'play', 'card': 'h', 'target': 'enemy'}
    battle.step(action)
    saved = battle.export()
    assert replay(json.loads(json.dumps(saved))).state == battle.state
    rewound = replay(saved, cursor=0)
    assert rewound.state == initial
    rewound.step(action)
    assert rewound.state == battle.state
    assert saved == battle.export()


def test_replay_rejects_unknown_version() -> None:
    # AI_NOTE: 未知の保存形式を現在の形式として黙って再生しない。
    saved = Battle(sample()).export()
    saved['version'] = 999
    with pytest.raises(ValueError):
        replay(saved)


def test_input_and_output_are_detached() -> None:
    # AI_NOTE: UIへ返す辞書の編集で対戦本体が変わると保存・比較の根拠が壊れる。
    supplied = sample()
    battle = Battle(supplied)
    supplied['players'][0]['pp'] = 0
    assert battle.state['players'][0]['pp'] == 2
    output = battle.step({'type': 'play', 'card': 'h', 'target': 'enemy'})
    expected = deepcopy(battle.state)
    output['state']['players'][1]['health'] = -100
    saved = battle.export()
    saved['initial']['players'][0]['pp'] = 99
    assert battle.state == expected
    assert battle.export()['initial']['players'][0]['pp'] == 2


@pytest.mark.parametrize('player', [0, 1])
def test_observation_hides_private_cards(player: int) -> None:
    # AI_NOTE: 隠されたカードIDが手札だけでなく山札・履歴経由でもAIへ漏れないことを調べる。
    state = sample()
    for i, ps in enumerate(state['players']):
        ps['hand'] = [{'id': f'secret-hand-{i}', 'card_id': 'test-body'}]
        ps['deck'] = [{'id': f'secret-deck-{i}', 'card_id': 'test-damage-5'}]
    battle = Battle(state)
    observed = battle.observation(player)
    text = json.dumps(observed)
    assert f'secret-hand-{player}' in text
    assert f'secret-hand-{1-player}' not in text
    assert 'secret-deck-0' not in text
    assert 'secret-deck-1' not in text
    before = deepcopy(battle.state)
    observed.clear()
    assert battle.state == before


def test_recording_does_not_change_battle() -> None:
    # AI_NOTE: 高速実行と目視実行は同じ対戦処理を使い、記録有無で勝敗が変わらない。
    fast, visible = Battle(sample(), record=False), Battle(sample(), record=True)
    action = {'type': 'play', 'card': 'h', 'target': 'enemy'}
    fast.step(action)
    visible.step(action)
    assert fast.state == visible.state
    assert fast.legal_actions() == visible.legal_actions()


def test_differences_find_wrong_expected_health() -> None:
    # AI_NOTE: テスト実行が成功しても期待する数値が違えば不合格にし、位置を報告する。
    result = run_case({'initial': sample(), 'actions': [], 'expected': {
        'players': [{}, {'board': [{'health': 5}]}],
    }})
    assert not result['passed']
    assert any(item['expected'] == 5 and item['actual'] == 6 and 'health' in item['path']
               for item in result['differences'])


def test_differences_reject_extra_array_entries() -> None:
    # AI_NOTE: 空の期待盤面は全消滅の意味であり、部分辞書比較でも残存カードを見逃さない。
    result = run_case({'initial': sample(), 'actions': [], 'expected': {
        'players': [{}, {'board': []}],
    }})
    assert not result['passed']
    assert result['differences']


def test_legal_actions_can_execute() -> None:
    # AI_NOTE: 操作候補が画面に出るのに受理されない不整合を最小局面で検出する。
    battle = Battle(sample())
    before = deepcopy(battle.state)
    actions = battle.legal_actions()
    assert {'type': 'play', 'card': 'h', 'target': 'enemy'} in actions
    assert battle.state == before
    for action in actions:
        Battle(sample()).step(action)


def test_random_effect_is_reproducible() -> None:
    # AI_NOTE: 同じ開始乱数と操作から再現でき、候補外へのダメージを与えない。
    definition = {'random': {'card_id': 'random', 'name': '検証用ランダムダメージ',
        'kind': 'spell', 'cost': 0,
        'effects': [{'op': 'damage', 'target': 'random_enemy', 'amount': 1}]}}
    state = {'rng': 1234, 'players': [
        {'hand': [{'id': 'h', 'card_id': 'random'}]},
        {'board': [{'id': 'a', 'card_id': 'test-body'}, {'id': 'b', 'card_id': 'test-body'}]},
    ]}
    first, second = Battle(state, cards=definition), Battle(state, cards=definition)
    action = {'type': 'play', 'card': 'h'}
    first.step(action)
    second.step(action)
    assert first.state == second.state
    assert sorted(c['health'] for c in first.state['players'][1]['board']) == [2, 3]
    assert first.state['players'][1]['health'] == 20
    assert replay(first.export()).state == first.state


def test_unsupported_effect_is_rejected() -> None:
    # AI_NOTE: 未実装効果を無視して正常に動いたように見せないことを入力時に保証する。
    definition = {'bad': {'card_id': 'bad', 'name': '未対応検査', 'kind': 'spell',
                         'cost': 0, 'effects': [{'op': 'unimplemented_effect'}]}}
    with pytest.raises(ValueError):
        Battle({'players': [{'hand': [{'id': 'h', 'card_id': 'bad'}]}, {}]}, cards=definition)


def test_catalog_and_cases_are_available() -> None:
    # AI_NOTE: パッケージ利用でも組込みカードと検証例を読み出せることを確認する。
    assert 'test-damage-5' in catalog()
    assert len(load_cases()) == len(CASES)
    assert len({case['id'] for case in CASES}) == len(CASES)
    assert len(default_state()['players']) == 2


def test_expected_error_must_actually_occur() -> None:
    # AI_NOTE: エラーを期待した例で正常終了した場合を誤って合格にしない。
    result = run_case({'initial': sample(), 'actions': [], 'expected': {},
                       'expected_error': 'ValueError'})
    assert not result['passed']


def test_unknown_card_is_rejected() -> None:
    # AI_NOTE: 未対応カードを能力なしの代用品へ勝手に変換しない。
    with pytest.raises(ValueError):
        Battle({'players': [{'hand': [{'id': 'h', 'card_id': 'unsupported-card'}]}, {}]})
