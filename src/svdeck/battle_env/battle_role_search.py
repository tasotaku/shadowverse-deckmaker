"""Finite turn search with role diversity and atomic chance expectations.

Role/beam limits are approximations. Chance outcomes of an evaluated action are
never ranked as separate choices. Unknown deck draws stop a speculative route.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from fractions import Fraction
from time import perf_counter
from typing import Any, cast

from svdeck.battle_env.battle import Battle, Json
from svdeck.battle_env.battle_ai import evaluate
from svdeck.battle_env.battle_practical import Chance, ChanceBattle, Limit


class RoleBattle(ChanceBattle):
    unknown_draw = False

    def emit(self, kind: str, message: str, **values: Any) -> None:
        # AI_NOTE: A witness deck is a hypothesis; never continue as if its next card were known.
        if kind == 'effect' and values['effect']['op'] in {'draw', 'deck_summon'}:
            self.unknown_draw = True

    def branch(self, action: Json, draws: tuple[int, ...]) -> RoleBattle:
        # AI_NOTE: Reset per-action uncertainty while preserving ChanceBattle's independent state/queues.
        base = copy.copy(self)
        base.unknown_draw = False
        return cast(RoleBattle, super(RoleBattle, base).branch(action, draws))


@dataclass
class Budget:
    maximum: int
    deadline: float
    nodes: int = 0
    cutoffs: set[str] = field(default_factory=set)

    def check(self) -> None:
        # AI_NOTE: Every search phase shares one decision budget, including chance expansion.
        if perf_counter() >= self.deadline:
            self.cutoffs.add('time')
            raise Limit('time')
        if self.nodes >= self.maximum:
            self.cutoffs.add('nodes')
            raise Limit('nodes')


@dataclass
class Leaf:
    battle: RoleBattle
    probability: Fraction
    steps: list[Json]


@dataclass
class Plan:
    action: Json
    score: float
    leaves: list[Leaf]
    used: set[str]
    roles: set[str]
    unknown: bool = False


def strings(value: Any) -> set[str]:
    # AI_NOTE: Discard/selection slots also consume original hand cards, not only action.card.
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*(strings(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(strings(v) for v in value))
    return set()


def goals(battle: Battle, actor: int) -> list[str]:
    # AI_NOTE: Goals order work; keep damage, resources and development even when defending.
    own, enemy = battle.state['players'][actor], battle.state['players'][1-actor]
    result = ['damage'] if enemy['health'] <= 8 else []
    if own['health'] <= 10 or sum(e['attack'] for e in enemy['board']) >= own['health']:
        result += ['heal', 'defense']
    if len(enemy['board']) >= 2:
        result += ['remove_all', 'remove_multi']
    if enemy['board']:
        result += ['remove_one']
    result += ['develop', 'resource', 'damage', 'defense', 'heal', 'support', 'unknown']
    return list(dict.fromkeys(result))


class Turn:
    def __init__(self, battle: Battle, profiles: dict[str, Json], weights: dict[str, float],
                 budget: Budget, max_nodes: int, width: int, max_actions: int = 6):
        # AI_NOTE: Reuse the normal validated engine, isolating only state and chance control.
        self.root = RoleBattle(battle.state, battle.cards, record=False)
        self.root.deadline = budget.deadline
        self.actor = battle.state['active_player']
        self.hand = {e['id'] for e in battle.state['players'][self.actor]['hand']}
        self.profiles, self.weights, self.budget = profiles, weights, budget
        self.stop_at = budget.nodes + max_nodes
        self.width, self.max_actions = width, max_actions
        self.priorities = goals(battle, self.actor)
        self.cache: dict[tuple[str, int], list[Plan]] = {}
        self.ends: dict[str, Plan] = {}
        self.cutoffs: set[str] = set()

    def branches(self, battle: RoleBattle, action: Json) -> list[tuple[RoleBattle, Fraction, tuple[int, ...]]]:
        # AI_NOTE: An over-budget chance action is rejected as a whole; no lucky partial expectation.
        pending: list[tuple[tuple[int, ...], Fraction]] = [((), Fraction(1))]
        result: list[tuple[RoleBattle, Fraction, tuple[int, ...]]] = []
        while pending:
            self.budget.check()
            if self.budget.nodes >= self.stop_at:
                self.cutoffs.add('turn_nodes')
                raise Limit('turn_nodes')
            draws, probability = pending.pop()
            try:
                child = battle.branch(action, draws)
            except Chance as chance:
                if len(result) + len(pending) + chance.size > 128 or len(draws) >= 32:
                    self.cutoffs.add('chance_outcomes')
                    raise Limit('chance_outcomes')
                pending.extend((draws+(i,), probability/chance.size) for i in reversed(range(chance.size)))
            else:
                self.budget.nodes += 1
                result.append((child, probability, draws))
        return result

    def tags(self, battle: Battle, action: Json) -> set[str]:
        # AI_NOTE: Board attacks and evolution can satisfy a role without a hand card.
        kind = action['type']
        if kind == 'attack':
            return {'damage' if str(action['target']).startswith('leader:') else 'remove_one'}
        if kind in {'evolve', 'super_evolve'}:
            found = battle.find(action['source'])
            return {'develop', 'remove_one', 'support'} | (set(self.profiles[found[2]['card_id']]['roles']) if found else set())
        if kind == 'play':
            found = battle.find(action['card'])
            return set(self.profiles[found[2]['card_id']]['roles']) if found else {'unknown'}
        return {'support'} if kind == 'extra_pp' else set()

    def finish(self, battle: RoleBattle) -> Plan:
        # AI_NOTE: Closing a turn is atomic too; callers discard the whole action if any sibling cannot close.
        key = json.dumps(battle.state, sort_keys=True, separators=(',', ':'))
        if key in self.ends:
            return self.ends[key]
        end = {'type': 'end_turn'}
        if battle.state['winner'] is not None or battle.state['active_player'] != self.actor:
            return Plan(end, evaluate(battle, self.actor, self.weights), [Leaf(battle, Fraction(1), [])], set(), set())
        children = self.branches(battle, end)
        leaves = [Leaf(b, p, [{'action': end, 'draws': list(d)}]) for b, p, d in children]
        result = Plan(end, sum(float(leaf.probability)*evaluate(leaf.battle, self.actor, self.weights)
                               for leaf in leaves), leaves, set(), set(), any(leaf.battle.unknown_draw for leaf in leaves))
        self.ends[key] = result
        return result

    def select(self, plans: list[Plan], width: int) -> list[Plan]:
        # AI_NOTE: Keep a representative of each response role instead of a scalar-only top-K beam.
        ranked = sorted(plans, key=lambda p: (-p.score, json.dumps(p.action, sort_keys=True)))
        result = ranked[:width]
        for role in self.priorities:
            candidate = next((p for p in ranked if role in p.roles), None)
            if candidate is not None and all(p is not candidate for p in result):
                result.append(candidate)
        return result

    def options(self, battle: RoleBattle | None = None, depth: int | None = None) -> list[Plan]:
        # AI_NOTE: Branch decisions may adapt after chance; all resulting probabilities remain attached.
        battle = self.root if battle is None else battle
        depth = self.max_actions if depth is None else depth
        key = (json.dumps(battle.state, sort_keys=True, separators=(',', ':')), depth)
        if key in self.cache:
            return self.cache[key]
        try:
            baseline = self.finish(battle)
        except Limit as limit:
            self.cutoffs.update({'unclosed_turn', str(limit)})
            return []
        if depth <= 0 or battle.state['winner'] is not None or battle.state['active_player'] != self.actor:
            if depth <= 0:
                self.cutoffs.add('action_depth')
            return [baseline]
        actions = [a for a in battle.legal_actions() if a['type'] != 'end_turn']
        actions.sort(key=lambda a: (min((self.priorities.index(t) for t in self.tags(battle, a)
                                         if t in self.priorities), default=99), json.dumps(a, sort_keys=True)))
        plans = [baseline]
        raw: dict[int, list[tuple[RoleBattle, Fraction, tuple[int, ...]]]] = {}
        for action in actions:
            if self.budget.nodes >= self.stop_at:
                self.cutoffs.add('turn_nodes')
                break
            try:
                children = self.branches(battle, action)
                leaves: list[Leaf] = []
                for child, probability, draws in children:
                    stopped = self.finish(child)
                    leaves.extend(Leaf(l.battle, probability*l.probability,
                                       [{'action': action, 'draws': list(draws)}]+l.steps) for l in stopped.leaves)
            except Limit as limit:
                self.cutoffs.add(str(limit))
                break
            consumed = strings(action) & self.hand
            before_hand = {e['id'] for e in battle.state['players'][self.actor]['hand']}
            for child, _, _ in children:
                consumed.update((before_hand-{e['id'] for e in child.state['players'][self.actor]['hand']}) & self.hand)
            plan = Plan(action, sum(float(l.probability)*evaluate(l.battle, self.actor, self.weights) for l in leaves),
                        leaves, consumed, self.tags(battle, action),
                        any(child.unknown_draw for child, _, _ in children))
            plans.append(plan)
            raw[id(plan)] = children
        selected = self.select(plans[1:], self.width)
        if len(selected) < len(plans)-1:
            self.cutoffs.add('beam')
        for plan in selected:
            if self.budget.nodes >= self.stop_at or perf_counter() >= self.budget.deadline:
                self.cutoffs.add('turn_nodes' if self.budget.nodes >= self.stop_at else 'time')
                break
            updated: list[Leaf] = []
            used, tags = set(plan.used), set(plan.roles)
            for child, probability, draws in raw[id(plan)]:
                if child.unknown_draw:
                    self.cutoffs.add('unknown_draw')
                    continuation = self.finish(child)
                else:
                    continuations = self.options(child, depth-1)
                    continuation = max(continuations, key=lambda p: p.score) if continuations else self.finish(child)
                updated.extend(Leaf(l.battle, probability*l.probability,
                                    [{'action': plan.action, 'draws': list(draws)}]+l.steps) for l in continuation.leaves)
                used.update(continuation.used)
                tags.update(continuation.roles)
            # A policy with too many output branches remains at its fully evaluated shorter horizon.
            if len(updated) > 256:
                self.cutoffs.add('policy_outcomes')
                continue
            plan.score = sum(float(l.probability)*evaluate(l.battle, self.actor, self.weights) for l in updated)
            plan.leaves, plan.used, plan.roles = updated, used, tags
        self.cache[key] = plans
        return plans
