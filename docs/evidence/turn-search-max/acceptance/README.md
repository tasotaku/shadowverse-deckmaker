# Acceptance stopped: delivered snapshot withdrawn

Verdict: **INCOMPLETE**. One T1 journey began at 2026-09-24T20:15:03.185206+00:00 and stopped by 2026-09-24T20:18:15.2917622+00:00. The parent withdrew delivered a6dddc5084d2eebee99a8ecd02a321eab0593998 before medium/hard timing began. No product failure was supplied to or diagnosed by this independent executor. The timer was not reset, no trial retried, and no production source/diff or development ledger read.

Completed: nine delivered plus nine predecessor small trials, independent oracle state/action/outcome comparison, all 42 saved candidate decodes, all 42 public witness replays, two adaptive branch continuations and an explicit max-states=1 hard incomplete diagnostic. All completed checks passed. This cannot establish the unrun criteria.

|Small case|Predecessor compute s|Delivered compute s|Old RSS MiB|New RSS MiB|
|---|---:|---:|---:|---:|
|hand_none_a_b_ab|1.205420|0.539050|124.473|109.074|
|barrier_bane_low_stack_trade|1.200559|0.546888|124.754|109.305|
|different_enemy_abilities|1.149786|0.546654|124.398|109.664|
|large_attack_health_tradeoff|1.160744|0.533012|124.551|109.379|
|random_bad_outcome_retained|1.151071|0.541442|124.637|109.297|
|oldest_barrier_split_order|1.252269|0.548049|124.809|109.551|
|summon_storm_grant_order|0.021490|0.021004|28.758|28.879|
|random_sequential_duplicate_outcomes|0.024522|0.015496|28.746|28.703|
|independent_random_then_chosen_remove|1.170184|0.534219|124.457|109.590|

Small runs have one measured trial each and are descriptive. Raw phase, serialization, worker/process wall and startup/exit timings are in [small-timing-table.json](small-timing-table.json); regression flags are in [small-regressions.json](small-regressions.json). Memory uses Windows whole-process PeakWorkingSetSize. No medium/hard medians, ranges, ratio or speed verdict were computed.

Evidence: [report](report.json), [frozen observations](observations-frozen-before-ledger.json), [oracle comparisons](observations.json), [saved candidate decoding](small-decoded-candidates.json), [public witnesses](public-witnesses.json), [adaptive branches](adaptive.json), [tiny diagnostic](tiny.json), [process schedule](worker-schedule.json), [commands](commands.jsonl), [input provenance](input-manifest.json), [pinned hashes](pinned-inputs.json), [cleanup](cleanup.json).

The host is released. Output was retained under output/turn-search-max-acceptance; a replacement acceptance needs a new fresh executor and new output location.
