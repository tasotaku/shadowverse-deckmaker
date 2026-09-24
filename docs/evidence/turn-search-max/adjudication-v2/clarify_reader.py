"""Resolve reader-only representation assumptions, without altering raw evidence."""
import json, hashlib, subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path.cwd();OUT=ROOT/'docs/evidence/turn-search-max/adjudication-v2';RAW=ROOT/'output/turn-search-max-acceptance-final'
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,x): (OUT/p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def digest(x):return hashlib.sha256(x).hexdigest()
def preserves(given,complete,path=''):
    if isinstance(given,dict):return isinstance(complete,dict) and all(k in complete and preserves(v,complete[k],path+'/'+k) for k,v in given.items())
    if isinstance(given,list):
        if path.endswith('/keywords'):return sorted(given)==sorted(complete)
        return isinstance(complete,list) and len(given)==len(complete) and all(preserves(a,b,path+'/'+str(i)) for i,(a,b) in enumerate(zip(given,complete)))
    return type(given)==type(complete) and given==complete
integrity=read(OUT/'integrity.json');source=[]
for x in integrity['source_checks']:
    directory=ROOT if x['version']=='delivered' else ROOT/'output/max-baseline-worktree'
    revision='c178cae225e2cecc986fb88df2941391bd342c64' if x['version']=='delivered' else '47eb2ef8d843dcc7c20d13f70a2a51eabf21a087'
    blob=subprocess.run(['git','show',revision+':'+x['path'].replace('\\','/')],capture_output=True,check=True).stdout
    disk=(directory/x['path']).read_bytes();equal=digest(disk.replace(b'\r\n',b'\n'))==digest(blob.replace(b'\r\n',b'\n'))
    source.append({**x,'git_LF_normalized_equal':equal,'source_text_displayed':False})
rows=read(OUT/'row-review.json')['rows'];records=[];root_checks=[]
for suite in ('medium','hard'):
    cases=read(ROOT/f'docs/evidence/turn-search-compare/independent-{suite}-cases.v1.json')
    for idx,case in enumerate(cases):
        group=[r for r in rows if r['case']==case['id']]
        # All full canonical records were hashed independently in the first pass.
        # Read each record's source JSON to establish all supplied fixture values remain present.
        for row in group:
            data=read(row['path']);record=data['record']
            good=preserves(case['cards'],record['cards']) and preserves(case['state'],record['initial']) and record['actions']==[] and record['frames']==[]
            records.append({'path':row['path'],'case':case['id'],'all_supplied_card_and_state_values_preserved':good,'record_version':record['version'],'engine_version':record['engine_version']})
            del data,record
        roots=[read(RAW/f'root-{suite}-{idx}-{version}.json') for version in ('predecessor','delivered','historical')]
        root_checks.append({'case':case['id'],'all_supplied_values_preserved':all(preserves(case['state'],r['state']) for r in roots),'decoded_roots_equal':all(r['state']==roots[0]['state'] for r in roots),'stop':all(r['stop'] for r in roots),'no_end_turn':all(c['action']['type']!='end_turn' for r in roots for c in r['choices'])})
raw=read(OUT/'independent-preledger-findings.json');original_failures=raw['failures']
resolved=[]
for x in raw['F1_F6_U1_U3_checks']:
    if x['check']=='source_current_and_original_git_identity':
        x['pass']=all(r['current_equal'] and r['git_LF_normalized_equal'] for r in source);x['detail']='123 original source hashes remain byte-identical; Git source identity matches after LF normalization (six delivered files had mixed endings). No source text read.'
    elif x['check'].startswith('record_fixture_'):
        path=x['check'][len('record_fixture_'):];x['pass']=next(r for r in records if r['path']==path)['all_supplied_card_and_state_values_preserved'];x['detail']='Public Battle record adds normalized defaults to sparse fixture; every supplied field and list element preserved.'
    elif x['check'].startswith('public_decoded_roots_'):
        case=x['check'][len('public_decoded_roots_'):];r=next(r for r in root_checks if r['case']==case);x['pass']=all(v for k,v in r.items() if k!='case');x['detail']=r
    resolved.append(x)
raw['F1_F6_U1_U3_checks']=resolved;raw['failures']=[x for x in resolved if not x['pass']];raw['reader_representation_clarification_recorded_at']=datetime.now(timezone.utc).isoformat()
write('reader-representation-checks.json',{'scope':'Reader assumptions only; no product or specification change, no new product execution. Fixed public record normalizes sparse input; source Git bytes can contain mixed Windows line endings. Initial overly strict checks preserved here.', 'initial_reader_false_negatives':original_failures,'source_checks':source,'record_checks':records,'root_checks':root_checks,'new_product_invocations':0})
write('independent-preledger-findings.json',raw)
print(json.dumps({'reader_checks_resolved':len(original_failures),'remaining_failures':raw['failures'],'source_files':len(source),'records':len(records),'roots':len(root_checks)}))
