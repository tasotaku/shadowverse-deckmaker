"""Optional Numba implementation of the closed fixed-slot transition kernel.

Numba infers the array/tuple types at compilation; the public Python boundary is
typed in battle_frontier_native.py. No scores or probabilistic pruning occur here.
"""
# mypy: ignore-errors
from __future__ import annotations

import numpy as np
from numba import njit

from .battle_frontier_native_index import _grow, _locate
from .battle_frontier_native_delta import _combat_key, _spell_key


@njit(cache=True)
def _pack(state, layout):
    # AI_NOTE: Each field lies within one uint64, preserving every state bit without hashing collisions.
    a, b, c = np.uint64(0), np.uint64(0), np.uint64(0)
    for i in range(len(state)):
        part = np.uint64(state[i]+layout[i, 3]) << np.uint64(layout[i, 1])
        if layout[i, 0] == 0:
            a |= part
        elif layout[i, 0] == 1:
            b |= part
        else:
            c |= part
    return a, b, c


@njit(cache=True)
def _unpack(key, layout):
    # AI_NOTE: The evolution field is biased by two so dead EP/SEP states remain distinct.
    state = np.empty(len(layout), dtype=np.int64)
    for i in range(len(layout)):
        state[i] = np.int64((key[layout[i, 0]] >> np.uint64(layout[i, 1])) & np.uint64(layout[i, 2]))-layout[i, 3]
    return state


@njit(cache=True, inline='always')
def _unpack_into(key, layout, state):
    # AI_NOTE: Each BFS batch owns one decoded buffer instead of allocating one per visited node.
    for i in range(len(layout)):
        state[i] = np.int64((key[layout[i, 0]] >> np.uint64(layout[i, 1])) & np.uint64(layout[i, 2]))-layout[i, 3]


@njit(cache=True, inline='always')
def _evolved(slot, evolution, prototypes):
    # AI_NOTE: Already-evolved entities keep their original protection, including super evolution.
    if evolution > 0 and (evolution-1)//2 == slot:
        return 1 if evolution % 2 else 2
    return prototypes[slot, 1]


@njit(cache=True, inline='always')
def _damage(state, slot, amount, n, count, prototypes):
    # AI_NOTE: Zero damage and super protection precede barrier consumption, matching Battle.
    if amount <= 0 or slot < n and _evolved(slot, state[2*count+1], prototypes) == 2:
        return
    if state[count+slot] & 1:
        state[count+slot] &= ~1
    else:
        state[slot] = max(0, state[slot]-amount)


@njit(cache=True)
def _actions(state, prototypes, spells, config, result):
    # AI_NOTE: Generate the same public legal-action order; STOP is implicit at every node.
    n, count, token, owner, turn, ep, sep, evolved_turn = config
    tail = 2*count
    spent, evolution, hand, pp, health, extra = state[tail:tail+6]
    used = 0
    if health <= 0:
        return used
    if owner == 1 and not extra:
        result[used] = (0, 0, -1)
        used += 1
    for card in range(len(spells)):
        if not hand & (1 << card) or spells[card, 0] > pp:
            continue
        mode = spells[card, 2]
        if mode == 1 or mode == 2:
            start, stop = (n, count) if mode == 1 else (0, n)
            for slot in range(start, stop):
                if state[slot] > 0:
                    result[used] = (1, card, slot)
                    used += 1
        else:
            result[used] = (1, card, -1)
            used += 1
    guards = False
    for j in range(n, count):
        if state[j] > 0 and state[count+j] & 16:
            guards = True
    for i in range(n):
        if state[i] <= 0:
            continue
        words = state[count+i]
        evolved = _evolved(i, evolution, prototypes)
        ready = prototypes[i, 2] < turn or bool(words & 4)
        if not spent & (1 << i) and (ready or words & 8 or evolved):
            for j in range(n, count):
                if state[j] > 0 and (not guards or state[count+j] & 16):
                    result[used] = (2, i, j)
                    used += 1
            if ready and not guards:
                result[used] = (2, i, -1)
                used += 1
        if evolved or evolution or evolved_turn:
            continue
        if ep > 0 and turn >= 5-owner:
            result[used] = (3, i, -1)
            used += 1
        if sep > 0 and turn >= 7-owner:
            result[used] = (4, i, -1)
            used += 1
    return used


@njit(cache=True)
def _transition_into(state, kind, source, target, random_target, prototypes, spells, config, static_ids, hand_ids, result):
    # AI_NOTE: A transition receives one fixed draw; every possible draw is separately enumerated.
    result[:] = state
    n, count, token, owner, turn, ep, sep, evolved_turn = config
    tail = 2*count
    evolution = result[tail+1]
    if kind == 1:
        result[tail+2] &= ~(1 << source)
        result[tail+3] -= spells[source, 0]
        op, mode, amount = spells[source, 1:4]
        if target < 0:
            target = random_target
        if op == 0:
            if target >= 0:
                _damage(result, target, amount, n, count, prototypes)
        elif op == 1:
            result[target] = 0
        elif op == 2:
            result[count+target] |= amount
        elif op == 3:
            last = -1
            for slot in range(n, count):
                if result[slot] > 0:
                    last = slot
            remaining = amount
            for slot in range(n, count):
                if result[slot] <= 0:
                    continue
                share = remaining if slot == last else min(remaining, result[slot])
                _damage(result, slot, share, n, count, prototypes)
                remaining -= share
                if not remaining:
                    break
        elif op == 4:
            live = 0
            for slot in range(n):
                live += result[slot] > 0
            if live < 5:
                next_id = result[tail+6]
                while True:
                    occupied = False
                    for value in static_ids:
                        if value == next_id:
                            occupied = True
                    for slot in range(count):
                        if result[slot] > 0 and prototypes[slot, 5] == next_id:
                            occupied = True
                    for card in range(len(hand_ids)):
                        if result[tail+2] & (1 << card) and hand_ids[card] == next_id:
                            occupied = True
                    if not occupied:
                        break
                    next_id += 1
                result[tail+6] = next_id+1
                result[tail+7] = 1
                result[token] = prototypes[token, 3]
                result[count+token] = prototypes[token, 4]
    elif kind == 2:
        result[tail] |= 1 << source
        boost = (2 if evolution % 2 else 3) if evolution > 0 and (evolution-1)//2 == source else 0
        attack = prototypes[source, 0]+boost
        if target < 0:
            result[tail+4] = max(0, result[tail+4]-attack)
        else:
            _damage(result, target, attack, n, count, prototypes)
            _damage(result, source, prototypes[target, 0], n, count, prototypes)
            if result[count+source] & 2:
                result[target] = 0
            if result[count+target] & 2 and _evolved(source, evolution, prototypes) != 2:
                result[source] = 0
            if result[target] == 0 and _evolved(source, evolution, prototypes) == 2:
                result[tail+4] = max(0, result[tail+4]-1)
    elif kind == 3 or kind == 4:
        result[tail+1] = 2*source+(2 if kind == 4 else 1)
        result[source] += 3 if kind == 4 else 2
    else:
        result[tail+3] += 1
        result[tail+5] = 1
    for slot in range(count):
        if result[slot] <= 0:
            result[count+slot] = 0
            result[tail] &= ~(1 << slot)
    evolution = result[tail+1]
    if evolution > 0 and result[(evolution-1)//2] <= 0:
        result[tail+1] = -1 if evolution % 2 else -2
    return result


@njit(cache=True)
def _transition(state, kind, source, target, random_target, prototypes, spells, config, static_ids, hand_ids):
    # AI_NOTE: The compatibility wrapper returns independent storage; the enumerator reuses its private buffer.
    return _transition_into(state, kind, source, target, random_target, prototypes, spells, config,
                            static_ids, hand_ids, np.empty_like(state))


@njit(cache=True)
def _batch(keys, witnesses, seen, size, cursor, batch_size, max_outcomes,
           layout, prototypes, spells, config, static_ids, hand_ids):
    # AI_NOTE: Chance branches are budgeted atomically; partial probability distributions never enter the graph.
    stop = min(cursor+batch_size, len(keys))
    actions = np.empty((128, 3), dtype=np.int64)
    branch_keys = np.empty((5, 3), dtype=np.uint64)
    branch_draws = np.empty(5, dtype=np.int64)
    branch_fresh = np.empty(5, dtype=np.bool_)
    state = np.empty(len(layout), dtype=np.int64)
    n, count = config[:2]
    total_choices, total_outcomes, duplicates = 0, 0, 0
    while cursor < size and cursor < stop:
        state_key = (keys[cursor, 0], keys[cursor, 1], keys[cursor, 2])
        _unpack_into(state_key, layout, state)
        count_actions = _actions(state, prototypes, spells, config, actions)
        for action_index in range(count_actions):
            kind, source, target = actions[action_index]
            branches = 0
            if kind == 1 and spells[source, 2] == 3:
                for slot in range(n, count):
                    if state[slot] > 0:
                        branch_keys[branches] = _spell_key(state, state_key, source, target, slot, layout,
                                                          prototypes, spells, config, static_ids, hand_ids)
                        branch_draws[branches] = branches
                        branches += 1
            if branches == 0:
                if kind == 1:
                    branch_keys[0] = _spell_key(state, state_key, source, target, -1, layout,
                                              prototypes, spells, config, static_ids, hand_ids)
                else:
                    branch_keys[0] = _combat_key(state, state_key, kind, source, target, layout, prototypes, config)
                branch_draws[0] = -1
                branches = 1
            if branches > max_outcomes:
                return size, cursor, 2, total_choices, total_outcomes, duplicates, seen
            fresh = 0
            for branch in range(branches):
                key = (branch_keys[branch, 0], branch_keys[branch, 1], branch_keys[branch, 2])
                repeated = False
                for prior in range(branch):
                    if (branch_keys[prior, 0] == key[0] and branch_keys[prior, 1] == key[1]
                            and branch_keys[prior, 2] == key[2]):
                        repeated = True
                # AI_NOTE: Retain the atomic budget check's lookup; no other action mutates seen before insertion.
                branch_fresh[branch] = not repeated and seen[_locate(seen, keys, key)] == 0
                if branch_fresh[branch]:
                    fresh += 1
            if size+fresh > len(keys):
                return size, cursor, 1, total_choices, total_outcomes, duplicates, seen
            if (size+fresh)*10 > len(seen)*7:
                seen = _grow(seen, keys, size)
            code = kind*256+source*16+target+1
            for branch in range(branches):
                key = (branch_keys[branch, 0], branch_keys[branch, 1], branch_keys[branch, 2])
                if branch_fresh[branch]:
                    seen[_locate(seen, keys, key)] = size+1
                    keys[size] = key
                    witnesses[size] = (cursor, code, branch_draws[branch])
                    size += 1
                else:
                    duplicates += 1
            total_choices += 1
            total_outcomes += branches
        cursor += 1
    return size, cursor, 0, total_choices, total_outcomes, duplicates, seen
