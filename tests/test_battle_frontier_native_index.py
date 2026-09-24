"""Exact collisions, row identity and resize boundaries in the native visited set."""
from __future__ import annotations

import pytest

pytest.importorskip('numba')
import numpy as np

from svdeck.battle_frontier_native_index import _grow, _hash, _locate


def test_index_collisions_full_words_and_zero() -> None:
    # AI_NOTE: Force 24 distinct keys into one initial bucket, including keys differing only in the last word.
    capacity = 64
    bucket = int(_hash((np.uint64(0), np.uint64(0), np.uint64(0)))) & (capacity-1)
    rows = [(0, 0, value) for value in range(10000)
            if int(_hash((np.uint64(0), np.uint64(0), np.uint64(value)))) & (capacity-1) == bucket][:24]
    assert len(rows) == 24 and rows[0] == (0, 0, 0)
    keys = np.array(rows+[(2**64-1, 2**64-1, 2**64-1)], dtype=np.uint64)
    index = np.zeros(capacity, dtype=np.uint64)
    for row in range(len(keys)):
        key = tuple(keys[row])
        position = _locate(index, keys, key)
        assert index[position] == 0
        index[position] = (int(_hash(key)) & 0xffffffff00000000) | (row+1)
    assert np.count_nonzero(index) == len(keys)
    for row in range(len(keys)):
        assert int(index[_locate(index, keys, tuple(keys[row]))]) & 0xffffffff == row+1


def test_index_repeated_growth_preserves_rows() -> None:
    # AI_NOTE: Multiple doublings retain every exact identity and never rewrite the BFS array or witness row numbering.
    rng = np.random.default_rng(481)
    keys = rng.integers(0, np.iinfo(np.uint64).max, (10000, 3), dtype=np.uint64)
    original = keys.copy()
    index = np.zeros(8, dtype=np.uint64)
    doublings = 0
    for row in range(len(keys)):
        if (row+1)*10 > len(index)*7:
            index = _grow(index, keys, row)
            doublings += 1
        location = _locate(index, keys, tuple(keys[row]))
        assert index[location] == 0
        index[location] = (int(_hash(tuple(keys[row]))) & 0xffffffff00000000) | (row+1)
    assert doublings > 8
    assert np.array_equal(keys, original)
    assert np.count_nonzero(index) == len(keys)
    for row in range(len(keys)):
        assert int(index[_locate(index, keys, tuple(keys[row]))]) & 0xffffffff == row+1


def test_matching_fingerprint_requires_full_key() -> None:
    # AI_NOTE: Inject a same-fingerprint collision so equality must reject keys differing only in the third uint64.
    keys = np.array([(0, 0, 0), (0, 0, 2**64-1)], dtype=np.uint64)
    query = tuple(keys[1])
    hashed = int(_hash(query))
    index = np.zeros(8, dtype=np.uint64)
    slot = hashed & 7
    index[slot] = (hashed & 0xffffffff00000000) | 1
    assert _locate(index, keys, query) == (slot+1) & 7
    index[(slot+1) & 7] = (hashed & 0xffffffff00000000) | 2
    assert _locate(index, keys, query) == (slot+1) & 7
