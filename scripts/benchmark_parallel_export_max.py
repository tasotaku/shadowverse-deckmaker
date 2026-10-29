"""Test whether bounded independent SHA batches improve export throughput."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import gc
import hashlib
import json
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from svdeck.battle.battle import Battle
from svdeck.battle.battle_frontier_fast import Kernel
from svdeck.battle.battle_frontier_native import NativeSearch
from svdeck.battle.battle_frontier_export import materialize


def main() -> None:
    # AI_NOTE: Independent partitions preserve all hashes and rows; CPU time exposes any wall-time versus throughput tradeoff.
    folder = Path('output/turn-search-max/export')
    case = json.loads(Path('docs/evidence/turn-search-compare/independent-hard-cases.v1.json').read_text(encoding='utf-8'))[0]
    search = NativeSearch(Kernel(Battle(case['state'], case['cards'])), np.load(folder/'keys.npy'),
                          np.load(folder/'layout.npy'), np.zeros((1, 3), dtype=np.int32), 0, True, [], {})
    candidates = np.load(folder/'candidates.npy').tolist()
    materialize(search, candidates[:1], backend='compiled')
    reports = []
    for workers in (1, 2, 4):
        gc.collect()
        start, cpu = perf_counter(), process_time()
        size = (len(candidates)+workers-1)//workers
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = [pool.submit(materialize, search, candidates[offset:offset+size], backend='compiled', workers=1)
                       for offset in range(0, len(candidates), size)]
            parts = [future.result() for future in pending]
        elapsed, cpu_elapsed = perf_counter()-start, process_time()-cpu
        hashes = [value for _, part in parts for value in part]
        row_hash = hashlib.sha256()
        for rows, _ in parts:
            for row in rows.data:
                assert isinstance(row, bytes)
                row_hash.update(row)
        reports.append({'workers': workers, 'seconds': elapsed, 'process_cpu_seconds': cpu_elapsed,
                        'rows_sha256': row_hash.hexdigest(),
                        'semantic_sha256': hashlib.sha256(b''.join(sorted(hashes))).hexdigest()})
        del parts, pending, hashes, rows
    assert len({report['rows_sha256'] for report in reports}) == 1
    assert len({report['semantic_sha256'] for report in reports}) == 1
    (folder/'parallel.json').write_text(json.dumps(reports, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
