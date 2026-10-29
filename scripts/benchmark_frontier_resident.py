"""Measure repeated in-memory catalogue calls separately from cold JSON export."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from svdeck.battle.battle import Battle
from svdeck.battle.battle_frontier_catalog import analyze_catalog
from svdeck.battle.battle_frontier_compare import canonical, kernel_key, semantic_key, source_manifest, digest
from svdeck.battle.battle_frontier import freeze
from svdeck.battle.battle_frontier_fast import Kernel
from svdeck.battle.combat_benchmark import peak_memory


def worker(args: argparse.Namespace) -> None:
    # AI_NOTE: 同じprocessで初期化を一度だけ払い、学習ループ向けの遅延復元APIの費用を直接測る。
    case = next(c for c in json.loads(args.cases.read_text(encoding='utf-8')) if c['id'] == args.case)
    battle = Battle(case['state'], case['cards'])
    started = perf_counter()
    warm = analyze_catalog(battle, backend=args.backend, max_states=1, seconds=60)
    del warm
    gc.collect()
    initialization = perf_counter()-started
    kernel = Kernel(battle)
    shapes: dict[int, str] = {}
    hands = [digest(freeze(dict(entity, keywords=sorted(entity['keywords'])))) for entity in kernel.hand]
    trials = []
    for _ in range(args.trials):
        start = perf_counter()
        catalog = analyze_catalog(battle, backend=args.backend, max_states=1000000, seconds=120)
        call = perf_counter()-start
        validation_started = perf_counter()
        hashes = []
        for node in catalog.candidates:
            if catalog.native is not None:
                key = kernel_key(kernel, catalog.native.states[node], shapes, hands)
            elif catalog.graph is not None and catalog.graph.get('encoding') == 'fixed-slots-v1':
                key = kernel_key(kernel, tuple(catalog.graph['positions'][node]), shapes, hands)
            else:
                key = semantic_key(Battle(catalog.state_at(node), battle.cards))
            hashes.append(hashlib.sha256(canonical(key).encode('utf-8')).digest())
        candidate_digest = hashlib.sha256(b''.join(sorted(hashes))).hexdigest()
        validation = perf_counter()-validation_started
        complete, count, stats = catalog.complete, len(catalog.candidates), dict(catalog.stats)
        cleanup_started = perf_counter()
        del catalog, hashes
        gc.collect()
        cleanup = perf_counter()-cleanup_started
        trials.append({'complete': complete, 'candidate_count': count, 'candidate_semantic_sha256': candidate_digest,
                       'call_seconds': call, 'required_cleanup_seconds': cleanup,
                       'compute_seconds': call+cleanup, 'verification_seconds_separate': validation, 'stats': stats})
    result = {'case_id': args.case, 'backend': args.backend, 'mode': 'resident-in-memory-catalog',
              'scope': 'All states/candidates retained; state dictionaries and conditional edges decoded on demand. No JSON candidate export.',
              'initialization_seconds': initialization, 'warmup': 'One one-state initialization; not a measured completed search.',
              'trials': trials, 'peak_memory': peak_memory(), 'memory_scope': 'whole case process including initialization and verification',
              'source': source_manifest(), 'fixture_sha256': hashlib.sha256(args.cases.read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def main() -> None:
    # AI_NOTE: 各case・方式を別processで直列実行し、コンパイル済みruntimeが他方式の計測に混入しないようにする。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case')
    parser.add_argument('--backend', choices=['reference', 'cache', 'native'])
    parser.add_argument('--trials', type=int, default=3)
    args = parser.parse_args()
    if args.output.exists() or args.trials < 1:
        parser.error('Use an unused output path and positive trials')
    if args.case:
        if args.backend is None:
            parser.error('--case requires --backend')
        worker(args)
        return
    args.output.mkdir(parents=True)
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    for i, case in enumerate(cases):
        methods = ['reference', 'cache', 'native']
        if i % 2:
            methods.reverse()
        for method in methods:
            output = args.output/f'{i}-{method}.json'
            subprocess.run([sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--cases', str(args.cases),
                            '--case', case['id'], '--backend', method, '--trials', str(args.trials),
                            '--output', str(output)], check=True)
    print(json.dumps({'complete': True, 'output': str(args.output), 'case_count': len(cases)}))


if __name__ == '__main__':
    main()
