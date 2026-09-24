"""Exact sparse packed changes for attacks, evolution and the extra PP action."""
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
