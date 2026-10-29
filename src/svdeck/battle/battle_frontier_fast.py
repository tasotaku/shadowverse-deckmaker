"""Exact integer transitions for the closed, single-effect current-turn subset.

No score pruning. Unsupported effects return to the ordinary Battle engine.
"""
from __future__ import annotations

import copy
from fractions import Fraction
from typing import Any

from svdeck.battle.battle import Battle, Json

State = tuple[int, ...]
WORDS = ('バリア', '必殺', '疾走', '突進', '守護')
BARRIER, BANE, STORM, RUSH, WARD = (1 << i for i in range(5))
PHASES = ('effects', 'fanfare', 'evolve', 'super_evolve', 'enhance_effects', 'last_words',
          'end_turn', 'attack_effects', 'on_discard', 'on_evolved', 'triggers', 'hand_triggers',
          'forms', 'modes', 'leave_banish', 'spellboost')


def _plain(card: Json) -> bool:
    # AI_NOTE: 効果を持たないフォロワーだけを固定slotへ入れ、能力の省略による高速化を防ぐ。
    return bool(card['kind'] == 'follower' and not any(card.get(k) for k in PHASES)
                and 'enhance' not in card and not set(card.get('keywords', [])) - set(WORDS)
                and card.get('health', 0) > 0)


def eligible(battle: Battle) -> bool:
    # AI_NOTE: 対応する閉じた作用集合だけ選ぶ。公開手札履歴や未対応能力を省略して高速側へ入れない。
    if battle.state['winner'] is not None or 'deck_knowledge' in battle.state:
        return False
    owner = battle.state['active_player']
    for player in battle.state['players']:
        if player['health'] <= 0 or player.get('crests') or player.get('damage_shield'):
            return False
        if any(battle.cards[e['card_id']].get('hand_triggers') for e in player['hand']):
            return False
        for entity in player['board']:
            if (not _plain(battle.cards[entity['card_id']]) or entity.get('form')
                    or entity['health'] <= 0 or set(entity['keywords']) - set(WORDS)):
                return False
    summons = 0
    for entity in battle.state['players'][owner]['hand']:
        card = battle.cards[entity['card_id']]
        effects = card.get('effects', [])
        if (card['kind'] != 'spell' or 'enhance' in card or len(effects) != 1
                or any(card.get(k) for k in PHASES if k != 'effects')
                or entity.get('form') or set(entity['keywords']) - set(WORDS)):
            return False
        effect = effects[0]
        op, target = effect['op'], effect.get('target', 'self')
        if op == 'damage':
            if (set(effect) - {'op', 'target', 'amount', 'count'} or target not in ('chosen_enemy', 'random_enemy')
                    or type(effect.get('amount')) is not int or effect.get('count', 1) != 1):
                return False
        elif op == 'split_damage':
            if set(effect) - {'op', 'target', 'amount'} or target != 'self' or type(effect.get('amount')) is not int:
                return False
        elif op == 'destroy':
            if set(effect) - {'op', 'target'} or target != 'chosen_enemy':
                return False
        elif op == 'grant':
            if (set(effect) - {'op', 'target', 'keywords'} or target != 'chosen_ally'
                    or set(effect.get('keywords', [])) - set(WORDS)):
                return False
        elif op == 'summon':
            if (set(effect) - {'op', 'target', 'card_id', 'count'} or target != 'self'
                    or effect.get('count', 1) != 1 or not _plain(battle.cards[effect['card_id']])):
                return False
            summons += 1
        else:
            return False
    return summons <= 1


def _mask(words: list[str]) -> int:
    # AI_NOTE: 対応する5能力を重複しないbitへ写し、付与とバリア消費を整数演算で扱う。
    return sum(1 << i for i, word in enumerate(WORDS) if word in words)


def _freeze(value: Any) -> Any:
    # AI_NOTE: 能力定義の全内容を比較し、同名や同じスタッツだけで異なるカードをまとめない。
    if isinstance(value, dict):
        return tuple((k, _freeze(v)) for k, v in sorted(value.items()))
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


class Kernel:
    """State: health slots, keyword slots, spent/evolution/hand/PP/HP/extra/next-id/spawn.

    Evolution -1/-2 preserves spent EP/SEP after its follower has died. Positive
    codes identify a living newly evolved slot. Slots preserve oldest-first order.
    """

    def __init__(self, battle: Battle):
        # AI_NOTE: 初期個体の順番と定義を固定し、生成する1体だけ末尾slotを予約する。
        if not eligible(battle):
            raise ValueError('盤面は整数探索の対象外です')
        self.battle = battle
        self.root = copy.deepcopy(battle.state)
        self.owner = self.root['active_player']
        self.own, self.enemy = (self.root['players'][i] for i in (self.owner, 1-self.owner))
        self.hand = self.own['hand']
        self.spells = [(e['cost'], battle.cards[e['card_id']]['effects'][0]) for e in self.hand]
        self.hand_ids = {e['id']: i for i, e in enumerate(self.hand)}
        self.token = -1
        self.prototypes = copy.deepcopy(self.own['board'])
        for _, effect in self.spells:
            if effect['op'] == 'summon':
                self.token = len(self.prototypes)
                # Generate the same default entity fields as Battle, without mutating the input.
                scratch = copy.copy(battle)
                scratch.state = copy.deepcopy(self.root)
                token = scratch.fresh(effect['card_id'])
                token['entered_turn'] = self.own['turn']
                self.prototypes.append(token)
        self.n = len(self.prototypes)
        self.prototypes.extend(copy.deepcopy(self.enemy['board']))
        self.count = len(self.prototypes)
        self.tail = 2*self.count
        self.ids = {e['id']: i for i, e in enumerate(self.prototypes) if i != self.token}
        self.static_ids = {e['id'] for p in self.root['players'] for e in p['deck']}
        self.static_ids.update(e['id'] for e in self.enemy['hand'])
        hp = tuple(0 if i == self.token else e['health'] for i, e in enumerate(self.prototypes))
        keywords = tuple(0 if i == self.token else _mask(e['keywords']) for i, e in enumerate(self.prototypes))
        spent = sum(1 << i for i, e in enumerate(self.prototypes[:self.n]) if i != self.token and e['attacks'])
        self.initial: State = hp + keywords + (spent, 0, (1 << len(self.hand))-1, self.own['pp'],
                                               self.enemy['health'], int(self.own['extra_pp_used']), self.root['next_id'], 0)
        self.behaviors = [_freeze({k: v for k, v in battle.cards[e['card_id']].items()
                                  if k not in ('card_id', 'name', 'text', 'attack', 'health', 'synthetic')})
                          for e in self.prototypes]
        self.shape_ids: dict[Any, int] = {}
        self.shape_cache: dict[tuple[int, int, int, int], int] = {}

    def _evolved(self, slot: int, evolution: int) -> int:
        # AI_NOTE: 今回進化した個体以外は初期進化状態を保ち、超進化保護を正しく判定する。
        return (1 if evolution % 2 else 2) if evolution > 0 and (evolution-1)//2 == slot else int(self.prototypes[slot]['evolved'])

    def _boost(self, slot: int, evolution: int) -> int:
        # AI_NOTE: 初期スタッツへ加算するのは今回の進化分だけで、既存進化の強化を二重加算しない。
        return (2 if evolution % 2 else 3) if evolution > 0 and (evolution-1)//2 == slot else 0

    def _id(self, state: State, slot: int) -> str:
        # AI_NOTE: 生成IDは登場時の衝突回避結果から戻す。生成前に消えたIDの再利用も表現する。
        return f'e{state[self.tail+6]-1}' if slot == self.token else str(self.prototypes[slot]['id'])

    def _slot(self, state: State, entity_id: str) -> int:
        # AI_NOTE: 生成個体が死亡済み初期個体のIDを再利用した場合は、生きた生成slotを優先する。
        if self.token >= 0 and state[self.tail+7] and entity_id == self._id(state, self.token):
            return self.token
        return self.ids[entity_id]

    def actions(self, state: State) -> list[Json]:
        # AI_NOTE: Battleの公開操作順・対象順を保ち、ターン終了だけは列挙しない。
        spent, evolution, hand, pp, health, extra, _, _ = state[self.tail:]
        if health <= 0:
            return []
        actions: list[Json] = [{'type': 'extra_pp'}] if self.owner == 1 and not extra else []
        enemies = [j for j in range(self.n, self.count) if state[j] > 0]
        allies = [i for i in range(self.n) if state[i] > 0]
        for i, (cost, effect) in enumerate(self.spells):
            if not hand & (1 << i) or cost > pp:
                continue
            target = effect.get('target', 'self')
            if target in ('chosen_enemy', 'chosen_ally'):
                for slot in enemies if target == 'chosen_enemy' else allies:
                    actions.append({'type': 'play', 'card': self.hand[i]['id'], 'target': self._id(state, slot)})
            else:
                actions.append({'type': 'play', 'card': self.hand[i]['id']})
        guards = [j for j in enemies if state[self.count+j] & WARD]
        for i in allies:
            words = state[self.count+i]
            evolved = self._evolved(i, evolution)
            ready = self.prototypes[i]['entered_turn'] < self.own['turn'] or bool(words & STORM)
            if not spent & (1 << i) and (ready or words & RUSH or evolved):
                for j in guards or enemies:
                    actions.append({'type': 'attack', 'source': self._id(state, i), 'target': self._id(state, j)})
                if ready and not guards:
                    actions.append({'type': 'attack', 'source': self._id(state, i), 'target': f'leader:{1-self.owner}'})
            if evolved or evolution or self.own['evolved_this_turn']:
                continue
            for kind, resource, threshold in (('evolve', 'ep', 5-self.owner), ('super_evolve', 'sep', 7-self.owner)):
                if self.own[resource] > 0 and self.own['turn'] >= threshold:
                    actions.append({'type': kind, 'source': self._id(state, i)})
        return actions

    def outcomes(self, state: State, action: Json) -> list[tuple[State, Fraction, tuple[int, ...]]]:
        # AI_NOTE: ランダムは操作から分離する。敵が空なら抽選を消費せず、悪い結果も全て残す。
        kind = action['type']
        if kind == 'play':
            effect = self.spells[self.hand_ids[action['card']]][1]
            if effect.get('target') == 'random_enemy':
                enemies = [i for i in range(self.n, self.count) if state[i] > 0]
                if enemies:
                    probability = Fraction(1, len(enemies))
                    return [(self._transition(state, action, target), probability, (draw,))
                            for draw, target in enumerate(enemies)]
        return [(self._transition(state, action, -1), Fraction(1), ())]

    def _transition(self, state: State, action: Json, random_target: int) -> State:
        # AI_NOTE: 確定した1抽選結果だけ遷移させ、反撃・必殺・死亡後の状態正規化を一度で処理する。
        hp = list(state[:self.count])
        words = list(state[self.count:self.tail])
        spent, evolution, hand, pp, health, extra, next_id, spawned = state[self.tail:]

        def damage(slot: int, amount: int) -> None:
            # AI_NOTE: 超進化保護はバリア消費より先。0点はバリアを消費しない。
            if amount <= 0 or slot < self.n and self._evolved(slot, evolution) == 2:
                return
            if words[slot] & BARRIER:
                words[slot] &= ~BARRIER
            else:
                hp[slot] = max(0, hp[slot]-amount)

        kind = action['type']
        if kind == 'play':
            card = self.hand_ids[action['card']]
            cost, effect = self.spells[card]
            hand &= ~(1 << card)
            pp -= cost
            op = effect['op']
            target = self._slot(state, action['target']) if 'target' in action else random_target
            if op == 'damage':
                if target >= 0:
                    damage(target, effect['amount'])
            elif op == 'destroy':
                hp[target] = 0
            elif op == 'grant':
                words[target] |= _mask(effect.get('keywords', []))
            elif op == 'split_damage':
                remaining = effect['amount']
                enemies = [j for j in range(self.n, self.count) if hp[j] > 0]
                for offset, j in enumerate(enemies):
                    share = remaining if offset == len(enemies)-1 else min(remaining, hp[j])
                    damage(j, share)
                    remaining -= share
                    if not remaining:
                        break
            elif op == 'summon' and sum(h > 0 for h in hp[:self.n]) < 5:
                live_ids = self.static_ids | {self._id(state, i) for i, h in enumerate(hp) if h > 0}
                live_ids.update(e['id'] for i, e in enumerate(self.hand) if hand & (1 << i))
                while f'e{next_id}' in live_ids:
                    next_id += 1
                next_id += 1
                spawned = 1
                hp[self.token] = self.prototypes[self.token]['health']
                words[self.token] = _mask(self.prototypes[self.token]['keywords'])
        elif kind == 'attack':
            source = self._slot(state, action['source'])
            spent |= 1 << source
            attack = self.prototypes[source]['attack'] + self._boost(source, evolution)
            if action['target'].startswith('leader:'):
                health = max(0, health-attack)
            else:
                target = self._slot(state, action['target'])
                damage(target, attack)
                damage(source, self.prototypes[target]['attack'])
                if words[source] & BANE:
                    hp[target] = 0
                if words[target] & BANE and self._evolved(source, evolution) != 2:
                    hp[source] = 0
                if hp[target] == 0 and self._evolved(source, evolution) == 2:
                    health = max(0, health-1)
        elif kind in ('evolve', 'super_evolve'):
            source = self._slot(state, action['source'])
            super_evolve = kind == 'super_evolve'
            evolution = 2*source + (2 if super_evolve else 1)
            hp[source] += 3 if super_evolve else 2
        elif kind == 'extra_pp':
            pp += 1
            extra = 1
        else:
            raise ValueError('ターン内探索の操作ではありません')
        for i, value in enumerate(hp):
            if value <= 0:
                words[i] = 0
                spent &= ~(1 << i)
        if evolution > 0 and hp[(evolution-1)//2] <= 0:
            evolution = -1 if evolution % 2 else -2
        return tuple(hp) + tuple(words) + (spent, evolution, hand, pp, health, extra, next_id, spawned)

    def _entity(self, state: State, slot: int) -> Json:
        # AI_NOTE: 固定の個体情報へ変動値だけを戻し、公開JSONと再生検証で同じ状態を扱えるようにする。
        entity: Json = copy.deepcopy(self.prototypes[slot])
        evolution = state[self.tail+1]
        boost = self._boost(slot, evolution)
        entity.update(id=self._id(state, slot), health=state[slot],
                      attack=entity['attack']+boost, max_health=entity['max_health']+boost,
                      evolved=self._evolved(slot, evolution),
                      keywords=sorted(word for bit, word in enumerate(WORDS) if state[self.count+slot] & (1 << bit)))
        if slot < self.n:
            entity['attacks'] = entity['attacks'] or int(bool(state[self.tail] & (1 << slot)))
        return entity

    def state(self, state: State) -> Json:
        # AI_NOTE: 公開stateへ戻す時だけ辞書を作る。失敗召喚と召喚後死亡はspawnで区別し墓場を復元する。
        result = copy.deepcopy(self.root)
        spent, evolution, hand, pp, health, extra, next_id, spawned = state[self.tail:]
        own, enemy = (result['players'][i] for i in (self.owner, 1-self.owner))
        own['board'] = [self._entity(state, i) for i in range(self.n) if state[i] > 0]
        enemy['board'] = [self._entity(state, i) for i in range(self.n, self.count) if state[i] > 0]
        own['hand'] = [e for i, e in enumerate(own['hand']) if hand & (1 << i)]
        played = len(self.hand)-hand.bit_count()
        own['combo'] += played
        own['graveyard'] += played
        for i, entity in enumerate(self.prototypes):
            if state[i] <= 0 and (i != self.token or spawned):
                player = own if i < self.n else enemy
                player['graveyard'] += 1
                player['destroyed'].append(entity['card_id'])
        for player in (own, enemy):
            player['destroyed'].sort()
            for entity in player['hand']:
                entity['keywords'].sort()
        own['pp'], own['extra_pp_used'] = pp, bool(extra)
        own['ep'] -= int(evolution == -1 or evolution > 0 and evolution % 2 == 1)
        own['sep'] -= int(evolution == -2 or evolution > 0 and evolution % 2 == 0)
        own['evolved_this_turn'] = own['evolved_this_turn'] or bool(evolution)
        enemy['health'] = health
        result['next_id'] = next_id
        result['winner'] = self.owner if health <= 0 else None
        return result

    def endpoint(self, state: State) -> tuple[Any, tuple[int, ...], int]:
        # AI_NOTE: shapeの整数番号は同じKernel内だけ有効。カード能力・攻撃権・登場時刻を全て比較条件に残す。
        spent, evolution, hand, pp, health, _, _, _ = state[self.tail:]
        shapes: list[tuple[int, ...]] = []
        values = [self.own['health'], -health, pp,
                  self.own['ep']-int(evolution == -1 or evolution > 0 and evolution % 2 == 1),
                  self.own['sep']-int(evolution == -2 or evolution > 0 and evolution % 2 == 0)]
        for sign, slots in ((1, range(self.n)), (-1, range(self.n, self.count))):
            board = []
            for slot in slots:
                if state[slot] <= 0:
                    continue
                entity = self.prototypes[slot]
                evolved = self._evolved(slot, evolution)
                attacks = entity['attacks'] or int(slot < self.n and bool(spent & (1 << slot)))
                mask = state[self.count+slot]
                key = slot, mask, evolved, attacks
                shape = self.shape_cache.get(key)
                if shape is None:
                    traits = {k: v for k, v in entity.items()
                              if k not in ('id', 'card_id', 'name', 'attack', 'health', 'max_health')}
                    traits.update(evolved=evolved, attacks=attacks,
                                  keywords=sorted(word for bit, word in enumerate(WORDS) if mask & (1 << bit)))
                    marker = self.behaviors[slot], _freeze(traits)
                    shape = self.shape_ids.setdefault(marker, len(self.shape_ids))
                    self.shape_cache[key] = shape
                board.append(shape)
                boost = self._boost(slot, evolution)
                values.extend(sign*v for v in (entity['attack']+boost, state[slot], entity['max_health']+boost))
            shapes.append(tuple(board))
        return (self.owner if health <= 0 else None, tuple(shapes)), tuple(values), hand
