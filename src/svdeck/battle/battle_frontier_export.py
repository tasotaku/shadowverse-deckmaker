"""Batch materialization with the existing, byte-identical semantic digest."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
from numpy.typing import NDArray

from svdeck.battle.battle_frontier_fast import Kernel, WORDS, _freeze
from svdeck.battle.battle_frontier_io import States
from svdeck.battle.battle_frontier_native import NativeSearch
from svdeck.battle.battle_frontier_skyline import _compiled, _decode, _group, _boost, _shapes


def _json(value: Any) -> bytes:
    # AI_NOTE: Match the public comparator's canonical JSON exactly, including sorted object keys.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _markers(kernel: Kernel, table: NDArray[np.int64]) -> dict[int, str]:
    # AI_NOTE: Only immutable behavior hashes are cached; IDs/stats excluded by the public endpoint remain excluded.
    result: dict[int, str] = {}
    for slot, entity in enumerate(kernel.prototypes):
        for mask in range(32):
            for evolved in range(3):
                for spent in range(2):
                    number = int(table[slot, mask, evolved, spent])
                    if number in result:
                        continue
                    traits = {k: v for k, v in entity.items()
                              if k not in ('id', 'card_id', 'name', 'attack', 'health', 'max_health')}
                    traits.update(evolved=evolved,
                                  attacks=entity['attacks'] or (spent if slot < kernel.n else 0),
                                  keywords=sorted(word for bit, word in enumerate(WORDS) if mask & (1 << bit)))
                    result[number] = hashlib.sha256(_json((kernel.behaviors[slot], _freeze(traits)))).hexdigest()
    return result


@_compiled
def _project(keys: NDArray[np.uint64], indices: NDArray[np.int64], layout: NDArray[np.int64],
             table: NDArray[np.int64], prototypes: NDArray[np.int64], n: int, bits: int,
             own_health: int, ep: int, sep: int) -> tuple[NDArray[np.int64], NDArray[np.uint64],
                                                       NDArray[np.int64], NDArray[np.int64]]:
    # AI_NOTE: Decode each candidate once in compiled code and emit only the variable numeric part of its endpoint.
    count = len(prototypes)
    states = np.empty((len(indices), len(layout)), dtype=np.int64)
    groups = np.empty((len(indices), 3), dtype=np.uint64)
    values = np.empty((len(indices), 5+3*count), dtype=np.int64)
    lengths = np.empty(len(indices), dtype=np.int64)
    for row in range(len(indices)):
        state = _decode(keys[indices[row]], layout)
        states[row] = state
        groups[row] = _group(state, table, prototypes, n, bits)
        evolution = state[2*count+1]
        values[row, 0] = own_health
        values[row, 1] = -state[2*count+4]
        values[row, 2] = state[2*count+3]
        values[row, 3] = ep-int(evolution == -1 or evolution > 0 and evolution % 2 == 1)
        values[row, 4] = sep-int(evolution == -2 or evolution > 0 and evolution % 2 == 0)
        length = 5
        for slot in range(count):
            if state[slot] <= 0:
                continue
            sign = 1 if slot < n else -1
            boost = _boost(slot, evolution)
            values[row, length] = sign*(prototypes[slot, 0]+boost)
            values[row, length+1] = sign*state[slot]
            values[row, length+2] = sign*(prototypes[slot, 1]+boost)
            length += 3
        lengths[row] = length
    return states, groups, values, lengths


def _native_batches(search: NativeSearch, candidates: list[int], batch_size: int, workers: int,
                    arguments: tuple[Any, ...]) -> Iterator[tuple[NDArray[np.int64], NDArray[np.uint8]]]:
    # AI_NOTE: Keep at most workers batches in flight and consume in original order; each SHA buffer is thread-local.
    from svdeck.battle.battle_frontier_export_native import project_and_hash
    if workers == 1:
        for start in range(0, len(candidates), batch_size):
            yield project_and_hash(search.keys, np.asarray(candidates[start:start+batch_size], dtype=np.int64),
                                   *arguments)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for window in range(0, len(candidates), batch_size*workers):
                pending = [pool.submit(project_and_hash, search.keys,
                                       np.asarray(candidates[start:start+batch_size], dtype=np.int64), *arguments)
                           for start in range(window, min(window+batch_size*workers, len(candidates)), batch_size)]
                for future in pending:
                    yield future.result()


def materialize(search: NativeSearch, candidates: list[int], *, batch_size: int = 8192,
                backend: str = 'auto', workers: int | None = None) -> tuple[States, list[bytes]]:
    # AI_NOTE: Keep the old JSON rows and SHA256 contract while avoiding per-row Python state/endpoint construction.
    if batch_size < 1:
        raise ValueError('batch_size must be positive')
    if backend not in ('auto', 'python', 'compiled'):
        raise ValueError('unsupported export backend')
    if workers is not None and (isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 64):
        raise ValueError('workers must be an integer between 1 and 64')
    if workers is None:
        workers = min(4, os.cpu_count() or 1) if len(candidates) >= 131072 else 1
    kernel = search.kernel
    rows: States
    hashes: list[bytes]
    table, prototypes, bits = _shapes(kernel)
    markers = _markers(kernel, table)
    hands = [hashlib.sha256(_json(_freeze(dict(e, keywords=sorted(e['keywords']))))).hexdigest()
             for e in kernel.hand]
    hand_json = [_json(sorted(value for bit, value in enumerate(hands) if mask & (1 << bit)))
                 for mask in range(1 << len(hands))]
    if backend != 'python':
        from svdeck.battle.battle_frontier_export_native import sha256_provider, CompiledStates, HashUnavailable
        provider = sha256_provider()
        if provider is not None:
            marker_bytes = np.zeros((len(markers)+1, 64), dtype=np.uint8)
            for number, marker in markers.items():
                marker_bytes[number] = np.frombuffer(marker.encode('ascii'), dtype=np.uint8)
            hand_bytes = np.zeros((len(hand_json), max(map(len, hand_json))), dtype=np.uint8)
            lengths = np.array([len(value) for value in hand_json], dtype=np.int64)
            for number, value in enumerate(hand_json):
                hand_bytes[number, :len(value)] = np.frombuffer(value, dtype=np.uint8)
            rows, hashes = CompiledStates(len(kernel.initial)), []
            arguments = (search.layout, table, prototypes, kernel.n, kernel.owner, kernel.own['health'],
                         kernel.own['ep'], kernel.own['sep'], marker_bytes, hand_bytes, lengths, provider[1])
            try:
                for decoded, hashed in _native_batches(search, candidates, batch_size, workers, arguments):
                    if decoded.size and decoded.min() >= -32768 and decoded.max() <= 32767:
                        rows.data.extend(decoded.astype('<i2').view(f'V{rows.width*2}').ravel().tolist())
                    else:
                        rows.data.extend(rows.key(tuple(row)) for row in decoded.tolist())
                    hashes.extend(hashed.view('V32').ravel().tolist())
            except HashUnavailable:
                if backend == 'compiled':
                    raise
                # AI_NOTE: Discard the entire partial batch result and redo exact hashes through the previous Python path.
            else:
                return rows, hashes
        if backend == 'compiled':
            raise RuntimeError('no compatible SHA256 library available')
    boards: dict[int, bytes] = {0: b'[]'}
    rows = States(len(kernel.initial))
    hashes = []
    winner_json = (b'null}', str(kernel.owner).encode('ascii')+b'}')
    mask = (1 << bits)-1
    for start in range(0, len(candidates), batch_size):
        decoded, groups, values, lengths = _project(
            search.keys, np.asarray(candidates[start:start+batch_size], dtype=np.int64), search.layout,
            table, prototypes, kernel.n, bits, kernel.own['health'], kernel.own['ep'], kernel.own['sep'])
        if decoded.size and decoded.min() >= -32768 and decoded.max() <= 32767:
            rows.data.extend(decoded.astype('<i2').view(f'V{rows.width*2}').ravel().tolist())
        else:
            rows.data.extend(rows.key(tuple(row)) for row in decoded.tolist())
        numeric = values.tolist()
        remaining = decoded[:, kernel.tail+2].tolist()
        for row, ((own, enemy, winner), length, hand) in enumerate(zip(groups.tolist(), lengths.tolist(), remaining)):
            for board in (own, enemy):
                if board not in boards:
                    current, ordered = board, []
                    while current:
                        ordered.append(markers[current & mask])
                        current >>= bits
                    boards[board] = _json(ordered[::-1])
            encoded = (b'{"boards":['+boards[own]+b','+boards[enemy]+b'],"hand":'+hand_json[hand]
                       +b',"values":'+_json(numeric[row][:length])+b',"winner":'+winner_json[winner])
            hashes.append(hashlib.sha256(encoded).digest())
    return rows, hashes
