"""公開40枚の取り込みと、同じ実行環境を使う対戦・保存・描画なし実行を検査。"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from svdeck.battle import Battle, catalog, replay, run_case
from svdeck.battle_decks import load_decks, new_match, presets

DECKS = ('ramp-dragon', 'last-words-nightmare')
CASES = json.loads((Path(__file__).parents[1] / 'src/svdeck/data/battle_meta_cases.json').read_text())


def test_two_sourced_complete_decks() -> None:
    # AI_NOTE: 40枚を満たすだけでなく出典と必要カードの対応を検査する。
    decks = load_decks()
    assert {d['id'] for d in decks} == set(DECKS)
    cards = catalog()
    for deck in decks:
        assert deck['ready'] and not deck['missing'] and not deck['illegal']
        assert sum(deck['cards'].values()) == 40
        assert deck['source'].startswith('https://game8.jp/')
        assert deck['official_deck'].startswith('https://shadowverse-wb.com/')
        assert all(cid in cards and 1 <= n <= 3 for cid, n in deck['cards'].items())
    assert len(presets()) == 4


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_saved_real_card_cases(case: dict[str, Any]) -> None:
    # AI_NOTE: 人向け画面の実カード検査例も同じ開始・終了条件で固定する。
    result = run_case(case)
    assert result['passed'], result['differences']


@pytest.mark.parametrize('first', DECKS)
@pytest.mark.parametrize('second', DECKS)
@pytest.mark.parametrize('seed', [1, 7])
def test_whole_match_replay_and_recording_parity(first: str, second: str, seed: int) -> None:
    # AI_NOTE: 記録OFFでも同じ合法手・乱数・終局になることを実デッキの連鎖で検査する。
    recorded = new_match(first, second, seed)
    fast = Battle(recorded.initial, recorded.cards, record=False)
    randomizer = random.Random(seed)
    for _ in range(600):
        if recorded.state['winner'] is not None:
            break
        actions = recorded.legal_actions()
        assert fast.legal_actions() == actions
        active = [a for a in actions if a['type'] != 'end_turn']
        action = randomizer.choice(active or actions)
        recorded.step(action)
        fast.step(action)
        assert fast.state == recorded.state
    assert recorded.state['winner'] is not None
    assert replay(recorded.export()).state == recorded.state
    assert fast.frames == [] and fast.events == []


def test_unknown_deck_rejected() -> None:
    # AI_NOTE: 見つからないデッキを暗黙に既定構築へ差し替えない。
    with pytest.raises(ValueError, match='未登録'):
        new_match('unknown', DECKS[0])
