import json,pathlib,datetime,time,copy
from svdeck.battle import Battle
base=pathlib.Path('output/lookahead-acceptance-v1-final-t1'); out=pathlib.Path('docs/evidence/battle-lookahead/user-tests/final-t1')
fixtures={c['id']:c for c in json.load(open('tests/fixtures/battle_lookahead_acceptance.json',encoding='utf-8'))}
manifest=json.load(open('docs/evidence/battle-lookahead/acceptance-inputs/manifest.json',encoding='utf-8'))['T1']['cli']
ref=json.load(open('docs/evidence/battle-lookahead/acceptance-inputs/reference.json',encoding='utf-8')); refs={r['id']:r for r in ref['cases']}
checks=[]
for call in manifest:
 r=json.loads((base/call['id']/'report.json').read_text(encoding='utf-8')); f=fixtures[call['case']]
 expectation=ref['one_turn_reference'] if call['turns']==1 else refs[call['case']]
 candidates=[]
 for cand in r['candidates']:
  e=next(x for x in expectation['actions'] if x['action']==cand['action'])
  ok=cand['win_probability_exact']==e['value'][0] and str(-int(cand['loss_probability_exact']))==e['value'][1]
  b=Battle(copy.deepcopy(f['state']),f['cards']); b.step(cand['action']); hand=b.state['players'][0]['hand']
  candidates.append({'action':cand['action'],'probabilities_match_reference':ok,'remaining_hand_after_action':[{'id':x['id'],'name':x['name']} for x in hand],'remaining_pp':b.state['players'][0]['pp'],'win':cand['win_probability_exact'],'loss':cand['loss_probability_exact']})
 edges=[]
 nodes={n['id']:n for n in r['policy']}
 for n in r['policy']:
  if not n['action']:continue
  b=Battle(copy.deepcopy(n['state']),f['cards']); legal=n['action'] in b.observation(b.state['active_player'])['legal_actions']; b.step(n['action'])
  for edge in n['outcomes']:
   target=nodes[edge['node']]['state']; identical=b.state==target
   edges.append({'node':n['id'],'active_player':n['state']['active_player'],'turns_remaining':n['turns_remaining'],'action':n['action'],'legal':legal,'next_state_matches':identical,'post_health':[p['health'] for p in b.state['players']],'post_pp':[p['pp'] for p in b.state['players']],'post_winner':b.state['winner']})
 checks.append({'id':call['id'],'requested_turns':call['turns'],'reported_turns':r['turns'],'complete':r['complete'],'optimal':r['optimal'],'cutoffs':r['cutoffs'],'recommendation':r['recommended_action'],'recommendation_matches_reference':r['recommended_action'] in expectation['optimal_first_actions'],'candidates':candidates,'hand_patterns':r['hand_patterns'],'policy_edges_public_Battle_replay':edges,'exported_replay':r['replay'],'reported_process_peak_bytes':r['stats']['peak_rss_bytes'],'reported_memory_method':r['stats']['memory_method']})
(out/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'all_reference_values_match':all(c['probabilities_match_reference'] for x in checks for c in x['candidates']),'all_recommendations_match':all(x['recommendation_matches_reference'] for x in checks),'all_policy_edges_legal_and_match':all(e['legal'] and e['next_state_matches'] for x in checks for e in x['policy_edges_public_Battle_replay']),'edges_checked':sum(len(x['policy_edges_public_Battle_replay']) for x in checks),'checks_file':str(out/'checks.json')},indent=2))
raw=json.loads((out/'raw.json').read_text()); stopped=datetime.datetime.now(datetime.timezone.utc).isoformat(); raw['journey_stopped_at']=stopped;raw['journey_elapsed_seconds']=time.perf_counter()-raw['journey_start_perf']; (out/'raw.json').write_text(json.dumps(raw,indent=2),encoding='utf-8')
print('Journey elapsed seconds:',raw['journey_elapsed_seconds'])
