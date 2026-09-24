# Additional full-enumeration measurement

**PASS** — both hard cases completed with `--max-states 100000000 --seconds 3600` at commit `8ff3337084bc94b574eeaa6b50df9de026d01175`.

This is a new larger-budget measurement. The fixed spec-v1 600-second /10-million-state result is unchanged. The 125-minute experiment budget is not a performance SLA.

| Case | States | Candidates | Search seconds | Analysis seconds | Launch through output seconds | Actual Python OS peak bytes |
|---|---:|---:|---:|---:|---:|---:|
| hard_full_board_branching_1 | 11,936,220 | 2,382,573 | 547.396 | 770.027 | 888.584 | 6,545,989,632 |
| hard_full_board_branching_2 | 8,661,088 | 1,643,067 | 390.056 | 556.818 | 644.082 | 4,686,004,224 |

Concurrent overlap: 644.079 seconds. Case2 started with 18.09 GiB physical memory available, above the 16GiB launch condition. No safety shutdown and no CLI rerun occurred.

Independent consumer: full standard JSON syntax parse; sparse mmap row access; exact table counts; all node IDs expanded exactly once; public state_at/witness_steps/replay_branch samples; exact rational probability samples. Both inputs remain 5 versus 5 with 6 cards in each hand.

Keywords are compared as unordered ability sets, destroyed history as an unordered list per the public equivalence contract, and rng excluded. Board order, IDs, resources, stats and other fields remain exact. Initial raw ordering mismatches are preserved in referenced raw evidence.

Large graph files and raw timelines remain under `output/frontier-full-measurement/`; `summary.json` records absolute paths, byte sizes and SHA256. Input/public-doc/spec/source hashes are recorded alongside it.

Limit: this does not independently enumerate all states as an oracle. It verifies completion counters and samples of semantic behavior.
