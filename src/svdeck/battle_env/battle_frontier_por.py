"""Experimental sleep-set traversal; exact STOP reachability, not a full policy graph."""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from time import perf_counter

from svdeck.battle_env.battle import Json
from svdeck.battle_env.battle_frontier_fast import Kernel, State

Action = tuple[tuple[str, str], ...]
Witness = tuple[State, Action, tuple[int, ...]]
Branch = tuple[State, Fraction, tuple[int, ...]]


def action_key(action: Json) -> Action:
    # AI_NOTE: 公開操作を不変キーへ変換し、異なる対象や手札個体を同一視しない。
    return tuple(sorted((key, str(value)) for key, value in action.items()))


@dataclass
class Result:
    states: set[State] = field(default_factory=set)
    witnesses: dict[State, Witness] = field(default_factory=dict)
    chance: dict[tuple[State, Action], list[Branch]] = field(default_factory=dict)
    expansions: int = 0
    transitions: int = 0
    outcomes: int = 0
    slept: int = 0
    reopens: int = 0
    seconds: float = 0.0
    complete: bool = True


class Independence:
    def __init__(self, kernel: Kernel):
        # AI_NOTE: 単一効果kernel内だけで可換性を証明する。未知能力を局所性だけで判断しない。
        self.kernel = kernel
        self.actions: dict[Action, Json] = {}
        self.supports: dict[Action, tuple[frozenset[int], int, int] | None] = {}

    def register(self, state: State, action: Json) -> Action:
        # AI_NOTE: 生成個体IDは可変なので召喚slotを含む操作を可換化から除外する。
        key = action_key(action)
        if key in self.actions:
            return key
        self.actions[key] = action
        k = self.kernel
        support: tuple[frozenset[int], int, int] | None = None
        kind = action['type']
        if kind == 'attack' and not action['target'].startswith('leader:'):
            source = k._slot(state, action['source'])
            target = k._slot(state, action['target'])
            if source != k.token and target != k.token:
                support = (frozenset((source, target)), -1, 0)
        elif kind == 'play':
            card = k.hand_ids[action['card']]
            cost, effect = k.spells[card]
            if effect['op'] in ('damage', 'destroy', 'grant') and effect.get('target') in ('chosen_enemy', 'chosen_ally'):
                target = k._slot(state, action['target'])
                if target != k.token:
                    support = (frozenset((target,)), card, cost)
        self.supports[key] = support
        return key

    def commutes(self, state: State, left: Action, right: Action) -> bool:
        # AI_NOTE: 資源不足・同じ個体・超進化による顔ダメージを除き、両順で合法かつ同一の状態になる。
        if self.kernel.token >= 0:
            return False
        a, b = self.supports[left], self.supports[right]
        if a is None or b is None or a[0] & b[0]:
            return False
        if a[1] >= 0 and b[1] >= 0:
            if a[1] == b[1] or a[2]+b[2] > state[self.kernel.tail+3]:
                return False
        evolution = state[self.kernel.tail+1]
        for key in (left, right):
            action = self.actions[key]
            if action['type'] == 'attack':
                source = self.kernel.ids[action['source']]
                if self.kernel._evolved(source, evolution) == 2:
                    return False
        return True


def enumerate_states(kernel: Kernel, *, por: bool, seconds: float = 30.0) -> Result:
    # AI_NOTE: 各prefixをSTOP候補として保存し、sleep集合が小さくなる再到達では必ず再展開する。
    started = perf_counter()
    deadline = started+seconds
    result = Result()
    blocked: dict[State, frozenset[Action]] = {}
    independence = Independence(kernel)

    def visit(state: State, sleep: frozenset[Action]) -> None:
        # AI_NOTE: 全停止状態を保ったまま独立操作の逆順を省く。確率操作はsleepを全解除する。
        if perf_counter() >= deadline:
            result.complete = False
            return
        if state in blocked:
            previous = blocked[state]
            if not por or previous <= sleep:
                return
            sleep = previous & sleep
            result.reopens += 1
        blocked[state] = sleep
        result.expansions += 1
        local_sleep = set(sleep)
        for action in kernel.actions(state):
            key = independence.register(state, action)
            if key in local_sleep:
                result.slept += 1
                continue
            branches = kernel.outcomes(state, action)
            result.transitions += 1
            result.outcomes += len(branches)
            if any(draws for _, _, draws in branches):
                result.chance[state, key] = branches
            next_sleep = frozenset(b for b in local_sleep if independence.commutes(state, key, b)) if por else frozenset()
            for child, _, tape in branches:
                if child not in result.states:
                    result.states.add(child)
                    result.witnesses[child] = (state, key, tape)
                visit(child, next_sleep)
                if not result.complete:
                    return
            if por:
                local_sleep.add(key)

    result.states.add(kernel.initial)
    visit(kernel.initial, frozenset())
    result.seconds = perf_counter()-started
    return result
