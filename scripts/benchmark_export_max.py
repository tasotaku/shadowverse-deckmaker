"""Development component benchmark; full public CLI timings are measured separately."""
from __future__ import annotations

import gc
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

from svdeck.battle_env.battle import Battle
from svdeck.battle_env.battle_frontier_fast import Kernel
from svdeck.battle_env.battle_frontier_native import NativeSearch, enumerate_native
from svdeck.battle_env.battle_frontier_skyline import frontier
from svdeck.battle_env.battle_frontier_export import materialize


def main() -> None:
    # AI_NOTE: Persist one exact native input so component variants do identical work without repeating enumeration.
    folder = Path('output/turn-search-max/export')
    output = folder/(sys.argv[1] if len(sys.argv) > 1 else 'materialization.json')
    if output.exists():
        raise FileExistsError(output)
    folder.mkdir(parents=True, exist_ok=True)
    case = json.loads(Path('docs/evidence/turn-search-compare/independent-hard-cases.v1.json').read_text(encoding='utf-8'))[0]
    battle = Battle(case['state'], case['cards'])
    if not (folder/'keys.npy').exists():
        search = enumerate_native(battle, max_states=100000000, seconds=3600)
        candidates, complete = frontier(search.kernel, search.keys, search.layout, float('inf'))
        assert search.complete and complete
        np.save(folder/'keys.npy', search.keys)
        np.save(folder/'layout.npy', search.layout)
        np.save(folder/'candidates.npy', np.array(candidates, dtype=np.int64))
        del search, candidates
        gc.collect()
    search = NativeSearch(Kernel(battle), np.load(folder/'keys.npy'), np.load(folder/'layout.npy'),
                          np.zeros((1, 3), dtype=np.int32), 0, True, [], {})
    candidates = np.load(folder/'candidates.npy').tolist()
    materialize(search, candidates[:1], backend='compiled')
    reports = []
    for backend in ('python', 'compiled'):
        started = perf_counter()
        rows, hashes = materialize(search, candidates, backend=backend)
        material_seconds = perf_counter()-started
        digest_started = perf_counter()
        semantic = hashlib.sha256(b''.join(sorted(hashes))).hexdigest()
        row_digest = hashlib.sha256()
        for row in rows.data:
            assert isinstance(row, bytes)
            row_digest.update(row)
        verify_seconds = perf_counter()-digest_started
        reports.append({'backend': backend, 'candidate_count': len(rows), 'material_seconds': material_seconds,
                        'verification_seconds': verify_seconds, 'semantic_sha256': semantic, 'rows_sha256': row_digest.hexdigest()})
        del rows, hashes
        gc.collect()
    assert reports[0]['semantic_sha256'] == reports[1]['semantic_sha256']
    assert reports[0]['rows_sha256'] == reports[1]['rows_sha256']
    output.write_text(json.dumps(reports, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
