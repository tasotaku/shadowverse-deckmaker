"""Collision-exact numeric index into the packed BFS state array."""
# mypy: ignore-errors
from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True, inline='always')
def _hash(key):
    # AI_NOTE: Hashing selects a probe sequence only; equality always compares all 192 state bits.
    value = key[0] ^ (key[1]*np.uint64(0x9E3779B185EBCA87)) ^ (key[2]*np.uint64(0xC2B2AE3D27D4EB4F))
    value ^= value >> np.uint64(30)
    value *= np.uint64(0xBF58476D1CE4E5B9)
    value ^= value >> np.uint64(27)
    value *= np.uint64(0x94D049BB133111EB)
    return value ^ (value >> np.uint64(31))


@njit(cache=True, inline='always')
def _locate(index, keys, key):
    # AI_NOTE: Zero denotes empty; positive int32 entries reference existing BFS rows plus one.
    mask = np.uint64(len(index)-1)
    hashed = _hash(key)
    stamp = hashed & np.uint64(0xffffffff00000000)
    slot = hashed & mask
    while index[slot]:
        if index[slot] & np.uint64(0xffffffff00000000) == stamp:
            row = np.int64(index[slot] & np.uint64(0xffffffff))-1
            if keys[row, 0] == key[0] and keys[row, 1] == key[1] and keys[row, 2] == key[2]:
                return slot
        slot = (slot+np.uint64(1)) & mask
    return slot


@njit(cache=True)
def _grow(index, keys, size):
    # AI_NOTE: Rehash row references in BFS order without duplicating state words or changing witnesses.
    grown = np.zeros(len(index)*2, dtype=np.uint64)
    for row in range(size):
        key = (keys[row, 0], keys[row, 1], keys[row, 2])
        grown[_locate(grown, keys, key)] = (_hash(key) & np.uint64(0xffffffff00000000)) | np.uint64(row+1)
    return grown
