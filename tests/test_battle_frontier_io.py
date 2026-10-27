"""Large edge tables retain ordinary JSON semantics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from svdeck.battle_env.battle_frontier_io import Rows, States, dump_graph, json_default


def test_chunked_graph_roundtrip(tmp_path: Path) -> None:
    # AI_NOTE: chunk境界の前後・空配列・Unicode・通常JSON encoderの全てで列と値を保つ。
    rows = Rows(3)
    expected = [(index, index+1, index % 5) for index in range(8200)]
    for row in expected:
        rows.append(row)
    assert rows[8190:8195] == expected[8190:8195]
    assert rows[-1] == expected[-1]
    result = {'outcomes': rows, 'empty': [], 'positions': expected, '説明': {'能力': 'バリア'}}
    path = tmp_path/'graph.json'
    dump_graph(result, path)
    decoded = json.loads(path.read_text(encoding='utf-8'))
    assert decoded == json.loads(json.dumps(result, default=json_default))
    assert decoded['outcomes'] == [list(row) for row in expected]
    assert len(rows.data)*rows.data.itemsize == 8200*3*4


def test_rows_invalid_access() -> None:
    # AI_NOTE: 不正な行は黙って切り詰めず拒否し、範囲外を空行として返さない。
    rows = Rows(3)
    with pytest.raises(ValueError):
        rows.append((1, 2))
    with pytest.raises(IndexError):
        _ = rows[0]
    with pytest.raises(TypeError):
        json_default(object())


def test_state_storage_mixed_width_roundtrip(tmp_path: Path) -> None:
    # AI_NOTE: signed16境界と任意精度整数を同じ表に混ぜても、キー・JSON・行比較が元の値へ一致する。
    expected = [(-32768, 32767, 0), (-32769, 32768, 10**100), (1, -2, 3)] * 2734
    states = States(3)
    states.data.extend(states.key(row) for row in expected)
    assert isinstance(states.data[0], bytes)
    assert isinstance(states.data[1], tuple)
    assert states == expected
    assert states[-1] == expected[-1]
    assert states[8190:8200] == expected[8190:8200]
    assert len(set(states.data)) == len(set(expected))
    assert len(states.data[0]) == 6
    path = tmp_path/'states.json'
    dump_graph({'positions': states}, path)
    decoded = json.loads(path.read_text(encoding='utf-8'))
    assert decoded['positions'] == [list(row) for row in expected]
    assert decoded == json.loads(json.dumps({'positions': states}, default=json_default))
    with pytest.raises(ValueError):
        states.key((1, 2))
    with pytest.raises(IndexError):
        _ = states[len(states)]
