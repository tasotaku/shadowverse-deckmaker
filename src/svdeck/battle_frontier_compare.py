"""Isolated, comparable candidate-output measurements for current-turn search."""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import statistics
import subprocess
import sys
from contextlib import nullcontext
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from typing import Any
from unittest.mock import patch

from .battle import Battle, Json, replay
from .battle_frontier import analyze, endpoint_key, freeze, state_at, witness_steps
from .battle_frontier_fast import Kernel, State, eligible
from .battle_frontier_io import States, dump_graph
from .battle_practical import Chance, ChanceBattle, replay_branch, validate_scope
from .combat_benchmark import peak_memory

SEMANTICS = ('Every own-turn prefix may STOP before end-turn effects. Candidates are board/resource endpoints, '
             'not mutually selectable deterministic plans or state reachability probabilities. '
             'Use conditional expansion for all legal choices and exact chance outcomes after observation.')


def canonical(value: Any) -> str:
    # AI_NOTE: JSON表現を固定し、探索順や辞書挿入順によるdigest差を除く。
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value: Any) -> str:
    # AI_NOTE: 比較キーだけをhash化し、状態数の一致を意味同一性の代用にしない。
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def semantic_key(battle: Battle) -> Json:
    # AI_NOTE: 公開Pareto比較と同じ能力・順序・資源・残手札をcanonical keyへ落とす。
    shape, values = endpoint_key(battle)
    winner, boards = shape
    hand = battle.state['players'][battle.state['active_player']]['hand']
    normalized = []
    for entity in hand:
        entity = dict(entity, keywords=sorted(entity['keywords']))
        normalized.append(digest(freeze(entity)))
    return {'winner': winner, 'boards': [[digest(body) for body in board] for board in boards],
            'values': values, 'hand': sorted(normalized)}


def kernel_key(kernel: Kernel, state: State, shapes: dict[int, str], hands: list[str]) -> Json:
    # AI_NOTE: kernel内だけ有効なshape番号を能力定義のhashへ戻し、異なる列挙順でも比較する。
    shape, values, hand = kernel.endpoint(state)
    if len(shapes) != len(kernel.shape_ids):
        shapes.update({number: digest(marker) for marker, number in kernel.shape_ids.items() if number not in shapes})
    winner, boards = shape
    return {'winner': winner, 'boards': [[shapes[body] for body in board] for board in boards],
            'values': values, 'hand': sorted(value for bit, value in enumerate(hands) if hand & (1 << bit))}


def expand_state(record: Json, state: Json) -> Json:
    # AI_NOTE: 保存候補からも抽選を選択肢に変えず、未観測の抽選を全て列挙して条件付き継続を返す。
    base = replay(record)
    current = ChanceBattle(state, base.cards, record=False)
    validate_scope(current)
    choices = []
    for action in current.legal_actions():
        if action['type'] == 'end_turn':
            continue
        pending: list[tuple[tuple[int, ...], Fraction]] = [((), Fraction(1))]
        outcomes: list[Json] = []
        while pending:
            tape, probability = pending.pop()
            try:
                child = current.branch(action, tape)
            except Chance as chance:
                if len(pending)+len(outcomes)+chance.size > 10000 or len(tape) >= 128:
                    raise ValueError('conditional expansion exceeds the documented 10000-outcome budget')
                pending.extend((tape+(i,), probability/chance.size) for i in reversed(range(chance.size)))
            else:
                outcomes.append({'state': child.state, 'probability': str(probability), 'draws': list(tape)})
        choices.append({'action': action, 'outcomes': outcomes})
    return {'version': 1, 'conditional': True, 'scope': SEMANTICS, 'state': state, 'stop': True, 'choices': choices}


def source_manifest() -> Json:
    # AI_NOTE: commitだけでなく実行された変更中のsourceもhash化し、別コードの計測を混同しない。
    root = Path(__file__).resolve().parents[2]
    files = {str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted((root/'src/svdeck').glob('battle*.py'))}
    files['src/svdeck/combat_benchmark.py'] = hashlib.sha256((root/'src/svdeck/combat_benchmark.py').read_bytes()).hexdigest()
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    dependencies = {name: importlib.metadata.version(name) for name in ('numpy', 'numba') if importlib.util.find_spec(name) is not None}
    return {'revision': revision, 'source_sha256': digest(files), 'files': files, 'dependencies': dependencies,
            'interpreter': sys.executable, 'python': sys.version, 'platform': platform.platform(),
            'machine': platform.machine(), 'processor': platform.processor()}


def run_worker(args: argparse.Namespace) -> None:
    # AI_NOTE: worker一個を一方式一局面一試行に固定し、setup/候補化/cleanupと保存費用を区別する。
    started = perf_counter()
    case_bytes = args.cases.read_bytes()
    cases = json.loads(case_bytes)
    case = next(case for case in cases if case['id'] == args.case)
    battle = Battle(case['state'], case['cards'])
    validate_scope(battle)
    setup_seconds = perf_counter()-started
    root = Battle(battle.state, battle.cards, record=False)
    kernel = Kernel(root) if eligible(root) else None
    native: Any = None
    graph: Json | None = None
    fallback = None
    call_started = perf_counter()
    setup_seconds = call_started-started
    if args.algorithm == 'native' and kernel is not None:
        from .battle_frontier_native import enumerate_native, prepare
        try:
            prepare(kernel)
        except (ValueError, OverflowError) as error:
            fallback = str(error)
        else:
            native = enumerate_native(root, max_states=args.max_states, seconds=args.seconds)
    if native is not None:
        from .battle_frontier_skyline import frontier
        states = native.states
        prune_started = perf_counter()
        candidates, frontier_complete = frontier(native.kernel, native.keys, native.layout, call_started+args.seconds)
        pruning_seconds = perf_counter()-prune_started
        stats = dict(native.stats)
        enumeration_complete = native.complete
        cutoffs = list(native.cutoffs)+([] if frontier_complete else ['frontier time'])
        backend = 'native'
        witness = native.witness_steps
        kernel = native.kernel
    else:
        if kernel is None:
            fallback = 'supported compound effects require generic engine'
        from .battle_frontier_cache import CachedKernel
        context = patch('svdeck.battle_frontier_fast.Kernel', CachedKernel) if args.algorithm == 'cache' and kernel is not None else nullcontext()
        with context:
            graph = analyze(root, max_states=args.max_states, seconds=args.seconds, backend='auto')
        states = graph['positions']
        candidates = graph['candidates']
        stats = dict(graph['stats'])
        frontier_complete = bool(graph['frontier_complete'])
        enumeration_complete = bool(graph['enumeration_complete'])
        cutoffs = list(graph['cutoffs'])
        backend = 'generic' if kernel is None else args.algorithm if args.algorithm != 'native' else 'baseline-fallback'
        pruning_seconds = (stats['elapsed_ms']-stats['search_ms'])/1000
        witness = lambda index: witness_steps(graph, index)
    enumeration_seconds = stats['search_ms']/1000
    backend_cleanup_seconds = stats.get('cleanup_ms', 0)/1000
    algorithm_setup_seconds = max(0.0, perf_counter()-call_started-enumeration_seconds-pruning_seconds-backend_cleanup_seconds)
    material_started = perf_counter()
    complete = enumeration_complete and frontier_complete and not cutoffs
    payload: Json = {'version': 1, 'mode': 'candidates', 'case_id': case['id'], 'algorithm': args.algorithm,
                     'actual_backend': backend, 'fallback_reason': fallback, 'scope': SEMANTICS,
                     'complete': complete, 'enumeration_complete': enumeration_complete,
                     'frontier_complete': frontier_complete, 'cutoffs': cutoffs,
                     'record': root.export(), 'candidate_count': len(candidates), 'state_count': len(states),
                     'encoding': 'fixed-slots-v1' if kernel is not None else 'full-state-v1'}
    hashes = []
    if kernel is not None:
        candidate_rows: Any = States(len(kernel.initial))
        shapes: dict[int, str] = {}
        hands = [digest(freeze(dict(entity, keywords=sorted(entity['keywords'])))) for entity in kernel.hand]
        for index in candidates:
            state = states[index]
            candidate_rows.data.append(candidate_rows.key(state))
            hashes.append(bytes.fromhex(digest(kernel_key(kernel, state, shapes, hands))))
    else:
        candidate_rows = []
        assert graph is not None
        for index in candidates:
            full = state_at(graph, index)
            candidate_rows.append(full)
            hashes.append(bytes.fromhex(digest(semantic_key(Battle(full, root.cards, record=False)))))
    payload['candidates'] = candidate_rows
    candidate_digest = hashlib.sha256(b''.join(sorted(hashes))).hexdigest()
    payload['candidate_semantic_sha256'] = candidate_digest
    payload['candidate_digest_scope'] = 'complete frontier' if complete else 'incomplete prefix only'
    payload['witness_samples'] = [{'candidate': number, 'steps': witness(index)}
                                  for number, index in enumerate(candidates[:args.witness_samples])]
    if len(states) <= args.debug_threshold:
        candidate_set = set(candidates)
        nodes = []
        for index in range(len(states)):
            full = kernel.state(states[index]) if kernel is not None else state_at(graph, index)  # type: ignore[arg-type]
            nodes.append({'node': index, 'candidate': index in candidate_set, 'state': full,
                          'semantic_key': semantic_key(Battle(full, root.cards, record=False)),
                          'witness': witness(index), 'conditional': expand_state(payload['record'], full)['choices']})
        payload['debug_nodes'] = nodes
    material_seconds = perf_counter()-material_started
    cleanup_started = perf_counter()
    del hashes, graph, native, states, witness, candidates, kernel
    gc.collect()
    cleanup_seconds = perf_counter()-cleanup_started+backend_cleanup_seconds
    compute_seconds = perf_counter()-started
    serial_started = perf_counter()
    dump_graph(payload, args.output/'result.json')
    serialization_seconds = perf_counter()-serial_started
    peak, memory_method = peak_memory()
    report: Json = {'version': 1, 'case_id': case['id'], 'algorithm': args.algorithm, 'actual_backend': backend,
                    'mode': 'candidates', 'complete': complete, 'enumeration_complete': enumeration_complete,
                    'frontier_complete': frontier_complete, 'cutoffs': cutoffs, 'fallback_reason': fallback,
                    'candidate_count': payload['candidate_count'], 'state_count': payload['state_count'],
                    'candidate_semantic_sha256': candidate_digest, 'stats': stats,
                    'timings': {'setup_seconds': setup_seconds, 'algorithm_setup_seconds': algorithm_setup_seconds,
                                'enumeration_seconds': enumeration_seconds, 'pruning_seconds': pruning_seconds,
                                'candidate_materialization_seconds': material_seconds, 'cleanup_seconds': cleanup_seconds,
                                'compute_seconds': compute_seconds, 'serialization_seconds': serialization_seconds,
                                'worker_wall_seconds': perf_counter()-started},
                    'peak_rss_bytes': peak, 'memory_method': memory_method, 'memory_scope': 'whole worker lifetime',
                    'result_path': 'result.json', 'result_bytes': (args.output/'result.json').stat().st_size,
                    'input_sha256': hashlib.sha256(case_bytes).hexdigest(), 'case_sha256': digest(case),
                    'options': {'seconds': args.seconds, 'max_states': args.max_states, 'mode': 'candidates',
                                'debug_threshold': args.debug_threshold, 'witness_samples': args.witness_samples}}
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def summarize(rows: list[Json], algorithms: list[str], cases: list[str]) -> Json:
    # AI_NOTE: 全完走・同一候補集合の共通caseだけを比較し、prefixや未検証正確性から勝者を断定しない。
    grouped = []
    totals: dict[str, float] = {}
    spans: dict[str, tuple[float, float]] = {}
    eligible_methods = []
    for algorithm in algorithms:
        successful = True
        median_total = low_total = high_total = 0.0
        for case in cases:
            subset = [row for row in rows if row['algorithm'] == algorithm and row['case_id'] == case]
            complete_rows = [row for row in subset if row.get('complete') and 'timings' in row]
            if len(complete_rows) != len(subset) or not subset:
                successful = False
            times = [row['timings']['compute_seconds'] for row in complete_rows]
            group: Json = {'case_id': case, 'algorithm': algorithm, 'trials': subset,
                           'complete': bool(subset) and len(complete_rows) == len(subset)}
            if times:
                median_total += statistics.median(times)
                low_total += min(times)
                high_total += max(times)
                group.update(median_compute_seconds=statistics.median(times), compute_range_seconds=[min(times), max(times)],
                             median_serialization_seconds=statistics.median(row['timings']['serialization_seconds'] for row in complete_rows),
                             median_peak_rss_bytes=statistics.median(row['peak_rss_bytes'] for row in complete_rows))
            grouped.append(group)
        if successful:
            eligible_methods.append(algorithm)
            totals[algorithm] = median_total
            spans[algorithm] = low_total, high_total
    mismatches = []
    for case in cases:
        hashes = {row['candidate_semantic_sha256'] for row in rows if row['case_id'] == case and row.get('complete')}
        if len(hashes) > 1:
            mismatches.append(case)
    order = sorted(eligible_methods, key=lambda algorithm: totals[algorithm])
    status = 'incomplete' if not order else 'candidate_mismatch' if mismatches else 'provisional_performance_leader'
    winner = order[0] if order and not mismatches else None
    if not mismatches and len(order) > 1 and spans[order[0]][1] >= spans[order[1]][0]:
        status, winner = 'practical_tie_or_uncertain', None
    return {'version': 1, 'mode': 'candidates', 'scope': SEMANTICS, 'groups': grouped,
            'selection': {'status': status, 'algorithm': winner, 'case_scope': cases, 'aggregate_median_compute_seconds': totals,
                          'aggregate_range_seconds': spans, 'candidate_mismatch_cases': mismatches,
                          'rule': 'Among complete equal-output methods, lowest sum of per-case median compute time; overlapping aggregate ranges are uncertain.',
                          'correctness_status': 'Cross-method agreement only; independent oracle evidence required before recommendation.'}}


def run_suite(args: argparse.Namespace) -> None:
    # AI_NOTE: warmupを測定外に分離し、方式順を反転しながら各試行を新しい直列processで実行する。
    args.output.mkdir(parents=True)
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    algorithms = args.algorithms.split(',')
    if not algorithms or any(name not in ('baseline', 'cache', 'native') for name in algorithms):
        raise ValueError('algorithms must be a comma-separated subset of baseline,cache,native')
    manifest = source_manifest()
    manifest.update(input_path=str(args.cases.resolve()), input_sha256=hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                    algorithms=algorithms, trials=args.trials, warmup='one one-state fresh-process warmup per case and algorithm outside measured trials',
                    process_policy='one measured child at a time; no parallel benchmark workers started by this harness',
                    competing_load_note=args.load_note, horizon='own current turn before end_turn', output_mode='candidates',
                    options={'seconds': args.seconds, 'max_states': args.max_states, 'debug_threshold': args.debug_threshold,
                             'witness_samples': args.witness_samples},
                    selection_rule='Lowest sum of complete per-case median compute time with exact candidate agreement; report overlapping ranges as uncertain.')
    manifest['options_sha256'] = digest(manifest['options'])
    (args.output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    rows = []
    for case_number, case in enumerate(cases):
        for trial in range(-1, args.trials):
            order = algorithms if (trial+case_number) % 2 == 0 else list(reversed(algorithms))
            for algorithm in order:
                folder = args.output/f'case-{case_number:03d}'/algorithm/('warmup' if trial < 0 else f'trial-{trial+1}')
                folder.mkdir(parents=True)
                command = [sys.executable, '-X', 'utf8', '-m', 'svdeck.battle_frontier_compare', '--worker',
                           '--cases', str(args.cases.resolve()), '--case', case['id'], '--algorithm', algorithm,
                           '--output', str(folder.resolve()), '--seconds', str(args.seconds), '--max-states', str(1 if trial < 0 else args.max_states),
                           '--debug-threshold', str(args.debug_threshold), '--witness-samples', str(args.witness_samples)]
                started = perf_counter()
                with (folder/'stdout.log').open('w', encoding='utf-8') as stdout, (folder/'stderr.log').open('w', encoding='utf-8') as stderr:
                    completed = subprocess.run(command, stdout=stdout, stderr=stderr, check=False)
                wall = perf_counter()-started
                path = folder/'report.json'
                report = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
                    'case_id': case['id'], 'algorithm': algorithm, 'mode': 'candidates', 'complete': False,
                    'cutoffs': ['worker error'], 'error_log': str((folder/'stderr.log').relative_to(args.output))}
                report['cold_start_and_exit_seconds'] = max(0.0, wall-report.get('timings', {}).get('worker_wall_seconds', wall))
                report.update(trial=trial+1, warmup=trial < 0, exit_code=completed.returncode,
                              process_wall_seconds=wall, report_path=str(path.relative_to(args.output)),
                              result_path=str((folder/'result.json').relative_to(args.output)),
                              source_sha256=manifest['source_sha256'], options_sha256=digest(report.get('options', manifest['options'])))
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                if trial >= 0:
                    rows.append(report)
                print(json.dumps({'case': case['id'], 'algorithm': algorithm, 'trial': trial+1,
                                  'complete': report['complete'], 'process_wall_seconds': wall}), flush=True)
                summary = summarize(rows, algorithms, [item['id'] for item in cases])
                summary['manifest_path'] = 'manifest.json'
                summary['run_complete'] = len(rows) == len(cases)*len(algorithms)*args.trials
                if not summary['run_complete']:
                    summary['selection'].update(status='running', algorithm=None)
                (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')


def main() -> None:
    # AI_NOTE: 通常比較と条件付き展開を公開CLIへまとめ、JSONだけで利用できる入口を提供する。
    parser = argparse.ArgumentParser(description='Compare exact own-turn candidate algorithms in serial fresh processes.')
    parser.add_argument('--cases', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--algorithms', default='baseline,cache,native')
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--max-states', type=int, default=1000000)
    parser.add_argument('--debug-threshold', type=int, default=1000)
    parser.add_argument('--witness-samples', type=int, default=100)
    parser.add_argument('--load-note', default='Caller has not recorded external competing load; harness workers are serial.')
    parser.add_argument('--expand', type=Path, help='Saved result.json to expand conditionally (root unless candidate/steps/state supplied).')
    position = parser.add_mutually_exclusive_group()
    position.add_argument('--candidate', type=int)
    position.add_argument('--steps', type=Path, help='Conditional replay steps JSON from the saved record root.')
    position.add_argument('--state', type=Path, help='Full state JSON returned by an earlier conditional expansion.')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--case', help=argparse.SUPPRESS)
    parser.add_argument('--algorithm', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.expand:
        if args.output.exists():
            parser.error('output must be an unused JSON file')
        result = json.loads(args.expand.read_text(encoding='utf-8'))
        record = result['record']
        state = replay(record).state
        if args.candidate is not None:
            if not 0 <= args.candidate < len(result['candidates']):
                parser.error('candidate must be a valid nonnegative row index')
            row = result['candidates'][args.candidate]
            state = Kernel(replay(record)).state(tuple(row)) if result['encoding'] == 'fixed-slots-v1' else row
        if args.steps:
            state = replay_branch(record, json.loads(args.steps.read_text(encoding='utf-8')))['state']
        if args.state:
            state = json.loads(args.state.read_text(encoding='utf-8'))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(expand_state(record, state), ensure_ascii=False, indent=2), encoding='utf-8')
        return
    if args.cases is None or args.trials < 1 or not 0 < args.seconds <= 3600 or not 1 <= args.max_states <= 100000000:
        parser.error('provide cases, positive trials, seconds in (0,3600], max-states in [1,100000000]')
    if args.debug_threshold < 0 or args.witness_samples < 0:
        parser.error('debug-threshold and witness-samples must be nonnegative')
    if args.worker:
        run_worker(args)
    else:
        if args.output.exists():
            parser.error('output must be an unused directory')
        run_suite(args)


if __name__ == '__main__':
    main()
