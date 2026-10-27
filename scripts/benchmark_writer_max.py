"""Isolate numeric JSON writing using one unchanged hard candidate payload."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from svdeck.battle_env.battle import Battle
from svdeck.battle_env.battle_frontier_fast import Kernel
from svdeck.battle_env.battle_frontier_native import NativeSearch
from svdeck.battle_env.battle_frontier_export import materialize
from svdeck.battle_env.battle_frontier_export_native import encode_rows
from svdeck.battle_env.battle_frontier_io import States, dump_graph


def main() -> None:
    # AI_NOTE: All variants serialize identical stored rows; hashing reads every output byte outside the timed interval.
    folder = Path('output/turn-search-max/export')
    case = json.loads(Path('docs/evidence/turn-search-compare/independent-hard-cases.v1.json').read_text(encoding='utf-8'))[0]
    search = NativeSearch(Kernel(Battle(case['state'], case['cards'])), np.load(folder/'keys.npy'),
                          np.load(folder/'layout.npy'), np.zeros((1, 3), dtype=np.int32), 0, True, [], {})
    candidates = np.load(folder/'candidates.npy').tolist()
    rows, _ = materialize(search, candidates, backend='compiled')
    previous = States(rows.width)
    previous.data = rows.data
    encode_rows(np.frombuffer(rows.data[0], dtype='<i2').reshape((1, rows.width)))
    results = []
    for label, value in (('python', previous), ('compiled', rows)):
        path = folder/f'writer-{label}.json'
        start = perf_counter()
        dump_graph({'candidates': value}, path)
        elapsed = perf_counter()-start
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        results.append({'writer': label, 'candidate_count': len(rows), 'save_seconds': elapsed,
                        'output_bytes': path.stat().st_size, 'file_sha256': digest})
    assert results[0]['file_sha256'] == results[1]['file_sha256']
    (folder/'serialization.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
