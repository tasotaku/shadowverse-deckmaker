# Local transition cache experiment

This is an exact experimental `Kernel` replacement. It retains the complete
state graph, every legal action, every chance outcome/probability/draw tape,
and the existing endpoint frontier. It makes no score-based or dominance pruning.
The public default backend is unchanged.

Legal actions are cached by the fields that determine legality. Transition
misses call the existing fixed-slot kernel and record local writes, with relative
hand/PP/attack-bit updates. Hits apply those writes to the current full state.
Actions are decoded once into fixed slot descriptors. Cache eviction affects
only speed: action lists reset at 65,536 keys and transitions at 131,072 keys.
Summon keys include all live IDs, the remaining hand and next entity ID; random
outcomes preserve the current oldest-first enemy sequence and each exact chance.
The supported scope is exactly the existing fixed-slot kernel's scope.

## Verification

- `tests/test_battle_frontier_cache.py`: 105 PASS. Eight independent graph
  fixtures, 96 complete generated reachable-state traversals with every transition
  checked against the reference kernel, and unsupported compound-effect rejection.
- Relevant existing plus new suite: 261 PASS in 8.68 seconds.
- Strict mypy: 3 files PASS (`--follow-imports=silent` avoids checking unrelated
  imported test helpers' existing suppression comments).
- Both measured complete workloads have identical digests over all states,
  actions, choices, outcomes, candidates, probabilities and draw tapes.

## Preliminary measurements

Each row in [measurements.json](measurements.json) came from a separate Python
process. The workload is `hard_full_board_branching_1`, with board size reduced
to 3 or 4 on each side and the first five hand cards retained. Analysis has a
30-second budget; all four runs completed. The measurement includes complete
graph and candidate construction, excludes graph serialization and digest work.

| Board | States | Outcome edges | Reference | Cache | Reference peak | Cache peak |
|---|---:|---:|---:|---:|---:|---:|
| 3 vs 3 | 6,800 | 32,392 | 0.246 s | 0.248 s | 33.7 MB | 35.4 MB |
| 4 vs 4 | 105,328 | 648,357 | 5.066 s | 4.741 s | 86.4 MB | 99.8 MB |

The medium cache avoided 639,432 of 648,357 rule-transition calculations
(98.62%). Python traversal, key construction, copying and graph bookkeeping
still remain. Initial nested-tuple cache keys were slower than the reference;
predecoded action descriptors made the experiment useful. Earlier development
measurements varied from 4.07 to 4.74 seconds for the refined cache versus
5.07 to 5.32 seconds for the reference. Do not claim a stable speedup from these
single-run measurements: the root comparison harness should benchmark every
algorithm under one shared protocol. No 5-vs-5 run has been performed here.

## Reproduction

```powershell
python scripts/benchmark_frontier_cache.py --variant reference --size 4 --hand 5
python scripts/benchmark_frontier_cache.py --variant cache --size 4 --hand 5
```

For the root benchmark, each method should run in its own process. The experiment
adapter uses `unittest.mock.patch('svdeck.battle_frontier_fast.Kernel', CachedKernel)`
around the existing `analyze(..., backend='fixed-slots')` call. It restores the
symbol immediately afterward. Production integration should use explicit factory
injection or a named backend rather than a global patch.
