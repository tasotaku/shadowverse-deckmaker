"""Freeze independently observed F1-F6/U1-U3 before opening development evidence."""
from run import *

obs=read(HERE/'observations.json')
decoded=read(HERE/'small-decoded-candidates.json')
witnesses=read(HERE/'public-witnesses.json')
adaptive=read(HERE/'adaptive.json')
probabilities=read(HERE/'random-probabilities.json')
tiny=read(HERE/'tiny.json')
comparisons=read(HERE/'row-comparisons.json')
roots=read(HERE/'roots.json')
timings=read(HERE/'timing-table.json')
schedule=read(HERE/'worker-schedule.json')
score=read(HERE/'score.json')
paths=read(HERE/'summary-path-validation.json')
provenance=read(HERE/'input-manifest.json')
commands=[json.loads(line) for line in (HERE/'commands.jsonl').read_text(encoding='utf8').splitlines()]
ends=[row for row in commands if 'end' in row]
actual_order=[row['label'] for row in ends if row['label'].startswith(('medium-','hard-'))]
expected_order=['medium-0-predecessor','medium-0-delivered','medium-1-delivered','medium-1-predecessor','medium-2-predecessor','medium-2-delivered','hard-0-delivered','hard-0-predecessor','hard-1-predecessor','hard-1-delivered']
integrity=[]
for version,cwd in [('predecessor',OLD),('delivered',ROOT)]:
    before=provenance['versions'][version]
    actual={str(p.relative_to(cwd)):sha(p) for p in sorted((cwd/'src').rglob('*.py'))}
    integrity.append({'version':version,'source_hashes_unchanged':actual==before['source_hashes'],
        'revision_unchanged':subprocess.check_output(['git','-c','safe.directory='+str(cwd),'rev-parse','HEAD'],cwd=cwd,text=True).strip()==before['revision']})
save(HERE/'final-source-integrity.json',integrity)
functional={
 'F1':not obs['failures'] and all(x['exact_decoded_candidate_set'] and x['no_duplicate_semantic_candidates'] for x in decoded) and all(x['all_complete_native'] for x in timings),
 'F2':not obs['failures'] and len(obs['observations'])==9,
 'F3':all(x['all_replayed'] for x in witnesses) and adaptive['root_random_mass']=='1' and len(adaptive['branches'])==2 and all(x['exact_replay'] for x in adaptive['branches']) and len({json.dumps(x['chosen_action'],sort_keys=True) for x in adaptive['branches']})==2 and all(x['all_random_groups_mass_one'] for x in probabilities),
 'F4':len(comparisons)==5 and all(all(x['equality'].values()) and x['all_complete_native_counts_and_fixture_values'] for x in comparisons) and all(x['exact_decoded_roots_equal'] and all(y['fixture_values_preserved'] and y['stop'] and y['no_end_turn'] for y in x['observations']) for x in roots),
 'F5':score['strict_speed_pass'],
 'F6':actual_order==expected_order and schedule['all_workers_serial'] and schedule['measured_small_workers']==18 and schedule['measured_medium_workers']==18 and schedule['measured_hard_workers']==12 and schedule['excluded_performance_warmups']==10 and schedule['excluded_small_warmups']==18 and all(x['exit_code']==0 for x in ends) and tiny['complete'] is False and bool(tiny['cutoffs']) and all(all(x.values()) for x in [{'source':r['source_hashes_unchanged'],'revision':r['revision_unchanged']} for r in integrity]) and remaining()>0,
}
ux={'U1':[row['label'] for row in ends[:2]]==['help','small-delivered'],
    'U2':all(x['summary_statistics_match'] for x in timings) and all(x['report_exists'] and x['result_exists'] and x['summary_matches_raw_report'] and x['result_bytes_match'] for x in paths),
    'U3':functional['F3']}
result={'recorded_at':now(),'recorded_monotonic':time.monotonic(),'elapsed_seconds':time.monotonic()-read(HERE/'journey.json')['start_monotonic'],
        'development_ledger_opened':False,'functional':functional,'ux':ux,'actual_performance_order':actual_order,
        'evidence':{'small_oracle':'observations.json','decoded_small':'small-decoded-candidates.json','conditional':'adaptive.json','witnesses':'public-witnesses.json','random':'random-probabilities.json','tiny':'tiny.json','serialized_rows':'row-comparisons.json','roots':'roots.json','timings':'timing-table.json','score':'score.json','schedule':'worker-schedule.json','summary_paths':'summary-path-validation.json','source_integrity':'final-source-integrity.json'},
        'functional_findings':[{'id':k,'status':'FAIL','evidence':result_path} for k,result_path in []],
        'ux_findings':[],
        'cli_usability':'GO' if all(functional.values()) and all(ux.values()) else 'NO-GO',
        'largest_remaining_usability_problem':'Standard JSON expansion reloads the full saved result, so large candidate artifacts impose time and memory cost for each one-off continuation; the public docs disclose this.',
        'interaction':{'ordinary_product_invocations':2,'surface':'CLI only','clicks':None,'scrolls':None,'manual_surface_switches':None,'focus':None,'reason':'Spec has no desktop UI actions or response-time SLA.'}}
result['functional_findings']=[{'id':key,'status':'FAIL','evidence':result['evidence']} for key,value in functional.items() if not value]
result['ux_findings']=[{'id':key,'status':'FAIL'} for key,value in ux.items() if not value]
save(HERE/'independent-findings.json',result)
comparison_path=HERE/'comparison.md'
with comparison_path.open('a',encoding='utf8') as stream:
    stream.write('\nCandidate agreement: all five medium/hard cases compare every full integer row with multiplicity, the encoding, complete canonical record, product digest and witness serialization across every fresh trial and the pinned historical outputs. See row-comparisons.json, rows.json and roots.json for exact results. This is serialized-state regression equality, not a new hard independent oracle.\n')
    stream.write('\nPer-case regressions (all units and raw pairs are in timing-table.json):\n\n|Case|Compute new/old|Time regression|Peak RSS new/old|Memory regression|\n|---|---:|---|---:|---|\n')
    for row in score['per_case_changes']:
        stream.write(f"|{row['case']}|{row['compute_ratio_delivered_over_predecessor']:.4f}|{row['compute_regression']}|{row['median_rss_ratio_delivered_over_predecessor']:.4f}|{row['memory_regression']}|\n")
print(json.dumps({'functional':functional,'ux':ux,'elapsed_seconds':result['elapsed_seconds']}))
