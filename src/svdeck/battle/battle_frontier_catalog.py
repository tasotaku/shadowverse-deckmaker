"""Training-oriented exact endpoint catalogue with on-demand chance decisions."""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Callable

from svdeck.battle.battle import Battle, Json, integer
from svdeck.battle.battle_frontier import analyze, state_at, witness_steps
from svdeck.battle.battle_frontier_fast import eligible
from svdeck.battle.battle_practical import validate_scope
from svdeck.battle.combat_benchmark import peak_memory

if TYPE_CHECKING:
    from svdeck.battle.battle_frontier_native import NativeSearch


@dataclass
class Catalog:
    """Candidates are reachable STOP states, not independently selectable luck.

Use expand() to average all chance outcomes before comparing legal actions.
Node numbers and representative witnesses are local to this one catalogue.
"""
    candidates: list[int]
    complete: bool
    enumeration_complete: bool
    frontier_complete: bool
    cutoffs: list[str]
    stats: Json
    record: Json
    native: NativeSearch | None = None
    graph: Json | None = None

    def state_at(self, node: int) -> Json:
        # AI_NOTE: 保存した整数状態を必要な時だけ辞書に戻し、候補全件の巨大な複製を作らない。
        integer(node, 'node', 0, self.stats['states']-1)
        if self.native is not None:
            return self.native.kernel.state(self.native.states[node])
        assert self.graph is not None
        return state_at(self.graph, node)

    def witness_steps(self, node: int) -> list[Json]:
        # AI_NOTE: 最初の到達例だけを返す。指定された抽選結果の条件付き再生であり最適方策ではない。
        integer(node, 'node', 0, self.stats['states']-1)
        if self.native is not None:
            return self.native.witness_steps(node)
        assert self.graph is not None
        return witness_steps(self.graph, node)

    def expand(self, node: int) -> list[Json]:
        # AI_NOTE: 全合法手と各手の全抽選結果を復元し、不利な出目を捨てずに条件付き評価を可能にする。
        integer(node, 'node', 0, self.stats['states']-1)
        result: list[Json] = []
        if self.native is not None:
            kernel = self.native.kernel
            state = self.native.states[node]
            for action in kernel.actions(state):
                result.append({'action': action, 'outcomes': [
                    {'state': kernel.state(child), 'probability': str(probability), 'draws': list(draws)}
                    for child, probability, draws in kernel.outcomes(state, action)]})
            return result
        assert self.graph is not None
        graph = self.graph
        if not self.enumeration_complete and node not in graph['expanded']:
            raise ValueError('This node was not fully expanded before the search budget expired')
        for source, action_id, start, end in graph['choices']:
            if source != node:
                continue
            result.append({'action': graph['actions'][action_id], 'outcomes': [
                {'state': state_at(graph, target), 'probability': graph['probabilities'][probability],
                 'draws': list(graph['draws'][draws])}
                for target, probability, draws in graph['outcomes'][start:end]]})
        return result


def analyze_catalog(battle: Battle, *, max_states: int = 100000, max_outcomes: int = 4096,
                    seconds: float = 10, backend: str = 'auto',
                    progress: Callable[[Json], None] | None = None) -> Catalog:
    # AI_NOTE: nativeは任意依存・厳密範囲が揃う場合だけ選ぶ。範囲外や複合効果は既存の完全処理へ戻す。
    started = perf_counter()
    integer(max_states, 'max_states', 1, 100000000)
    integer(max_outcomes, 'max_outcomes', 1, 10000)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 3600:
        raise ValueError('seconds must be greater than zero and at most 3600')
    if backend not in ('auto', 'native', 'reference', 'cache'):
        raise ValueError('backend must be auto, native, reference, or cache')
    validate_scope(battle)
    fallback = ''
    native = None
    if backend in ('auto', 'native'):
        if not eligible(battle):
            fallback = 'Input requires the generic supported-effect engine'
        else:
            try:
                from svdeck.battle.battle_frontier_native import enumerate_native
                from svdeck.battle.battle_frontier_skyline import frontier
            except ImportError:
                fallback = 'Optional performance dependencies are not installed'
            else:
                try:
                    native = enumerate_native(battle, max_states=max_states, max_outcomes=max_outcomes,
                                              seconds=seconds, progress=progress)
                except (ValueError, OverflowError) as error:
                    fallback = str(error)
    if native is not None:
        initialization_started = perf_counter()
        frontier(native.kernel, native.keys[:1], native.layout, float('inf'))
        skyline_initialization = perf_counter()-initialization_started
        prune_started = perf_counter()
        # JIT initialization is reported; only runtime work consumes the supplied search budget.
        runtime_used = (native.stats['total_ms']-native.stats['warmup_ms'])/1000
        deadline = prune_started+max(0, seconds-runtime_used)
        candidates, complete = frontier(native.kernel, native.keys, native.layout, deadline)
        cutoffs = list(native.cutoffs)
        if not complete:
            cutoffs.append('frontier time')
        peak, method = peak_memory()
        stats = dict(native.stats)
        stats.update(pruning_ms=(perf_counter()-prune_started)*1000, candidates=len(candidates),
                     skyline_initialization_ms=skyline_initialization*1000,
                     elapsed_ms=(perf_counter()-started)*1000, peak_rss_bytes=peak, memory_method=method,
                     memory_scope='whole process peak', fallback_reason=None)
        return Catalog(candidates, native.complete and complete, native.complete, complete,
                       cutoffs, stats, native.kernel.battle.export(), native=native)
    if backend == 'native':
        raise ValueError(fallback)
    if backend == 'cache' and eligible(battle):
        from svdeck.battle.battle_frontier_cache import CachedKernel
        from svdeck.battle.battle_frontier_packed import analyze_packed
        graph = analyze_packed(battle, max_states=max_states, max_outcomes=max_outcomes, seconds=seconds,
                               progress=progress, kernel_factory=CachedKernel)
        graph['stats']['backend'] = 'cache'
    else:
        graph = analyze(battle, max_states=max_states, max_outcomes=max_outcomes, seconds=seconds, progress=progress)
    graph['stats']['fallback_reason'] = fallback or None
    graph['stats']['elapsed_ms'] = (perf_counter()-started)*1000
    return Catalog(graph['candidates'], graph['complete'], graph['enumeration_complete'],
                   graph['frontier_complete'], graph['cutoffs'], graph['stats'], graph['record'], graph=graph)
