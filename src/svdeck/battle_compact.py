"""Compact exact solver for combat with simple damage spells; other cards use Battle."""
from __future__ import annotations

from fractions import Fraction
from time import perf_counter
from typing import Any

from .battle import Battle, Json

Pair = tuple[Any, Any]
State = tuple[int, ...]
Action = tuple[int, int, int]


def eligible(battle: Battle) -> bool:
    # AI_NOTE: 履歴・条件・生成を読まない閉じた部分だけ高速化し、それ以外は既存の厳密探索へ戻す。
    owner = battle.state['active_player']
    for player in battle.state['players']:
        if player['health'] <= 0:
            return False
        for entity in player['board']:
            card = battle.cards[entity['card_id']]
            if entity['health'] <= 0 or entity.get('form') or any(card.get(k) for k in ('evolve', 'super_evolve', 'fanfare', 'effects')):
                return False
    for entity in battle.state['players'][owner]['hand']:
        card = battle.cards[entity['card_id']]
        effects = card.get('effects', [])
        if card['kind'] != 'spell' or 'enhance' in card or len(effects) != 1:
            return False
        effect = effects[0]
        if (set(effect)-{'op', 'target', 'amount'} or effect.get('op') != 'damage'
                or effect.get('target') not in ('chosen_enemy', 'random_enemy')
                or type(effect.get('amount')) is not int):
            return False
    return True


class Compact:
    def __init__(self, battle: Battle, weights: dict[str, int], objective: str,
                 max_states: int, max_depth: int, max_outcomes: int, deadline: float):
        # AI_NOTE: 個体ID・盤面順は固定slotへ写し、変わる整数だけをメモする。カード名や履歴は状態を増やさない。
        self.owner = battle.state['active_player']
        self.own, self.enemy = (battle.state['players'][i] for i in (self.owner, 1-self.owner))
        self.entities = self.own['board']+self.enemy['board']
        self.n, self.m = len(self.own['board']), len(self.enemy['board'])
        self.count = self.n+self.m
        self.weights, self.objective = weights, objective
        self.max_states, self.max_depth, self.max_outcomes = max_states, max_depth, max_outcomes
        self.deadline = deadline
        self.base_attack = [e['attack'] for e in self.entities]
        self.evolved = [e['evolved'] for e in self.entities]
        self.base_keywords = [len(e['keywords'])-int('バリア' in e['keywords']) for e in self.entities]
        self.bane = sum(1 << i for i, e in enumerate(self.entities) if '必殺' in e['keywords'])
        self.guard = sum(1 << i for i, e in enumerate(self.entities) if '守護' in e['keywords'])
        self.ready = sum(1 << i for i, e in enumerate(self.own['board'])
                         if e['entered_turn'] < self.own['turn'] or '疾走' in e['keywords'])
        self.rush = self.ready | sum(1 << i for i, e in enumerate(self.own['board'])
                                     if '突進' in e['keywords'] or e['evolved'])
        self.spells = [(e['cost'], battle.cards[e['card_id']]['effects'][0]) for e in self.own['hand']]
        self.initial: State = tuple(e['health'] for e in self.entities)+(sum(1 << i for i, e in enumerate(self.entities) if 'バリア' in e['keywords']),
            sum(1 << i for i, e in enumerate(self.own['board']) if e['attacks']), 0,
            (1 << len(self.spells))-1, self.own['pp'], self.enemy['health'], int(self.own['extra_pp_used']))
        self.cache: dict[State, tuple[Pair, Action | None]] = {}
        self.visiting = 0
        self.hits, self.transitions = 0, 0
        self.cutoffs: set[str] = set()
        # Each initial follower attacks once, each spell once, one evolution and one extra PP: strict horizon.
        self.horizon = self.n+len(self.spells)+2

    def encode(self, battle: Battle) -> State:
        # AI_NOTE: 公開エンジンの再生結果を同じ整数状態に写し、出力方策の全遷移を高速側と照合する。
        own, enemy = (battle.state['players'][i] for i in (self.owner, 1-self.owner))
        present = {e['id']: e for e in own['board']+enemy['board']}
        hp, barrier, spent, evolution = [], 0, 0, 0
        for i, original in enumerate(self.entities):
            entity = present.get(original['id'])
            hp.append(entity['health'] if entity else 0)
            if entity:
                barrier |= int('バリア' in entity['keywords']) << i
                if i < self.n:
                    spent |= int(entity['attacks'] > 0) << i
                    if entity['evolved'] != original['evolved']:
                        evolution = 2*i+entity['evolved']
        # A dead evolved follower no longer identifies its slot; callers compare resources separately in tests.
        hand_ids = {e['id'] for e in own['hand']}
        hand = sum(1 << i for i, e in enumerate(self.own['hand']) if e['id'] in hand_ids)
        return tuple(hp)+(barrier, spent, evolution, hand, own['pp'], enemy['health'], int(own['extra_pp_used']))

    def parts(self, state: State) -> tuple[int, int, int, int, int, int, int]:
        # AI_NOTE: slotの末尾に資源を固定配置し、可変長の両盤面を区別する。
        barrier, spent, evolution, hand, pp, health, extra = state[self.count:]
        return barrier, spent, evolution, hand, pp, health, extra

    def score(self, state: State) -> Pair:
        # AI_NOTE: 公開の評価式と同じ重みを整数で計算し、抽選を平均する時だけ有理数へ変える。
        barrier, _, evolution, hand, pp, health, _ = self.parts(state)
        w = self.weights
        score = w['leader']*(self.own['health']-health)
        for i in range(self.count):
            if state[i] <= 0:
                continue
            attack = self.base_attack[i]+(2+(evolution % 2 == 0) if evolution and (evolution-1)//2 == i else 0)
            score += (1 if i < self.n else -1)*(w['body']+w['attack']*attack+w['health']*state[i]
                         +w['keyword']*(self.base_keywords[i]+bool(barrier & (1 << i))))
            if i < self.n:
                score += w['own_board_health']*state[i]
        score += w['hand']*hand.bit_count()+w['pp']*pp
        score += w['ep']*(self.own['ep']-bool(evolution % 2))
        score += w['sep']*(self.own['sep']-bool(evolution and evolution % 2 == 0))
        return int(health <= 0), score+w['win']*int(health <= 0)

    def actions(self, state: State) -> list[Action]:
        # AI_NOTE: 公開Battleと同順の合法手を列挙し、同点時の推奨手も安定させる。
        _, spent, evolution, hand, pp, _, extra = self.parts(state)
        result: list[Action] = [(4, 0, 0)] if self.owner == 1 and not extra else []
        enemies = [i for i in range(self.n, self.count) if state[i] > 0]
        for k, (cost, effect) in enumerate(self.spells):
            if hand & (1 << k) and cost <= pp:
                if effect['target'] == 'chosen_enemy':
                    result.extend((0, k, j) for j in enemies)
                else:
                    result.append((0, k, -1))
        guards = [j for j in enemies if self.guard & (1 << j)]
        for i in range(self.n):
            if state[i] <= 0:
                continue
            if not spent & (1 << i) and (self.rush & (1 << i) or evolution and (evolution-1)//2 == i):
                result.extend((1, i, j) for j in guards or enemies)
                if not guards and self.ready & (1 << i):
                    result.append((1, i, -1))
            if self.evolved[i] or evolution or self.own['evolved_this_turn']:
                continue
            for kind, resource, threshold in ((2, 'ep', 5-self.owner), (3, 'sep', 7-self.owner)):
                if self.own[resource] > 0 and self.own['turn'] >= threshold:
                    result.append((kind, i, 0))
        return result

    def children(self, state: State, action: Action) -> list[State]:
        # AI_NOTE: 同時反撃・必殺・超進化保護・バリア消費を保持し、抽選は生存敵slot順の等確率にする。
        kind, source, target = action
        barrier, spent, evolution, hand, pp, health, extra = self.parts(state)
        targets = [i for i in range(self.n, self.count) if state[i] > 0] if kind == 0 and target == -1 else [target]
        if not targets:
            targets = [-1]
        result = []
        for selected in targets:
            hp = list(state[:self.count])
            shield = barrier
            def damage(i: int, amount: int) -> None:
                # AI_NOTE: 0ダメージではバリアを消費せず、味方超進化はバリアより先に防ぐ。
                nonlocal shield
                if amount <= 0 or i < self.n and (self.evolved[i] == 2 or evolution == 2*i+2):
                    return
                if shield & (1 << i):
                    shield &= ~(1 << i)
                else:
                    hp[i] = max(0, hp[i]-amount)
            new_spent, new_evolution, new_hand, new_pp, new_health, new_extra = spent, evolution, hand, pp, health, extra
            if kind == 0:
                cost, effect = self.spells[source]
                new_hand &= ~(1 << source)
                new_pp -= cost
                if selected >= 0:
                    damage(selected, effect['amount'])
            elif kind == 1:
                new_spent |= 1 << source
                attack = self.base_attack[source]+(2+(evolution % 2 == 0) if evolution and (evolution-1)//2 == source else 0)
                if selected == -1:
                    new_health = max(0, health-attack)
                else:
                    damage(selected, attack)
                    damage(source, self.base_attack[selected])
                    if self.bane & (1 << source):
                        hp[selected] = 0
                    if self.bane & (1 << selected) and self.evolved[source] != 2 and evolution != 2*source+2:
                        hp[source] = 0
                    if hp[selected] == 0 and (self.evolved[source] == 2 or evolution == 2*source+2):
                        new_health = max(0, health-1)
            elif kind in (2, 3):
                new_evolution = 2*source+kind-1
                hp[source] += kind
            else:
                new_pp += 1
                new_extra = 1
            alive = sum(1 << i for i, h in enumerate(hp) if h > 0)
            result.append(tuple(hp)+(shield & alive, new_spent & alive, new_evolution, new_hand, new_pp, new_health, new_extra))
        return result

    def solve(self, state: State, depth: int = 0) -> Pair:
        # AI_NOTE: 全合法手を比較する厳密DP。上限超過時は未探索を劣位とみなさず、呼出側へ打切りを伝える。
        key = state if self.max_depth >= self.horizon else state+(depth,)
        cached = self.cache.get(key)
        if cached is not None:
            self.hits += 1
            return cached[0]
        if len(self.cache)+self.visiting >= self.max_states:
            self.cutoffs.add('states')
            raise RuntimeError('compact limit')
        if perf_counter() >= self.deadline:
            self.cutoffs.add('time')
            raise RuntimeError('compact limit')
        best = self.score(state)
        chosen = None
        if state[self.count+5] > 0:
            if depth >= self.max_depth:
                self.cutoffs.add('depth')
                raise RuntimeError('compact limit')
            self.visiting += 1
            try:
                for action in self.actions(state):
                    branches = self.children(state, action)
                    if len(branches) > self.max_outcomes:
                        self.cutoffs.add('chance outcomes')
                        raise RuntimeError('compact limit')
                    values = [self.solve(child, depth+1) for child in branches]
                    self.transitions += len(values)
                    if len(values) == 1:
                        expected = values[0]
                    else:
                        expected = (Fraction(sum(v[0] for v in values), len(values)), Fraction(sum(v[1] for v in values), len(values)))
                    if (expected if self.objective == 'lethal' else expected[::-1]) > (best if self.objective == 'lethal' else best[::-1]):
                        best, chosen = expected, action
            finally:
                self.visiting -= 1
        self.cache[key] = (best, chosen)
        return best

    def choice(self, state: State, depth: int) -> Action | None:
        # AI_NOTE: 深さ上限が効く設定では残り手数を区別したメモから方策を復元する。
        return self.cache[state if self.max_depth >= self.horizon else state+(depth,)][1]

    def public_action(self, action: Action) -> Json:
        # AI_NOTE: 固定slotを元の個体IDに戻し、通常APIで合法性と全抽選結果を再生できる形にする。
        kind, source, target = action
        if kind == 0:
            result: Json = {'type': 'play', 'card': self.own['hand'][source]['id']}
            if target >= 0:
                result['target'] = self.entities[target]['id']
            return result
        if kind == 1:
            return {'type': 'attack', 'source': self.entities[source]['id'],
                    'target': f'leader:{1-self.owner}' if target == -1 else self.entities[target]['id']}
        if kind in (2, 3):
            return {'type': 'evolve' if kind == 2 else 'super_evolve', 'source': self.entities[source]['id']}
        return {'type': 'extra_pp'}
