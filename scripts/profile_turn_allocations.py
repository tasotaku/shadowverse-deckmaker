"""Actual Numba NRT allocation counters outside scored CLI trials."""
from __future__ import annotations

import cProfile
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter

os.environ['NUMBA_NRT_STATS'] = '1'

from numba.core.runtime import rtsys

from svdeck.battle.battle import Battle
from svdeck.battle.battle_frontier_catalog import analyze_catalog
from svdeck.battle.battle_frontier_compare import peak_memory
import svdeck.battle.battle_frontier_native as native


def main() -> None:
    # AI_NOTE: Count actual NRT calls around the same public catalog workload, excluding warmup and unrelated Python allocations.
    label, output = sys.argv[1], Path(sys.argv[2])
    cases_path = Path('docs/evidence/turn-search-compare/independent-medium-cases.v1.json')
    case = json.loads(cases_path.read_text(encoding='utf-8'))[2]
    battle = Battle(case['state'], case['cards'])
    analyze_catalog(battle, max_states=1, seconds=60, backend='native')
    gc.collect()
    before = rtsys.get_allocation_stats()
    profiler = cProfile.Profile()
    started = perf_counter()
    profiler.enable()
    catalog = analyze_catalog(battle, max_states=100000000, seconds=3600, backend='native')
    profiler.disable()
    elapsed = perf_counter()-started
    during = rtsys.get_allocation_stats()
    complete, stats = catalog.complete, catalog.stats
    assert complete
    del catalog
    gc.collect()
    after = rtsys.get_allocation_stats()
    output.parent.mkdir(parents=True, exist_ok=True)
    profiler.dump_stats(str(output.with_suffix('.prof')))
    source = Path(native.__file__)
    result = {'version': label, 'case_id': case['id'], 'fixture_sha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(),
              'source_path': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'scope': 'public analyze_catalog: exact enumeration plus skyline, excluding CLI export, warmup excluded; cProfile and NRT stats enabled; not scored timing',
              'allocation_method': 'NUMBA_NRT_STATS=1 / numba.core.runtime.rtsys.get_allocation_stats',
              'allocation_scope': 'Numba NRT allocation/free and MemInfo counts, not bytes or total process/native-library allocation traffic',
              'before': before._asdict(), 'returned': during._asdict(), 'after_cleanup': after._asdict(),
              'delta_returned': dict(zip(before._fields, [b-a for a, b in zip(before, during)])),
              'delta_after_cleanup': dict(zip(before._fields, [b-a for a, b in zip(before, after)])),
              'complete': complete, 'stats': stats, 'instrumented_seconds': elapsed, 'peak_memory': peak_memory()}
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
