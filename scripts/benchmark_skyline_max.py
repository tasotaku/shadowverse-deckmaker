"""Compare exact skyline component variants on the same saved reachable states."""
from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

from svdeck.battle.battle import Battle
from svdeck.battle.battle_frontier_fast import Kernel


def main() -> None:
    # AI_NOTE: Snapshot module identity and hash while independently checking every returned candidate index and its order.
    name = sys.argv[1]
    folder = Path('output/turn-search-max/skyline')
    source = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('src/svdeck/battle/battle_frontier_skyline.py')
    spec = importlib.util.spec_from_file_location('svdeck.max_skyline_'+name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    saved = Path('output/turn-search-max/export')
    keys, layout = np.load(saved/'keys.npy'), np.load(saved/'layout.npy')
    expected = np.load(saved/'candidates.npy')
    case = json.loads(Path('docs/evidence/turn-search-compare/independent-hard-cases.v1.json').read_text(encoding='utf-8'))[0]
    kernel = Kernel(Battle(case['state'], case['cards']))
    module.frontier(kernel, keys[:1], layout, float('inf'))
    gc.collect()
    start = perf_counter()
    candidates, complete = module.frontier(kernel, keys, layout, float('inf'))
    elapsed = perf_counter()-start
    actual = np.array(candidates, dtype=np.int64)
    assert complete and np.array_equal(actual, expected)
    from svdeck.battle.battle_frontier_compare import peak_memory
    result = {'variant': name, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'candidate_count': len(candidates), 'seconds': elapsed,
              'peak_memory': peak_memory(), 'same_all_ordered_indices': True,
              'indices_sha256': hashlib.sha256(actual.tobytes()).hexdigest()}
    (folder/(name+'.json')).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
