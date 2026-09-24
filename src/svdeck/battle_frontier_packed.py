"""Exhaustive graph traversal for the closed fixed-slot battle kernel."""
from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING, Any, Callable

from .battle import Battle, Json
from .battle_frontier_io import Rows
from .combat_benchmark import peak_memory

if TYPE_CHECKING:
    from .battle_frontier_fast import Kernel


def frontier(kernel: Kernel, states: list[tuple[int, ...]], deadline: float) -> tuple[list[int], bool]:
    # AI_NOTE: 全停止状態を比較する。確率辺や探索済み状態はPareto整理で削除しない。
    groups: dict[Any, dict[tuple[tuple[int, ...], int], int]] = {}
    for index, state in enumerate(states):
        if perf_counter() >= deadline:
            return list(range(len(states))), False
        shape, values, hand = kernel.endpoint(state)
        groups.setdefault(shape, {}).setdefault((values, hand), index)
    selected = []
    for group in groups.values():
        skyline: list[tuple[tuple[int, ...], int]] = []
        for values, hand in sorted(group, key=lambda item: (item[0], item[1].bit_count()), reverse=True):
            if perf_counter() >= deadline:
                return list(range(len(states))), False
            if not any(prior_hand & hand == hand and all(a >= b for a, b in zip(prior, values))
                       for prior, prior_hand in skyline):
                skyline.append((values, hand))
                selected.append(group[values, hand])
    return sorted(selected), True


def analyze_packed(battle: Battle, *, max_states: int, max_outcomes: int, seconds: float,
                   progress: Callable[[Json], None] | None = None) -> Json:
    # AI_NOTE: 整数kernelの全合法手を列挙し、グラフだけをpacked保存する。beamや深さ制限は使わない。
    from .battle_frontier import Pool, freeze
    from .battle_frontier_fast import Kernel
    started = perf_counter()
    deadline = started+seconds
    root = Battle(battle.state, battle.cards, record=False)
    kernel = Kernel(root)
    states = [kernel.initial]
    seen = {kernel.initial: 0}
    actions, probabilities, tapes = Pool(), Pool(), Pool()
    choices, outcomes, witnesses = Rows(4), Rows(3), Rows(3)
    witnesses.append((0, 0, 0))
    expanded: list[int] = []
    pending = [0]
    duplicates = 0
    cutoffs: set[str] = set()
    while pending and not cutoffs:
        index = pending.pop()
        state = states[index]
        for action in kernel.actions(state):
            if perf_counter() >= deadline:
                cutoffs.add('time')
                break
            branches = kernel.outcomes(state, action)
            if len(branches) > max_outcomes:
                cutoffs.add('chance outcomes')
                break
            fresh_keys = {child for child, _, _ in branches if child not in seen}
            if len(states)+len(fresh_keys) > max_states:
                cutoffs.add('states')
                break
            action_id = actions.add(freeze(action), action)
            offset = len(outcomes)
            for child, probability, draws in branches:
                target = seen.get(child)
                tape = tapes.add(draws)
                if target is None:
                    target = len(states)
                    seen[child] = target
                    states.append(child)
                    witnesses.append((index, action_id, tape))
                    pending.append(target)
                else:
                    duplicates += 1
                outcomes.append((target, probabilities.add(str(probability)), tape))
            choices.append((index, action_id, offset, len(outcomes)))
        else:
            expanded.append(index)
        if progress is not None and len(expanded) % 100000 == 0:
            progress({'phase': 'enumeration', 'states': len(states), 'expanded': len(expanded),
                      'outcomes': len(outcomes), 'elapsed_seconds': perf_counter()-started})
    enumeration_complete = not pending and len(expanded) == len(states)
    search_ms = (perf_counter()-started)*1000
    # Keys are retained by states; release the duplicate lookup before endpoint grouping.
    seen.clear()
    if progress is not None:
        progress({'phase': 'frontier', 'states': len(states), 'enumeration_complete': enumeration_complete,
                  'elapsed_seconds': perf_counter()-started})
    candidates, frontier_complete = frontier(kernel, states, deadline)
    if not frontier_complete:
        cutoffs.add('frontier time')
    peak, method = peak_memory()
    return {'version': 1, 'strategy': 'current-turn-frontier', 'encoding': 'fixed-slots-v1',
            'complete': not cutoffs, 'enumeration_complete': enumeration_complete,
            'frontier_complete': frontier_complete, 'cutoffs': sorted(cutoffs),
            'scope': 'Own current turn before end-turn effects. Every node allows STOP. Uniform chance outcomes, not selectable actions.',
            'dominance_scope': 'Endpoint board stats and own resources, with exact remaining-hand containment and identical ordered board traits including attack rights; not future-game dominance. Full decision graph is unpruned.',
            'record': root.export(), 'root': 0, 'positions': states, 'actions': actions.values,
            'probabilities': probabilities.values, 'draws': tapes.values, 'choices': choices, 'outcomes': outcomes,
            'witnesses': witnesses, 'expanded': expanded, 'candidates': candidates,
            'stats': {'states': len(states), 'choices': len(choices), 'outcomes': len(outcomes),
                      'duplicates': duplicates, 'candidates': len(candidates), 'search_ms': search_ms,
                      'elapsed_ms': (perf_counter()-started)*1000, 'peak_rss_bytes': peak, 'memory_method': method,
                      'memory_scope': 'whole process peak', 'max_states': max_states, 'max_outcomes': max_outcomes,
                      'seconds': seconds, 'backend': 'fixed-slots'}}
