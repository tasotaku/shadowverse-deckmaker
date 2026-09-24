# Independent native acceptance comparison

|Workload|Version|Complete|Actual backend|Candidates|Compute s median [min, max]|Serialization s median|Process wall s median|Peak RSS MiB median|
|---|---|---:|---|---:|---:|---:|---:|---:|
|hand_none_a_b_ab|predecessor|True|native|4|1.1407 [1.1407, 1.1407]|0.0008|2.6699|124.45|
|hand_none_a_b_ab|delivered|True|native|4|0.5954 [0.5954, 0.5954]|0.0046|2.1152|109.07|
|barrier_bane_low_stack_trade|predecessor|True|native|6|1.1664 [1.1664, 1.1664]|0.0011|2.6819|124.50|
|barrier_bane_low_stack_trade|delivered|True|native|6|0.5458 [0.5458, 0.5458]|0.0056|2.0438|109.38|
|different_enemy_abilities|predecessor|True|native|3|1.1435 [1.1435, 1.1435]|0.0006|2.7028|124.81|
|different_enemy_abilities|delivered|True|native|3|0.5321 [0.5321, 0.5321]|0.0043|2.0248|109.62|
|large_attack_health_tradeoff|predecessor|True|native|3|1.1685 [1.1685, 1.1685]|0.0007|2.7022|124.70|
|large_attack_health_tradeoff|delivered|True|native|3|0.5691 [0.5691, 0.5691]|0.0056|2.1028|109.20|
|random_bad_outcome_retained|predecessor|True|native|3|1.1473 [1.1473, 1.1473]|0.0008|2.7081|124.46|
|random_bad_outcome_retained|delivered|True|native|3|0.5388 [0.5388, 0.5388]|0.0042|2.0352|109.29|
|oldest_barrier_split_order|predecessor|True|native|6|1.1454 [1.1454, 1.1454]|0.0010|2.7127|124.51|
|oldest_barrier_split_order|delivered|True|native|6|0.5351 [0.5351, 0.5351]|0.0046|2.0534|109.46|
|summon_storm_grant_order|predecessor|True|generic|6|0.0216 [0.0216, 0.0216]|0.0010|1.4813|28.83|
|summon_storm_grant_order|delivered|True|generic|6|0.0239 [0.0239, 0.0239]|0.0012|1.4599|28.83|
|random_sequential_duplicate_outcomes|predecessor|True|generic|4|0.0157 [0.0157, 0.0157]|0.0009|1.4838|28.77|
|random_sequential_duplicate_outcomes|delivered|True|generic|4|0.0209 [0.0209, 0.0209]|0.0007|1.4600|28.68|
|independent_random_then_chosen_remove|predecessor|True|native|7|1.1496 [1.1496, 1.1496]|0.0010|2.6754|124.35|
|independent_random_then_chosen_remove|delivered|True|native|7|0.5401 [0.5401, 0.5401]|0.0054|2.0332|109.73|
|medium_3v3_target_random|predecessor|True|native|489|1.1804 [1.1648, 1.2017]|0.0014|1.5358|125.13|
|medium_3v3_target_random|delivered|True|native|489|0.5695 [0.5628, 0.5720]|0.0044|2.0407|109.98|
|medium_3v3_summon_grant|predecessor|True|native|1,774|1.1824 [1.1623, 1.1827]|0.0028|2.7493|127.07|
|medium_3v3_summon_grant|delivered|True|native|1,774|0.5827 [0.5796, 0.5829]|0.0047|2.1414|110.60|
|medium_4v4_order_split|predecessor|True|native|24,974|1.3700 [1.3501, 1.3821]|0.0310|2.9103|146.66|
|medium_4v4_order_split|delivered|True|native|24,974|0.6331 [0.6302, 0.6375]|0.0088|2.1791|120.74|
|hard_full_board_branching_1|predecessor|True|native|2,382,573|46.7468 [46.3329, 47.6205]|3.5804|50.7174|2024.85|
|hard_full_board_branching_1|delivered|True|native|2,382,573|19.2738 [19.1539, 19.4164]|0.3394|19.9275|1322.55|
|hard_full_board_branching_2|predecessor|True|native|1,643,067|31.1386 [30.9722, 31.5069]|2.5083|34.0732|1295.53|
|hard_full_board_branching_2|delivered|True|native|1,643,067|12.5581 [12.4663, 12.5882]|0.2580|13.1301|960.68|

Fresh predecessor: 47eb2ef8d843dcc7c20d13f70a2a51eabf21a087. Delivered: c178cae225e2cecc986fb88df2941391bd342c64. Source hashes/import paths are in input-manifest.json and source-provenance.json.

Hard sum of medians: predecessor 77.885375 s; delivered 31.831908 s; delivered/predecessor 0.408702. Strict speed condition: True. Sum of observed ranges: {'predecessor': [77.30508159997407, 79.12740230001509], 'delivered': [31.620230100059416, 32.004608499933966]}. Overlap: False.

Small values are single-trial descriptive observations. Per-case time/RSS regressions appear in score.json. Whole-worker lifetime memory uses Windows PeakWorkingSetSize, in bytes in JSON and MiB here. All phase, saving, worker/process wall and startup/exit timing is retained in timing-table.json.

Finite host-specific observations do not establish statistical significance, universal superiority or absolute optimality. Consecutive per-case trials may have temporal drift. The 100 ms independent observer has corresponding quantization; OS creation/exit times provide another check. Historical outputs retain ca50628d4d0d88a44b36d2b32b86a7f37e3250ef provenance and supply serialized-output regression evidence only; historical timings are excluded.

All 28 normal case/version groups completed with empty cutoffs. Requested algorithm is native throughout. Seven small cases and every medium/hard case have actual_backend=native; two small compound cases use the documented generic fallback in both versions. F1 native-only wording is a v1 TEST_SPEC_ISSUE, not missing candidate output.

Candidate agreement: 9/9 small exact candidate sets and all 49 debug states, all advertised legal conditional distributions, and all 42 saved candidate rows decoded via --candidate match the independent oracle. All 42 published witness samples replayed, including two adaptive branches. Every one of the 41 medium/hard fresh and pinned historical saved outputs matched complete integer-row multisets including duplicates, encoding, canonical complete record, and witness serialization. This is serialized-state regression equality, not a new hard independent oracle or independently recomputed product digest. See rows.json and row-comparisons.json.

|Case|Compute new/old|Time regression|Peak RSS new/old|Memory regression|
|---|---:|---|---:|---|
|hand_none_a_b_ab|0.5219|False|0.8765|False|
|barrier_bane_low_stack_trade|0.4680|False|0.8786|False|
|different_enemy_abilities|0.4654|False|0.8783|False|
|large_attack_health_tradeoff|0.4871|False|0.8758|False|
|random_bad_outcome_retained|0.4696|False|0.8781|False|
|oldest_barrier_split_order|0.4672|False|0.8792|False|
|summon_storm_grant_order|1.1054|True|0.9999|False|
|random_sequential_duplicate_outcomes|1.3330|True|0.9967|False|
|independent_random_then_chosen_remove|0.4698|False|0.8824|False|
|medium_3v3_target_random|0.4824|False|0.8789|False|
|medium_3v3_summon_grant|0.4928|False|0.8703|False|
|medium_4v4_order_split|0.4621|False|0.8232|False|
|hard_full_board_branching_1|0.4123|False|0.6532|False|
|hard_full_board_branching_2|0.4033|False|0.7415|False|

Phase medians, seconds. Individual diagnostic timers are not added to reconstruct directly measured compute. Setup includes cached loading/JIT preparation, and process wall includes startup, output and exit.

|Case|Version|Algorithm setup|Enumeration|Pruning|Materialization|Cleanup|Serialization|Startup/exit|Process wall|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|medium_3v3_target_random|predecessor|1.1079|0.0007|0.0136|0.0273|0.0224|0.0014|0.3325|1.5358|
|medium_3v3_target_random|delivered|0.3988|0.0004|0.0852|0.0595|0.0169|0.0044|1.4733|2.0407|
|medium_3v3_summon_grant|predecessor|1.0921|0.0018|0.0150|0.0376|0.0221|0.0028|1.5636|2.7493|
|medium_3v3_summon_grant|delivered|0.4051|0.0010|0.0865|0.0621|0.0220|0.0047|1.5532|2.1414|
|medium_4v4_order_split|predecessor|1.1104|0.0437|0.0245|0.1553|0.0321|0.0310|1.5097|2.9103|
|medium_4v4_order_split|delivered|0.4026|0.0215|0.0958|0.0878|0.0182|0.0088|1.5329|2.1791|
|hard_full_board_branching_1|predecessor|1.0698|26.2064|5.1961|14.3026|0.0730|3.5804|0.3409|50.7174|
|hard_full_board_branching_1|delivered|0.3926|11.8091|4.4401|2.5553|0.0765|0.3394|0.3276|19.9275|
|hard_full_board_branching_2|predecessor|1.1027|17.5081|2.9368|9.5862|0.0593|2.5083|0.3551|34.0732|
|hard_full_board_branching_2|delivered|0.3891|7.6997|2.6026|1.7661|0.0580|0.2580|0.3137|13.1301|

Independent OS observer: all 76 normal warmup/trial workers retain monotonic first/last observations and measured PeakWorkingSet. 8 OS exit timestamps were unavailable; external-crosschecks.json discloses these limits and the 100 ms observation resolution. Python launchers add separate startup time. Raw process logs retain original values.

Development audit: four distinct optimization families plus rejected alternatives are retained, with 68 final manifest source/artifact hashes matching. Actual comparable-workload NRT allocation calls are 297,893 predecessor versus 255 delivered; frees match. These are Numba allocation/MemInfo counts, not bytes or total native allocation traffic. Both versions have raw profiles and whole-process peaks. Enumeration remains the largest phase. See development-audit.json and ../development/README.md.
