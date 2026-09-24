"""Compact in-memory edge tables, emitted as ordinary JSON row arrays."""
from __future__ import annotations

import json
from array import array
from collections.abc import Iterator, Sequence
from pathlib import Path
from struct import Struct, error as StructError
from typing import Any, overload


class States(Sequence[tuple[int, ...]]):
    def __init__(self, width: int) -> None:
        # AI_NOTE: 通常値の状態はsigned16のbytesへ格納する。任意の大きい整数は元のtupleへ退避する。
        self.codec = Struct('<'+'h'*width)
        self.width = width
        self.data: list[bytes | tuple[int, ...]] = []

    def key(self, row: tuple[int, ...]) -> bytes | tuple[int, ...]:
        # AI_NOTE: 値だけで一意に保存形式を決めるので、範囲外の混在でも同値状態の統合結果は変わらない。
        if len(row) != self.width:
            raise ValueError('Invalid state width')
        try:
            return self.codec.pack(*row)
        except StructError:
            return row

    def __len__(self) -> int:
        # AI_NOTE: 行数は保存形式によらず従来のnode数で返す。
        return len(self.data)

    @overload
    def __getitem__(self, index: int) -> tuple[int, ...]: ...
    @overload
    def __getitem__(self, index: slice) -> list[tuple[int, ...]]: ...

    def __getitem__(self, index: int | slice) -> tuple[int, ...] | list[tuple[int, ...]]:
        # AI_NOTE: 公開入口では整数行へ復元し、JSONとstate_atの既存形式を維持する。
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        row = self.data[index]
        return tuple(self.codec.unpack(row)) if isinstance(row, bytes) else row

    def __iter__(self) -> Iterator[tuple[int, ...]]:
        # AI_NOTE: 展開・書出しする1状態だけ復元し、全状態のtupleを同時に保持しない。
        for row in self.data:
            yield tuple(self.codec.unpack(row)) if isinstance(row, bytes) else row

    def __eq__(self, other: object) -> bool:
        # AI_NOTE: 同じ保存幅の状態列はbytes比較で、通常の行配列とは復元値で等値比較する。
        if isinstance(other, States) and self.width == other.width:
            return self.data == other.data
        if isinstance(other, Sequence):
            return len(self) == len(other) and all(a == b for a, b in zip(self, other))
        return NotImplemented

    def json_chunks(self, batch_size: int = 8192) -> Iterator[str]:
        # AI_NOTE: A typed chunk boundary permits faster numeric writers while retaining ordinary JSON and mutable rows.
        if batch_size < 1:
            raise ValueError('batch_size must be positive')
        for offset in range(0, len(self), batch_size):
            yield json.dumps(self[offset:offset+batch_size], ensure_ascii=False, separators=(',', ':'))[1:-1]


class Rows(Sequence[tuple[int, ...]]):
    def __init__(self, width: int) -> None:
        # AI_NOTE: 数千万辺をPython tupleの束で保持せず、固定幅の整数配列で保存する。
        self.width = width
        self.data = array('I')

    def append(self, row: tuple[int, ...]) -> None:
        # AI_NOTE: 行境界を固定し、通常JSONへ戻すときの列ずれを防ぐ。
        if len(row) != self.width:
            raise ValueError('Invalid row width')
        self.data.extend(row)

    def __len__(self) -> int:
        # AI_NOTE: 呼出側のnode/edge件数は整数要素数でなく行数を表す。
        return len(self.data)//self.width

    @overload
    def __getitem__(self, index: int) -> tuple[int, ...]: ...
    @overload
    def __getitem__(self, index: slice) -> list[tuple[int, ...]]: ...

    def __getitem__(self, index: int | slice) -> tuple[int, ...] | list[tuple[int, ...]]:
        # AI_NOTE: 公開APIでは従来の行配列と同じ添字・sliceで扱える。
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        offset = index*self.width
        return tuple(self.data[offset:offset+self.width])

    def __iter__(self) -> Iterator[tuple[int, ...]]:
        # AI_NOTE: 行を必要なときだけ復元し、全配列の同時コピーを避ける。
        for offset in range(0, len(self.data), self.width):
            yield tuple(self.data[offset:offset+self.width])


def json_default(value: Any) -> Any:
    # AI_NOTE: HTTPなど通常JSON encoderから共有整数表を標準の配列へ変換する。
    if isinstance(value, (Rows, States)):
        return list(value)
    raise TypeError(f'Not JSON serializable: {type(value).__name__}')


def dump_graph(result: dict[str, Any], path: Path) -> None:
    # AI_NOTE: 大きい表は小分けにC製JSON encoderへ渡し、巨大文字列と全行コピーを作らない。
    with path.open('w', encoding='utf-8') as stream:
        stream.write('{')
        for number, (key, value) in enumerate(result.items()):
            if number:
                stream.write(',')
            stream.write(json.dumps(key)+':')
            if isinstance(value, States):
                stream.write('[')
                for offset, chunk in enumerate(value.json_chunks()):
                    if offset:
                        stream.write(',')
                    stream.write(chunk)
                stream.write(']')
            elif isinstance(value, (list, Rows)):
                stream.write('[')
                for offset in range(0, len(value), 8192):
                    if offset:
                        stream.write(',')
                    stream.write(json.dumps(value[offset:offset+8192], ensure_ascii=False,
                                            separators=(',', ':'), default=json_default)[1:-1])
                stream.write(']')
            else:
                stream.write(json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=json_default))
        stream.write('}')
