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
def _dominates(a: NDArray[np.int64], b: NDArray[np.int64], prototypes: NDArray[np.int64], n: int) -> bool:
    # AI_NOTE: 同じ形状内で全スタッツ・PP・進化資源・手札包含を比較し、大小不明の組を落とさない。
    count = len(prototypes)
    tail = 2*count
    ae, be = a[tail+1], b[tail+1]
    if a[tail+2] & b[tail+2] != b[tail+2] or a[tail+3] < b[tail+3] or a[tail+4] > b[tail+4]:
        return False
    aep, bep = ae == -1 or ae > 0 and ae % 2 == 1, be == -1 or be > 0 and be % 2 == 1
    asp, bsp = ae == -2 or ae > 0 and ae % 2 == 0, be == -2 or be > 0 and be % 2 == 0
    if aep > bep or asp > bsp:
        return False
    for side in range(2):
        start, end, sign = (0, n, 1) if side == 0 else (n, count, -1)
        ai, bi = start, start
        while ai < end:
            if a[ai] <= 0:
                ai += 1
                continue
            while bi < end and b[bi] <= 0:
                bi += 1
            if bi == end:
                return False
            ab, bb = _boost(ai, ae), _boost(bi, be)
            if sign == 1:
                if (a[ai] < b[bi] or prototypes[ai, 0]+ab < prototypes[bi, 0]+bb
                        or prototypes[ai, 1]+ab < prototypes[bi, 1]+bb):
                    return False
            elif (a[ai] > b[bi] or prototypes[ai, 0]+ab > prototypes[bi, 0]+bb
                  or prototypes[ai, 1]+ab > prototypes[bi, 1]+bb):
                return False
            ai += 1
            bi += 1
    return True


@_compiled
def _batch(keys: NDArray[np.uint64], layout: NDArray[np.int64], table: NDArray[np.int64],
           prototypes: NDArray[np.int64], n: int, bits: int, heads: Any,
           following: NDArray[np.int32], kept: NDArray[np.uint8], start: int, end: int) -> None:
    # AI_NOTE: shapeごとの連結skylineで新旧双方の支配を判定する。等価なら最初の代表を残す。
    for index in range(start, end):
        state = _decode(keys[index], layout)
        group = _group(state, table, prototypes, n, bits)
        head = heads[group] if group in heads else -1
        current = head
        rejected = False
        while current >= 0:
            if _dominates(_decode(keys[current], layout), state, prototypes, n):
                rejected = True
                break
            current = following[current]
        if rejected:
            continue
        current, previous = head, -1
        while current >= 0:
            nxt = following[current]
            if _dominates(state, _decode(keys[current], layout), prototypes, n):
                kept[current] = 0
                if previous < 0:
                    head = nxt
                else:
                    following[previous] = nxt
            else:
                previous = current
            current = nxt
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
    for start in range(0, len(keys), batch_size):
        if perf_counter() >= deadline:
            return list(range(len(keys))), False
        _batch(keys, layout, table, prototypes, kernel.n, bits, heads, following, kept,
               start, min(start+batch_size, len(keys)))
    if perf_counter() >= deadline:
        return list(range(len(keys))), False
    return np.flatnonzero(kept).tolist(), True
