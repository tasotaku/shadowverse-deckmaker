"""確認したカード本文と実行定義の対応。未対応カードは登録しない。"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from svdeck.db import DB_PATH

Json = dict[str, Any]


def effect(op: str, target: str = 'self', **values: Any) -> Json:
    # AI_NOTE: カードの数値と作用だけを宣言し、計算は対戦本体へ集約する。
    return {'op': op, 'target': target, **values}


def definitions() -> dict[str, Json]:
    # AI_NOTE: 全文を確認したカードIDだけを対応扱いにする。下位効果の一部分一致では登録しない。
    d: dict[str, Json] = {}
    for card_id, keywords in {
        '10001130':['守護'], '10002120':[], '10021110':['疾走'], '10021130':['疾走'],
        '10041120':['守護'], '10051110':['疾走','必殺'], '10061120':['守護'],
        '10071130':['必殺','守護'], '90001110':[], '90011110':['突進'], '90021110':[],
        '90031110':[], '90031120':['守護'],
    }.items():
        d[card_id] = {'keywords': keywords}
    d['10001110'] = {'enhance':4, 'enhance_effects':[effect('buff', attack=3,health=3)]}
    d['10001120'] = {'keywords':['守護'], 'last_words':[effect('draw',count=1)], 'evolve':[effect('draw',count=1)]}
    d['10002110'] = {'evolve':[effect('heal','own_leader',amount=2)], 'super_evolve':[effect('heal','own_leader',amount=4)]}
    d['10011110'] = {'fanfare':[effect('generate',card_id='90011110',count=2)]}
    d['10011120'] = {'fanfare':[effect('combo',amount=1)]}
    d['10011130'] = {'fanfare':[effect('evolve',condition='combo3')], 'attack_effects':[effect('heal','own_leader',amount=2)]}
    d['10012110'] = {'fanfare':[effect('damage','chosen_enemy',amount=3,condition='combo3')]}
    d['10012310'] = {'effects':[effect('bounce','chosen_ally_card'),effect('damage','random_enemy',amount=2)]}
    d['10021120'] = {'keywords':['突進'], 'last_words':[effect('draw',count=1)]}
    d['10022110'] = {'last_words':[effect('summon',card_id='90021110',count=1)]}
    d['10031310'] = {'effects':[effect('draw',count=1)]}
    d['10031320'] = {'effects':[effect('summon',card_id='90031110',count=1)]}
    d['10032120'] = {'spellboost': True}
    d['10041110'] = {'fanfare':[effect('damage','chosen_enemy',amount=1)]}
    d['10041130'] = {'fanfare':[effect('damage','enemy_leader',amount=6)]}
    # Awakening replaces the base amount; represented by a separate engine expansion below.
    d['10042110'] = {'evolve':[effect('damage','chosen_enemy',amount=4)], 'super_evolve':[effect('damage','all_enemy',amount=4)]}
    d['10042310'] = {'effects':[effect('ramp',amount=1),effect('draw',count=1,condition='max_pp10')]}
    d['10051120'] = {'fanfare':[effect('damage','own_leader',amount=1)]}
    d['10051130'] = {'fanfare':[effect('necro',amount=4,effects=[effect('grant',keywords=['疾走'])])]}
    d['10052310'] = {'effects':[effect('destroy','chosen_ally'),effect('draw',count=2)]}
    d['10061110'] = {'keywords':['守護'], 'fanfare':[effect('heal','own_leader',amount=5)]}
    d['10061130'] = {'fanfare':[effect('buff','chosen_other_ally',attack=1,health=1)], 'evolve':[effect('buff','chosen_other_ally',attack=1,health=1)]}
    d['10072120'] = {'keywords':['守護'], 'evolve':[effect('summon',card_id='10072120',count=1)], 'super_evolve':[effect('summon',card_id='10072120',count=2)]}
    d['90004320'] = {'effects':[effect('destroy','chosen_enemy')]}
    d['90014310'] = {'effects':[effect('damage','chosen_any_enemy',amount=3)]}
    d['90021310'] = {'effects':[effect('damage','chosen_any_enemy',amount=1)]}
    d['90021320'] = {'effects':[effect('heal','own_leader',amount=2)]}
    d['90021330'] = {'effects':[effect('buff','chosen_ally',attack=1,keywords=['突進'])]}
    d['90021340'] = {'effects':[effect('buff','chosen_ally',health=1,keywords=['守護'])]}
    d['90031310'] = {'effects':[effect('damage','random_enemy',amount=3)]}
    d['90033310'] = {'effects':[effect('draw',count=2),effect('damage','random_enemy',amount=2)]}
    d['90034320'] = {'effects':[effect('damage','chosen_any_enemy',amount=2),effect('heal','own_leader',amount=1)]}
    d['90034340'] = {'effects':[effect('damage','all_enemy',amount=5)]}
    d['10101310'] = {'effects':[effect('summon',card_id='90001110',count=5)]}
    d['10102110'] = {'fanfare':[effect('damage','all_enemy',amount=1)], 'evolve':[effect('damage','all_enemy',amount=1)]}
    d['10102310'] = {'effects':[effect('draw',count=2)]}
    d['10103110'] = {'evolve':[effect('destroy','chosen_enemy')]}
    from svdeck.battle_meta_cards import definitions as meta_definitions
    return d | meta_definitions()


def source_hash(row: sqlite3.Row) -> str:
    # AI_NOTE: 能力調整や進化本文の変更を検出し、古い実行定義を自動的に適用しない。
    return hashlib.sha256(json.dumps([row[k] for k in ('card_id','name','cost','atk','life','type_category','skill_text','evo_json','ref_effect_text')],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def synthetic_cards() -> dict[str, Json]:
    # AI_NOTE: ユーザー提示の5ダメージなどは検証用カードとして実カードと明確に分ける。
    common: Json = {'cost':1, 'attack':2, 'health':3, 'keywords':[], 'kind':'follower', 'synthetic':True, 'class_name':'検証用', 'text':'能力なし（検証用カード）'}
    cards: dict[str, Json] = {
        'test-body': {**common, 'name':'検証用フォロワー'},
        'test-barrier': {**common, 'name':'バリアの検証用フォロワー','cost':2,'keywords':['バリア'],'text':'バリア（検証用カード）'},
        'test-damage-5': {**common,'name':'選択5ダメージ（検証用）','cost':2,'kind':'spell','attack':0,'health':0,'text':'相手フォロワー1体を選び5ダメージ。','effects':[effect('damage','chosen_enemy',amount=5)]},
    }
    for key, card in cards.items():
        card['card_id'] = key
    return copy.deepcopy(cards)


def load_catalog(db_path: Path | None = None) -> dict[str, Json]:
    # AI_NOTE: 権利物のDBを配布せず、利用者のローカルDBを読取専用で参照する。
    cards = synthetic_cards()
    path = DB_PATH if db_path is None else db_path
    manifest_path = Path(__file__).with_name('data') / 'battle_supported.json'
    if not path.exists() or not manifest_path.exists():
        return cards
    manifest = json.loads(manifest_path.read_text())
    defs = definitions()
    connection = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tribes: dict[str, list[int]] = {}
        for item in connection.execute('SELECT card_id, tribe_id FROM card_tribe'):
            tribes.setdefault(str(item[0]), []).append(item[1])
        for row in connection.execute('SELECT c.*, n.note FROM card c LEFT JOIN card_note n USING(card_id)'):
            card_id = str(row['card_id'])
            if card_id not in defs or manifest.get(card_id) != source_hash(row):
                continue
            cards[card_id] = {'card_id':card_id, 'name':row['name'], 'kind':row['type_category'], 'cost':row['cost'], 'attack':row['atk'], 'health':row['life'], 'keywords':[], 'text':re.sub('<[^>]+>', '', row['skill_text'] or ''), 'class_name':row['class_name'], 'token':bool(row['is_token']), 'rotation':bool(row['is_include_rotation']), 'source_hash':manifest[card_id], 'source':f'https://shadowverse-wb.com/ja/deck/cardslist/card/?card_id={card_id}', 'note':row['note'] or '', 'tribes': tribes.get(card_id, []), **defs[card_id]}
    finally:
        connection.close()
    # AI_NOTE: ネストした生成先も調べ、本文変更で生成先が外れたら親も対応扱いにしない。
    def references(value: Any) -> set[str]:
        if isinstance(value, list):
            return set().union(*(references(child) for child in value))
        if isinstance(value, dict):
            direct = {str(value['card_id'])} if value.get('op') in {'summon', 'generate'} else set()
            return direct | set().union(*(references(child) for child in value.values()))
        return set()

    changed = True
    while changed:
        changed = False
        for card_id, card in list(cards.items()):
            if references(card) - cards.keys():
                del cards[card_id]
                changed = True
    return cards
