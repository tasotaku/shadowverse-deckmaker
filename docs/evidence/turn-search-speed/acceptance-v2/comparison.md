# Fresh v2 complete native comparison

Fresh predecessor: e4520c044df5e8672b106f1ce29d6fd53d67458b. Delivered: ca50628d4d0d88a44b36d2b32b86a7f37e3250ef. Historical rows retain revision 61061aa8963f3b87fc759c693088eea38a2b8d4d and are not fresh timing; they are not relabeled as e4520c0.

|Workload|Evidence / version|Complete|Candidate agreement|Candidates|Compute s median [range]|Serialization s median|Process wall s median|Peak RSS MiB median|
|---|---|---:|---|---:|---:|---:|---:|---:|
|medium_3v3_target_random|predecessor|True|Exact full rows|489|1.1127 [1.0897, 1.1255]|0.0015|1.4130|123.35|
|medium_3v3_target_random|delivered|True|Exact full rows|489|1.1293 [1.1274, 1.1468]|0.0013|1.4200|125.19|
|medium_3v3_target_random|historical|True|Exact full rows|489|1.0755 [1.0541, 1.0952]|0.0014|1.3862|122.88|
|medium_3v3_summon_grant|predecessor|True|Exact full rows|1,774|1.1452 [1.1012, 1.1494]|0.0029|1.4506|124.11|
|medium_3v3_summon_grant|delivered|True|Exact full rows|1,774|1.1368 [1.1235, 1.1373]|0.0027|1.4331|127.22|
|medium_3v3_summon_grant|historical|True|Exact full rows|1,774|1.1039 [1.0799, 1.1215]|0.0032|1.3961|123.54|
|medium_4v4_order_split|predecessor|True|Exact full rows|24,974|1.5629 [1.5528, 1.6244]|0.0307|1.9055|138.11|
|medium_4v4_order_split|delivered|True|Exact full rows|24,974|1.3477 [1.3431, 1.3718]|0.0303|1.7085|146.77|
|medium_4v4_order_split|historical|True|Exact full rows|24,974|1.5152 [1.5103, 1.5199]|0.0283|1.8311|137.90|
|hard_full_board_branching_1|predecessor|True|Exact full rows|2,382,573|108.2360 [108.2360, 108.2360]|3.5055|112.0987|2317.68|
|hard_full_board_branching_1|delivered|True|Exact full rows|2,382,573|46.6978 [46.6978, 46.6978]|3.7027|50.7662|2024.86|
|hard_full_board_branching_1|historical|True|Exact full rows|2,382,573|104.4700 [104.4700, 104.4700]|3.4935|108.3448|2317.85|
|hard_full_board_branching_2|predecessor|True|Exact full rows|1,643,067|68.0691 [68.0691, 68.0691]|2.5513|70.9578|1465.60|
|hard_full_board_branching_2|delivered|True|Exact full rows|1,643,067|29.4383 [29.4383, 29.4383]|2.5456|32.3338|1295.70|
|hard_full_board_branching_2|historical|True|Exact full rows|1,643,067|68.7605 [68.7605, 68.7605]|2.3688|71.5331|1466.95|

Fresh hard compute sum: predecessor 176.305097 s; delivered 76.136095 s; delivered/predecessor 0.431843. Strict speed condition: True.

Memory is whole worker lifetime Windows PeakWorkingSetSize. Raw bytes, all trials, per-case changes and independent process observations are retained in timing-table.json, score.json and worker-schedule.json. Existing JIT caches were preserved and logged. One automatic one-state warmup per case/version is excluded.

Limitations: one trial per hard/version supports host-specific observed improvement only. Three medium trials are consecutive within each invocation; case-level version alternation does not remove within-case temporal drift. An external 100ms process observer ran identically for all fresh performance invocations. Its monotonic interval is quantized at approximately 100ms; OS start/exit times provide a second wall-clock cross-check. Peak RSS reported by the worker can be slightly lower than the observer because the worker saves its report after taking its own peak snapshot. No historical timing is used in the acceptance score.

Candidate agreement means independently computed complete integer-row multiset equality, including multiplicity, plus identical encoding, complete canonical record and witness samples across every corresponding fresh and historical output. All 15 roots were decoded with the public CLI and match; every explicitly supplied card/state fixture value is preserved. This is exact serialized-state regression equality, not a recomputed product semantic digest or an independent hard oracle. Independently decoded small candidate sets and all advertised debug states/actions/outcomes match the frozen independent small oracle.

Observed regressions: medium_3v3_target_random median compute is 1.49% slower (1.1127 to 1.1293 s). Medium median peak RSS rises 1.49%, 2.51%, and 6.27% in fixture order. Both hard cases improve compute and reduce peak RSS. These medium changes are disclosed; the fixed acceptance gate is the strictly lower complete hard compute sum.
