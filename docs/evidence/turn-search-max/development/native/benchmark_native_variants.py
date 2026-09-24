"""Development measurements for exact native enumeration, separate from export."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
from time import perf_counter

from svdeck.battle import Battle
from svdeck.battle_frontier_native import enumerate_native
from svdeck.combat_benchmark import peak_memory

parser = argparse.ArgumentParser()
parser.add_argument('--cases', type=Path, required=True)
parser.add_argument('--case', type=int, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--trials', type=int, default=1)
args = parser.parse_args()
case = json.loads(args.cases.read_text(encoding='utf-8'))[args.case]
battle = Battle(case['state'], case['cards'])
started = perf_counter()
enumerate_native(battle, max_states=1, seconds=60)
initialization = perf_counter()-started
trials = []
for trial in range(args.trials):
    result = enumerate_native(battle, max_states=100000000, seconds=3600)
    row = {'complete': result.complete, 'cutoffs': result.cutoffs, 'stats': result.stats,
           'keys_sha256': hashlib.sha256(result.keys).hexdigest(),
           'witness_sha256': hashlib.sha256(result.witnesses).hexdigest()}
    print(json.dumps(row), flush=True)
    trials.append(row)
    del result
    gc.collect()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps({'case': case['id'], 'initialization_seconds': initialization,
                                  'trials': trials, 'peak_memory': peak_memory()}, indent=2), encoding='utf-8')
