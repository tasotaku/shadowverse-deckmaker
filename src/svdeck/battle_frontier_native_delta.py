"""Exact sparse packed updates for the closed current-turn action set."""
# mypy: ignore-errors
from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True, inline='always')
def _replace(key, field, value, layout):
    # AI_NOTE: A validated field fits one word, so replacing its full mask preserves every unrelated bit.
    word, shift, mask, bias = layout[field]
    clear = ~(np.uint64(mask) << np.uint64(shift))
    part = np.uint64(value+bias) << np.uint64(shift)
    if word == 0:
        return (key[0] & clear) | part, key[1], key[2]
    if word == 1:
        return key[0], (key[1] & clear) | part, key[2]
    return key[0], key[1], (key[2] & clear) | part


@njit(cache=True, inline='always')
def _kill_key(state, key, slot, count, layout):
    # AI_NOTE: Canonical death clears abilities and attacks and retains whether EP or SEP was already spent.
    tail = 2*count
    key = _replace(key, slot, 0, layout)
    key = _replace(key, count+slot, 0, layout)
    key = _replace(key, tail, state[tail] & ~(1 << slot), layout)
    evolution = state[tail+1]
    if evolution > 0 and (evolution-1)//2 == slot:
        key = _replace(key, tail+1, -1 if evolution % 2 else -2, layout)
    return key


@njit(cache=True, inline='always')
def _hit_key(state, key, slot, amount, n, count, layout, prototypes):
    # AI_NOTE: Zero damage and own-side super protection leave barriers intact, exactly as the array transition does.
    if amount <= 0:
        return key
    evolution = state[2*count+1]
    if slot < n:
        evolved = prototypes[slot, 1]
        if evolution > 0 and (evolution-1)//2 == slot:
            evolved = 1 if evolution % 2 else 2
        if evolved == 2:
            return key
    if state[count+slot] & 1:
        return _replace(key, count+slot, state[count+slot] & ~1, layout)
    health = max(0, state[slot]-amount)
    if health == 0:
        return _kill_key(state, key, slot, count, layout)
    return _replace(key, slot, health, layout)


@njit(cache=True)
def _spell_key(state, key, source, target, random_target, layout, prototypes, spells, config, static_ids, hand_ids):
    # AI_NOTE: Every effect changes packed fields directly; random draws still produce separately checked complete branches.
    n, count, token = config[:3]
    tail = 2*count
    hand = state[tail+2] & ~(1 << source)
    key = _replace(key, tail+2, hand, layout)
    key = _replace(key, tail+3, state[tail+3]-spells[source, 0], layout)
    op, mode, amount = spells[source, 1:4]
    if target < 0:
        target = random_target
    if op == 0:
        if target >= 0:
            key = _hit_key(state, key, target, amount, n, count, layout, prototypes)
    elif op == 1:
        key = _kill_key(state, key, target, count, layout)
    elif op == 2:
        key = _replace(key, count+target, state[count+target] | amount, layout)
    elif op == 3:
        last = -1
        for slot in range(n, count):
            if state[slot] > 0:
                last = slot
        remaining = amount
        for slot in range(n, count):
            if state[slot] <= 0:
                continue
            share = remaining if slot == last else min(remaining, state[slot])
            key = _hit_key(state, key, slot, share, n, count, layout, prototypes)
            remaining -= share
            if not remaining:
                break
    elif op == 4:
        live = 0
        for slot in range(n):
            live += state[slot] > 0
        if live < 5:
            next_id = state[tail+6]
            while True:
                occupied = False
                for value in static_ids:
                    if value == next_id:
                        occupied = True
                for slot in range(count):
                    if state[slot] > 0 and prototypes[slot, 5] == next_id:
                        occupied = True
                for card in range(len(hand_ids)):
                    if hand & (1 << card) and hand_ids[card] == next_id:
                        occupied = True
                if not occupied:
                    break
                next_id += 1
            key = _replace(key, tail+6, next_id+1, layout)
            key = _replace(key, tail+7, 1, layout)
            key = _replace(key, token, prototypes[token, 3], layout)
            key = _replace(key, count+token, prototypes[token, 4], layout)
    return key


@njit(cache=True)
def _combat_key(state, key, kind, source, target, layout, prototypes, config):
    # AI_NOTE: Non-card actions change at most seven fields; avoid cloning and repacking every fixed slot.
    n, count = config[:2]
    tail = 2*count
    evolution = state[tail+1]
    if kind == 0:
        key = _replace(key, tail+3, state[tail+3]+1, layout)
        return _replace(key, tail+5, 1, layout)
    if kind == 3 or kind == 4:
        key = _replace(key, tail+1, 2*source+(2 if kind == 4 else 1), layout)
        return _replace(key, source, state[source]+(3 if kind == 4 else 2), layout)
    source_evolution = prototypes[source, 1]
    boost = 0
    if evolution > 0 and (evolution-1)//2 == source:
        source_evolution = 1 if evolution % 2 else 2
        boost = 2 if evolution % 2 else 3
    attack = prototypes[source, 0]+boost
    spent = state[tail] | (1 << source)
    if target < 0:
        key = _replace(key, tail, spent, layout)
        return _replace(key, tail+4, max(0, state[tail+4]-attack), layout)
    source_health, target_health = state[source], state[target]
    source_words, target_words = state[count+source], state[count+target]
    if attack > 0:
        if target_words & 1:
            target_words &= ~1
        else:
            target_health = max(0, target_health-attack)
    retaliation = prototypes[target, 0]
    if retaliation > 0 and source_evolution != 2:
        if source_words & 1:
            source_words &= ~1
        else:
            source_health = max(0, source_health-retaliation)
    if source_words & 2:
        target_health = 0
    if target_words & 2 and source_evolution != 2:
        source_health = 0
    if target_health == 0:
        target_words = 0
        if source_evolution == 2:
            key = _replace(key, tail+4, max(0, state[tail+4]-1), layout)
    if source_health == 0:
        source_words = 0
        spent &= ~(1 << source)
        if evolution > 0 and (evolution-1)//2 == source:
            key = _replace(key, tail+1, -1 if evolution % 2 else -2, layout)
    key = _replace(key, tail, spent, layout)
    key = _replace(key, source, source_health, layout)
    key = _replace(key, target, target_health, layout)
    key = _replace(key, count+source, source_words, layout)
    return _replace(key, count+target, target_words, layout)
