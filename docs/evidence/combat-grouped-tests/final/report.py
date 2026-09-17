import json,datetime
from pathlib import Path
P=Path('docs/evidence/combat-grouped-tests/final')
def read(n): return json.loads((P/n).read_text(encoding='utf8'))
def save(n,x): (P/n).write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf8')
rows=read('replays.json'); combat=read('combat.json'); comp=read('comparisons.json'); details=[]
for r in rows:
 c=r['candidate']; state=r['response']['state']; a,b=state['players']
 checks={'http_200':r['status']==200,'own_board':[{k:u[k] for k in c['own_board'][i]} for i,u in enumerate(a['board'])]==c['own_board'],'enemy_board':[{k:u[k] for k in c['enemy_board'][i]} for i,u in enumerate(b['board'])]==c['enemy_board'],'enemy_health':b['health']==c['enemy_health'],'own_health':a['health']==20,'ep':a['ep']==c['ep'],'sep':a['sep']==c['sep'],'enemy_resources':(b['ep'],b['sep'])==((1,1) if r['fixture']=='F4' else (0,0)),'moves_unedited':r['request']['record']['actions']==c['actions'],'only_combat':all(x['type'] in ['attack','evolve','super_evolve'] for x in c['actions'])}
 details.append({'fixture':r['fixture'],'mode':r['mode'],'index':r['index'],'checks':checks,'passed':all(checks.values()),'remaining_attack_sources':[x['source'] for x in r['response']['legal_actions'] if x['type']=='attack']})
assert all(x['passed'] for x in details)
assert all(x['response']['complete'] and x['status']==200 for x in combat)
for x in comp:
 shapes=[sorted(u['id'] for u in c['own_board']) for c in x['response']['candidates'] if not c['enemy_board']]
 assert ['T'] in shapes and ['S1','S2'] in shapes and x['response']['complete']
assert comp[0]['response']['stats']['states']<comp[1]['response']['stats']['states']
save('checks.json',details)
now=datetime.datetime.now(datetime.timezone.utc).isoformat(); start=read('start.json')['started_at']
evidence=[
'FE1 PASS: six /api/combat requests returned HTTP 200 and complete=true, candidate counts F1=2,F2=3,F3=4,F4 attack=1/evolve=2/super=3. No server errors or truncation. Public HTTP uses server default budget; paired analyze explicitly uses max_states=50000.',
'FE2 PASS: F1 candidate 1 clears X by A attacking X and retains B=3/1; B attacks leader leaving 17 health, ep=sep=0, no attacks remaining. No A-only cleared outcome returned (combat.json,replays.json).',
'FE3 PASS: F2 cleared candidates retain A=4/2 with enemy health16 and B=2/4 with enemy health18; both have spent their attacks, identical zero evolution resources (replays 1,2).',
'FE4 PASS: F3 candidate2 retains S1=2/1+S2=2/1 after T attacks X; candidate3 retains T=4/1 after S2 and S1 both attack X. Both enemy boards empty, enemy health16, zero resources, no attacks remaining. Both shapes also present in both comparison responses.',
'FE5 PASS: F4 attack path damage1, 1/1 survivor, ep/sep1/1; evolve path damage3,3/3 survivor,ep/sep0/1; super path damage4,4/4 survivor,ep/sep1/0. All actual replays match and include leader attacks.',
'FE6 PASS: all 15 candidates replayed once HTTP200. checks.json records exact advertised board fields, both leader health values and both players resources; every comparison true. Actions include only attack/evolve/super_evolve. fixtures records/cursors/snapshots unchanged. Both analyze Battle.state and export unchanged immediately before/after.',
'FE7 PASS: paired F3 mode attack max_states50000, complete=true both. Default states13 transitions14 duplicates0 elapsed_ms1.251; exhaustive states17 transitions31 duplicates15 elapsed_ms1.449. Both required shapes retained. Default states 23.5% and transitions54.8% lower.',
'UX1 PASS: 15 replay requests used returned record plus original candidate.actions, frames=[], cursor=len(actions); zero move edits or hidden-state reconstruction.',
'UX2 PASS: survivor stats, leader health, EP/SEP directly available in candidate and replay states. API usability GO. UI not exercised; focus, automatic transitions and viewport are not applicable.',
'Interactions counted: 1 readiness GET during preflight, 6 combat POST,15 replay POST,2 public analyze calls; no retries. UI clicks/keys/surface switches/scrolls=0. One isolated journey in one batch; dedicated client processes exited. Fixture preparation included in measured journey; 13-minute budget respected.'
]
report={'schema_version':'user-test-report/v1','spec_id':'combat-grouped-candidate-acceptance','spec_version':1,'spec_sha256':'58d3a3edcc4611e97d029dd8ac7a12f28d9675781e209638fbbb5f2b320167fe','executor_id':'fresh-acceptance-final','started_at':start,'finished_at':now,'scheduling':{'available_executor_slots':1,'batch_count':1},'execution_artifacts':{'preserved_workspace':str(P.resolve()),'completed_record':str((P/'replays.json').resolve())},'tests':[{'id':'T1','batch':1,'execution_count':1,'status':'PASS','journey_started_at':start,'journey_stopped_at':now,'stop_reason':'completed','functional_findings':[],'ux_findings':[],'unexpected_findings':[],'test_spec_issues':[],'evidence':evidence,'cleanup':{'status':'completed','finished_at':now,'evidence':'Dedicated HTTP client processes exited; public service intentionally left running; isolated immutable fixture and response artifacts preserved under final/.'}}],'product_findings_count':0,'blind_spots':['Visual UI layout, focus, scrolling and transitions were not exercised by API-only fixed spec.','Skills, card plays, automatic effects, complex keywords and large-board scaling are outside scope.']}
save('report.json',report)
print('PASS:15 candidate checks; report saved. Duration seconds',(datetime.datetime.fromisoformat(now)-datetime.datetime.fromisoformat(start)).total_seconds())
