"""Fresh deterministic review. Standard library only; no product imports/execution."""
from pathlib import Path
from collections import Counter, defaultdict
from fractions import Fraction
from datetime import datetime, timezone
import copy, hashlib, json, statistics, subprocess, time

ROOT=Path.cwd(); BASE=ROOT/'docs/evidence/turn-search-max'; OLD=BASE/'acceptance-final'; OUT=BASE/'adjudication-v2'; RAW=ROOT/'output/turn-search-max-acceptance-final'
def now(): return datetime.now(timezone.utc).isoformat()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def write(name,data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
checks=[]
def check(label,ok,detail=None):
    checks.append({'check':label,'pass':bool(ok),'detail':detail})
    if not ok: print('CHECK_FAILED',label,detail,flush=True)
def statekey(s):
    s=copy.deepcopy(s);s.pop('rng',None)
    for p in s['players']:
        p['destroyed']=sorted(p.get('destroyed',[]))
        for z in ('hand','board','deck'):
            for e in p[z]:
                if isinstance(e,dict):e['keywords']=sorted(e.get('keywords',[]))
    return canon(s)
def endpoint(s,cards):
    own=s['active_player'];ps=[s['players'][own],s['players'][1-own]];boards=[]
    values=[ps[0]['health'],-ps[1]['health'],ps[0]['pp'],ps[0]['ep'],ps[0]['sep']]
    for side,p in enumerate(ps):
        b=[]
        for e in p['board']:
            behavior={k:v for k,v in cards[e['card_id']].items() if k not in {'id','card_id','name','text','class_name','synthetic','cost','attack','health','max_health'}}
            if 'keywords' in behavior:behavior['keywords']=sorted(behavior['keywords'])
            traits={k:v for k,v in e.items() if k not in {'id','card_id','name','attack','health','max_health'}}
            traits['keywords']=sorted(traits.get('keywords',[]));b.append([behavior,traits])
            values.extend((1 if side==0 else -1)*e[k] for k in ('attack','health','max_health'))
        boards.append(b)
    hands=[]
    for e in ps[0]['hand']:
        e=copy.deepcopy(e);e['keywords']=sorted(e.get('keywords',[]));hands.append(canon(e))
    return canon([s['winner'],boards]),tuple(values),tuple(sorted(hands))
def frontier(keys):
    keys=set(keys)
    return {x for x in keys if not any(x!=y and x[0]==y[0] and all(a>=b for a,b in zip(y[1],x[1])) and Counter(y[2])>=Counter(x[2]) for y in keys)}

start=now();start_clock=time.monotonic()
if not (OUT/'review-start.json').exists():write('review-start.json',{'started_at':start,'started_monotonic':start_clock,'new_product_invocations':0,'role':'fresh-independent-retained-observation-adjudicator'})
index_path=OLD/'raw-observation-manifest.json';index=read(index_path)
check('sealed_inventory_identity',sha(index_path)=='c095f69095f59a1e7279f0b42ef7a6fdf7e9fc01bb8a8c7166422a5da29f5906')
check('v2_spec_identity',sha(BASE/'spec.v2.json')=='2220a6440f20dfa617f452fc9bc49f9ce73d1856ada3b468ab488c64b0fd933e')
check('v2_protocol_identity',sha(BASE/'design-input-manifest.v2.json')=='7a5faeb7283528b1190f6163c220138e000afde391bb6b6a5674a9f80477d310')
inventory=[]
for e in index['entries']:
    p=ROOT/e['path'];actual=sha(p);ok=p.stat().st_size==e['bytes'] and actual==e['sha256']
    inventory.append({'path':str(p),'bytes':p.stat().st_size,'sha256':actual,'pass':ok})
check('all_sealed_files',all(x['pass'] for x in inventory),{'files':len(inventory),'bytes':sum(x['bytes'] for x in inventory)})
pins=read(BASE/'input-manifest.v1.json');pinchecks=[]
for category in ('inputs','fixtures','independent_oracle_inputs','historical_candidate_inputs'):
    for e in pins[category]:
        actual=sha(ROOT/e['path']);pinchecks.append({'category':category,'path':e['path'],'sha256':actual,'pass':actual==e['sha256']})
check('all_fixed_inputs',all(x['pass'] for x in pinchecks),len(pinchecks))
provenance=read(OLD/'input-manifest.json');sourcechecks=[]
for version,record in provenance['versions'].items():
    directory=ROOT if version=='delivered' else ROOT/'output/max-baseline-worktree'
    revision='c178cae225e2cecc986fb88df2941391bd342c64' if version=='delivered' else '47eb2ef8d843dcc7c20d13f70a2a51eabf21a087'
    check('revision_'+version,record['revision']==revision)
    check('module_path_'+version,Path(record['provenance']['module_file'])==directory/'src/svdeck/battle_frontier_compare.py')
    for path,h in record['source_hashes'].items():
        actual=sha(directory/path)
        blob=subprocess.run(['git','show',revision+':'+path.replace('\\','/')],cwd=ROOT,check=True,capture_output=True).stdout
        blobs=[hashlib.sha256(blob).hexdigest(),hashlib.sha256(blob.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')).hexdigest()]
        sourcechecks.append({'version':version,'path':path,'pinned':h,'current_sha256':actual,'current_equal':actual==h,'git_blob_or_crlf_equal':h in blobs})
check('source_current_and_original_git_identity',all(x['current_equal'] and x['git_blob_or_crlf_equal'] for x in sourcechecks),len(sourcechecks))
check('dependencies_same',provenance['versions']['predecessor']['provenance']['dependencies']==provenance['versions']['delivered']['provenance']['dependencies'])
check('original_source_after_unchanged',all(x['source_hashes_unchanged'] and x['revision_unchanged'] for x in read(OLD/'final-source-integrity.json')))
journey=read(OLD/'journey.json');completion=read(OLD/'observation-completion.json')
check('original_clock_and_seal_within_budget',journey['deadline_monotonic']-journey['start_monotonic']==3600 and completion['completed_monotonic']<=index['sealed_monotonic']<journey['deadline_monotonic'] and completion['elapsed_seconds']==completion['completed_monotonic']-journey['start_monotonic'],{'completed_seconds':completion['elapsed_seconds'],'sealed_seconds':index['sealed_monotonic']-journey['start_monotonic']})
write('integrity.json',{'recorded_at':now(),'inventory':inventory,'fixed_inputs':pinchecks,'source_checks':sourcechecks,'completion':completion,'checks':checks})
print('INTEGRITY_DONE',len(checks),flush=True)

fixtures={s:read(ROOT/f'docs/evidence/turn-search-compare/independent-{s}-cases.v1.json') for s in ('small','medium','hard')}
commands=[json.loads(x) for x in (OLD/'commands.jsonl').read_text(encoding='utf-8').splitlines()]
starts=[c for c in commands if 'end_monotonic' not in c];ends=[c for c in commands if 'end_monotonic' in c]
check('command_roster_unique_complete',len(starts)==len(ends)==len({c['label'] for c in starts}) and all(c['exit_code']==0 and c['end_monotonic']<=completion['completed_monotonic'] for c in ends),len(ends))
expected_order=['medium-0-predecessor','medium-0-delivered','medium-1-delivered','medium-1-predecessor','medium-2-predecessor','medium-2-delivered','hard-0-delivered','hard-0-predecessor','hard-1-predecessor','hard-1-delivered']
check('fixed_performance_invocation_order',[c['label'] for c in starts if c['label'].startswith(('medium-','hard-'))]==expected_order)
check('all_invocations_serial',all(a['end_monotonic']<=b['start_monotonic'] for a,b in zip(ends,starts[1:])))
check('U1_help_then_one_suite',[c['label'] for c in starts[:2]]==['help','small-delivered'])
timings=[];workers=[];backends=[];manifests=[]
for suite,n in [('small',9),('medium',3),('hard',2)]:
  for version in ['predecessor','delivered']:
    for idx,case in enumerate(fixtures[suite]):
      label=f'small-{version}' if suite=='small' else f'{suite}-{idx}-{version}';base=RAW/label;ci=idx if suite=='small' else 0
      manifest=read(base/'manifest.json');summary=read(base/'summary.json');group=next(g for g in summary['groups'] if g['case_id']==case['id']);trials=[]
      check('manifest_'+label+'_'+str(idx),manifest['revision']==provenance['versions'][version]['revision'] and manifest['algorithms']==['native'] and manifest['trials']==(1 if suite=='small' else 3) and summary['run_complete'])
      manifests.append({'label':label,'manifest_path':str(base/'manifest.json'),'module_path':provenance['versions'][version]['provenance']['module_file'],'revision':manifest['revision'],'options':manifest['options'],'input_sha256':manifest['input_sha256']})
      check('fixture_subset_'+label+'_'+str(idx),read(manifest['input_path'])==(fixtures[suite] if suite=='small' else [case]) and sha(manifest['input_path'])==manifest['input_sha256'])
      expected_options={'seconds':3600.0,'max_states':100000000,'debug_threshold':1000000 if suite=='small' else 0,'witness_samples':100}
      check('options_'+label+'_'+str(idx),manifest['options']==expected_options)
      for entry in group['trials']:
        report=read(base/entry['report_path']);check('summary_raw_link_'+label+'_'+str(idx)+'_'+str(report['trial']),entry==report and (base/entry['result_path']).stat().st_size==report['result_bytes'])
        check('normal_complete_'+label+'_'+str(idx)+'_'+str(report['trial']),all(report[k] is True for k in ('complete','enumeration_complete','frontier_complete')) and not report['cutoffs'] and report['exit_code']==0 and not report['warmup'] and report['algorithm']=='native')
        allowed=report['actual_backend']=='native' or (suite=='small' and idx in (6,7) and report['actual_backend']=='generic' and 'compound' in report['fallback_reason'])
        check('backend_'+label+'_'+str(idx)+'_'+str(report['trial']),allowed)
        backends.append({'label':label,'case':case['id'],'trial':report['trial'],'actual_backend':report['actual_backend'],'fallback_reason':report['fallback_reason']})
        trials.append(report)
      check('all_trial_numbers_'+label+'_'+str(idx),[r['trial'] for r in trials]==list(range(1,(1 if suite=='small' else 3)+1)))
      compute=[r['timings']['compute_seconds'] for r in trials];serial=[r['timings']['serialization_seconds'] for r in trials];rss=[r['peak_rss_bytes'] for r in trials]
      check('summary_aggregates_'+label+'_'+str(idx),group['median_compute_seconds']==statistics.median(compute) and group['compute_range_seconds']==[min(compute),max(compute)] and group['median_serialization_seconds']==statistics.median(serial) and group['median_peak_rss_bytes']==statistics.median(rss))
      timings.append({'suite':suite,'case':case['id'],'index':idx,'version':version,'label':label,'compute_median_seconds':statistics.median(compute),'compute_range_seconds':[min(compute),max(compute)],'serialization_median_seconds':statistics.median(serial),'peak_rss_median_bytes':statistics.median(rss),'candidate_count':trials[0]['candidate_count'],'actual_backend':trials[0]['actual_backend'],'raw_reports':[str(base/e['report_path']) for e in group['trials']],'trials':trials})
      raw_procs=read(OLD/(label+'.processes.json'));proc=[p for p in raw_procs if p['name'].lower()=='python.exe'];leaves=[p for p in proc if not any(q['parent_pid']==p['pid'] and p['first_seen_monotonic']<=q['first_seen_monotonic']<=p['observed_monotonic_end'] for q in proc)];leaves.sort(key=lambda p:p['os_start_epoch'])
      check('raw_leaf_count_'+label+'_'+str(idx),len(leaves)==(18 if suite=='small' else 4))
      selected=leaves[idx*2:idx*2+2] if suite=='small' else leaves
      warm=read(base/f'case-{ci:03d}/native/warmup/report.json');check('warmup_'+label+'_'+str(idx),warm['warmup'] and warm['options']['max_states']==1)
      for wi,(p,r) in enumerate(zip(selected,[warm]+trials)):
        wall=p['observed_monotonic_end']-p['first_seen_monotonic'];valid_os=p['os_end_epoch']>=p['os_start_epoch']
        workers.append({'suite':suite,'label':label,'case':case['id'],'role':'warmup' if wi==0 else f'trial-{wi}',**p,'valid_os_time':valid_os,'external_monotonic_seconds':wall,'reported_process_seconds':r['process_wall_seconds'],'reported_worker_seconds':r['timings']['worker_wall_seconds'],'reported_peak_bytes':r['peak_rss_bytes'],'wall_delta_seconds':wall-r['process_wall_seconds'],'memory_delta_bytes':p['peak_rss_bytes']-r['peak_rss_bytes']})
      check('trial_timing_memory_'+label+'_'+str(idx),all(r['peak_rss_bytes']>0 and r['memory_method']=='Windows PeakWorkingSetSize' and r['memory_scope']=='whole worker lifetime' and r['timings']['compute_seconds']+r['timings']['serialization_seconds']<=r['timings']['worker_wall_seconds']+0.01 and r['process_wall_seconds']>=r['timings']['worker_wall_seconds'] for r in trials))
workers.sort(key=lambda p:p['first_seen_monotonic'])
check('raw_worker_serial',all(a['os_end_epoch']<=b['os_start_epoch'] if a['valid_os_time'] else a['observed_monotonic_end']<=b['first_seen_monotonic']+0.11 for a,b in zip(workers,workers[1:])))
check('worker_roster',Counter((p['suite'],p['role']=='warmup') for p in workers)=={('small',True):18,('small',False):18,('medium',True):6,('medium',False):18,('hard',True):4,('hard',False):12})
tiny=read(RAW/'tiny/case-000/native/trial-1/result.json');check('tiny_explicit_incomplete',tiny['complete'] is False and bool(tiny['cutoffs']))
totals={v:sum(r['compute_median_seconds'] for r in timings if r['suite']=='hard' and r['version']==v) for v in ('predecessor','delivered')};ranges={v:[sum(r['compute_range_seconds'][i] for r in timings if r['suite']=='hard' and r['version']==v) for i in range(2)] for v in totals}
check('F5_hard_score',totals['delivered']<totals['predecessor'],totals)
score={'sum_of_hard_medians_seconds':totals,'delivered_predecessor_ratio':totals['delivered']/totals['predecessor'],'aggregate_ranges_seconds':ranges,'ranges_overlap':max(v[0] for v in ranges.values())<=min(v[1] for v in ranges.values())}
write('timing-review.json',{'score':score,'timings':timings,'workers':workers,'manifests':manifests,'backends':backends,'commands':ends,'checks':checks})
print('TIMING_DONE',score,flush=True)

oracles=read(ROOT/'docs/evidence/turn-search-compare/acceptance-t1/oracle.json');public_witnesses=read(OLD/'public-witnesses.json');small=[]
for idx,(case,oracle) in enumerate(zip(fixtures['small'],oracles)):
    path=RAW/f'small-delivered/case-{idx:03d}/native/trial-1/result.json';r=read(path);nodes=r['debug_nodes'];states={x['id']:x['state'] for x in oracle['states']};oracle_keys={statekey(s) for s in states.values()}
    expected=frontier(endpoint(s,case['cards']) for s in states.values());actual={endpoint(n['state'],case['cards']) for n in nodes if n['candidate']}
    check('small_all_states_'+case['id'],{statekey(n['state']) for n in nodes}==oracle_keys)
    check('small_candidates_'+case['id'],actual==expected)
    expected_edges=defaultdict(Fraction);observed_edges=defaultdict(Fraction)
    for e in oracle['edges']:expected_edges[(statekey(states[e['source']]),canon(e['action']),statekey(states[e['target']]),tuple(e['choices']))]+=Fraction(e['probability'])
    masses=[];groups=0
    for n in nodes:
        for choice in n['conditional']:
            groups+=1;masses.append(sum(Fraction(o['probability']) for o in choice['outcomes'])==1)
            for o in choice['outcomes']:observed_edges[(statekey(n['state']),canon(choice['action']),statekey(o['state']),tuple(o['draws']))]+=Fraction(o['probability'])
    check('small_all_actions_draws_outcomes_'+case['id'],dict(expected_edges)==dict(observed_edges))
    check('small_all_probability_masses_'+case['id'],all(masses))
    def replay(steps):
        cursor=statekey(states[oracle['root']])
        for step in steps:
            targets={k[2] for k in expected_edges if k[0]==cursor and k[1]==canon(step['action']) and k[3]==tuple(step.get('draws',step.get('choices',[])))}
            assert len(targets)==1, (case['id'],step,len(targets))
            cursor=next(iter(targets))
        return cursor
    check('small_debug_witnesses_'+case['id'],all(replay(n['witness'])==statekey(n['state']) for n in nodes))
    wobs=public_witnesses[idx]['observations'];check('small_all_public_witnesses_'+case['id'],[o['witness'] for o in wobs]==r['witness_samples'] and all(replay(o['witness']['steps'])==statekey(o['target']) and endpoint(o['target'],case['cards']) in expected for o in wobs))
    decoded=[read(RAW/f'small-candidate-{idx}-{ci}.json') for ci in range(r['candidate_count'])]
    check('small_every_saved_candidate_expanded_'+case['id'],Counter(endpoint(o['state'],case['cards']) for o in decoded)==Counter(expected))
    check('small_own_current_turn_'+case['id'],all(n['state']['active_player']==states[oracle['root']]['active_player'] and [p['turn'] for p in n['state']['players']]==[p['turn'] for p in states[oracle['root']]['players']] for n in nodes) and all(json.loads(k[1])['type']!='end_turn' for k in expected_edges))
    if idx in (6,7):check('small_mandatory_fallback_'+case['id'],r['actual_backend']=='generic' and r['encoding']=='full-state-v1' and 'compound' in r['fallback_reason'] and sha(path)==sha(RAW/f'small-predecessor/case-{idx:03d}/native/trial-1/result.json'))
    if idx==8:
        root=read(RAW/'adaptive-root.json');choice=next(c for c in root['choices'] if c['action']=={'type':'play','card':'random'});actions=[]
        for bi,o in enumerate(choice['outcomes']):
            observed=read(RAW/f'adaptive-observed-{bi}.json');continuation=read(RAW/f'adaptive-continuation-{bi}.json');steps=read(RAW/f'adaptive-steps-{bi}.json');result=read(RAW/f'adaptive-replay-{bi}.json')
            follow=next(c for c in continuation['choices'] if c['action']==steps[1]['action']);actions.append(steps[1]['action'])
            check('adaptive_branch_'+str(bi),statekey(observed)==statekey(o['state'])==statekey(continuation['state']) and replay(steps)==statekey(result['state']) and statekey(result['state']) in {statekey(x['state']) for x in follow['outcomes']})
        check('adaptive_distinct_legal_followups',len({canon(a) for a in actions})==len(actions)==2,actions)
    small.append({'case':case['id'],'states':len(oracle_keys),'candidates':len(expected),'conditional_groups':groups,'debug_witnesses':len(nodes),'public_witnesses':len(wobs),'decoded_candidates':len(decoded),'actual_backend':r['actual_backend'],'raw_path':str(path)})
write('small-review.json',{'cases':small,'checks':checks})
print('SMALL_DONE',small,flush=True)

rows=[]
for suite in ('medium','hard'):
  for idx,case in enumerate(fixtures[suite]):
    paths=[RAW/f'{suite}-{idx}-{v}/case-000/native/trial-{t}/result.json' for v in ('predecessor','delivered') for t in (1,2,3)]
    paths += [ROOT/e['path'] for e in pins['historical_candidate_inputs'] if e['role']=='historical-result' and f'/{suite}-{idx}-' in e['path']]
    group=[]
    for p in paths:
      r=read(p);candidate_rows=r['candidates'];widths={len(x) for x in candidate_rows}
      check('full_integer_rows_'+str(p),all(type(x) is list and all(type(v) is int for v in x) for x in candidate_rows) and len(widths)==1 and len(candidate_rows)==r['candidate_count'])
      enc=sorted(json.dumps(x,ensure_ascii=False,separators=(',',':')).encode('utf-8') for x in candidate_rows);h=hashlib.sha256()
      for b in enc:h.update(len(b).to_bytes(8,'big'));h.update(b)
      row={'suite':suite,'case':case['id'],'path':str(p),'encoding':r['encoding'],'row_count':len(enc),'distinct_count':sum(i==0 or x!=enc[i-1] for i,x in enumerate(enc)),'row_width':next(iter(widths)),'canonical_record_sha256':hashlib.sha256(canon(r['record']).encode('utf-8')).hexdigest(),'full_row_multiset_sha256':h.hexdigest(),'product_semantic_sha256':r['candidate_semantic_sha256'],'witness_sha256':hashlib.sha256(canon(r['witness_samples']).encode('utf-8')).hexdigest()}
      check('record_fixture_'+str(p),r['record']['cards']==case['cards'] and r['record']['initial']==case['state'])
      check('medium_hard_result_complete_'+str(p),all(r[k] is True for k in ('complete','enumeration_complete','frontier_complete')) and not r['cutoffs'] and r['actual_backend']=='native')
      group.append(row);rows.append(row);del r,candidate_rows,enc
      print('ROW_DONE',suite,idx,str(p.relative_to(ROOT)),row['row_count'],flush=True)
    fields=['encoding','row_count','distinct_count','row_width','canonical_record_sha256','full_row_multiset_sha256','product_semantic_sha256','witness_sha256']
    check('all_fresh_historical_equal_'+case['id'],all(all(x[f]==group[0][f] for f in fields) for x in group) and group[0]['encoding']=='fixed-slots-v1',len(group))
    roots=[read(RAW/f'root-{suite}-{idx}-{v}.json') for v in ('predecessor','delivered','historical')]
    check('public_decoded_roots_'+case['id'],all(statekey(o['state'])==statekey(case['state']) and o['stop'] is True for o in roots) and roots[0]==roots[1]==roots[2])
write('row-review.json',{'method':'every full integer row, duplicates retained, sorted canonical UTF-8 with unsigned 8-byte big-endian length prefixes; SHA256. No production decoder or digest used for equality.','rows':rows,'checks':checks})
write('independent-preledger-findings.json',{'recorded_at':now(),'review_started_at':read(OUT/'review-start.json')['started_at'],'F1_F6_U1_U3_checks':checks,'failures':[c for c in checks if not c['pass']],'score':score,'new_product_invocations':0,'new_measured_workers':0,'new_warmups':0,'new_retries':0,'source_text_read':False,'prior_verdict_read':False,'development_ledger_read':False,'small_totals':{k:sum(x[k] for x in small) for k in ('states','candidates','conditional_groups','debug_witnesses','public_witnesses','decoded_candidates')},'row_outputs':len(rows)})
print('PRELEDGER_DONE',len(checks),'FAILURES',sum(not c['pass'] for c in checks),flush=True)
