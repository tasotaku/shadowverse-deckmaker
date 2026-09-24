"""Exact compiled endpoint skyline; never removes states from the search graph.

The optional performance extra supplies NumPy/Numba. Integer board-shape keys
preserve order, abilities, attack rights, and card behavior exactly.
"""
from __future__ import annotations

from time import perf_counter
from typing import Any, Callable, TypeVar, cast

import numpy as np
from numpy.typing import NDArray
from numba import njit, types
from numba.typed import Dict

from .battle_frontier_fast import Kernel, WORDS, _freeze
from .battle_frontier_packed import _byte_vectors

F = TypeVar('F', bound=Callable[..., Any])


def _compiled(function: F) -> F:
    # AI_NOTE: 任意の並べ替えや近似を導入せず、同じ整数比較を機械語化する。
    return cast(F, njit(cache=True)(function))


@_compiled
def _decode(key: NDArray[np.uint64], layout: NDArray[np.int64]) -> NDArray[np.int64]:
    # AI_NOTE: 各fieldは64bit境界を跨がない。進化の負値は保存時のbiasを引いて戻す。
    state = np.empty(len(layout), dtype=np.int64)
    for i in range(len(layout)):
        word, shift, mask, bias = layout[i]
        state[i] = np.int64((key[word] >> np.uint64(shift)) & np.uint64(mask))-bias
    return state


def _shapes(kernel: Kernel) -> tuple[NDArray[np.int64], NDArray[np.int64], int]:
    # AI_NOTE: カード名や個体IDだけを無視し、既存endpointと同じ全traitsを整数IDに写す。
    table = np.empty((kernel.count, 32, 3, 2), dtype=np.int64)
    prototypes = np.empty((kernel.count, 3), dtype=np.int64)
    markers: dict[Any, int] = {}
    for slot, entity in enumerate(kernel.prototypes):
        prototypes[slot] = (entity['attack'], entity['max_health'], entity['evolved'])
        for mask in range(32):
            for evolved in range(3):
                for spent in range(2):
                    traits = {k: v for k, v in entity.items()
                              if k not in ('id', 'card_id', 'name', 'attack', 'health', 'max_health')}
                    traits.update(evolved=evolved, attacks=entity['attacks'] or (spent if slot < kernel.n else 0),
                                  keywords=sorted(word for bit, word in enumerate(WORDS) if mask & (1 << bit)))
                    marker = kernel.behaviors[slot], _freeze(traits)
                    table[slot, mask, evolved, spent] = markers.setdefault(marker, len(markers)+1)
    bits = max(1, len(markers).bit_length())
    if bits*5 > 64:
        raise ValueError('Board shape exceeds exact 64-bit encoding')
    return table, prototypes, bits


@_compiled
def _boost(slot: int, evolution: int) -> int:
    # AI_NOTE: 元から進化済みの個体には加算せず、今回進化した個体だけを強化する。
    return (2 if evolution % 2 else 3) if evolution > 0 and (evolution-1)//2 == slot else 0


@_compiled
def _group(state: NDArray[np.int64], table: NDArray[np.int64], prototypes: NDArray[np.int64],
           n: int, bits: int) -> tuple[np.uint64, np.uint64, np.uint64]:
    # AI_NOTE: 生存個体の順番を保った非ゼロID列で、異なる盤面形状を衝突なく区別する。
    count = len(prototypes)
    spent, evolution = state[2*count], state[2*count+1]
    own, enemy = np.uint64(0), np.uint64(0)
    for slot in range(count):
        if state[slot] <= 0:
            continue
        evolved = prototypes[slot, 2]
        if evolution > 0 and (evolution-1)//2 == slot:
            evolved = 1 if evolution % 2 else 2
        shape = np.uint64(table[slot, state[count+slot], evolved, int(bool(spent & (1 << slot)))])
        if slot < n:
            own = (own << np.uint64(bits)) | shape
        else:
            enemy = (enemy << np.uint64(bits)) | shape
    return own, enemy, np.uint64(state[2*count+4] <= 0)


@_compiled
def _decode_into(key: NDArray[np.uint64], layout: NDArray[np.int64], state: NDArray[np.int64]) -> None:
    # AI_NOTE: Reuse two buffers per batch instead of allocating an array for every skyline comparison.
    for i in range(len(layout)):
        word, shift, mask, bias = layout[i]
        state[i] = np.int64((key[word] >> np.uint64(shift)) & np.uint64(mask))-bias


@_compiled
def _relation(a: NDArray[np.int64], b: NDArray[np.int64], prototypes: NDArray[np.int64], n: int) -> int:
    # AI_NOTE: Compare both directions once; equality keeps existing a, while incomparable states return zero.
    count = len(prototypes)
    tail = 2*count
    ae, be = a[tail+1], b[tail+1]
    ad = a[tail+2] & b[tail+2] == b[tail+2] and a[tail+3] >= b[tail+3] and a[tail+4] <= b[tail+4]
    bd = b[tail+2] & a[tail+2] == a[tail+2] and b[tail+3] >= a[tail+3] and b[tail+4] <= a[tail+4]
    aep, bep = ae == -1 or ae > 0 and ae % 2 == 1, be == -1 or be > 0 and be % 2 == 1
    asp, bsp = ae == -2 or ae > 0 and ae % 2 == 0, be == -2 or be > 0 and be % 2 == 0
    ad = ad and aep <= bep and asp <= bsp
    bd = bd and bep <= aep and bsp <= asp
    if not ad and not bd:
        return 0
    for side in range(2):
        start, end = (0, n) if side == 0 else (n, count)
        ai, bi = start, start
        while ai < end:
            if a[ai] <= 0:
                ai += 1
                continue
            while bi < end and b[bi] <= 0:
                bi += 1
            if bi == end:
                return 0
            ab, bb = _boost(ai, ae), _boost(bi, be)
            age = (a[ai] >= b[bi] and prototypes[ai, 0]+ab >= prototypes[bi, 0]+bb
                   and prototypes[ai, 1]+ab >= prototypes[bi, 1]+bb)
            bge = (b[bi] >= a[ai] and prototypes[bi, 0]+bb >= prototypes[ai, 0]+ab
                   and prototypes[bi, 1]+bb >= prototypes[ai, 1]+ab)
            ad = ad and (age if side == 0 else bge)
            bd = bd and (bge if side == 0 else age)
            if not ad and not bd:
                return 0
            ai += 1
            bi += 1
    return -1 if ad else (1 if bd else 0)


@_compiled
def _batch(keys: NDArray[np.uint64], layout: NDArray[np.int64], table: NDArray[np.int64],
           prototypes: NDArray[np.int64], n: int, bits: int, heads: Any,
           following: NDArray[np.int32], kept: NDArray[np.uint8], start: int, end: int) -> None:
    # AI_NOTE: An existing skyline is an antichain: dominating one old row precludes rejection by another.
    state = np.empty(len(layout), dtype=np.int64)
    prior = np.empty(len(layout), dtype=np.int64)
    for index in range(start, end):
        _decode_into(keys[index], layout, state)
        group = _group(state, table, prototypes, n, bits)
        head = heads.get(group, -1)+0
        current, previous = head, -1
        rejected = False
        while current >= 0:
            nxt = following[current]
            _decode_into(keys[current], layout, prior)
            relation = _relation(prior, state, prototypes, n)
            if relation < 0:
                rejected = True
                break
            if relation > 0:
                kept[current] = 0
                if previous < 0:
                    head = nxt
                else:
                    following[previous] = nxt
            else:
                previous = current
            current = nxt
        if not rejected:
            following[index] = head
            kept[index] = 1
            heads[group] = index


@_compiled
def _lane(vector: NDArray[np.uint64], offset: int, value: int) -> None:
    # AI_NOTE: Eight value bits plus one guard bit make subtraction compare seven independent lanes exactly.
    vector[offset//7] |= np.uint64(value) << np.uint64((offset % 7)*9)


@_compiled
def _features(state: NDArray[np.int64], prototypes: NDArray[np.int64], n: int,
              vector: NDArray[np.uint64]) -> None:
    # AI_NOTE: The range proof is shared with the reference byte-vector path; larger values use scalar comparison.
    vector[:] = 0
    count = len(prototypes)
    tail = 2*count
    evolution = state[tail+1]
    _lane(vector, 0, state[tail+3])
    _lane(vector, 1, 128-state[tail+4])
    _lane(vector, 2, int(not (evolution == -1 or evolution > 0 and evolution % 2 == 1)))
    _lane(vector, 3, int(not (evolution == -2 or evolution > 0 and evolution % 2 == 0)))
    offset = 4
    for slot in range(count):
        if state[slot] <= 0:
            continue
        boost = _boost(slot, evolution)
        health, attack, maximum = state[slot], prototypes[slot, 0]+boost, prototypes[slot, 1]+boost
        if slot >= n:
            health, attack, maximum = 128-health, 128-attack, 128-maximum
        _lane(vector, offset, health)
        _lane(vector, offset+1, attack)
        _lane(vector, offset+2, maximum)
        offset += 3
    vector[-1] = np.uint64(state[tail+2])


@_compiled
def _packed_relation(a: NDArray[np.uint64], b: NDArray[np.uint64]) -> int:
    # AI_NOTE: Guard bits prevent inter-lane borrowing, so each word tests seven component inequalities at once.
    guard = np.uint64(0x4020100804020100)
    ad, bd = a[-1] & b[-1] == b[-1], b[-1] & a[-1] == a[-1]
    for word in range(len(a)-1):
        ad = ad and ((a[word] | guard)-b[word]) & guard == guard
        bd = bd and ((b[word] | guard)-a[word]) & guard == guard
        if not ad and not bd:
            return 0
    return -1 if ad else (1 if bd else 0)


@_compiled
def _packed_batch(keys: NDArray[np.uint64], layout: NDArray[np.int64], table: NDArray[np.int64],
                  prototypes: NDArray[np.int64], n: int, bits: int, heads: Any,
                  following: NDArray[np.int32], kept: NDArray[np.uint8], features: NDArray[np.uint64],
                  start: int, end: int) -> None:
    # AI_NOTE: Cache numeric comparison vectors only; exact group keys still protect behavior, traits and board order.
    state = np.empty(len(layout), dtype=np.int64)
    vector = np.empty(features.shape[1], dtype=np.uint64)
    for index in range(start, end):
        _decode_into(keys[index], layout, state)
        group = _group(state, table, prototypes, n, bits)
        head = heads.get(group, -1)+0
        current, previous = head, -1
        rejected = False
        _features(state, prototypes, n, vector)
        while current >= 0:
            nxt = following[current]
            relation = _packed_relation(features[current], vector)
            if relation < 0:
                rejected = True
                break
            if relation > 0:
                kept[current] = 0
                if previous < 0:
                    head = nxt
                else:
                    following[previous] = nxt
            else:
                previous = current
            current = nxt
        if not rejected:
            features[index] = vector
            following[index] = head
            kept[index] = 1
            heads[group] = index


def frontier(kernel: Kernel, keys: NDArray[np.uint64], layout: NDArray[np.int64], deadline: float,
             *, batch_size: int = 32768) -> tuple[list[int], bool]:
    # AI_NOTE: 探索と独立に全停止状態の候補を整理する。期限超過なら候補未整理を明示し全状態を返す。
    if batch_size < 1:
        raise ValueError('batch_size must be positive')
    if len(keys) >= 2**31:
        raise ValueError('Too many states for exact skyline links')
    if len(keys) and (kernel.n > 6 or kernel.count-kernel.n > 5):
        raise ValueError('Board exceeds supported fixed slots')
    table, prototypes, bits = _shapes(kernel)
    heads = Dict.empty(key_type=types.UniTuple(types.uint64, 3), value_type=types.int64)  # type: ignore[no-untyped-call]
    following = np.full(len(keys), -1, dtype=np.int32)
    kept = np.zeros(len(keys), dtype=np.uint8)
    compact = _byte_vectors(kernel)
    features = np.empty((len(keys) if compact else 0, (3*kernel.count+10)//7+1), dtype=np.uint64)
    for start in range(0, len(keys), batch_size):
        if perf_counter() >= deadline:
            return list(range(len(keys))), False
        if compact:
            _packed_batch(keys, layout, table, prototypes, kernel.n, bits, heads, following, kept, features,
                          start, min(start+batch_size, len(keys)))
        else:
            _batch(keys, layout, table, prototypes, kernel.n, bits, heads, following, kept,
                   start, min(start+batch_size, len(keys)))
    if perf_counter() >= deadline:
        return list(range(len(keys))), False
    return np.flatnonzero(kept).tolist(), True
