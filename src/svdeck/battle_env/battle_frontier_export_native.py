"""Exact ASCII candidate hashing through the existing system SHA256 implementation."""
from __future__ import annotations

import ctypes
import ctypes.util
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
import sys
from typing import Any

import numpy as np
from numpy.typing import NDArray
from numba import njit

from svdeck.battle_env.battle_frontier_skyline import _compiled, _decode_into, _boost
from svdeck.battle_env.battle_frontier_io import States

BOARDS = np.frombuffer(b'{"boards":[', dtype=np.uint8)
HAND = np.frombuffer(b'],"hand":', dtype=np.uint8)
VALUES = np.frombuffer(b',"values":[', dtype=np.uint8)
WINNER = np.frombuffer(b'],"winner":', dtype=np.uint8)
NULL = np.frombuffer(b'null', dtype=np.uint8)


class HashUnavailable(RuntimeError):
    """A present crypto symbol failed to produce a digest."""


@lru_cache(maxsize=1)
def sha256_provider() -> tuple[Any, Any] | None:
    # AI_NOTE: Check a known vector: a present OpenSSL symbol may still fail when its provider disables SHA256.
    paths = [str(Path(sys.base_prefix)/'DLLs/libcrypto-3.dll')]
    found = ctypes.util.find_library('crypto')
    if found:
        paths.append(found)
    for path in paths:
        try:
            library = ctypes.CDLL(path)
            function = library.SHA256
        except (OSError, AttributeError):
            continue
        function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
        function.restype = ctypes.c_void_p
        sample, digest = ctypes.create_string_buffer(b'abc'), ctypes.create_string_buffer(32)
        if not function(sample, 3, digest) or digest.raw != bytes.fromhex(
                'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'):
            continue
        return library, function
    return None


@njit(cache=True, inline='always')
def _append(buffer: NDArray[np.uint8], offset: int, text: NDArray[np.uint8]) -> int:
    # AI_NOTE: Only canonical ASCII fragments enter the numeric fast path, so copying bytes needs no escaping rules.
    for value in text:
        buffer[offset] = value
        offset += 1
    return offset


@njit(cache=True, inline='always')
def _integer(buffer: NDArray[np.uint8], offset: int, value: int) -> int:
    # AI_NOTE: Form unsigned magnitude without negating INT64_MIN, preserving the entire signed64 decimal domain.
    if value < 0:
        buffer[offset] = 45
        offset += 1
        magnitude = np.uint64(-(value+1))+np.uint64(1)
    else:
        magnitude = np.uint64(value)
    start = offset
    while True:
        buffer[offset] = np.uint64(48)+magnitude % np.uint64(10)
        offset += 1
        magnitude //= np.uint64(10)
        if magnitude == 0:
            break
    left, right = start, offset-1
    while left < right:
        buffer[left], buffer[right] = buffer[right], buffer[left]
        left += 1
        right -= 1
    return offset


@njit(cache=True, nogil=True)
def project_and_hash(keys: NDArray[np.uint64], indices: NDArray[np.int64], layout: NDArray[np.int64],
                     table: NDArray[np.int64], prototypes: NDArray[np.int64], n: int,
                     owner: int, own_health: int, ep: int, sep: int,
                     markers: NDArray[np.uint8], hands: NDArray[np.uint8], hand_lengths: NDArray[np.int64],
                     function: Any) -> tuple[NDArray[np.int64], NDArray[np.uint8]]:
    # AI_NOTE: Assemble exactly the existing sorted-key JSON and call SHA256 with a runtime pointer, safe across JIT caches.
    count = len(prototypes)
    tail = 2*count
    states = np.empty((len(indices), len(layout)), dtype=np.int64)
    hashes = np.empty((len(indices), 32), dtype=np.uint8)
    address = np.empty(1, dtype=np.uintp)
    buffer = np.empty(192+67*count+hands.shape[1]+21*(5+3*count), dtype=np.uint8)
    for row in range(len(indices)):
        state = states[row]
        _decode_into(keys[indices[row]], layout, state)
        spent, evolution, hand, pp, health = state[tail:tail+5]
        offset = _append(buffer, 0, BOARDS)
        for side in range(2):
            if side:
                buffer[offset] = 44
                offset += 1
            buffer[offset] = 91
            offset += 1
            start, stop = (0, n) if side == 0 else (n, count)
            first = True
            for slot in range(start, stop):
                if state[slot] <= 0:
                    continue
                if not first:
                    buffer[offset] = 44
                    offset += 1
                first = False
                evolved = prototypes[slot, 2]
                if evolution > 0 and (evolution-1)//2 == slot:
                    evolved = 1 if evolution % 2 else 2
                number = table[slot, state[count+slot], evolved, int(bool(spent & (1 << slot)))]
                buffer[offset] = 34
                offset = _append(buffer, offset+1, markers[number])
                buffer[offset] = 34
                offset += 1
            buffer[offset] = 93
            offset += 1
        offset = _append(buffer, offset, HAND)
        offset = _append(buffer, offset, hands[hand, :hand_lengths[hand]])
        offset = _append(buffer, offset, VALUES)
        offset = _integer(buffer, offset, own_health)
        for value in (-health, pp, ep-int(evolution == -1 or evolution > 0 and evolution % 2 == 1),
                      sep-int(evolution == -2 or evolution > 0 and evolution % 2 == 0)):
            buffer[offset] = 44
            offset = _integer(buffer, offset+1, value)
        for slot in range(count):
            if state[slot] <= 0:
                continue
            sign = 1 if slot < n else -1
            boost = _boost(slot, evolution)
            for value in (prototypes[slot, 0]+boost, state[slot], prototypes[slot, 1]+boost):
                buffer[offset] = 44
                offset = _integer(buffer, offset+1, sign*value)
        offset = _append(buffer, offset, WINNER)
        if health <= 0:
            offset = _integer(buffer, offset, owner)
        else:
            offset = _append(buffer, offset, NULL)
        buffer[offset] = 125
        address[0] = function(buffer.ctypes, offset+1, hashes[row].ctypes)
        if address[0] == 0:
            raise HashUnavailable('SHA256 calculation failed')
    return states, hashes


@_compiled
def encode_rows(rows: NDArray[Any]) -> NDArray[np.uint8]:
    # AI_NOTE: Numeric candidate rows need only decimal integers and array punctuation, with a checked 21-byte bound.
    output = np.empty(len(rows)*(3+rows.shape[1]*21), dtype=np.uint8)
    offset = 0
    for index in range(len(rows)):
        if index:
            output[offset] = 44
            offset += 1
        output[offset] = 91
        offset += 1
        for field in range(rows.shape[1]):
            if field:
                output[offset] = 44
                offset += 1
            offset = _integer(output, offset, int(rows[index, field]))
        output[offset] = 93
        offset += 1
    return output[:offset]


class CompiledStates(States):
    def json_chunks(self, batch_size: int = 8192) -> Iterator[str]:
        # AI_NOTE: Convert current row storage at write time, so edits to data never leave stale cached JSON behind.
        if batch_size < 1:
            raise ValueError('batch_size must be positive')
        for offset in range(0, len(self), batch_size):
            chunk = self.data[offset:offset+batch_size]
            if all(isinstance(row, bytes) for row in chunk):
                raw = b''.join(chunk)  # type: ignore[arg-type]
                decoded = np.frombuffer(raw, dtype='<i2').reshape((len(chunk), self.width))
                yield encode_rows(decoded).tobytes().decode('ascii')
            else:
                # AI_NOTE: Arbitrarily large Python tuples keep the existing general JSON path without truncation.
                import json
                yield json.dumps(self[offset:offset+batch_size], ensure_ascii=False, separators=(',', ':'))[1:-1]
