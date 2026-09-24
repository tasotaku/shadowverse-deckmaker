"""The accelerated writer must preserve every old candidate row and SHA byte."""
from __future__ import annotations

import hashlib
import ctypes
import json
from pathlib import Path

import numpy as np

import pytest

pytest.importorskip('numba')

from svdeck.battle import Battle
from svdeck.battle_frontier_compare import digest, kernel_key, semantic_key
from svdeck.battle_frontier_export import materialize
from svdeck.battle_frontier_fast import Kernel, _freeze
from svdeck.battle_frontier_native import enumerate_native
from svdeck.battle_frontier_export_native import CompiledStates, encode_rows
from svdeck.battle_frontier_io import States, dump_graph
from test_battle_frontier_fast import scenario


@pytest.mark.parametrize('seed', range(96))
def test_all_reachable_rows_and_hashes(seed: int) -> None:
    # AI_NOTE: Compare the new batched writer against both old kernel keys and independent full Battle keys.
    search = enumerate_native(scenario(seed), max_states=100000, seconds=60)
    assert search.complete
    candidates = list(range(len(search.keys)))
    rows, hashes = materialize(search, candidates, batch_size=7, workers=4 if seed % 2 else 1)
    kernel = search.kernel
    shapes: dict[int, str] = {}
    hands = [digest(_freeze(dict(e, keywords=sorted(e['keywords'])))) for e in kernel.hand]
    for index, (row, actual) in enumerate(zip(rows, hashes)):
        assert row == search.states[index]
        assert actual.hex() == digest(kernel_key(kernel, row, shapes, hands))
        assert actual.hex() == digest(semantic_key(Battle(kernel.state(row), kernel.battle.cards)))


def test_large_integer_rows_and_empty_candidates() -> None:
    # AI_NOTE: The signed16 optimization must fall back without truncation, including empty output and owner 1.
    battle = Battle({'active_player': 1, 'players': [{}, {'health': 100000, 'max_health': 100000,
                    'board': [{'id': 'large', 'card_id': 'f', 'health': 40000, 'max_health': 40000}]}]},
                    {'f': {'name': 'F', 'kind': 'follower', 'cost': 1, 'attack': 1, 'health': 40000}})
    search = enumerate_native(battle, max_states=100, seconds=60)
    rows, hashes = materialize(search, [0])
    assert rows[0] == search.states[0]
    assert hashes[0].hex() == digest(semantic_key(Battle(search.kernel.state(rows[0]), battle.cards)))
    empty, empty_hashes = materialize(search, [])
    assert len(empty) == 0 and empty_hashes == []
    with pytest.raises(ValueError, match='batch_size'):
        materialize(search, [0], batch_size=0)


@pytest.mark.parametrize('width', (0, 1, 5))
def test_numeric_json_roundtrip_and_mutation(tmp_path: Path, width: int) -> None:
    # AI_NOTE: Compare both writers against ordinary JSON across signed16 bounds, large fallback values and mutations.
    expected = [tuple([value]*width) for value in (-32768, 0, 32767, 10**40)]
    for cls in (States, CompiledStates):
        rows = cls(width)
        rows.data.extend(rows.key(row) for row in expected)
        for batch in (1, 3, 8192):
            assert json.loads('['+','.join(rows.json_chunks(batch))+']') == [list(row) for row in expected]
        replacement = tuple([-19]*width)
        rows.data[0] = rows.key(replacement)
        output = tmp_path/f'{cls.__name__}.json'
        dump_graph({'rows': rows, 'meta': '日本語'}, output)
        assert json.loads(output.read_text(encoding='utf-8')) == {'rows': [list(replacement), *map(list, expected[1:])], 'meta': '日本語'}
        rows.data.clear()
        dump_graph({'rows': rows}, output)
        assert json.loads(output.read_text(encoding='utf-8')) == {'rows': []}
        with pytest.raises(ValueError, match='positive'):
            list(rows.json_chunks(0))


def test_decimal_encoder_signed64_boundaries() -> None:
    # AI_NOTE: Native JSON must handle the signed64 minimum as well as zero, without overflow or precision loss.
    values = [[-(2**63), -1, 0, 1, 2**63-1], [10**18, -10**18, 10, -10, 100]]
    encoded = encode_rows(np.array(values, dtype=np.int64)).tobytes().decode('ascii')
    assert encoded == json.dumps(values, separators=(',', ':'))[1:-1]


def test_missing_crypto_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: Machines without the optional crypto symbol retain exact old output, with an explicit strict-mode error.
    from svdeck import battle_frontier_export_native as native
    search = enumerate_native(scenario(3), max_states=100000, seconds=60)
    indices = list(range(len(search.keys)))
    old = materialize(search, indices, backend='python')
    monkeypatch.setattr(native, 'sha256_provider', lambda: None)
    assert materialize(search, indices) == old
    with pytest.raises(RuntimeError, match='SHA256'):
        materialize(search, indices, backend='compiled')
    with pytest.raises(ValueError, match='backend'):
        materialize(search, indices, backend='invalid')
    for workers in (0, 65, True, 1.5):
        with pytest.raises(ValueError, match='workers'):
            materialize(search, indices, workers=workers)  # type: ignore[arg-type]


@pytest.mark.parametrize('workers,successful_calls', ((1, 0), (4, 0), (1, 2), (4, 2)))
def test_failed_crypto_call_never_exports_uninitialized_hashes(monkeypatch: pytest.MonkeyPatch,
                                                            workers: int, successful_calls: int) -> None:
    # AI_NOTE: Exercise a present but failing C symbol inside compiled code, including concurrent batches and strict mode.
    from svdeck import battle_frontier_export_native as native
    calls = 0

    def compute(source: int, length: int, target: int) -> int | None:
        # AI_NOTE: Fail after valid hashes to ensure auto fallback discards every partial compiled result.
        nonlocal calls
        calls += 1
        if calls > successful_calls:
            return None
        ctypes.memmove(target, hashlib.sha256(ctypes.string_at(source, length)).digest(), 32)
        return target

    broken = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p)(compute)
    search = enumerate_native(scenario(3), max_states=100000, seconds=60)
    indices = list(range(len(search.keys)))
    expected = materialize(search, indices, backend='python')
    monkeypatch.setattr(native, 'sha256_provider', lambda: (broken, broken))
    assert materialize(search, indices, batch_size=2, workers=workers) == expected
    with pytest.raises(native.HashUnavailable, match='SHA256'):
        materialize(search, indices, backend='compiled', batch_size=2, workers=workers)
