"""出典つきの環境デッキを登録し、全40枚が対応した組合せだけを開始する。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from svdeck.battle import Battle, catalog, new_game

Json = dict[str, Any]


def load_decks() -> list[Json]:
    # AI_NOTE: 更新日・出典・枚数を効果定義と分離し、環境レシピだけを差し替えられる。
    value = json.loads((Path(__file__).with_name('data') / 'battle_decks.json').read_text())
    cards = catalog()
    result: list[Json] = []
    for deck in value:
        missing = [cid for cid in deck['cards'] if cid not in cards]
        illegal = [cid for cid in deck['cards'] if cid in cards and not cards[cid].get('rotation')]
        result.append({**deck, 'ready': not missing and not illegal, 'missing': missing, 'illegal': illegal})
    return result


def new_match(first: str, second: str, seed: int = 1, mulligans: list[list[int]] | None = None) -> Battle:
    # AI_NOTE: 未対応札を別カードで埋めず、通常開始の40枚・クラス制約も検査する。
    decks = {d['id']: d for d in load_decks()}
    lists = []
    for ident in (first, second):
        if ident not in decks:
            raise ValueError(f'未登録の環境デッキです: {ident}')
        deck = decks[ident]
        if not deck['ready']:
            raise ValueError(f'{deck["name"]}には未対応または使用不可のカードがあります: {deck["missing"] + deck["illegal"]}')
        lists.append([cid for cid, count in deck['cards'].items() for _ in range(count)])
    return new_game(lists, seed=seed, mulligans=mulligans, format='rotation')


def presets() -> list[Json]:
    # AI_NOTE: 先攻後攻と同じデッキ同士も選べるよう、登録した全組合せを用意する。
    decks = load_decks()
    return [{'id': f'{a["id"]}-vs-{b["id"]}', 'title': f'{a["name"]} vs {b["name"]}',
             'initial': new_match(a['id'], b['id'], seed=14).state,
             'description': f'ローテーション・公開40枚構築（{a["checked_on"]}確認）。先攻: {a["name"]} / 後攻: {b["name"]}。',
             'sources': [a['source'], b['source']]}
            for a in decks for b in decks if a['ready'] and b['ready']]
