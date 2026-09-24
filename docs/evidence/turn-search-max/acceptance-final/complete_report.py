"""Finalize v1 without regrading its frozen backend ambiguity."""
from run import *
import statistics

timings=read(HERE/'timing-table.json');score=read(HERE/'score.json');schedule=read(HERE/'worker-schedule.json')
independent=read(HERE/'independent-findings.json');ledger=read(HERE/'development-audit.json');journey=read(HERE/'journey.json')
phase_rows=[]
for row in timings:
    if row['suite']=='small':continue
    phase_rows.append({'case':row['case'],'version':row['version'],
        'median_phases_seconds':{key:statistics.median(t.get(key,0) for t in row['all_timings']) for key in sorted({key for t in row['all_timings'] for key in t})},
        'median_cold_start_and_exit_seconds':statistics.median(row['cold_start_and_exit_seconds']),
        'median_process_wall_seconds':row['median_process_wall_seconds']})
save(HERE/'phase-table.json',phase_rows)
bad_os=[{'invocation':x['invocation'],'case':x['case'],'role':x['role'],'pid':x['pid']} for x in schedule['workers'] if not x['os_exit_timestamp_valid']]
crosschecks=[]
for worker in schedule['workers']:
    observed=worker['external_monotonic_observed_wall_seconds']; internal=worker['worker_wall_seconds']
    crosschecks.append({'invocation':worker['invocation'],'case':worker['case'],'role':worker['role'],'pid':worker['pid'],
        'external_observed_seconds':observed,'reported_worker_seconds':internal,'reported_process_seconds':worker['reported_process_wall_seconds'],
        'observed_minus_compute_seconds':observed-worker['compute_seconds'],
        'whole_process_peak_measured_independently':worker['observer_peak_working_set_bytes']>0,
        'observer_vs_report_peak_bytes':worker['observer_peak_working_set_bytes']-worker['reported_peak_rss_bytes']})
save(HERE/'external-crosschecks.json',crosschecks)
save(HERE/'harness-diagnostics.json',{
    'product_retries':0,'product_edits':0,
    'pid_reuse':'Initial summary reader classified parents by PID alone and rejected 17 instead of 18 small-predecessor workers. The raw observations retained all actual workers. Classifying parenthood by PID AND observed lifetime recovered all 76 warmup/trial workers without rerunning a product command.',
    'invalid_os_exit_timestamps':bad_os,
    'timestamp_handling':'Raw logs are unchanged. Invalid OS exit timestamps are null in the table; direct monotonic first/last observations and PeakWorkingSet are retained. The observer samples at 100 ms; this resolution and Python launcher startup explain small wall differences. No invalid negative OS duration is treated as real.',
    'supplemental_semantic_hash_diagnostic':'An optional reader attempted to reconstruct board semantic digest format from high-level public prose; its guessed board serialization did not match. Hand serialization did match. No production source was inspected and no such digest is claimed independently recomputed. These supplemental files are not equality evidence. Fixed small correctness is established from full decoded state/action/outcome semantics and exhaustive candidate expansion; medium/hard correctness evidence is exact full-row/record/encoding regression equality as the fixed spec explicitly permits.',
    'comparison_correction':'The first table label Complete incorrectly displayed complete AND actual_backend==native. It now displays actual completion separately from actual_backend; both generic-fallback cases were always complete. No raw trial value changed.'})

comparison_path=HERE/'comparison.md'
comparison_path.write_text(comparison_path.read_text(encoding='utf8').split('\nAll 28 normal case/version groups')[0],encoding='utf8')
with comparison_path.open('a',encoding='utf8') as stream:
    stream.write('\nAll 28 normal case/version groups completed with empty cutoffs. Requested algorithm is native throughout. Seven small cases and every medium/hard case have actual_backend=native; two small compound cases use the documented generic fallback in both versions. F1 native-only wording is a v1 TEST_SPEC_ISSUE, not missing candidate output.\n')
    stream.write('\nCandidate agreement: 9/9 small exact candidate sets and all 49 debug states, all advertised legal conditional distributions, and all 42 saved candidate rows decoded via --candidate match the independent oracle. All 42 published witness samples replayed, including two adaptive branches. Every one of the 41 medium/hard fresh and pinned historical saved outputs matched complete integer-row multisets including duplicates, encoding, canonical complete record, and witness serialization. This is serialized-state regression equality, not a new hard independent oracle or independently recomputed product digest. See rows.json and row-comparisons.json.\n')
    stream.write('\n|Case|Compute new/old|Time regression|Peak RSS new/old|Memory regression|\n|---|---:|---|---:|---|\n')
    for row in score['per_case_changes']:
        stream.write(f"|{row['case']}|{row['compute_ratio_delivered_over_predecessor']:.4f}|{row['compute_regression']}|{row['median_rss_ratio_delivered_over_predecessor']:.4f}|{row['memory_regression']}|\n")
    stream.write('\nPhase medians, seconds. Individual diagnostic timers are not added to reconstruct directly measured compute. Setup includes cached loading/JIT preparation, and process wall includes startup, output and exit.\n\n|Case|Version|Algorithm setup|Enumeration|Pruning|Materialization|Cleanup|Serialization|Startup/exit|Process wall|\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n')
    for row in phase_rows:
        phase=row['median_phases_seconds']
        stream.write(f"|{row['case']}|{row['version']}|{phase.get('algorithm_setup_seconds',0):.4f}|{phase.get('enumeration_seconds',0):.4f}|{phase.get('pruning_seconds',0):.4f}|{phase.get('candidate_materialization_seconds',0):.4f}|{phase.get('cleanup_seconds',0):.4f}|{phase.get('serialization_seconds',0):.4f}|{row['median_cold_start_and_exit_seconds']:.4f}|{row['median_process_wall_seconds']:.4f}|\n")
    stream.write('\nIndependent OS observer: all 76 normal warmup/trial workers retain monotonic first/last observations and measured PeakWorkingSet. '+str(len(bad_os))+' OS exit timestamps were unavailable; external-crosschecks.json discloses these limits and the 100 ms observation resolution. Python launchers add separate startup time. Raw process logs retain original values.\n')
    stream.write('\nDevelopment audit: four distinct optimization families plus rejected alternatives are retained, with 68 final manifest source/artifact hashes matching. Actual comparable-workload NRT allocation calls are 297,893 predecessor versus 255 delivered; frees match. These are Numba allocation/MemInfo counts, not bytes or total native allocation traffic. Both versions have raw profiles and whole-process peaks. Enumeration remains the largest phase. See development-audit.json and ../development/README.md.\n')

normal_complete=all(row['all_complete'] for row in timings)
small_total_states=sum(x['actual_states'] for x in read(HERE/'observations.json')['observations'])
assert small_total_states==49
spec_issue={'id':'F1_BACKEND_WORDING','type':'TEST_SPEC_ISSUE','expectation':'F1 says every normal small/medium/hard run has native backend identified.',
    'observation':'Pinned summon_storm_grant_order and random_sequential_duplicate_outcomes have algorithm=native but actual_backend=generic in BOTH versions, fallback_reason="supported compound effects require generic engine". All completion flags are true, cutoffs empty, and complete candidates/states/actions/outcomes match the independent oracle.',
    'conflict':'The fixed public docs explicitly require/describe generic fallback for compound effects. v1 does not clearly distinguish requested native algorithm from actual native execution for these pinned cases.',
    'disposition':'Preserve v1 as INCOMPLETE/TEST_SPEC_ISSUE; do not silently relax F1, relabel fallback as native, or retry product commands.'}
evidence=[
 f"F1: All 48 normal measured worker results complete, enumeration_complete and frontier_complete true with empty cutoffs; all 9 delivered candidate sets, all {small_total_states} debug states, actions/outcomes and rational distributions equal independent oracle. The actual-backend condition is ambiguous for 2 documented compound fallbacks; see test_spec_issues.",
 'F2: All nine fixed hand/ability/order/resource/attack-health fixtures pass independent complete-state skyline comparison; all 42 saved candidate rows were decoded through the public --candidate CLI with no duplicate semantic candidates.',
 'F3: All random conditional groups have exact rational mass one, including unfavorable and repeated-draw outcomes; all 42 public witnesses replay, and two observed adaptive branches choose distinct legal follow-up targets and reach identical independently replayed states.',
 'F4: 41 actual medium/hard saved outputs (30 fresh, 11 historical) have equal full integer-row multisets including multiplicity, encoding, row width, canonical complete record, and witness samples per case; all embedded fixture data and 15 public decoded roots agree. Historical source remains ca50628d4d0d88a44b36d2b32b86a7f37e3250ef.',
 f"F5: Hard sum of per-case three-trial compute medians: predecessor {score['hard_compute_sum_of_medians_seconds']['predecessor']:.9f}s, delivered {score['hard_compute_sum_of_medians_seconds']['delivered']:.9f}s; ratio {score['delivered_over_predecessor']:.9f}; strict speed criterion satisfied. Aggregate observed ranges do not overlap. All compute/phase/serialization/worker/process/startup times and whole-process PeakWorkingSet retained. Two small single-trial compute regressions disclosed.",
 'F6: Correct fixed ten-invocation version order; 18 medium and 12 hard measured workers, ten excluded performance warmups, 18 small measured workers and 18 small warmups retained. Tiny diagnostic complete=false and cutoffs=[states]. Original timer remains in use; source hashes and revisions unchanged. No product retry/edit or deletion.',
 'F7: After pre-ledger findings were saved, audited four distinct optimization families with adopted/rejected alternatives, ten enumeration raw reports, complete-state/witness consistency, 68 matching source/artifact hashes, comparable predecessor/final NRT profiles and scope-limited allocation counts. Largest remaining cost is enumeration; no absolute optimality claimed.',
 'U1: Direct commands show help then one delivered nine-case suite produces candidate output (two ordinary-use product invocations). Independent validation/performance commands are separate.',
 'U2: Every top-level summary and all 48 normal raw trial paths resolved. Corrected follow-up comparison separates actual completion/backend and supplies both versions, ranges, compute/save/wall/memory units, candidate agreement, ratio, phase medians and small regressions.',
 'U3: Public --expand, --state and --steps suffice for both adaptive branches. Documented CLI use is GO; largest remaining usability cost is reloading a large JSON result for each one-off expansion. CLI-only spec has no viewport/click/scroll/focus SLA.'
]
finish=now();stop=time.monotonic()
save(HERE/'observation-completion.json',{'all_unchanged_observations_comparisons_ledger_checks_completed_at':finish,'completed_monotonic':stop,'journey_start_monotonic':journey['start_monotonic'],'elapsed_seconds':stop-journey['start_monotonic'],'fixed_deadline_monotonic':journey['deadline_monotonic'],'within_original_60_minutes':stop<=journey['deadline_monotonic'],'product_retries':0,'product_edits':0,'spec_version':1,'v1_backend_ambiguity_preserved':True})
report={'schema_version':'user-test-report/v1','spec_id':'turn-search-native-max','spec_version':1,'spec_sha256':'5ec22b2ed753ea09648087703e21a6417d71cb2659c02114995153b3e01466b6','executor_id':'fresh-max-acceptance-final','started_at':journey['start'],'finished_at':finish,
 'scheduling':{'available_executor_slots':1,'batch_count':1},'execution_artifacts':{'preserved_workspace':str(ROOT),'completed_record':str(HERE/'observation-completion.json')},
 'tests':[{'id':'T1','batch':1,'execution_count':1,'status':'INCOMPLETE','journey_started_at':journey['start'],'journey_stopped_at':finish,'stop_reason':'impossible',
   'functional_findings':[],'ux_findings':[],'unexpected_findings':[],'test_spec_issues':[json.dumps(spec_issue,ensure_ascii=False)],'evidence':evidence,
   'cleanup':{'status':'completed','finished_at':now(),'evidence':'All owned CLI processes exited and their process handles were closed; no process kill needed. Every raw result, report, log and source checkout is retained; no data deleted or unrelated processes touched.'}}],
 'product_findings_count':0,'blind_spots':read(ROOT/'docs/evidence/turn-search-max/spec.v1.json')['coverage']['blind_spots']+[
   f"The independent observer has 100 ms resolution and {len(bad_os)} unavailable OS exit timestamps; direct monotonic worker observations and independent PeakWorkingSet remain for all 76 workers.",
   'An optional board-semantic-digest serialization experiment was not established from high-level public prose. No independently recomputed product digest is claimed; required independent full-state/action/candidate proof and permitted full-row/record regression proof are retained.',
   'Initial summary classifier/table errors were corrected only in the observation reader from immutable raw evidence; no product action or trial was retried.'
 ]}
assert normal_complete and ledger['F7'] and stop<=journey['deadline_monotonic']
save(HERE/'report.json',report)
(HERE/'README.md').write_text('# Independent acceptance v1\n\nv1 result: **INCOMPLETE — TEST_SPEC_ISSUE**, with no observed candidate-correctness failure. All required product commands and retained evidence audit completed within the original 60-minute timer. The requested native algorithm uses the documented generic fallback on two pinned compound small fixtures; the v1 native-backend wording does not unambiguously specify this case. This verdict is preserved, not silently regraded.\n\nHard complete compute median sum: **77.8854 → 31.8319 seconds** (ratio **0.40870**, 59.13% lower). All 30 fresh medium/hard trials and 11 historical outputs have exact complete row/record/encoding agreement. All nine small oracle checks and all 42 public candidate/witness checks agree. Two small single-trial compute regressions are explicitly shown in the comparison.\n\n- [Comparison and phase table](comparison.md)\n- [Contract report](report.json)\n- [Pre-ledger observations](independent-findings.json)\n- [Development evidence audit](development-audit.json)\n- [Original timer and completion](observation-completion.json)\n- [Source provenance](input-manifest.json)\n- [Observer limitations](harness-diagnostics.json)\n\nNo universal fastest/absolute optimality claim follows. Historical evidence retains its recorded ca50628d source identity and is not fresh predecessor timing.\n',encoding='utf8')
print(json.dumps({'status':'INCOMPLETE','reason':'TEST_SPEC_ISSUE','elapsed_seconds':stop-journey['start_monotonic'],'normal_complete':normal_complete,'F7':ledger['F7'],'invalid_os_exit_timestamps':len(bad_os)}))
