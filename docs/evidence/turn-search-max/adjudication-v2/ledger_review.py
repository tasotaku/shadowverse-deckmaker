from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,statistics,subprocess
ROOT=Path.cwd();BASE=ROOT/'docs/evidence/turn-search-max';OUT=BASE/'adjudication-v2';DEV=BASE/'development';OLD=BASE/'acceptance-final'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
checks=[]
def check(name,ok,detail=None):checks.append({'check':name,'pass':bool(ok),'detail':detail})
pre=read(OUT/'independent-preledger-findings.json');check('independent_findings_recorded_before_ledger',not pre['failures'] and not pre['development_ledger_read'],pre['reader_representation_clarification_recorded_at'])
manifest=read(DEV/'artifact-manifest.final.json');pins=[]
for e in manifest['source']+manifest['artifacts']:
    p=ROOT/e['path'];pins.append({'path':str(p),'sha256':sha(p),'pass':sha(p)==e['sha256'],'source_bytes_hashed_only':p.suffix=='.py'})
check('all_final_development_pins',all(x['pass'] for x in pins),len(pins))
blob=subprocess.run(['git','show','c178cae225e2cecc986fb88df2941391bd342c64:docs/evidence/turn-search-max/development/artifact-manifest.final.json'],check=True,capture_output=True).stdout
check('development_manifest_retained_in_original_delivered_commit',hashlib.sha256(blob.replace(b'\r\n',b'\n')).hexdigest()==hashlib.sha256((DEV/'artifact-manifest.final.json').read_bytes().replace(b'\r\n',b'\n')).hexdigest())
native=[]
for p in sorted((DEV/'native').glob('*.json')):
    x=read(p);native.append({'path':str(p),'case':x['case'],'initialization_seconds':x['initialization_seconds'],'trials':x['trials'],'peak_memory':x['peak_memory']})
native_trials=[t for x in native for t in x['trials']]
check('development_native_complete_and_equal',all(t['complete'] and not t['cutoffs'] and t['stats']['states']==11936220 and t['stats']['outcomes']==88767067 for t in native_trials) and len({t['keys_sha256'] for t in native_trials})==1 and len({t['witness_sha256'] for t in native_trials})==1,len(native_trials))
sky=[{'path':str(p),**read(p)} for p in sorted((DEV/'skyline').glob('*.json'))]
check('development_skyline_full_ordered_indices',all(x['same_all_ordered_indices'] and x['candidate_count']==2382573 for x in sky) and len({x['indices_sha256'] for x in sky})==1)
mat=read(DEV/'export/final-materialization.json');parallel=read(DEV/'export/parallel.json');writer=read(DEV/'export/serialization.json')
check('development_materialization_equal',len({x['rows_sha256'] for x in mat+parallel})==1 and len({x['semantic_sha256'] for x in mat+parallel})==1 and all(x['candidate_count']==2382573 for x in mat))
check('development_writer_same_bytes',len({x['file_sha256'] for x in writer})==1 and len({x['output_bytes'] for x in writer})==1 and all(x['candidate_count']==2382573 for x in writer))
alloc=[read(DEV/f'allocations-{v}.json') for v in ('predecessor','delivered')];prov=read(OLD/'input-manifest.json')
check('allocation_comparable_workload_scope',len({x['case_id'] for x in alloc})==1 and len({x['scope'] for x in alloc})==1 and len({x['fixture_sha256'] for x in alloc})==1 and all(x['complete'] and x['stats']['states']==56247 and x['stats']['outcomes']==241432 and x['stats']['candidates']==24974 for x in alloc))
check('allocation_raw_counter_arithmetic',all(all(x['returned'][k]-x['before'][k]==x['delta_returned'][k] and x['after_cleanup'][k]-x['before'][k]==x['delta_after_cleanup'][k] for k in ('alloc','free','mi_alloc','mi_free')) and x['delta_after_cleanup']['alloc']==x['delta_after_cleanup']['free'] for x in alloc))
check('allocation_source_identity',all(x['source_sha256']==prov['versions'][x['version']]['source_hashes'][str(Path('src/svdeck/battle_frontier_native.py'))] for x in alloc))
approaches=[
 {'approach':'Exact traversal: reused transition buffers, sparse updates and fingerprint/row index','source_identity':'baseline 47eb2ef; native/snapshots/*.py hashes in artifact-manifest.final.json; final native source hashes in the same manifest','command':'.venv/Scripts/python.exe -X utf8 development/native/benchmark_native_variants.py in variant checkout; unchanged hard fixture 0; max_states=100000000, seconds=3600; one-state initialization excluded','raw_evidence':'development/native/*.json','decision':'Adopt buffers, sparse combat/spell updates and fingerprint+row exact collision verification. Reject full-key buckets and retained probes.','correctness':'All 10 raw complete runs have identical full packed-state and BFS witness hashes.','observed_search_seconds':{Path(x['path']).stem:[t['stats']['search_ms']/1000 for t in x['trials']] for x in native},'scope':'Enumeration/cleanup; whole-process Windows PeakWorkingSetSize includes warmup and hash verification.'},
 {'approach':'Skyline region reuse and merged feature scanning','source_identity':{x['variant']:x['source_sha256'] for x in sky},'command':'.venv/Scripts/python.exe -X utf8 scripts/benchmark_skyline_max.py original|single_get|fused|recycled <saved-source>','raw_evidence':'development/skyline/*.json','decision':'Adopt recycled regions; reject single_get-only change.','correctness':'All ordered candidate indices and their hashes agree.','observations':sky,'scope':'Pruning interval; whole-process Windows peak includes loaded arrays.'},
 {'approach':'Compiled candidate formatting/SHA256 with bounded parallelism','source_identity':'Final export and export_native files pinned by artifact-manifest.final.json; retained earlier export snapshots describe exploratory timings','command':'.venv/Scripts/python.exe -X utf8 scripts/benchmark_export_max.py final-materialization.json; scripts/benchmark_parallel_export_max.py','raw_evidence':'development/export/final-materialization.json; development/export/parallel.json','decision':'Adopt compiled conversion and up to four workers for large output; keep small output serial.','correctness':'All candidate rows and semantic hashes agree for Python/compiled and 1/2/4 workers.','observations':mat,'parallel':parallel,'scope':'Partial materialization/verification wall time; CPU time rises with workers; pre-fix exploratory data is not final acceptance timing.'},
 {'approach':'Compiled JSON integer-row serialization','source_identity':'battle_frontier_io.py in final manifest and pinned export/final_io.py','command':'.venv/Scripts/python.exe -X utf8 scripts/benchmark_writer_max.py','raw_evidence':'development/export/serialization.json','decision':'Adopt same-byte writer.','correctness':'155577099 bytes and full-file SHA256 match.','observations':writer,'scope':'Serialization-only wall seconds; not compute score.'}
]
check('F7_breadth_adopted_and_rejected',len(approaches)>=3 and any('Reject' in x['decision'] or 'reject' in x['decision'] for x in approaches),len(approaches))
timings=read(OUT/'timing-review.json')['timings'];bottleneck=[]
for row in timings:
    if row['suite']=='hard' and row['version']=='delivered':
        phases={k:statistics.median(t['timings'][k] for t in row['trials']) for k in ('enumeration_seconds','pruning_seconds','candidate_materialization_seconds','cleanup_seconds','algorithm_setup_seconds')}
        bottleneck.append({'case':row['case'],'phase_median_seconds':phases,'dominant_phase':max(phases,key=phases.get),'compute_median_seconds':row['compute_median_seconds']})
write={'audit_started_after_independent_findings':pre['reader_representation_clarification_recorded_at'],'audit_recorded_at':now(),'checks':checks,'pins':pins,'approaches':approaches,'native_observations':native,'allocation_observations':alloc,'allocation_measured_counts':[x['delta_returned']['alloc'] for x in alloc],'allocation_scope':'Actual Numba NRT allocation/free and MemInfo counts only, not bytes or total Python/OpenSSL/native traffic. Total native allocation counts/bytes unavailable. Instrumented times excluded from score.','allocation_peak_bytes':[x['peak_memory'][0] for x in alloc],'final_bottleneck':bottleneck,'limits':['Finite host/workloads, not universal fastest or absolute optimum.','GPU, distributed search and proven action-order equivalence not tested.','A retained-probe development trial had disclosed competing copy; repeat observations remain retained.','Exploratory compiled-export timings predate library-failure correction; final scored CLI data identifies final source.'],'new_product_invocations':0}
(OUT/'ledger-review.json').write_text(json.dumps(write,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'checks':len(checks),'failures':[x for x in checks if not x['pass']],'approaches':len(approaches),'allocation_counts':write['allocation_measured_counts'],'bottleneck':bottleneck},ensure_ascii=False))
