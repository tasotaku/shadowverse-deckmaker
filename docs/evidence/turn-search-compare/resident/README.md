# Repeated training calls in one process

This is a separate experiment from the cold, JSON-export comparison. Each case/method owns a fresh process; it performs one one-state initialization, then three **complete** calls through the public `analyze_catalog` API. The three result objects expose all candidates and on-demand state/action decoding. They do not serialize all candidate states to JSON. Timing includes the API call, result release and an explicit `gc.collect()`; independent canonical candidate hashing is outside this timing and explicitly recorded. A real training loop need not force garbage collection on every call, so both call and cleanup times are retained separately. Whole-process peak RSS includes initialization and hashing and must not be treated as isolated per-trial memory.

All 27 calls completed. Every trial and method has the same candidate semantic digest for its case. This is cross-method agreement, additional to the independent small oracle tests.

| States | Reference median | Local cache median | Compiled median |
|---:|---:|---:|---:|
| 1,050 | 0.03137 s | 0.02959 s | 0.02933 s |
| 3,214 | 0.09888 s | 0.09032 s | 0.03645 s |
| 56,247 | 1.94491 s | 1.70427 s | 0.11259 s |

The first case is practically tied: measured ranges overlap. On the larger two, the compiled method is faster after initialization; the 56,247-state case improves about 17.3 times over reference and 15.1 times over the local cache. Native initialization costs 1.066–1.093 seconds per new process, versus 0.005–0.008 seconds for the Python methods. The cold benchmark includes this cost and can rank differently. These figures must not be combined with its JSON-output ranking.

The host was reserved for this experiment after T1 correctness calculations finished and before T2 timed workers started. Each adjacent JSON retains all three trial times, complete flags, candidate digests, exact source/environment manifest, initialization, verification time, and peak-memory measurement.

Reproduce from the repository root:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/benchmark_frontier_resident.py --cases docs/evidence/turn-search-compare/independent-medium-cases.v1.json --output output/unused-resident-comparison
```
