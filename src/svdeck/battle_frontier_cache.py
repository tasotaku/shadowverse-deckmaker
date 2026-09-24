"""Experimental exact local-transition memoization for the fixed-slot kernel.

No state, action, or chance branch is pruned. Cache misses use the existing
kernel rules; hits reuse only writes whose complete read set matches.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any

from .battle import Battle, Json
from .battle_frontier_fast import Kernel, RUSH, STORM, State, WARD

Patch = tuple[tuple[tuple[int, int], ...], int, int, int]


class CachedKernel(Kernel):
    """Kernel-compatible experiment; full graph consumers need no changed schema."""

    def __init__(self, battle: Battle) -> None:
        # AI_NOTE: 各局面で閉じたcacheを持ち、カード定義や個体IDの異なる解析間で再利用しない。
        super().__init__(battle)
        self.action_cache: dict[tuple[int, ...], list[Json]] = {}
        self.patch_cache: dict[tuple[Any, ...], Patch] = {}
        self.action_hits = self.action_misses = self.patch_hits = self.patch_misses = 0
        self.action_resets = self.patch_resets = 0
        self.unit = Fraction(1)
        self.fractions = {i: Fraction(1, i) for i in range(1, self.count+1)}
        self.descriptors: dict[tuple[str, ...], tuple[int, str, tuple[int, ...], int]] = {}
        self.by_identity: dict[int, tuple[int, str, tuple[int, ...], int]] = {}
        self.common_actions: dict[tuple[str, ...], Json] = {}

    def actions(self, state: State) -> list[Json]:
        # AI_NOTE: 合法性はHPの量でなく生死だけを読む。能力・攻撃権・資源・生成IDは全て残す。
        live = sum(1 << i for i in range(self.count) if state[i] > 0)
        spent, evolution, hand, pp, health, extra, next_id, spawned = state[self.tail:]
        legal_words = tuple(state[self.count+i] & (STORM | RUSH if i < self.n else WARD)
                            for i in range(self.count))
        affordable = sum(1 << i for i, (cost, _) in enumerate(self.spells) if hand & (1 << i) and cost <= pp)
        key = (live, *legal_words, spent, evolution, affordable,
               int(health > 0), extra, next_id if spawned else 0)
        actions = self.action_cache.get(key)
        if actions is not None:
            self.action_hits += 1
            return actions
        self.action_misses += 1
        actions = []
        for action in super().actions(state):
            marker = (*action.values(), str(spawned), str(next_id))
            common = self.common_actions.setdefault(marker, action)
            if id(common) not in self.by_identity:
                self.by_identity[id(common)] = self.descriptor(state, common)
            actions.append(common)
        if len(self.action_cache) >= 65536:
            self.action_cache.clear()
            self.action_resets += 1
        self.action_cache[key] = actions
        return actions

    def descriptor(self, state: State, action: Json) -> tuple[int, str, tuple[int, ...], int]:
        # AI_NOTE: 同一公開操作の対象slotは生成IDが同じ間一定なので、辞書とID解析を一度だけ行う。
        marker = (*action.values(), str(state[self.tail+7]), str(state[self.tail+6]))
        found = self.descriptors.get(marker)
        if found is not None:
            return found
        kind = action['type']
        source = self._slot(state, action['source']) if 'source' in action else -1
        target = (self._slot(state, action['target'])
                  if 'target' in action and not action['target'].startswith('leader:') else -1)
        card = self.hand_ids[action['card']] if kind == 'play' else -1
        op = self.spells[card][1]['op'] if card >= 0 else kind
        slots = tuple(i for i in (source, target) if i >= 0)
        if op == 'split_damage':
            slots = tuple(range(self.n, self.count))
        if op == 'summon':
            slots = tuple(range(self.count))
        found = len(self.descriptors), op, slots, card
        self.descriptors[marker] = found
        return found

    def outcomes(self, state: State, action: Json) -> list[tuple[State, Fraction, tuple[int, ...]]]:
        # AI_NOTE: 抽選対象の生存順と確率は現在状態から決める。遷移cacheで悪い結果を落とさない。
        if action['type'] == 'play':
            effect = self.spells[self.hand_ids[action['card']]][1]
            if effect.get('target') == 'random_enemy':
                enemies = [i for i in range(self.n, self.count) if state[i] > 0]
                if enemies:
                    probability = self.fractions[len(enemies)]
                    return [(self.transition(state, action, target), probability, (draw,))
                            for draw, target in enumerate(enemies)]
        return [(self.transition(state, action, -1), self.unit, ())]

    def transition(self, state: State, action: Json, random_target: int) -> State:
        # AI_NOTE: 操作が実際に読む局所値で照合し、手札/PP/攻撃bitだけは相対差分を適用する。
        evolution = state[self.tail+1]
        descriptor = self.by_identity.get(id(action))
        if descriptor is None:
            descriptor = self.descriptor(state, action)
        code, op, slots, _ = descriptor
        if random_target >= 0:
            slots = (random_target,)
        key: tuple[Any, ...] = (code, evolution, random_target)
        for slot in slots:
            key += (state[slot], state[self.count+slot])
        if op == 'attack':
            key += (state[self.tail+4],)
        if op == 'summon':
            key += (state[self.tail+2], state[self.tail+6], state[self.tail+7])
        patch = self.patch_cache.get(key)
        if patch is None:
            self.patch_misses += 1
            child = super()._transition(state, action, random_target)
            relative = {self.tail, self.tail+2, self.tail+3}
            writes = tuple((i, value) for i, value in enumerate(child)
                           if i not in relative and value != state[i])
            patch = (writes, state[self.tail] ^ child[self.tail],
                     state[self.tail+2] ^ child[self.tail+2], child[self.tail+3]-state[self.tail+3])
            if len(self.patch_cache) >= 131072:
                self.patch_cache.clear()
                self.patch_resets += 1
            self.patch_cache[key] = patch
            return child
        self.patch_hits += 1
        writes, spent, hand, pp = patch
        values = list(state)
        for index, value in writes:
            values[index] = value
        values[self.tail] ^= spent
        values[self.tail+2] ^= hand
        values[self.tail+3] += pp
        return tuple(values)

    def cache_stats(self) -> dict[str, int]:
        # AI_NOTE: 完全探索の計算量とcacheによる再計算回避量を分けて記録する。
        return {'action_hits': self.action_hits, 'action_misses': self.action_misses,
                'patch_hits': self.patch_hits, 'patch_misses': self.patch_misses,
                'action_resets': self.action_resets, 'patch_resets': self.patch_resets}
