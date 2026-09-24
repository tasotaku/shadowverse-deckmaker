"""Optional compiled, exact current-turn enumeration without storing graph edges.

Every reachable state and one legal witness is stored. Legal decisions and their
complete conditional chance branches can be reconstructed with Kernel at any
node; the representation therefore does not confuse chance with player choice.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from math import isfinite
from time import perf_counter
from typing import Callable, overload

import numpy as np
from numpy.typing import NDArray

from .battle import Battle, Json
from .battle_frontier_fast import Kernel, State, _mask, eligible
from .battle_frontier_native_core import _batch, _pack, _unpack
from .battle_frontier_native_index import _locate

UInts = NDArray[np.uint64]
Ints = NDArray[np.int64]


def _numeric_id(value: str) -> int:
    # AI_NOTE: Only canonical eN IDs collide with Battle.fresh; e01 and arbitrary IDs do not.
    number = value[1:]
    if not value.startswith('e') or len(number) > 19 or not number.isdecimal():
        return -1
    parsed = int(number)
    return parsed if parsed < 2**60 and str(parsed) == number else -1


def prepare(kernel: Kernel) -> tuple[Ints, Ints, Ints, Ints, Ints, Ints]:
    # AI_NOTE: Prove bounded 192-bit storage before JIT, rejecting oversized/unsupported states without truncation.
    if kernel.n > 6 or kernel.count-kernel.n > 5 or len(kernel.hand) > 10:
        raise ValueError('native fixed-slot dimensions are unsupported')
    prototype_values = [[e['attack'], e['evolved'], e['entered_turn'], e['health'],
                         _mask(e['keywords']), _numeric_id(e['id'])]
                        for e in kernel.prototypes]
    operations = {'damage': 0, 'destroy': 1, 'grant': 2, 'split_damage': 3, 'summon': 4}
    modes = {'self': 0, 'chosen_enemy': 1, 'chosen_ally': 2, 'random_enemy': 3}
    spell_values = [[cost, operations[e['op']], modes[e.get('target', 'self')],
                     _mask(e.get('keywords', [])) if e['op'] == 'grant' else e.get('amount', 0)]
                    for cost, e in kernel.spells]
    if (any(cost < 0 for cost, _ in kernel.spells)
            or any(e['attack'] < 0 or e['health'] <= 0 for e in kernel.prototypes)):
        raise ValueError('native bounds require nonnegative costs and attacks')
    config_values = [kernel.n, kernel.count, kernel.token, kernel.owner, kernel.own['turn'],
                     kernel.own['ep'], kernel.own['sep'], int(kernel.own['evolved_this_turn'])]
    upper = [e['health']+3 for e in kernel.prototypes]+[31]*kernel.count
    upper += [(1 << kernel.n)-1, 2*kernel.n+2, (1 << len(kernel.hand))-1, kernel.own['pp']+1,
              kernel.enemy['health'], 1,
              kernel.root['next_id']+len(kernel.static_ids)+kernel.count+len(kernel.hand)+1, 1]
    if any(value < 0 or value >= 2**60 for value in upper):
        raise ValueError('native integer bounds exceeded')
    # AI_NOTE: Validate Python integers before NumPy conversion, including max_health used later by the compiled skyline.
    operands = [value for row in prototype_values+spell_values for value in row]
    operands += config_values+[kernel.own['health']]+[e['max_health'] for e in kernel.prototypes]
    if any(value < -(2**60) or value >= 2**60 for value in operands):
        raise ValueError('native transition operands exceeded')
    prototypes = np.array(prototype_values, dtype=np.int64).reshape((-1, 6))
    spells = np.array(spell_values, dtype=np.int64).reshape((-1, 4))
    config = np.array(config_values, dtype=np.int64)
    static = np.array([_numeric_id(value) for value in kernel.static_ids], dtype=np.int64)
    hand_ids = np.array([_numeric_id(e['id']) for e in kernel.hand], dtype=np.int64)
    layout = np.empty((len(upper), 4), dtype=np.int64)
    word, offset = 0, 0
    for i, maximum in enumerate(upper):
        width = max(1, maximum.bit_length())
        if offset+width > 64:
            word, offset = word+1, 0
        if word >= 3:
            raise ValueError('native state requires more than 192 bits')
        layout[i] = word, offset, (1 << width)-1, 2 if i == kernel.tail+1 else 0
        offset += width
    return layout, prototypes, spells, config, static, hand_ids


class NativeStates(Sequence[State]):
    """Read-only decoded view over three uint64 words per reachable state."""

    def __init__(self, keys: UInts, layout: Ints):
        # AI_NOTE: Keep packed storage; endpoint consumers decode only the row they need.
        self.keys, self.layout = keys, layout
        self.fields = [tuple(map(int, row)) for row in layout]

    def __len__(self) -> int:
        # AI_NOTE: Report actual used rows, not reserved search capacity.
        return len(self.keys)

    @overload
    def __getitem__(self, index: int) -> State: ...

    @overload
    def __getitem__(self, index: slice) -> list[State]: ...

    def __getitem__(self, index: int | slice) -> State | list[State]:
        # AI_NOTE: Python decoding is exact and requires no per-row JIT dispatch for existing consumers.
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        row = tuple(map(int, self.keys[index]))
        return tuple(((row[word] >> shift) & mask)-bias for word, shift, mask, bias in self.fields)

    def __iter__(self) -> Iterator[State]:
        # AI_NOTE: Avoid Sequence's extra failing index dispatch at the end of large traversals.
        return (self[index] for index in range(len(self)))


@dataclass
class NativeSearch:
    kernel: Kernel
    keys: UInts
    layout: Ints
    witnesses: NDArray[np.int32]
    expanded: int
    complete: bool
    cutoffs: list[str]
    stats: Json

    @property
    def states(self) -> NativeStates:
        # AI_NOTE: The exact state view shares packed storage and is compatible with the existing skyline.
        return NativeStates(self.keys, self.layout)

    def action(self, node: int, code: int) -> Json:
        # AI_NOTE: Decode a stored representative action against its actual parent, including generated token IDs.
        state = self.states[node]
        kind, source, target = code//256, (code % 256)//16, code % 16-1
        if kind == 0:
            return {'type': 'extra_pp'}
        if kind == 1:
            action: Json = {'type': 'play', 'card': self.kernel.hand[source]['id']}
            if target >= 0:
                action['target'] = self.kernel._id(state, target)
            return action
        action = {'type': ('attack', 'evolve', 'super_evolve')[kind-2],
                  'source': self.kernel._id(state, source)}
        if kind == 2:
            action['target'] = self.kernel._id(state, target) if target >= 0 else f'leader:{1-self.kernel.owner}'
        return action

    def witness_steps(self, node: int) -> list[Json]:
        # AI_NOTE: Every node has a parent with lower BFS index; decode a reproducible conditional chance tape.
        result: list[Json] = []
        while node:
            parent, code, draw = map(int, self.witnesses[node])
            result.append({'action': self.action(parent, code), 'draws': [] if draw < 0 else [draw]})
            node = parent
        result.reverse()
        return result

    def expand(self, node: int) -> list[Json]:
        # AI_NOTE: Reconstruct all legal decisions and exact conditional chance branches, without storing repeated graph edges.
        state = self.states[node]
        result: list[Json] = []
        for action in self.kernel.actions(state):
            outcomes: list[Json] = []
            for child, probability, draws in self.kernel.outcomes(state, action):
                key = [int(value) for value in _pack(np.array(child, dtype=np.int64), self.layout)]
                outcomes.append({'key': key, 'probability': str(probability), 'draws': list(draws)})
            result.append({'action': action, 'outcomes': outcomes})
        return result


def enumerate_native(battle: Battle, *, max_states: int = 100000, max_outcomes: int = 4096,
                     seconds: float = 10, progress: Callable[[Json], None] | None = None,
                     batch_size: int = 4096) -> NativeSearch:
    # AI_NOTE: Compile once, then enumerate all states in bounded batches; compilation time is reported separately.
    if not eligible(battle):
        raise ValueError('native fixed-slot battle is unsupported')
    if (not 1 <= max_states <= 100000000 or not 1 <= max_outcomes <= 10000
            or not isfinite(seconds) or seconds < 0 or batch_size < 1):
        raise ValueError('invalid native search budget')
    started = perf_counter()
    kernel = Kernel(Battle(battle.state, battle.cards, record=False))
    prepared = prepare(kernel)
    layout = prepared[0]
    initial = np.array(kernel.initial, dtype=np.int64)
    first = tuple(np.uint64(value) for value in _pack(initial, layout))
    # AI_NOTE: A one-row warmup compiles every branch but cannot add any child or affect the real traversal.
    warm_keys = np.array([first], dtype=np.uint64)
    warm_witnesses = np.zeros((1, 3), dtype=np.int32)
    seen = np.zeros((2048, 4), dtype=np.uint64)
    seen[_locate(seen, warm_keys, first)] = (first[0], first[1], first[2], 1)
    _batch(warm_keys, warm_witnesses, seen, 1, 0, 1, max_outcomes, *prepared)
    ready = perf_counter()
    keys = np.empty((max_states, 3), dtype=np.uint64)
    witnesses = np.empty((max_states, 3), dtype=np.int32)
    keys[0], witnesses[0] = first, (0, 0, -1)
    size, cursor, status, choices, outcomes, duplicates = 1, 0, 0, 0, 0, 0
    deadline = ready+seconds
    while cursor < size and not status and perf_counter() < deadline:
        size, cursor, status, added_choices, added_outcomes, added_duplicates, seen = _batch(
            keys, witnesses, seen, size, cursor, batch_size, max_outcomes, *prepared)
        choices += added_choices
        outcomes += added_outcomes
        duplicates += added_duplicates
        if progress is not None:
            progress({'phase': 'enumeration', 'states': size, 'expanded': cursor,
                      'elapsed_seconds': perf_counter()-ready})
    done = perf_counter()
    cutoffs = ['states'] if status == 1 else ['chance outcomes'] if status == 2 else ['time'] if cursor < size else []
    index_bytes = seen.nbytes
    # AI_NOTE: The hash index stores only row references and releases independently of returned packed states.
    del seen
    released = perf_counter()
    stats: Json = {'backend': 'native', 'states': size, 'expanded_states': cursor,
                   'choices': choices, 'outcomes': outcomes, 'duplicate_outcomes': duplicates,
                   'warmup_ms': (ready-started)*1000, 'search_ms': (done-ready)*1000,
                   'cleanup_ms': (released-done)*1000, 'total_ms': (released-started)*1000,
                   'state_words': 3, 'index_bytes': index_bytes}
    return NativeSearch(kernel, keys[:size], layout, witnesses[:size], cursor, not cutoffs, cutoffs, stats)
