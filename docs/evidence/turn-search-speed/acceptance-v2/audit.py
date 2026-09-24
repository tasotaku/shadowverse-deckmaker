from run import *
import statistics,gc
from consume_small import statekey,endpoint,skyline

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()
def subset(a,b,path=''):
 if isinstance(a,dict):
  return all(k in b and subset(v,b[k],path+'/'+k) for k,v in a.items())
 if isinstance(a,list):
  if path.endswith('/keywords'):return sorted(a)==sorted(b)
  return len(a)==len(b) and all(subset(x,y,path+'/'+str(i)) for i,(x,y) in enumerate(zip(a,b)))
 return type(a)==type(b) and a==b

def audit_result(path,case):
 t=time.perf_counter();r=read(path);rows=r['candidates'];widths=set();encoded=[]
 for row in rows:
  assert isinstance(row,list) and all(type(v) is int for v in row),(str(path),'noninteger row')
  widths.add(len(row));encoded.append(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode('utf8'))
 assert len(widths)==1 and r['encoding']=='fixed-slots-v1'
 encoded.sort();h=hashlib.sha256();distinct=0;last=None
 for x in encoded:
  h.update(len(x).to_bytes(8,'big'));h.update(x)
  if x!=last:distinct+=1
  last=x
 rec=r['record'];res={'path':str(path),'sha256':sha(path),'row_count':len(rows),'distinct_count':distinct,'row_width':next(iter(widths)),'encoding':r['encoding'],'canonical_record_sha256':digest(rec),'full_integer_row_multiset_sha256':h.hexdigest(),'witness_samples_sha256':digest(r['witness_samples']),'reported_semantic_sha256':r['candidate_semantic_sha256'],'candidate_count':r['candidate_count'],'count_matches':len(rows)==r['candidate_count'],'complete':all(r[x] is True for x in ['complete','enumeration_complete','frontier_complete']) and not r['cutoffs'],'actual_backend':r['actual_backend'],'fixture_cards_preserved':subset(case['cards'],rec['cards']),'fixture_initial_values_preserved':subset(case['state'],rec['initial']),'record_version':rec['version'],'record_engine_version':rec['engine_version'],'record_actions_empty':rec['actions']==[],'record_frames_empty':rec['frames']==[],'audit_seconds':time.perf_counter()-t}
 del r,rows,encoded;gc.collect();return res

if __name__=='__main__':
 mode=sys.argv[1]
 if mode=='rows':
  allrows=[];comparisons=[];freshmeta=read(HERE/'input-manifest.json');manifests=[]
  for suite,count,repeat in [('medium',3,3),('hard',2,1)]:
   cases=read(ROOT/f'docs/evidence/turn-search-compare/independent-{suite}-cases.v1.json')
   for idx,case in enumerate(cases):
    group=[]
    for version in ['predecessor','delivered','historical']:
     base=ROOT/f'output/turn-search-acceptance-t2/{suite}' if version=='historical' else OUT/f'{suite}-{idx}-{version}'
     manifest=read(base/'manifest.json')
     provenance_ok=None if version=='historical' else all(freshmeta['versions'][version]['source_hashes'][str(Path(k))]==v for k,v in manifest['files'].items())
     manifests.append({'suite':suite,'case':case['id'],'version':version,'path':str(base/'manifest.json'),'revision':manifest['revision'],'source_sha256':manifest['source_sha256'],'source_files_match_independently_hashed_checkout':provenance_ok,'dependencies':manifest['dependencies'],'python':manifest['python'],'platform':manifest['platform'],'input_sha256':manifest['input_sha256']})
     for trial in range(1,repeat+1):
      path=base/f'case-{idx if version=="historical" else 0:03d}/native/trial-{trial}/result.json'
      obs={'suite':suite,'case':case['id'],'case_index':idx,'version':version,'trial':trial,**audit_result(path,case)}
      group.append(obs);allrows.append(obs);save(HERE/'rows.json',allrows)
    equal_fields=['row_count','distinct_count','row_width','encoding','canonical_record_sha256','full_integer_row_multiset_sha256','reported_semantic_sha256','witness_samples_sha256']
    comparisons.append({'suite':suite,'case':case['id'],'outputs':len(group),'equality':{k:len({r[k] for r in group})==1 for k in equal_fields},'all_complete_native_counts_and_fixture_values':all(r['complete'] and r['actual_backend']=='native' and r['count_matches'] and r['fixture_cards_preserved'] and r['fixture_initial_values_preserved'] for r in group)})
    print(case['id'],comparisons[-1],flush=True)
  save(HERE/'row-comparisons.json',comparisons);save(HERE/'source-provenance.json',manifests)
 elif mode=='roots':
  roots=[]
  for suite,count in [('medium',3),('hard',2)]:
   cases=read(ROOT/f'docs/evidence/turn-search-compare/independent-{suite}-cases.v1.json')
   for idx,case in enumerate(cases):
    records=[];states=[]
    for version in ['predecessor','delivered','historical']:
     base=ROOT/f'output/turn-search-acceptance-t2/{suite}' if version=='historical' else OUT/f'{suite}-{idx}-{version}'
     path=base/f'case-{idx if version=="historical" else 0:03d}/native/trial-1/result.json';dest=OUT/f'root-{suite}-{idx}-{version}.json'
     run(f'root-{suite}-{idx}-{version}',['--expand',path,'--output',dest],version if version!='historical' else 'delivered')
     decoded=read(dest);state=decoded['state'];states.append(state)
     records.append({'version':version,'path':str(dest),'state_sha256':digest(state),'fixture_values_preserved':subset(case['state'],state),'stop':decoded['stop'],'no_end_turn':all(c['action']['type']!='end_turn' for c in decoded['choices'])})
    roots.append({'case':case['id'],'exact_decoded_roots_equal':all(s==states[0] for s in states),'observations':records})
  save(HERE/'roots.json',roots)
 elif mode=='small-candidates':
  cases=read(ROOT/'docs/evidence/turn-search-compare/independent-small-cases.v1.json');oracles=read(ROOT/'docs/evidence/turn-search-compare/acceptance-t1/oracle.json');observations=[]
  for idx,(case,oracle) in enumerate(zip(cases,oracles)):
   path=OUT/f'small/case-{idx:03d}/native/trial-1/result.json';r=read(path);actual=[]
   expected=skyline(endpoint(n['state'],case['cards']) for n in oracle['states'])
   for cidx in range(len(r['candidates'])):
    dest=OUT/f'small-candidate-{idx}-{cidx}.json';run(f'small-candidate-{idx}-{cidx}',['--expand',path,'--candidate',str(cidx),'--output',dest]);actual.append(endpoint(read(dest)['state'],case['cards']))
   observations.append({'case':case['id'],'saved_candidate_rows':len(r['candidates']),'decoded_candidate_count':len(actual),'independent_oracle_candidate_count':len(expected),'exact_decoded_candidate_set':set(actual)==expected,'no_duplicate_semantic_candidates':len(actual)==len(set(actual))})
  save(HERE/'small-decoded-candidates.json',observations)
