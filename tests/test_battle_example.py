"""配布する一試合を、保存状態の表示だけでなく実際に再計算して検査する。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from svdeck.battle import Battle, replay

DATA = Path(__file__).parents[1] / 'src/svdeck/data'


def load_record() -> dict[str, Any]:
    # AI_NOTE: 人向け画面に配布する記録そのものを検査対象にする。
    record: dict[str, Any] = json.loads((DATA / 'battle_example_replay.json').read_text())
    return record


def test_example_replays_to_game_over() -> None:
    # AI_NOTE: 対戦内の状態と乱数も含め、保存された終局まで全手を再計算する。
    record = load_record()
    result = replay(record)
    assert result.state['winner'] in (-1, 0, 1)
    assert result.state == record['frames'][-1]['state']
    assert result.legal_actions() == []
    assert 0 < len(record['actions']) <= 2000
    assert (DATA / 'battle_example_replay.json').stat().st_size < 4_000_000


def test_example_has_both_public_forty_card_decks() -> None:
    # AI_NOTE: 初手を引いた後なので、山札と手札を合わせて公開構築の全40枚を照合する。
    record = load_record()
    decks = {deck['id']: deck for deck in json.loads((DATA / 'battle_decks.json').read_text())}
    assert record['meta']['decks'] == ['ramp-dragon', 'last-words-nightmare']
    assert record['initial']['active_player'] == 0
    for player, deck_id in zip(record['initial']['players'], record['meta']['decks']):
        cards = [card['card_id'] for card in player['deck'] + player['hand']]
        assert len(cards) == 40
        assert Counter(cards) == Counter(decks[deck_id]['cards'])
        assert player['board'] == []


def test_example_records_every_legal_action_and_event() -> None:
    # AI_NOTE: 画面の一手送りで参照するフレーム数・順序・処理履歴を全手検査する。
    record = load_record()
    assert len(record['actions']) == len(record['frames'])
    battle = Battle(record['initial'], record['cards'])
    for action, frame in zip(record['actions'], record['frames']):
        assert action in battle.legal_actions()
        assert frame['action'] == action
        battle.step(action)
        assert battle.state == frame['state']
        assert battle.events == frame['events']


def test_example_can_seek_to_each_turn_start() -> None:
    # AI_NOTE: 各ターンの入口を開始状態から直接再生して、一手送りと同じ局面になるか確かめる。
    record = load_record()
    assert replay(record, 0).state == record['initial']
    turn_starts = [index + 1 for index, action in enumerate(record['actions']) if action['type'] == 'end_turn']
    assert len(turn_starts) >= 2
    for cursor in turn_starts:
        assert replay(record, cursor).state == record['frames'][cursor - 1]['state']
