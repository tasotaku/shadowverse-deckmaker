# Compare current-turn candidate algorithms

The native backend now batches candidate conversion and compares packed endpoint values. The JSON and semantic digest contracts are unchanged. [Further speed measurements](evidence/turn-search-speed/README.md) compare the previous and current native versions with complete saved candidate verification, including small-workload regressions.

From the repository root, run one comparison command against a JSON list of `{id,state,cards}` cases:

```powershell
.venv/Scripts/python.exe -X utf8 -m svdeck.battle.battle_frontier_compare --cases docs/evidence/turn-search-compare/independent-small-cases.v1.json --output output/my-unused-comparison --algorithms baseline,cache,native --trials 3 --seconds 60 --max-states 1000000 --load-note "No competing benchmark workers; host reserved for this run"
```

`--output` must be unused. Each algorithm/case/trial runs in a fresh child process, serially. Order alternates by trial and case. One separate one-state warmup per case/algorithm is outside the measured trials, but fresh-worker imports, cached JIT loading and setup remain in the measured compute time. Warmup initializes signatures/cache files; it does not imply a warmed long-lived training process. The native method requires NumPy/Numba from the optional performance environment. Missing dependencies are recorded as worker errors.

- `baseline`: existing exact full graph internally, existing Python skyline.
- `cache`: the same graph/skyline with exact local transition memoization.
- `native`: compiled exact state traversal and compiled exact skyline; graph actions are reconstructed on demand.
- All three export the same **candidate** output mode. They explicitly fall back to the supported generic engine for compound effects outside the fixed-slot subset. Native numeric/dimension limits use the existing exact backend and record the reason. Overall unsupported effects are rejected; no effects are removed.
- `--seconds` and `--max-states` bound analysis, not subprocess startup or JSON saving. An exhausted budget produces `complete:false` and `cutoffs`. This is never a finished frontier or performance winner.

The `summary.json` entry point lists completion, cases, algorithms, raw trial paths, per-case median/range of compute time, median serialization time and process peak RSS. `manifest.json` pins source file hashes, Git revision, Python/dependency versions, machine, input bytes, options, scheduling note and selection rule. Each trial retains `result.json`, `report.json`, stdout and stderr. Warmup reports remain in sibling `warmup` folders and are excluded from ranking.

`timings.compute_seconds` includes case parsing/normalization, algorithm setup and cached JIT loading, enumeration, dominance pruning, candidate materialization, semantic hashing and required cleanup. The individual phase fields, `serialization_seconds`, child `worker_wall_seconds`, externally measured `process_wall_seconds`, and combined `cold_start_and_exit_seconds` are reported separately. Phase timers are diagnostic, while `compute_seconds` is measured directly rather than reconstructed by adding rounded phases. `peak_rss_bytes` is whole-process Windows PeakWorkingSetSize (or OS getrusage on Unix), including materialization/saving. It is not Python-only heap usage.

The provisional comparison rule is the lowest sum of per-case median complete compute time across the supplied suite, with equal canonical candidate digests. Overlapping aggregate observed ranges are reported as uncertain. Incomplete methods are ineligible. This is **cross-method agreement, not independent correctness proof**; the summary requires independent oracle evidence before recommendation. Run development-medium and heldout suites separately: freeze the chosen roster and rule before opening heldout timings, and report any ranking reversal. A finite suite does not prove a universal fastest algorithm.

## Read candidate results

`result.json` is standard JSON with:

- `complete`, `enumeration_complete`, `frontier_complete`, `cutoffs`, `actual_backend`, `fallback_reason`, `candidate_count`, `state_count` and explanatory `scope`.
- A self-contained Battle `record`, preserving all card definitions and the initial state.
- `encoding:"fixed-slots-v1"` and `candidates` as compact integer state rows for eligible cases; `encoding:"full-state-v1"` and full state objects for generic cases. Use the public expansion command below to decode a row, without internal imports.
- `candidate_semantic_sha256`: traversal-independent digest of candidate semantics; `candidate_digest_scope` explicitly distinguishes complete frontiers from incomplete prefixes.
- `witness_samples`: up to `--witness-samples` representative conditional paths (default 100), keyed by candidate row index. Each step contains a legal `action` and conditional `draws`. A witness is not the unconditional probability of reaching that state.
- When total states are at most `--debug-threshold` (default 1000), `debug_nodes` includes **every** full state, candidate flag, semantic key, representative witness, and all legal conditional actions/outcomes. This is the advertised full-state/debug mode; larger outputs do not claim to serialize every internal state. Set threshold to 0 for equal compact-only measurements.

Candidates preserve the public endpoint comparison: winner; ordered follower behavior/traits including keywords, evolution, remaining attack rights, played turn and cost; own/enemy stats; leader HP and PP/EP/SEP; exact remaining hand identities. Equal endpoint representatives may differ in irrelevant history. Candidates are reachable stopping states, **not mutually selectable deterministic plans**. Random outcomes are observations, never player choices. Continue from the observed outcome through the conditional API below.

Canonical semantic keys have `winner`, `boards`, `values`, `hand`. Each board element is SHA256 of the canonical JSON frozen pair `(behavior,traits)` from the documented endpoint comparator; excluded descriptive/stat fields match that comparator. Each hand element hashes the complete entity with sorted keywords, frozen as sorted key/value pairs; hand hashes are sorted. `values` follows own leader HP, negative enemy HP, own PP/EP/SEP, then each own followed by enemy follower's attack/HP/maxHP with enemy values negated. A candidate hash is SHA256 of canonical JSON of this key (`ensure_ascii=False,sort_keys=True,separators=(',',':')`). Sort the raw 32-byte candidate hashes, concatenate, then SHA256 to obtain `candidate_semantic_sha256`. Debug nodes expose keys to make independent comparison straightforward. Do not compare arbitrary node numbers or representative IDs as proof of candidate equivalence.

## Conditional continuation from saved results

Expand the saved root, an indexed candidate, a conditional replay path, or a full observed state using one command:

```powershell
.venv/Scripts/python.exe -X utf8 -m svdeck.battle.battle_frontier_compare --expand output/my-unused-comparison/case-000/native/trial-1/result.json --output output/root-choices.json
.venv/Scripts/python.exe -X utf8 -m svdeck.battle.battle_frontier_compare --expand output/my-unused-comparison/case-000/native/trial-1/result.json --candidate 0 --output output/candidate-choices.json
.venv/Scripts/python.exe -X utf8 -m svdeck.battle.battle_frontier_compare --expand output/my-unused-comparison/case-000/native/trial-1/result.json --state output/observed-state.json --output output/next-choices.json
```

`--candidate`, `--steps` (JSON list of `{action,draws}`), and `--state` are mutually exclusive. Omit all to start at the record root. The output has the decoded `state`, `stop:true` and `choices:[{action,outcomes:[{state,probability,draws}]}]`. Probabilities are exact rational strings summing to 1 for each action, including unfavorable outcomes and repeated draws. Save one **observed** outcome's `state` as a JSON object and pass it with `--state` to get that branch's legal continuation; different outcomes can choose different subsequent targets. `--state` accepts a supplied state under the embedded rules; use `--steps` when root reachability must be validated. No `end_turn` is executed or offered.

Conditional expansion caps a single action at 10,000 outcomes / 128 draws and raises a clear error instead of exporting a partial probability distribution. Loading a large saved result with ordinary JSON requires memory proportional to that file; long-lived training should use the in-process catalog API to avoid repeated file loading.
