from pathlib import Path
from datetime import datetime,timezone
import json, hashlib
ROOT=Path.cwd();BASE=ROOT/'docs/evidence/turn-search-max';OLD=BASE/'acceptance-final';OUT=BASE/'adjudication-v2';RAW=ROOT/'output/turn-search-max-acceptance-final'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
checks=[]
def check(label,ok,detail):checks.append({'check':label,'pass':bool(ok),'detail':detail})
prov=read(OLD/'input-manifest.json');timing=read(OUT/'timing-review.json')
for m in timing['manifests']:
    manifest=read(m['manifest_path']);version=m['label'].split('-')[-1]
    expected=prov['versions'][version]['source_hashes']
    check('every_manifest_source_'+m['label'],all(expected[str(Path(k))]==v for k,v in manifest['files'].items()),len(manifest['files']))
for version in ('predecessor','delivered'):
    for i in range(9):
        p=RAW/f'small-{version}/case-{i:03d}/native/trial-1/result.json';r=read(p)
        check('small_saved_result_'+version+str(i),all(r[k] is True for k in ('complete','enumeration_complete','frontier_complete')) and not r['cutoffs'] and r['candidate_count']==len(r['candidates']) and (r['actual_backend']=='native' or (i in (6,7) and r['actual_backend']=='generic' and r['encoding']=='full-state-v1' and 'compound' in r['fallback_reason'])),str(p))
for e in read(BASE/'input-manifest.v1.json')['historical_candidate_inputs']:
    if e['role']=='historical-manifest':check('historical_revision_'+e['path'],read(ROOT/e['path'])['revision']=='ca50628d4d0d88a44b36d2b32b86a7f37e3250ef',e['path'])
commands=timing['commands'];argchecks=[]
for c in commands:
    cmd=c['command'];ok=cmd[1:5]==['-X','utf8','-m','svdeck.battle_frontier_compare'] and c['PYTHONPATH']==str(Path(c['cwd'])/'src')
    if '--cases' in cmd:
        def value(flag):return cmd[cmd.index(flag)+1]
        small=c['label'].startswith('small-');tiny=c['label']=='tiny'
        ok &= value('--algorithms')=='native' and value('--seconds')=='3600' and value('--max-states')==('1' if tiny else '100000000') and value('--trials')==('1' if small or tiny else '3') and value('--debug-threshold')==('1000000' if small else '0')
    argchecks.append({'label':c['label'],'pass':bool(ok)})
check('all_original_public_commands_arguments',all(x['pass'] for x in argchecks),argchecks)
completion=read(OLD/'observation-completion.json');index=read(OLD/'raw-observation-manifest.json')
required_roles={'adaptive-consumption','completion-time','independent-all-row-consumption','independent-row-comparison','independent-small-consumption','public-witness-consumption','rational-distribution-consumption','public-root-consumption','independent-small-candidate-consumption','ordinary-summary-path-consumption','independent-timing-consumption','post-observation-ledger-audit'}
check('all_original_consumption_sealed_before_deadline',required_roles<={e['role'] for e in index['entries']} and index['sealed_monotonic']<index['original_deadline_monotonic'],{'roles':sorted(required_roles),'completed_at':completion['all_unchanged_observations_comparisons_ledger_checks_completed_at'],'seal_elapsed_seconds':index['elapsed_seconds_at_seal']})
excluded=[]
for path in index['excluded_previous_verdict_paths']:
    p=ROOT/path;excluded.append({'path':path,'exists':p.exists(),'bytes':p.stat().st_size,'sha256_hash_only':sha(p),'content_inspected':False})
check('original_reports_preserved_unread',all(x['exists'] for x in excluded),excluded)
workers=timing['workers'];details={'measured_max_abs_process_wall_delta_seconds':max(abs(w['wall_delta_seconds']) for w in workers if w['role']!='warmup'),'measured_max_abs_peak_delta_bytes':max(abs(w['memory_delta_bytes']) for w in workers if w['role']!='warmup'),'invalid_os_end_timestamps':sum(not w['valid_os_time'] for w in workers),'invalid_measured_os_end_timestamps':sum(not w['valid_os_time'] and w['role']!='warmup' for w in workers),'observer':'Original Windows Toolhelp/GetProcessMemoryInfo sampled at 100 ms; monotonic first/end observations remain valid even where OS end timestamp is invalid. No new threshold imposed.'}
check('external_process_memory_observations_present',all(w['peak_rss_bytes']>0 and w['external_monotonic_seconds']>0 and w['exit_code']==0 for w in workers),details)
regressions=[]
for old in [r for r in timing['timings'] if r['version']=='predecessor']:
    new=next(r for r in timing['timings'] if r['version']=='delivered' and r['case']==old['case'])
    regressions.append({'suite':old['suite'],'case':old['case'],'compute_ratio':new['compute_median_seconds']/old['compute_median_seconds'],'memory_ratio':new['peak_rss_median_bytes']/old['peak_rss_median_bytes'],'compute_regression':new['compute_median_seconds']>old['compute_median_seconds'],'memory_regression':new['peak_rss_median_bytes']>old['peak_rss_median_bytes']})
(OUT/'supplemental-review.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'regressions':regressions,'external_crosscheck':details,'new_product_invocations':0},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'checks':len(checks),'failures':[x for x in checks if not x['pass']],'regressions':regressions,'external':details},ensure_ascii=False))
