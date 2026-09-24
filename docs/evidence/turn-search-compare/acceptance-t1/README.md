# T1 independent acceptance: PASS

27 comparisons (9 frozen cases × 3 public methods) passed exact independently projected candidates, canonical full states, actions, outcomes and rational probability checks.

F1 PASS: all 27 case/method results have complete/enumeration_complete/frontier_complete true. Independent JSON consumer compared full canonical state sets, projected Pareto endpoint sets, every source/action/target rational distribution and exact draw paths. Per algorithm: 49 canonical states, 42 endpoints, 41 action groups, 46 outcome edges over nine cases. Oracle has 50 raw states; two destruction-history permutations canonicalize together as explicitly documented. Zero set differences; observations.json records each case and exact missing/extra sets.

F2 PASS: root state occurs in every graph; all states retain initial active player and both turn counters. Every action key is an own-turn non-end_turn action. All 126 public --candidate expansions offer stop:true. No next-turn state/action appeared in exhaustive independent comparison.

F3 PASS within fixed-suite scope: independent endpoint projector preserves ordered board behavior/current traits, intrinsic card abilities, current keywords, evolution, cost, attacks, entered_turn, own/enemy attack/health/max-health vectors, leader health, PP/EP/SEP and full remaining hand identities. Exact candidate sets match every method. 27 original hand-authored witnesses per method replay with field checks: unused/a/b/ab/ba hand alternatives, bane/barrier/EP evolution, enemy-ability choices, attack-vs-health tradeoff, ordered damage, summon/grant/face-vs-trade. Detailed resulting states and candidate membership are retained in observations.json.

F4 PASS: all 123 action groups across methods have exact rational mass 1 and match the independent oracle including unfavorable draws. Random single damage includes both 1/2 branches. Double random includes four 1/4 draw paths, including coincident lr/rl states with separate mass. All 147 debug-state witnesses replay through independent all_outcomes. All 126 saved candidate witnesses were independently replayed and compared to the public --candidate decoded state.

F5 PASS: top-level scope explicitly says candidates are not mutually selectable deterministic plans or state reachability probabilities. Full small debug conditional graph matched oracle. Public --expand/--state/--steps performed six adaptive branches: after draw 0 choose remove exposed; after draw 1 choose remove protected. Every selected action was legal in that observed branch and public replay matched its resulting state. Paths/actions/probabilities saved in followup-observations.json and adaptive-*-*.json.

F6 PASS: one max-states=1 suite run produces all nine incomplete statuses with cutoffs [states], enumeration_complete:false, candidate_digest_scope:"incomplete prefix only". Summary selection is incomplete, algorithm:null; frontier_complete:true denotes completed prefix projection and does not override overall incomplete. Unsupported-effect probe rejects all three methods with exit_code 1; retained error logs name the exact unsupported effect; no successful result silently removes it.

UX1 PASS: exactly two documented product invocations (help + one nine-case/three-method comparison) obtained normal candidate output. Remaining commands are independent validation, explicit tiny-budget test, or documented conditional expansion. No production source edits/internal product imports were needed. Exact commands retained in raw-commands.json.

UX2 PASS: ordinary json.load consumed summary.json and every result. Summary directly exposed scope, mode, case_id, algorithm, complete, trial/result/report paths; all 27 normal result/report paths resolve. Tiny summary distinguishes finished harness run_complete:true from incomplete mathematical results via group complete:false and selection incomplete. No raw graph was needed to identify completion or paths.

UX3 PASS / CLI usability GO: all interaction used CLI, no UI focus/viewport/scroll acceptance criterion applies. Product command discovery and output consumption succeeded. Largest remaining usability friction: comparator documentation describes behavior/stat exclusions conceptually; readers implementing independent endpoint keys should preserve intrinsic card keywords as abilities. This was a corrected consumer assumption, not a directly observed product defect.

Budget/scheduling: first measured comparison started at 2026-09-24T16:05:02Z; final public followup completed at 16:08:58Z. Conservative preflight-inclusive start bound 16:03:00Z used in report (under six minutes through public execution versus fixed 20 minutes). CPU released immediately after public validation; no timing claim is derived from this correctness run.

No product or UX findings. Consumer-only projection correction is retained transparently; no product test was retried.
