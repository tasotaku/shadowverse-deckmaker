"""Read only retained evidence and hash source bytes; no production source inspection."""
from run import *
import statistics

assert (HERE/'independent-findings.json').exists()
dev=ROOT/'docs/evidence/turn-search-max/development'
manifest=read(dev/'artifact-manifest.final.json')
checks=[]
for entry in manifest['source']+manifest['artifacts']:
    path=ROOT/entry['path']
    checks.append({'path':entry['path'],'exists':path.exists(),'matches':path.exists() and sha(path)==entry['sha256']})
alloc=[read(dev/f'allocations-{version}.json') for version in ['predecessor','delivered']]
allocation_checks={'same_workload':alloc[0]['case_id']==alloc[1]['case_id'] and alloc[0]['fixture_sha256']==alloc[1]['fixture_sha256'],
    'same_scope':alloc[0]['scope']==alloc[1]['scope'],
    'same_states_outcomes_candidates':all(alloc[0]['stats'][key]==alloc[1]['stats'][key] for key in ['states','outcomes','candidates']),
    'complete':all(x['complete'] for x in alloc),
    'deltas_arithmetically_correct':all(x['delta_returned'][key]==x['returned'][key]-x['before'][key] for x in alloc for key in ['alloc','free','mi_alloc','mi_free']),
    'no_nrt_imbalance_after_cleanup':all(x['delta_after_cleanup']['alloc']==x['delta_after_cleanup']['free'] and x['delta_after_cleanup']['mi_alloc']==x['delta_after_cleanup']['mi_free'] for x in alloc),
    'source_identity_matches_preflight':all(x['source_sha256']==read(HERE/'input-manifest.json')['versions'][x['version']]['source_hashes'][str(Path('src/svdeck/battle_frontier_native.py'))] for x in alloc)}
native=[]
for path in sorted((dev/'native').glob('*.json')):
    data=read(path)
    if 'trials' in data:
        native.append({'path':str(path),'peak_memory':data['peak_memory'],'trials':data['trials']})
native_equal=all(trial['complete'] and not trial['cutoffs'] and trial['keys_sha256']==native[0]['trials'][0]['keys_sha256'] and trial['witness_sha256']==native[0]['trials'][0]['witness_sha256'] for row in native for trial in row['trials'])
approaches=[
 {'approach':'Transition allocation reuse, sparse updates and exact fingerprint index','decision':'Adopt buffers/sparse updates/fingerprint; reject full-key buckets and retained probes','source_identity':'native/snapshots hashes in artifact-manifest.json; baseline 47eb2ef; selected source pinned in artifact-manifest.final.json','command':'development/native/benchmark_native_variants.py in each variant checkout; hard fixture 0, max_states=100000000, seconds=3600 after one-state initialization','evidence':'native/*.json and native/README.md','correctness':'all complete packed-state and BFS witness byte digests agree','scope':'enumeration/cleanup timing; whole-process PeakWorkingSetSize includes initialization and digest verification'},
 {'approach':'Reuse removed skyline regions','decision':'Adopt recycled; reject dictionary single_get','source_identity':'source_sha256 per skyline JSON, snapshots pinned in manifests','command':'scripts/benchmark_skyline_max.py original|single_get|fused|recycled <saved-source>','evidence':'skyline/*.json','correctness':'same_all_ordered_indices=true and matching complete index digest','scope':'pruning timing; Windows whole-process peak includes loaded state arrays'},
 {'approach':'Compiled candidate formatting and SHA256, bounded thread parallelism','decision':'Adopt compiled formatting and up to four workers on large output; smaller output stays serial','source_identity':'source hashes pinned by final manifest; original partial measurements predate crypto failure fix as ledger explicitly discloses','command':'scripts/benchmark_export_max.py final-materialization.json; scripts/benchmark_parallel_export_max.py','evidence':'export/final-materialization.json and export/parallel.json','correctness':'complete row and semantic digests agree across Python/compiled and 1/2/4 workers','scope':'partial materialization/verification wall seconds and process CPU seconds; not scored public CLI total'},
 {'approach':'Compiled plain JSON integer-row writer','decision':'Adopt faster same-byte output writer','source_identity':'battle_frontier_io.py hash in final manifest','command':'scripts/benchmark_writer_max.py','evidence':'export/serialization.json','correctness':'same 155577099 output bytes and SHA256','scope':'serialization wall seconds only; not total compute'}
]
record={'audit_recorded_at':now(),'independent_findings_recorded_before_ledger':read(HERE/'independent-findings.json')['development_ledger_opened'] is False,
 'final_manifest_checks':checks,'all_manifest_hashes_match':all(x['matches'] for x in checks),'native_complete_state_witness_equality':native_equal,'native_variants':native,
 'allocation_checks':allocation_checks,'measured_nrt_allocations':[x['delta_returned']['alloc'] for x in alloc],
 'allocation_scope':'Actual Numba NRT allocation/MemInfo calls, not bytes, not total Python/OpenSSL/native allocation traffic. Total native allocation traffic unavailable.',
 'allocation_whole_process_peak_bytes':[x['peak_memory'][0] for x in alloc],'distinct_approaches':approaches,
 'limitations':['Development partial timings are exploratory and not substituted for fresh CLI trials.','One retained-probe development trial had a disclosed brief competing copy; repeat evidence retained.','Compiled-export exploratory timings predate the failure-handling fix; fresh final CLI measurements are authoritative.','GPU/distributed search and proven action-order equivalence remain untested; finite breadth is not absolute optimality.'],
 'F7':all(x['matches'] for x in checks) and all(allocation_checks.values()) and native_equal and len(approaches)>=3}
save(HERE/'development-audit.json',record)
print(json.dumps({'F7':record['F7'],'manifest_entries':len(checks),'allocation_checks':allocation_checks,'native_runs':len(native),'distinct_approaches':len(approaches)}))
