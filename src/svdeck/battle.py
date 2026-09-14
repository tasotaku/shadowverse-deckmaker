"""描画なしの対戦処理。同じ状態・操作列をCLI、試験、画面で共有する。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from svdeck import battle_rules as rules

Json = dict[str, Any]
VERSION = 1
KEYWORDS = {'守護', '突進', '疾走', 'バリア', '必殺', 'ドレイン', '潜伏', 'オーラ', '威圧', '破壊耐性'}
EFFECT_KEYS = {'op', 'target', 'amount', 'attack', 'health', 'keywords', 'card_id', 'count', 'condition', 'effects', 'choice', 'select_count', 'filter', 'modifiers', 'unique', 'crest'}
OPS = {'damage', 'heal', 'draw', 'buff', 'grant', 'destroy', 'banish', 'bounce', 'summon', 'generate', 'ramp', 'combo', 'necro', 'evolve', 'if', 'countdown'}
TARGETS = {'chosen_enemy', 'chosen_ally', 'chosen_other_ally', 'chosen_ally_card', 'chosen_any_enemy', 'self', 'own_leader', 'enemy_leader', 'all_enemy', 'all_ally', 'all', 'random_enemy'}


def catalog() -> dict[str, Json]:
    # AI_NOTE: 能力の対応は明示登録し、自由文の一部だけを実行して成功に見せない。
    from svdeck.battle_cards import load_catalog
    return load_catalog()


def integer(value: Any, label: str, low: int = 0, high: int = 100000) -> int:
    # AI_NOTE: boolや小数を数値として受けると再現用の状態が曖昧になるので境界で拒否する。
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}: 整数 {low}〜{high} が必要です')
    return value


def fingerprint(value: Any) -> str:
    # AI_NOTE: 保存済みのルールと状態を識別し、別の定義での再生を検知する。
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_effect(effect: Json, cards: dict[str, Json]) -> None:
    # AI_NOTE: 未対応効果・対象を入力時に拒否し、途中まで処理して継続することを防ぐ。
    if not isinstance(effect, dict) or set(effect) - EFFECT_KEYS or effect.get('op') not in OPS | rules.EXTRA_OPS:
        raise ValueError(f'未対応の効果です: {effect}')
    if effect.get('target', 'self') not in TARGETS | rules.EXTRA_TARGETS:
        raise ValueError('未対応の効果対象です')
    op, target = effect['op'], effect.get('target', 'self')
    if op in {'draw', 'summon', 'generate', 'ramp', 'combo', 'necro', 'if', 'pp', 'ep', 'leader_max', 'shield', 'repeat', 'reanimate', 'deck_summon'} and target != 'self':
        raise ValueError('この資源・生成処理は自分側のみ対応しています')
    if op in {'buff', 'grant', 'destroy', 'banish', 'bounce', 'evolve', 'countdown'} and target in {'own_leader', 'enemy_leader', 'chosen_any_enemy'}:
        raise ValueError('この処理はリーダーを対象にできません')
    for key in ('amount', 'count'):
        if key in effect:
            if effect[key] == 'board_count':
                if key != 'amount' or op != 'damage':
                    raise ValueError('場の枚数を参照する値はダメージのみ対応です')
            else:
                integer(effect[key], key, -100 if op == 'cost' else 0, 100)
    for key in ('attack', 'health'):
        if key in effect:
            integer(effect[key], key, -100, 100)
    if set(effect.get('keywords', [])) - KEYWORDS:
        raise ValueError('未対応の付与能力です')
    if effect['op'] in {'summon', 'generate'} and str(effect.get('card_id')) not in cards:
        raise ValueError('生成先のカードが未対応です')
    if op == 'summon' and cards[str(effect['card_id'])]['kind'] == 'spell':
        raise ValueError('スペルを場に出すことはできません')
    rules.validate_condition(effect.get('condition'))
    rules.validate_filter(effect.get('filter', {}))
    integer(effect.get('select_count', 1), 'select_count', 1, 9)
    if 'crest' in effect:
        rules.validate_crest(effect['crest'], cards)
        rules.validate_triggers(effect['crest']['triggers'], cards)
    if set(effect.get('modifiers', {})) - {'attack', 'health', 'keywords', 'tribes', 'lost_last_words'}:
        raise ValueError('未対応の生成時変更です')
    for child in effect.get('effects', []):
        validate_effect(child, cards)


class Battle:
    def __init__(self, state: Json, cards: dict[str, Json] | None = None, record: bool = True):
        # AI_NOTE: 入力を複製し、試験ケースや呼び出し元の状態へ副作用を漏らさない。
        from svdeck.battle_cards import synthetic_cards
        self.cards = copy.deepcopy(catalog() if cards is None else {**synthetic_cards(), **cards})
        self.recording = record
        self.events: list[Json] = []
        self.frames: list[Json] = []
        self.actions: list[Json] = []
        self.pending: list[tuple[list[Json], int, Json, str]] = []
        self.destroyed_in_action: set[str] = set()
        self.validate_cards()
        self.state = self.normalize(state)
        self.initial = copy.deepcopy(self.state)

    def validate_cards(self) -> None:
        # AI_NOTE: テスト用カードも実カードも同じ閉じた効果形式を検査する。
        allowed = {'card_id', 'name', 'kind', 'cost', 'attack', 'health', 'keywords', 'text', 'effects', 'fanfare', 'evolve', 'super_evolve', 'last_words', 'end_turn', 'attack_effects', 'enhance', 'enhance_effects', 'spellboost', 'countdown', 'class_name', 'token', 'rotation', 'source_hash', 'note', 'source', 'synthetic', 'forms', 'modes', 'triggers', 'hand_triggers', 'on_discard', 'on_evolved', 'leave_banish', 'tribes'}
        for key, card in self.cards.items():
            if not isinstance(card, dict) or set(card) - allowed:
                raise ValueError(f'未対応のカード定義項目です: {key}')
            card.setdefault('card_id', key)
            if str(card['card_id']) != key or card.get('kind') not in {'follower', 'spell', 'amulet'}:
                raise ValueError(f'不正なカード定義です: {key}')
            for prop in ('cost', 'attack', 'health'):
                integer(card.get(prop, 0), prop)
            if card['kind'] == 'follower' and card.get('health', 0) <= 0:
                raise ValueError('フォロワーの体力は1以上です')
            if set(card.get('keywords', [])) - KEYWORDS:
                raise ValueError(f'未対応の能力です: {key}')
            if card['kind'] != 'spell' and card.get('effects'):
                raise ValueError('フォロワー・アミュレットには発動タイミングを指定してください')
            if card['kind'] == 'spell' and any(card.get(phase) for phase in ('fanfare', 'evolve', 'super_evolve', 'last_words', 'end_turn', 'attack_effects')):
                raise ValueError('スペルに未対応の発動タイミングです')
            if set(card.get('forms', {})) - {'accelerate', 'crystallize'}:
                raise ValueError('未対応の別形態です')
            for variant in [card, *card.get('forms', {}).values()]:
                if set(variant) - allowed or set(variant.get('modes', {})) - {'effects', 'fanfare', 'evolve', 'super_evolve'}:
                    raise ValueError('未対応の別形態・モード定義です')
                for prop in ('cost', 'attack', 'health'):
                    integer(variant.get(prop, 0), prop)
                if set(variant.get('keywords', [])) - KEYWORDS:
                    raise ValueError('別形態に未対応の能力があります')
                for phase in rules.PHASES:
                    effects = variant.get(phase, [])
                    for effect in effects:
                        validate_effect(effect, self.cards)
                    rules.validate_selections(effects)
                    for mode in variant.get('modes', {}).get(phase, []):
                        for effect in mode:
                            validate_effect(effect, self.cards)
                        rules.validate_selections(effects + mode)
                for phase in ('effects', 'fanfare'):
                    rules.validate_selections(variant.get(phase, []) + variant.get('enhance_effects', []))
                rules.validate_triggers(variant.get('triggers', []), self.cards)
                rules.validate_triggers(variant.get('hand_triggers', []), self.cards)

    def entity(self, value: Any, ids: set[str]) -> Json:
        # AI_NOTE: 個体IDで同名カードを区別し、盤面から消えた対象を取り違えない。
        if isinstance(value, (str, int)):
            value = {'card_id': str(value)}
        if not isinstance(value, dict):
            raise ValueError('カードの状態はオブジェクトです')
        allowed = {'id', 'card_id', 'name', 'cost', 'attack', 'health', 'max_health', 'keywords', 'evolved', 'attacks', 'entered_turn', 'countdown', 'form', 'tribes', 'lost_last_words', 'last_trigger'}
        if set(value) - allowed:
            raise ValueError(f'未対応の個体状態です: {set(value) - allowed}')
        card_id = str(value.get('card_id'))
        if card_id not in self.cards:
            raise ValueError(f'未対応のカードです: {card_id}')
        card = rules.definition(self, value | {'card_id': card_id})
        if 'id' not in value:
            while f'e{self.state["next_id"]}' in ids:
                self.state['next_id'] += 1
            value = {**value, 'id': f'e{self.state["next_id"]}'}
            self.state['next_id'] += 1
        if not isinstance(value['id'], str) or not value['id'] or value['id'].startswith('leader:') or value['id'] in ids:
            raise ValueError('個体IDが不正または重複しています')
        ids.add(value['id'])
        result: Json = {'id': value['id'], 'card_id': card_id, 'name': card['name'], 'cost': card['cost'], 'attack': card.get('attack', 0), 'health': card.get('health', 0), 'max_health': card.get('health', 0), 'keywords': copy.deepcopy(card.get('keywords', [])), 'evolved': 0, 'attacks': 0, 'entered_turn': 0, 'countdown': card.get('countdown')}
        if card.get('tribes'):
            result['tribes'] = copy.deepcopy(card['tribes'])
        result.update(value)
        result['card_id'] = card_id
        if 'health' in value and 'max_health' not in value:
            result['max_health'] = max(result['max_health'], value['health'])
        for prop in ('cost', 'attack', 'health', 'max_health', 'attacks', 'entered_turn'):
            integer(result[prop], prop)
        integer(result['evolved'], 'evolved', 0, 2)
        if result['health'] > result['max_health'] or (card['kind'] == 'follower' and result['health'] <= 0):
            raise ValueError('フォロワーの体力状態が不正です')
        if set(result['keywords']) - KEYWORDS or len(set(result['keywords'])) != len(result['keywords']):
            raise ValueError('未対応または重複した能力です')
        if result['countdown'] is not None:
            integer(result['countdown'], 'countdown', 1)
        if 'lost_last_words' in result and type(result['lost_last_words']) is not bool:
            raise ValueError('ラストワード喪失の指定は真偽値です')
        if 'tribes' in result and (not isinstance(result['tribes'], list) or any(type(t) is not int for t in result['tribes'])):
            raise ValueError('タイプは整数の配列です')
        return result

    def normalize(self, raw: Json) -> Json:
        # AI_NOTE: 条件指定は実戦で到達済みという保証を付けず、構造と処理可能性を検査する。
        if not isinstance(raw, dict) or set(raw) - {'version', 'players', 'active_player', 'winner', 'rng', 'next_id', 'deck_knowledge', 'deck_origins'}:
            raise ValueError('開始状態の項目が不正です')
        if raw.get('version', VERSION) != VERSION:
            raise ValueError('未対応の状態バージョンです')
        players = raw.get('players', [{}, {}])
        if not isinstance(players, list) or len(players) != 2:
            raise ValueError('プレイヤーは2人です')
        self.state = {'version': VERSION, 'active_player': integer(raw.get('active_player', 0), 'active_player', 0, 1), 'winner': raw.get('winner'), 'rng': integer(raw.get('rng', 1), 'rng', 1, 4294967295), 'next_id': integer(raw.get('next_id', 1), 'next_id', 1), 'players': []}
        if type(self.state['winner']) is bool or self.state['winner'] not in (None, -1, 0, 1):
            raise ValueError('勝者が不正です')
        # Reserve all explicitly supplied IDs before allocating any omitted IDs.
        ids: set[str] = set()
        reserved = {e['id'] for p in players if isinstance(p, dict) for z in ('hand', 'deck', 'board') for e in p.get(z, []) if isinstance(e, dict) and 'id' in e}
        while f'e{self.state["next_id"]}' in reserved:
            self.state['next_id'] += 1
        for raw_player in players:
            p: Json = {'health': 20, 'max_health': 20, 'pp': 0, 'max_pp': 0, 'turn': 1, 'ep': 2, 'sep': 2, 'evolved_this_turn': False, 'extra_pp_used': False, 'graveyard': 0, 'combo': 0, 'hand': [], 'deck': [], 'board': [], 'destroyed': []}
            if not isinstance(raw_player, dict) or set(raw_player) - (set(p) | {'crests', 'damage_shield'}):
                raise ValueError('プレイヤー状態の項目が不正です')
            p.update(copy.deepcopy(raw_player))
            if not isinstance(p.get('crests', []), list):
                raise ValueError('クレストは配列です')
            crest_ids = set()
            for crest in p.get('crests', []):
                rules.validate_crest(crest, self.cards)
                if crest['id'] in crest_ids:
                    raise ValueError('同名クレストは重複できません')
                crest_ids.add(crest['id'])
            if 'damage_shield' in p:
                shield = p['damage_shield']
                if not isinstance(shield, dict) or set(shield) != {'owner', 'turn'}:
                    raise ValueError('保護期限の形式が不正です')
                integer(shield['owner'], 'shield.owner', 0, 1)
                integer(shield['turn'], 'shield.turn', 0)
            for prop in ('health', 'max_health', 'pp', 'max_pp', 'turn', 'ep', 'sep', 'graveyard', 'combo'):
                integer(p[prop], prop, 0, 10 if prop == 'max_pp' else 100000)
            if p['health'] > p['max_health'] or p['pp'] > p['max_pp'] + 1:
                raise ValueError('体力またはPPの範囲が不正です')
            for prop in ('evolved_this_turn', 'extra_pp_used'):
                if type(p[prop]) is not bool:
                    raise ValueError(f'{prop}は真偽値です')
            for zone, maximum in (('hand', 9), ('board', 5), ('deck', 200)):
                if not isinstance(p[zone], list) or len(p[zone]) > maximum:
                    raise ValueError(f'{zone}の枚数が上限を超えています')
                normalized = []
                for item in p[zone]:
                    # Avoid generated IDs reserved by later explicit entities.
                    while f'e{self.state["next_id"]}' in reserved:
                        self.state['next_id'] += 1
                    normalized.append(self.entity(item, ids))
                p[zone] = normalized
            if any(rules.definition(self, e)['kind'] == 'spell' for e in p['board']):
                raise ValueError('スペルを盤面に配置できません')
            if not isinstance(p['destroyed'], list) or any(str(c) not in self.cards for c in p['destroyed']):
                raise ValueError('破壊履歴に未対応のカードがあります')
            self.state['players'].append(p)
        if 'deck_knowledge' in raw:
            knowledge = raw['deck_knowledge']
            if not isinstance(knowledge, list) or len(knowledge) != 2:
                raise ValueError('公開デッキ情報は両者分が必要です')
            for entry in knowledge:
                if not isinstance(entry, dict) or set(entry) != {'deck_list', 'revealed', 'known_hand'}:
                    raise ValueError('公開デッキ情報の形式が不正です')
                for field in ('deck_list', 'revealed'):
                    if not isinstance(entry[field], dict):
                        raise ValueError('公開デッキ・公開履歴は辞書です')
                for cid, count in entry['deck_list'].items():
                    if cid not in self.cards:
                        raise ValueError('公開デッキに未対応のカードがあります')
                    integer(count, 'deck count', 1, 200)
                if any(not isinstance(ident, str) or not ident or cid not in entry['deck_list'] for ident, cid in entry['revealed'].items()):
                    raise ValueError('公開された元カードの情報が不正です')
                if any(count > entry['deck_list'][cid] for cid, count in Counter(entry['revealed'].values()).items()):
                    raise ValueError('公開枚数がデッキの枚数を超えています')
                if not isinstance(entry['known_hand'], list):
                    raise ValueError('公開された手札は配列です')
                known_ids = set()
                for item in entry['known_hand']:
                    if not isinstance(item, dict) or set(item) != {'id', 'card_id'} or not isinstance(item['id'], str) or not item['id'] or item['card_id'] not in self.cards or item['id'] in known_ids:
                        raise ValueError('公開された手札の形式が不正です')
                    known_ids.add(item['id'])
            self.state['deck_knowledge'] = copy.deepcopy(knowledge)
        if 'deck_origins' in raw:
            origins = raw['deck_origins']
            if 'deck_knowledge' not in raw or not isinstance(origins, list) or len(origins) != 2 or any(not isinstance(mapping, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in mapping.items()) for mapping in origins):
                raise ValueError('元カードの追跡情報が不正です')
            self.state['deck_origins'] = copy.deepcopy(origins)
        return self.state

    def enable_deck_knowledge(self) -> None:
        # AI_NOTE: 旧記録は初期40枚からだけ復元できる。途中局面の隠れたカードから推測しない。
        if 'deck_knowledge' in self.state:
            return
        players = self.state['players']
        if self.actions or any(p['board'] or len(p['hand']) + len(p['deck']) != 40 or p['destroyed'] or p['graveyard'] or p['combo'] or p['turn'] > 1 for p in players):
            raise ValueError('公開デッキの登録は未使用の初期40枚から行ってください')
        self.state['deck_knowledge'] = [{'deck_list': dict(Counter(e['card_id'] for e in p['hand'] + p['deck'])), 'revealed': {}, 'known_hand': []} for p in players]
        self.state['deck_origins'] = [{e['id']: e['id'] for e in p['hand'] + p['deck']} for p in players]
        self.initial = copy.deepcopy(self.state)

    def reveal(self, owner: int, entity: Json, in_hand: bool = False) -> None:
        # AI_NOTE: 公開処理だけで履歴を更新し、生成コピーは元デッキの消費に数えない。
        if 'deck_knowledge' not in self.state:
            return
        entry = self.state['deck_knowledge'][owner]
        origin = self.state.get('deck_origins', [{}, {}])[owner].get(entity['id'])
        if origin:
            entry['revealed'][origin] = entity['card_id']
        entry['known_hand'] = [item for item in entry['known_hand'] if item['id'] != entity['id']]
        if in_hand:
            entry['known_hand'].append({'id': entity['id'], 'card_id': entity['card_id']})

    def emit(self, kind: str, message: str, **values: Any) -> None:
        # AI_NOTE: 数値だけでなく原因と対象を保存し、画面から誤処理を追えるようにする。
        if self.recording:
            self.events.append({'kind': kind, 'message': message, **values})

    def find(self, entity_id: str) -> tuple[int, str, Json] | None:
        # AI_NOTE: 対象は現在の状態から毎回引き直す。消滅・破壊後の古い参照を再利用しない。
        if entity_id in ('leader:0', 'leader:1'):
            owner = int(entity_id[-1])
            return owner, 'leader', self.state['players'][owner]
        for owner, p in enumerate(self.state['players']):
            for zone in ('board', 'hand', 'deck'):
                for entity in p[zone]:
                    if entity['id'] == entity_id:
                        return owner, zone, entity
        return None

    def condition(self, effect: Json, owner: int) -> bool:
        # AI_NOTE: 条件判定は発動時の資源を参照するため、前の効果による変化を反映できる。
        return rules.condition(self, effect.get('condition'), owner)

    def choices(self, target: str, owner: int, source: Json) -> list[str]:
        # AI_NOTE: 守護は攻撃だけに、オーラ/潜伏は相手による選択だけに適用する。
        if target == 'chosen_hand':
            return [e['id'] for e in self.state['players'][owner]['hand'] if e['id'] != source['id']]
        enemy = 1 - owner
        result = []
        players = (owner,) if target in {'chosen_ally', 'chosen_other_ally', 'chosen_ally_card'} else (enemy,)
        for who in players:
            for e in self.state['players'][who]['board']:
                if rules.definition(self, e)['kind'] != 'follower' and target != 'chosen_ally_card':
                    continue
                if target == 'chosen_other_ally' and e['id'] == source['id']:
                    continue
                if who != owner and set(e['keywords']) & {'オーラ', '潜伏'}:
                    continue
                result.append(e['id'])
        if target == 'chosen_any_enemy':
            result.append(f'leader:{enemy}')
        return result

    def play_effects(self, card: Json, pp: int, mode: int | None = None) -> list[Json]:
        # AI_NOTE: 元の効果とエンハンスを合成した同じ列を、合法手と実行に渡す。
        effects = rules.phases(card, 'effects' if card['kind'] == 'spell' else 'fanfare', mode)
        if 'enhance' in card and pp >= card['enhance']:
            effects += card.get('enhance_effects', [])
        return effects

    def playable(self, entity: Json, pp: int) -> tuple[Json, str | None]:
        # AI_NOTE: 本体を使えるPPでは結晶・アクセラレートを選べない。
        card = self.cards[entity['card_id']]
        available = [(name, form) for name, form in card.get('forms', {}).items() if form['cost'] <= pp]
        if entity['cost'] > pp and available:
            name, form = max(available, key=lambda item: item[1]['cost'])
            return rules.definition(self, entity | {'form': name}), name
        return card, None

    def legal_actions(self) -> list[Json]:
        # AI_NOTE: モード・対象・別形態をすべて行動に含め、AIと画面の判断を一致させる。
        if self.state['winner'] is not None:
            return []
        owner = self.state['active_player']
        p, opponent = self.state['players'][owner], self.state['players'][1-owner]
        actions: list[Json] = [{'type': 'end_turn'}]
        if owner == 1 and not p['extra_pp_used']:
            actions.append({'type': 'extra_pp'})
        for entity in p['hand']:
            card, form = self.playable(entity, p['pp'])
            cost = card['cost'] if form else (card['enhance'] if 'enhance' in card and p['pp'] >= card['enhance'] else entity['cost'])
            if cost > p['pp'] or (card['kind'] != 'spell' and len(p['board']) >= 5):
                continue
            phase = 'effects' if card['kind'] == 'spell' else 'fanfare'
            modes: list[int | None] = list(range(len(card.get('modes', {}).get(phase, [])))) or [None]
            for mode in modes:
                effects = self.play_effects(card, p['pp'], mode)
                for selected in rules.action_choices(self, effects, owner, entity, card['kind'] == 'spell', True):
                    action = {'type': 'play', 'card': entity['id'], **selected}
                    if form:
                        action['form'] = form
                    if mode is not None:
                        action['mode'] = mode
                    actions.append(action)
        guards = [e['id'] for e in opponent['board'] if rules.definition(self, e)['kind'] == 'follower' and '守護' in e['keywords'] and '潜伏' not in e['keywords']]
        for entity in p['board']:
            card = rules.definition(self, entity)
            if card['kind'] != 'follower':
                continue
            ready = entity['entered_turn'] < p['turn'] or '疾走' in entity['keywords']
            rush = ready or '突進' in entity['keywords'] or entity['evolved'] > 0
            if entity['attacks'] == 0 and rush:
                for other in opponent['board']:
                    if rules.definition(self, other)['kind'] != 'follower' or set(other['keywords']) & {'潜伏', '威圧'}:
                        continue
                    if not guards or other['id'] in guards:
                        actions.append({'type': 'attack', 'source': entity['id'], 'target': other['id']})
                if ready and not guards:
                    actions.append({'type': 'attack', 'source': entity['id'], 'target': f'leader:{1-owner}'})
            if entity['evolved'] or p['evolved_this_turn']:
                continue
            for kind, resource, threshold in (('evolve', 'ep', 5-owner), ('super_evolve', 'sep', 7-owner)):
                if p[resource] <= 0 or p['turn'] < threshold:
                    continue
                phase = 'super_evolve' if kind == 'super_evolve' and ('super_evolve' in card or 'super_evolve' in card.get('modes', {})) else 'evolve'
                modes = list(range(len(card.get('modes', {}).get(phase, [])))) or [None]
                for mode in modes:
                    for selected in rules.action_choices(self, rules.phases(card, phase, mode), owner, entity, False):
                        action = {'type': kind, 'source': entity['id'], **selected}
                        if mode is not None:
                            action['mode'] = mode
                        actions.append(action)
        return actions

    def fresh(self, card_id: str) -> Json:
        # AI_NOTE: 生成・手札戻しは元カードの定義から再作成し、古い強化を持ち越さない。
        ids = {e['id'] for p in self.state['players'] for z in ('board', 'hand', 'deck') for e in p[z]}
        return self.entity({'card_id': card_id}, ids)

    def remove(self, target_id: str, mode: str) -> bool:
        # AI_NOTE: 墓場の数字と破壊履歴は別に扱い、消滅と手札戻しでは破壊履歴を作らない。
        found = self.find(target_id)
        if found is None or found[1] != 'board':
            return False
        owner, _, entity = found
        p = self.state['players'][owner]
        if mode == 'destroy' and ('破壊耐性' in entity['keywords'] or (entity['evolved'] == 2 and owner == self.state['active_player'])):
            self.emit('prevent_destroy', f'{entity["name"]}は能力による破壊を防いだ', target=target_id)
            return False
        if rules.definition(self, entity).get('leave_banish'):
            mode = 'banish'
        p['board'].remove(entity)
        self.emit(mode, f'{entity["name"]}: ' + {'destroy': '破壊', 'death': '体力0で破壊', 'banish': '消滅', 'bounce': '手札へ戻る'}[mode], target=target_id)
        if mode in {'destroy', 'death'}:
            self.destroyed_in_action.add(target_id)
            p['graveyard'] += 1
            if rules.definition(self, entity)['kind'] == 'follower':
                p['destroyed'].append(entity['card_id'])
            if not entity.get('lost_last_words'):
                self.pending.append((rules.definition(self, entity).get('last_words', []), owner, entity, 'ラストワード'))
        if mode == 'bounce':
            returned = self.fresh(entity['card_id'])
            origin = self.state.get('deck_origins', [{}, {}])[owner].get(entity['id'])
            if origin:
                self.state['deck_origins'][owner][returned['id']] = origin
            self.add_hand(owner, returned, public=True)
        return True

    def settle(self) -> None:
        # AI_NOTE: 同時ダメージの反撃前に死亡を処理せず、まとまった作用の後に死亡を確定する。
        for owner in (self.state['active_player'], 1-self.state['active_player']):
            for entity in list(self.state['players'][owner]['board']):
                if rules.definition(self, entity)['kind'] == 'follower' and entity['health'] <= 0:
                    self.remove(entity['id'], 'death')
        dead = [i for i, p in enumerate(self.state['players']) if p['health'] <= 0]
        if dead:
            self.state['winner'] = -1 if len(dead) == 2 else 1-dead[0]
            self.emit('game_over', '引き分け' if len(dead) == 2 else f'プレイヤー{1-dead[0]+1}の勝利', winner=self.state['winner'])

    def damage(self, target_id: str, amount: int, source: Json | None = None) -> int:
        # AI_NOTE: バリアと超進化の軽減を通した実ダメージを返し、必殺/ドレインの条件に使う。
        found = self.find(target_id)
        if found is None:
            return 0
        owner, zone, entity = found
        if amount <= 0:
            return 0
        before = entity['health']
        if zone == 'leader' and entity.get('damage_shield'):
            self.emit('prevent_damage', 'リーダーへのダメージを防いだ', target=target_id, before=before, after=before)
            return 0
        if zone != 'leader' and entity['evolved'] == 2 and owner == self.state['active_player']:
            self.emit('prevent_damage', f'{entity["name"]}: 超進化でダメージを防いだ', target=target_id, before=before, after=before)
            return 0
        if zone != 'leader' and 'バリア' in entity['keywords']:
            entity['keywords'].remove('バリア')
            self.emit('barrier', f'{entity["name"]}: バリアを消費してダメージ0', target=target_id, before=before, after=before)
            return 0
        entity['health'] = max(0, before-amount)
        self.emit('damage', f'{entity.get("name", "リーダー")}: {amount}ダメージ ({before} → {entity["health"]})', target=target_id, source=source.get('id') if source else None, amount=amount, before=before, after=entity['health'])
        return amount

    def add_hand(self, owner: int, entity: Json, public: bool = False) -> None:
        # AI_NOTE: 手札あふれは墓場だけを増やし、破壊履歴やラストワードを発生させない。
        p = self.state['players'][owner]
        if len(p['hand']) >= 9:
            self.reveal(owner, entity)
            p['graveyard'] += 1
            self.emit('overflow', f'{entity["name"]}: 手札上限で手札に入らず墓場+1', target=entity['id'])
            return
        p['hand'].append(entity)
        if public:
            self.reveal(owner, entity, in_hand=True)
        self.emit('hand', f'{entity["name"]}を手札に加えた', target=entity['id'])

    def random_index(self, length: int) -> int:
        # AI_NOTE: 再現可能な乱数状態を保存し、巻き戻し後も同じ分岐を再生する。
        x = self.state['rng']
        x ^= (x << 13) & 0xffffffff
        x ^= x >> 17
        x ^= (x << 5) & 0xffffffff
        self.state['rng'] = x & 0xffffffff
        return int(self.state['rng'] % length)

    def targets(self, effect: Json, owner: int, source: Json, chosen: Any) -> list[str]:
        # AI_NOTE: 選択IDを用途ごとに読み、対象が先の効果で消えた場合は再選択しない。
        target = effect.get('target', 'self')
        if target.startswith('chosen_'):
            value = chosen.get(effect.get('choice', 'target')) if isinstance(chosen, dict) else chosen
            values = value if isinstance(value, list) else ([value] if value else [])
            return [v for v in values if self.find(v)]
        if target == 'event':
            return [source['event_target']] if source.get('event_target') and self.find(source['event_target']) else []
        if target in {'own_leader', 'enemy_leader'}:
            return [f'leader:{owner if target == "own_leader" else 1-owner}']
        if target == 'all_leaders':
            return [f'leader:{owner}', f'leader:{1-owner}']
        if target == 'self':
            return [source['id']]
        owners = (owner, 1-owner) if target == 'all' else ((owner,) if target in {'all_ally', 'all_other_ally', 'random_ally'} else (1-owner,))
        entities = [e for i in owners for e in self.state['players'][i]['board'] if (rules.definition(self, e)['kind'] == 'follower' or effect.get('filter', {}).get('last_words')) and rules.matches(self, e, effect.get('filter', {}), source)]
        if target == 'all_other_ally':
            entities = [e for e in entities if e['id'] != source['id']]
        if entities and effect.get('filter', {}).get('highest_attack'):
            maximum = max(e['attack'] for e in entities)
            entities = [e for e in entities if e['attack'] == maximum]
        result = [e['id'] for e in entities]
        if target.startswith('random_'):
            picked = []
            for _ in range(min(effect.get('count', 1), len(result))):
                value = result.pop(self.random_index(len(result)))
                self.emit('random', 'ランダム対象を決定', target=value)
                picked.append(value)
            return picked
        if target == 'all_enemy_characters':
            result.append(f'leader:{1-owner}')
        return result

    def resolve(self, effects: list[Json], owner: int, source: Json, chosen: Any = None) -> None:
        # AI_NOTE: 効果リストの順をそのまま実行し、各作用を履歴に残す。自由文は実行時に解釈しない。
        for effect in effects:
            if self.state['winner'] is not None:
                break
            if not rules.condition(self, effect.get('condition'), owner, source):
                self.emit('condition', '条件未達のため効果なし', source=source['id'], condition=effect.get('condition'))
                continue
            p = self.state['players'][owner]
            op = effect['op']
            amount = effect.get('amount', 0)
            if amount == 'board_count':
                amount = sum(rules.definition(self, e)['kind'] == 'follower' for player in self.state['players'] for e in player['board'])
            self.emit('effect', f'{source["name"]}: ' + {'damage':'ダメージ','heal':'回復','draw':'カードを引く','buff':'強化','grant':'能力付与','destroy':'破壊','banish':'消滅','bounce':'手札に戻す','summon':'場に出す','generate':'手札に加える','ramp':'PP最大値を増やす','combo':'プレイ枚数を増やす','necro':'墓場を消費','evolve':'効果による進化','if':'条件判定','countdown':'カウントを進める','repeat':'繰り返し','discard':'手札を捨てる','pp':'PP回復','ep':'EP回復','cost':'手札コスト変更','remove_keywords':'能力を失う','leader_max':'リーダー最大体力変更','shield':'ダメージを防ぐ','split_damage':'ダメージを割りふる','deck_summon':'デッキから場に出す','reanimate':'リアニメイト','copy_banish':'消滅してコピー','crest':'クレスト付与'}[op], source=source['id'], effect=copy.deepcopy(effect))
            if rules.extended_effect(self, effect, owner, source, chosen):
                self.settle()
                continue
            if op in {'if', 'necro'}:
                if op == 'necro':
                    if p['graveyard'] < amount:
                        continue
                    p['graveyard'] -= amount
                self.resolve(effect.get('effects', []), owner, source, chosen)
            elif op == 'draw':
                for _ in range(integer(effect.get('count', amount or 1), 'draw count', 0, 100)):
                    pool = [e for e in p['deck'] if rules.matches(self, e, effect.get('filter', {}))]
                    if effect.get('filter') and not pool:
                        continue
                    if not p['deck']:
                        self.state['winner'] = 1-owner
                        self.emit('deck_empty', '山札から引けず敗北', owner=owner)
                        break
                    entity = pool[self.random_index(len(pool))] if effect.get('filter') else p['deck'][0]
                    p['deck'].remove(entity)
                    self.add_hand(owner, entity)
            elif op in {'summon', 'generate'}:
                for _ in range(effect.get('count', 1)):
                    if op == 'summon' and len(p['board']) >= 5:
                        self.emit('board_full', '盤面上限のため場に出ない')
                        continue
                    entity = self.fresh(str(effect['card_id']))
                    if op == 'generate':
                        self.add_hand(owner, entity, public=True)
                    else:
                        rules.summon(self, owner, entity, effect.get('modifiers'))
            elif op == 'ramp':
                before = p['max_pp']
                p['max_pp'] = min(10, before+amount)
                self.emit('ramp', f'PP最大値 {before} → {p["max_pp"]}', before=before, after=p['max_pp'])
            elif op == 'combo':
                p['combo'] += amount
            else:
                target_ids = self.targets(effect, owner, source, chosen)
                if not target_ids:
                    self.emit('no_target', '対象がいないため、この作用は発生しない', source=source['id'])
                for target_id in target_ids:
                    found = self.find(target_id)
                    if found is None:
                        continue
                    target_owner, zone, entity = found
                    if op == 'damage':
                        dealt = self.damage(target_id, amount, source)
                        if dealt and '潜伏' in source['keywords']:
                            source['keywords'].remove('潜伏')
                    elif op == 'heal':
                        before = entity['health']
                        entity['health'] = min(entity['max_health'], before+amount)
                        self.emit('heal', f'体力 {before} → {entity["health"]}', target=target_id, before=before, after=entity['health'])
                        if zone == 'leader':
                            rules.trigger(self, 'heal', target_owner)
                    elif op in {'destroy', 'banish', 'bounce'}:
                        self.remove(target_id, op)
                    elif op in {'buff', 'grant'}:
                        if zone == 'leader':
                            raise ValueError('リーダーへの強化は未対応です')
                        entity['attack'] = max(0, entity['attack'] + effect.get('attack', 0))
                        entity['max_health'] = max(0, entity['max_health'] + effect.get('health', 0))
                        entity['health'] = max(0, entity['health'] + effect.get('health', 0))
                        entity['keywords'] = list(dict.fromkeys(entity['keywords'] + effect.get('keywords', [])))
                        self.emit('buff', '攻撃力・体力・能力を更新', target=target_id, attack=entity['attack'], health=entity['health'], keywords=copy.deepcopy(entity['keywords']))
                    elif op == 'evolve':
                        self.evolve(entity, target_owner, False, False, None)
                    elif op == 'countdown' and entity['countdown'] is not None:
                        entity['countdown'] = max(0, entity['countdown']-amount)
                        if entity['countdown'] == 0:
                            self.remove(target_id, 'destroy')
            self.settle()

    def drain_pending(self) -> None:
        # AI_NOTE: ラストワードを発生順に処理し、異常な循環は成功にせず打ち切りエラーにする。
        count = 0
        while self.pending and self.state['winner'] is None:
            effects, owner, source, reason = self.pending.pop(0)
            if effects:
                self.emit('last_words' if reason == 'ラストワード' else 'trigger', f'{source["name"]}: {reason}', source=source['id'])
                self.resolve(effects, owner, source)
            count += 1
            if count > 500:
                raise ValueError('連鎖効果が実行上限を超えました')

    def evolve(self, entity: Json, owner: int, super_evolve: bool, spend: bool, chosen: Any, mode: int | None = None) -> None:
        # AI_NOTE: 効果進化は能力【進化時】を発動させず、EP/SEPによる進化と分ける。
        if entity['evolved']:
            return
        amount = 3 if super_evolve else 2
        entity['evolved'] = 2 if super_evolve else 1
        entity['attack'] += amount
        entity['health'] += amount
        entity['max_health'] += amount
        self.emit('evolve', f'{entity["name"]}: {"超進化" if super_evolve else "進化"} +{amount}/+{amount}', target=entity['id'])
        rules.trigger(self, 'evolved', owner, entity)
        if spend:
            p = self.state['players'][owner]
            p['sep' if super_evolve else 'ep'] -= 1
            p['evolved_this_turn'] = True
            card = rules.definition(self, entity)
            phase = 'super_evolve' if super_evolve and ('super_evolve' in card or 'super_evolve' in card.get('modes', {})) else 'evolve'
            self.resolve(rules.phases(card, phase, mode), owner, entity, chosen)

    def execute(self, action: Json) -> None:
        # AI_NOTE: 合法性を確認した1行動から、次の判断が必要な状態まで処理する。
        owner = self.state['active_player']
        p = self.state['players'][owner]
        kind = action['type']
        if kind == 'play':
            entity = next(e for e in p['hand'] if e['id'] == action['card'])
            card, form = self.playable(entity, p['pp'])
            effects = self.play_effects(card, p['pp'], action.get('mode'))
            cost = card['cost'] if form else (card['enhance'] if 'enhance' in card and p['pp'] >= card['enhance'] else entity['cost'])
            if form:
                entity.update({'form': form, 'attack': card.get('attack', 0), 'health': card.get('health', 0), 'max_health': card.get('health', 0), 'keywords': card.get('keywords', []), 'countdown': card.get('countdown')})
            p['hand'].remove(entity)
            self.reveal(owner, entity)
            p['pp'] -= cost
            p['combo'] += 1
            self.emit('play', f'{entity["name"]}を使用（{cost}PP）', source=entity['id'], cost=cost)
            if card['kind'] != 'spell':
                entity['entered_turn'] = p['turn']
                p['board'].append(entity)
                rules.trigger(self, 'enter', owner, entity)
            self.resolve(effects, owner, entity, action.get('choices', action.get('target')))
            if card['kind'] == 'spell':
                p['graveyard'] += 1
                for hand_card in p['hand']:
                    if self.cards[hand_card['card_id']].get('spellboost'):
                        hand_card['cost'] = max(0, hand_card['cost']-1)
                        self.emit('spellboost', f'{hand_card["name"]}: コスト-1', target=hand_card['id'], cost=hand_card['cost'])
        elif kind in {'evolve', 'super_evolve'}:
            entity = next(e for e in p['board'] if e['id'] == action['source'])
            self.evolve(entity, owner, kind == 'super_evolve', True, action.get('choices', action.get('target')), action.get('mode'))
        elif kind == 'attack':
            entity = next(e for e in p['board'] if e['id'] == action['source'])
            entity['attacks'] += 1
            if '潜伏' in entity['keywords']:
                entity['keywords'].remove('潜伏')
            self.emit('attack', f'{entity["name"]}が攻撃', source=entity['id'], target=action['target'])
            self.resolve(rules.definition(self, entity).get('attack_effects', []), owner, entity)
            self.drain_pending()
            target = self.find(action['target'])
            if target and self.find(entity['id']) and self.state['winner'] is None:
                _, zone, other = target
                dealt = self.damage(action['target'], entity['attack'], entity)
                received = self.damage(entity['id'], other['attack'], other) if zone == 'board' else 0
                if dealt and 'ドレイン' in entity['keywords']:
                    before_health = p['health']
                    p['health'] = min(p['max_health'], p['health']+dealt)
                    self.emit('heal', f'ドレインで{dealt}回復', target=f'leader:{owner}', before=before_health, after=p['health'])
                    rules.trigger(self, 'heal', owner)
                if zone == 'board':
                    if '必殺' in entity['keywords']:
                        self.remove(other['id'], 'destroy')
                    if '必殺' in other['keywords']:
                        self.remove(entity['id'], 'destroy')
                self.settle()
            if action['target'] in self.destroyed_in_action and entity['evolved'] == 2 and self.state['winner'] is None:
                self.damage(f'leader:{1-owner}', 1, entity)
                self.settle()
        elif kind == 'extra_pp':
            p['pp'] += 1
            p['extra_pp_used'] = True
            self.emit('extra_pp', 'エクストラPPを使用（このターンだけ+1PP）')
        elif kind == 'end_turn':
            # 同時に発動した終了時能力を先に予約し、その結果で出る能力を後ろへ積む。
            for entity in list(p['board']):
                effects = rules.definition(self, entity).get('end_turn', [])
                if effects:
                    self.pending.append((copy.deepcopy(effects), owner, copy.deepcopy(entity), 'ターン終了時'))
            rules.trigger(self, 'turn_end', owner)
            self.drain_pending()
            for player in self.state['players']:
                shield = player.get('damage_shield')
                if shield and shield['owner'] == owner and shield['turn'] <= p['turn']:
                    player.pop('damage_shield')
            if self.state['winner'] is not None:
                return
            self.state['active_player'] = 1-owner
            owner = 1-owner
            p = self.state['players'][owner]
            p['turn'] += 1
            p['max_pp'] = min(10, p['max_pp']+1)
            p['pp'] = p['max_pp']
            p['combo'] = 0
            p['evolved_this_turn'] = False
            if owner == 1 and p['turn'] == 6:
                p['extra_pp_used'] = False
            for entity in list(p['board']):
                entity['attacks'] = 0
                if entity['countdown'] is not None:
                    entity['countdown'] -= 1
                    if entity['countdown'] == 0:
                        self.remove(entity['id'], 'destroy')
            self.emit('turn', f'プレイヤー{owner+1}の{p["turn"]}ターン目', owner=owner)
            rules.trigger(self, 'turn_start', owner)
            self.drain_pending()
            self.resolve([{'op': 'draw', 'count': 1}], owner, {'id': f'leader:{owner}', 'name': 'ターン開始', 'keywords': []})
        self.settle()
        self.drain_pending()

    def step(self, action: Json) -> Json:
        # AI_NOTE: 不正操作や処理エラーは状態/乱数ごと巻き戻し、半端な対戦状態を残さない。
        if not isinstance(action, dict) or action not in self.legal_actions():
            raise ValueError(f'不正な操作・対象です: {action}')
        before = copy.deepcopy(self.state)
        self.events = []
        self.pending = []
        self.destroyed_in_action = set()
        try:
            self.execute(action)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            self.state = before
            self.events = []
            self.pending = []
            raise ValueError(f'操作を取り消しました: {error}') from error
        if self.recording:
            self.actions.append(copy.deepcopy(action))
            self.frames.append({'action': copy.deepcopy(action), 'state': copy.deepcopy(self.state), 'events': copy.deepcopy(self.events)})
        return {'state': copy.deepcopy(self.state), 'events': copy.deepcopy(self.events), 'legal_actions': self.legal_actions()}

    def observation(self, player: int) -> Json:
        # AI_NOTE: 観戦用の全状態と、対戦AIに渡す非公開情報を除いた状態を明確に分ける。
        integer(player, 'player', 0, 1)
        view = copy.deepcopy(self.state)
        view.pop('rng')
        view.pop('next_id')
        origins = view.pop('deck_origins', None)
        if origins is not None:
            view['own_hand_originals'] = {e['id']: origins[player][e['id']] for e in view['players'][player]['hand'] if e['id'] in origins[player]}
        for who, p in enumerate(view['players']):
            p['deck'] = {'count': len(p['deck'])}
            if who != player:
                p['hand'] = {'count': len(p['hand'])}
        view['legal_actions'] = self.legal_actions() if player == self.state['active_player'] else []
        return view

    def export(self) -> Json:
        # AI_NOTE: カード定義も埋め込むことでDB更新後も当時の条件で再生できる。
        return copy.deepcopy({'version': VERSION, 'engine_version': 'battle-2', 'cards': self.cards, 'cards_hash': fingerprint(self.cards), 'initial': self.initial, 'actions': self.actions, 'frames': self.frames})


def replay(record: Json, cursor: int | None = None) -> Battle:
    # AI_NOTE: 保存された終了状態を信用して表示せず、開始状態と操作から再計算して照合する。
    if record.get('version') != VERSION or record.get('engine_version', 'battle-1') not in {'battle-1', 'battle-2'}:
        raise ValueError('未対応のリプレイバージョンです')
    if record.get('cards_hash') != fingerprint(record.get('cards')):
        raise ValueError('リプレイのカード定義が変更されています')
    actions = record.get('actions')
    if not isinstance(actions, list) or len(actions) > 2000:
        raise ValueError('操作列は2000手以内です')
    count = len(actions) if cursor is None else integer(cursor, 'cursor', 0, len(actions))
    battle = Battle(record['initial'], record['cards'])
    frames = record.get('frames', [])
    for i, action in enumerate(actions[:count]):
        battle.step(action)
        if i < len(frames) and frames[i]['state'] != battle.state:
            raise ValueError(f'{i+1}手目の保存状態と再計算が一致しません')
        # AI_NOTE: 判断メモは再計算する対戦結果とは分離して保持する（正しさの保証ではない）。
        if i < len(frames) and isinstance(frames[i].get('decision'), dict):
            battle.frames[-1]['decision'] = copy.deepcopy(frames[i]['decision'])
    return battle


def differences(expected: Any, actual: Any, path: str = '') -> list[Json]:
    # AI_NOTE: 辞書の指定項目を比較し、配列は要素数も検査して余分なカードの残存を見逃さない。
    result: list[Json] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key, value in expected.items():
            result += differences(value, actual.get(key), f'{path}.{key}' if path else key)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            result.append({'path': path+'.length', 'expected': len(expected), 'actual': len(actual)})
        for i, (left, right) in enumerate(zip(expected, actual)):
            result += differences(left, right, f'{path}[{i}]')
    elif type(expected) is not type(actual) or expected != actual:
        result.append({'path': path, 'expected': expected, 'actual': actual})
    return result


def run_case(case: Json) -> Json:
    # AI_NOTE: 成功と想定した拒否を区別し、期待結果を実行後に書き換えない。
    if not isinstance(case, dict) or 'initial' not in case or 'expected' not in case or not isinstance(case.get('actions'), list):
        raise ValueError('ケースにはinitial、actions、expectedが必要です')
    if not case['expected'] and not case.get('expected_error'):
        raise ValueError('期待する終了状態を指定してください')
    battle = Battle(case['initial'], case.get('cards'))
    error: str | None = None
    for action in case['actions']:
        try:
            battle.step(action)
        except ValueError as exc:
            error = str(exc)
            break
    diff = differences(case['expected'], battle.state)
    expected_error = case.get('expected_error')
    if expected_error:
        if error is None or (isinstance(expected_error, str) and expected_error != 'ValueError' and expected_error not in error):
            diff.append({'path': 'error', 'expected': expected_error, 'actual': error})
    elif error:
        diff.append({'path': 'error', 'expected': None, 'actual': error})
    return {'passed': not diff, 'differences': diff, 'state': battle.state, 'events': battle.events, 'error': error, 'record': battle.export()}


def load_cases() -> list[Json]:
    # AI_NOTE: 手動再生と自動テストは同じケース集を読み、期待値の別管理を避ける。
    path = Path(__file__).with_name('data') / 'battle_cases.json'
    if not path.exists():
        return []
    value = json.loads(path.read_text())
    cases = list(value['cases'] if isinstance(value, dict) else value)
    extra = path.with_name('battle_meta_cases.json')
    if extra.exists():
        cards = catalog()
        for case in json.loads(extra.read_text()):
            try:
                Battle(case['initial'], cards)
            except ValueError:
                continue
            cases.append(case)
    return cases


def default_state() -> Json:
    # AI_NOTE: 起動直後に5ダメージの試験を操作でき、条件設定なしでも確認を始められる。
    return {'players': [{'pp': 6, 'max_pp': 6, 'turn': 6, 'hand': [{'id': 'damage', 'card_id': 'test-damage-5'}], 'board': [{'id': 'ally', 'card_id': 'test-body'}], 'deck': ['test-body']*10}, {'turn': 5, 'board': [{'id': 'enemy-3', 'card_id': 'test-body'}, {'id': 'enemy-6', 'card_id': 'test-body', 'health': 6, 'max_health': 6}, {'id': 'enemy-barrier', 'card_id': 'test-barrier'}], 'deck': ['test-body']*10}]}


def new_game(decks: list[list[str]], seed: int = 1, mulligans: list[list[int]] | None = None, format: str = 'rotation') -> Battle:
    # AI_NOTE: 通常対戦の40枚制限とクラスを検査し、自由配置の検証局面と区別する。
    cards = catalog()
    if format not in {'rotation', 'unlimited'} or not isinstance(decks, list) or len(decks) != 2:
        raise ValueError('フォーマットと両者のデッキを指定してください')
    for deck in decks:
        if not isinstance(deck, list) or len(deck) != 40:
            raise ValueError('デッキは40枚必要です')
        names: dict[str, int] = {}
        classes: set[str] = set()
        for card_id in deck:
            if card_id not in cards or cards[card_id].get('synthetic') or cards[card_id].get('token'):
                raise ValueError(f'未対応またはデッキに入れられないカードです: {card_id}')
            card = cards[card_id]
            if format == 'rotation' and not card['rotation']:
                raise ValueError('ローテーションで使用できないカードです')
            names[card['name']] = names.get(card['name'], 0)+1
            if names[card['name']] > 3:
                raise ValueError('同名カードは3枚までです')
            if card['class_name'] != 'ニュートラル':
                classes.add(card['class_name'])
        if len(classes) > 1:
            raise ValueError('異なるクラスのカードを混ぜられません')
    if mulligans is None:
        mulligans = [[], []]
    if not isinstance(mulligans, list) or len(mulligans) != 2:
        raise ValueError('引き直しは両者のインデックス配列で指定します')
    for selected in mulligans:
        if not isinstance(selected, list) or len(selected) != len(set(selected)):
            raise ValueError('引き直しの指定が不正です')
        for index in selected:
            integer(index, 'mulligan', 0, 3)
    battle = Battle({'rng':seed, 'players':[{'turn':0,'deck':decks[0]},{'turn':0,'deck':decks[1]}]}, cards)
    battle.enable_deck_knowledge()
    for owner, p in enumerate(battle.state['players']):
        for i in range(len(p['deck'])-1, 0, -1):
            j = battle.random_index(i+1)
            p['deck'][i], p['deck'][j] = p['deck'][j], p['deck'][i]
        p['hand'], p['deck'] = p['deck'][:4], p['deck'][4:]
    for owner, p in enumerate(battle.state['players']):
        returned = [p['hand'][i] for i in mulligans[owner]]
        for i in mulligans[owner]:
            p['hand'][i] = p['deck'].pop(0)
        p['deck'] += returned
        if returned:
            for i in range(len(p['deck'])-1, 0, -1):
                j = battle.random_index(i+1)
                p['deck'][i], p['deck'][j] = p['deck'][j], p['deck'][i]
    p = battle.state['players'][0]
    p['turn'], p['pp'], p['max_pp'] = 1, 1, 1
    p['hand'].append(p['deck'].pop(0))
    battle.initial = copy.deepcopy(battle.state)
    return battle


def demo_state() -> Json:
    # AI_NOTE: 対応済みカードだけの合法40枚を例示する。構築の強さは保証しない。
    ids = ['10001110','10001120','10001130','10002110','10002120','10101310','10102110','10102310','10103110','10011110','10011120','10011130','10012110','10012310']
    deck = [card for card in ids for _ in range(3)][:40]
    return new_game([deck, deck], seed=14, format='unlimited').state


def search(initial: Json, goal: Json, cards: dict[str, Json] | None = None, max_depth: int = 5, max_nodes: int = 10000) -> Json:
    # AI_NOTE: 限定範囲で成立する手順を探す。探索上限への到達を「不可能」と誤表示しない。
    from collections import deque
    integer(max_depth, 'max_depth', 0, 20)
    integer(max_nodes, 'max_nodes', 1, 100000)
    if not goal:
        raise ValueError('到達したい状態の条件が必要です')
    start = Battle(initial, cards, record=False)
    pending: Any = deque([(start.state, [])])
    visited = {fingerprint(start.state)}
    examined = 0
    limited = False
    while pending and examined < max_nodes:
        state, actions = pending.popleft()
        examined += 1
        if not differences(goal, state):
            witness = Battle(initial, start.cards)
            for action in actions:
                witness.step(action)
            return {'status':'found', 'actions':actions, 'examined':examined, 'record':witness.export(), 'note':'指定した状態と乱数での成立手順です。到達頻度・相手の最善手への保証はありません。'}
        if len(actions) >= max_depth:
            limited = True
            continue
        candidate = Battle(state, start.cards, record=False)
        for action in candidate.legal_actions():
            child = Battle(state, start.cards, record=False)
            child.step(action)
            key = fingerprint(child.state)
            if key not in visited:
                visited.add(key)
                pending.append((child.state, actions+[action]))
            if len(visited) >= max_nodes:
                limited = True
                break
        if len(visited) >= max_nodes:
            # The queued states still need their goal checked; do not call failure impossible.
            for queued, sequence in pending:
                if not differences(goal, queued):
                    witness = Battle(initial, start.cards)
                    for action in sequence:
                        witness.step(action)
                    return {'status':'found', 'actions':sequence, 'examined':examined, 'record':witness.export()}
            break
    return {'status':'limit' if limited or pending else 'not_found', 'examined':examined, 'max_depth':max_depth, 'max_nodes':max_nodes, 'note':'指定した条件と探索範囲では成立手順が見つかりませんでした。一般的な不可能の証明ではありません。'}


def main() -> None:
    # AI_NOTE: 描画なしの実行・ケース検査・計測を公開コマンドから行えるようにする。
    parser = argparse.ArgumentParser(description='AI用対戦環境（対応カード限定）')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('test')
    sub.add_parser('catalog')
    sub.add_parser('demo')
    find = sub.add_parser('search')
    find.add_argument('case', type=Path)
    find.add_argument('--depth', type=int, default=5)
    find.add_argument('--nodes', type=int, default=10000)
    play = sub.add_parser('run')
    play.add_argument('case', type=Path)
    check = sub.add_parser('replay')
    check.add_argument('record', type=Path)
    bench = sub.add_parser('benchmark')
    bench.add_argument('--games', type=int, default=100)
    args = parser.parse_args()
    if args.command == 'test':
        results = [{'name': c.get('title', c.get('name', c.get('id'))), **{k: v for k, v in run_case(c).items() if k in ('passed', 'differences', 'error')}} for c in load_cases()]
        print(json.dumps(results, ensure_ascii=False, indent=2))
        raise SystemExit(0 if results and all(r['passed'] for r in results) else 1)
    if args.command == 'demo':
        print(json.dumps(Battle(demo_state()).export(), ensure_ascii=False, indent=2))
    if args.command == 'search':
        spec = json.loads(args.case.read_text())
        print(json.dumps(search(spec['initial'], spec['expected'], spec.get('cards'), args.depth, args.nodes), ensure_ascii=False, indent=2))
    if args.command == 'catalog':
        print(json.dumps(catalog(), ensure_ascii=False, indent=2))
    if args.command == 'run':
        result = run_case(json.loads(args.case.read_text()))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result['passed'] else 1)
    if args.command == 'replay':
        print(json.dumps(replay(json.loads(args.record.read_text())).state, ensure_ascii=False, indent=2))
    if args.command == 'benchmark':
        integer(args.games, 'games', 1, 10000)
        cards = catalog()
        start, steps = time.perf_counter(), 0
        for _ in range(args.games):
            battle = Battle(default_state(), cards, record=False)
            while battle.state['winner'] is None:
                legal = battle.legal_actions()
                attacks = [a for a in legal if a['type'] == 'attack']
                plays = [a for a in legal if a['type'] == 'play']
                battle.step((attacks or plays or legal)[0])
                steps += 1
        elapsed = time.perf_counter()-start
        print(json.dumps({'games': args.games, 'actions': steps, 'seconds': elapsed, 'actions_per_second': steps/elapsed, 'note': '描画なし・ルール選択の相手。強化学習済みAIではありません。'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
