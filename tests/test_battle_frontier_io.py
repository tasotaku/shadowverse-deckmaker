"""Large edge tables retain ordinary JSON semantics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from svdeck.battle_frontier_io import Rows, dump_graph, json_default


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
