import datetime,hashlib,json
from pathlib import Path
from consume import ROOT,HERE,OUT
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
specpath=ROOT/'docs/evidence/turn-search-compare/independent-user-test-spec.v1.json'
lockpath=specpath.with_name('independent-user-test-spec.v1.lock.json')
spec=read(specpath);lock=read(lockpath);obs=read(HERE/'observations.json');follow=read(HERE/'followup-observations.json')
manifest=read(OUT/'manifest.json');summary=read(OUT/'summary.json')
tiny=read(ROOT/'output/turn-search-acceptance-t1-tiny/summary.json')
unsupported=read(ROOT/'output/turn-search-acceptance-t1-unsupported/summary.json')
inputs=[specpath,lockpath,ROOT/'docs/battle-frontier-compare.md',ROOT/'docs/battle-frontier.md',ROOT/'scripts/turn_frontier_reference.py',ROOT/'docs/evidence/turn-search-compare/independent-small-cases.v1.json',ROOT/'docs/evidence/turn-search-compare/independent-fixtures-manifest.v1.json']
fm=read(inputs[-1]);fixture=inputs[-2];assert hashlib.sha256(fixture.read_bytes()).hexdigest()==fm[fixture.name]['sha256']
assert len(obs['observations'])==27 and not obs['failures']
assert len(follow['candidate_expansion'])==126 and all(c['equals_witness'] and c['stop'] for c in follow['candidate_expansion'])
assert len(follow['adaptive'])==6 and all(c['replayed_equals_observed_followup'] and c['stop_offered'] for c in follow['adaptive'])
assert tiny['selection']['status']=='incomplete' and tiny['selection']['algorithm'] is None
for group in tiny['groups']:
    assert group['complete'] is False
    r=read(ROOT/'output/turn-search-acceptance-t1-tiny'/group['trials'][0]['result_path'])
    assert r['complete'] is False and r['enumeration_complete'] is False and 'states' in r['cutoffs'] and r['candidate_digest_scope']=='incomplete prefix only'
for g in unsupported['groups']:
    assert g['complete'] is False
    trial=g['trials'][0];assert trial['exit_code']==1
    log=(ROOT/'output/turn-search-acceptance-t1-unsupported'/trial['error_log']).read_text(encoding='utf8')
    assert 'independent_unsupported_effect' in log and 'ValueError' in log
for g in summary['groups']:
    assert g['complete'] is True
    for t in g['trials']:
        assert all((OUT/t[k]).exists() for k in ('result_path','report_path'))
role={'executor_id':'fresh-independent-turn-compare-acceptance-t1','role':'T1 only; no product implementation/source/diffs/prior verdicts inspected','inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],'entry':'.venv/Scripts/python.exe -X utf8 -m svdeck.battle_frontier_compare','read_surfaces':['fixed inputs','public help','self-produced standard JSON and public error logs'],'source_provenance_from_public_manifest':manifest,'scheduling':'T2 artifact review overlapped; CPU reserved for T1 correctness; released at 2026-09-24T16:08:58Z before root resident measurement/T2 timed trials','implementation_edits':False,'product_retries':0,'oracle_enumerations_per_case':1}
write(HERE/'role-input-manifest.json',role)
maincmds=[
'.venv/Scripts/python.exe -X utf8 -m svdeck.battle_frontier_compare --help',
'.venv/Scripts/python.exe -X utf8 -m svdeck.battle_frontier_compare --cases docs/evidence/turn-search-compare/independent-small-cases.v1.json --output output/turn-search-acceptance-t1 --algorithms baseline,cache,native --trials 1 --seconds 60 --max-states 1000000 --debug-threshold 1000 --load-note "T1 independent correctness; CPU reserved; no T2 measured workers"',
'.venv/Scripts/python.exe -X utf8 scripts/turn_frontier_reference.py --fixtures docs/evidence/turn-search-compare/independent-small-cases.v1.json --output docs/evidence/turn-search-compare/acceptance-t1/oracle.json',
'.venv/Scripts/python.exe -X utf8 docs/evidence/turn-search-compare/acceptance-t1/consume.py',
'.venv/Scripts/python.exe -X utf8 -m svdeck.battle_frontier_compare --cases docs/evidence/turn-search-compare/independent-small-cases.v1.json --output output/turn-search-acceptance-t1-tiny --algorithms baseline --trials 1 --seconds 60 --max-states 1 --load-note "T1 deliberate tiny-budget completeness check"',
'.venv/Scripts/python.exe -X utf8 docs/evidence/turn-search-compare/acceptance-t1/public-followup.py']
write(HERE/'raw-commands.json',{'main_commands':maincmds,'all_public_followup_commands':read(HERE/'public-followup-commands.json'),'normal_output_product_invocations':2,'validation_invocations_excluded_from_normal_output_limit':True,'consumer_correction':'First projection erroneously discarded intrinsic card keywords as well as numeric/descriptive fields. Corrected public-doc interpretation preserves intrinsic abilities; initial raw mismatch retained in consumer-initial-projection-observations.json. No product rerun, input mutation, algorithm change, or fixture retry.'})
evidence=[
'F1 PASS: all 27 case/method results have complete/enumeration_complete/frontier_complete true. Independent JSON consumer compared full canonical state sets, projected Pareto endpoint sets, every source/action/target rational distribution and exact draw paths. Per algorithm: 49 canonical states, 42 endpoints, 41 action groups, 46 outcome edges over nine cases. Oracle has 50 raw states; two destruction-history permutations canonicalize together as explicitly documented. Zero set differences; observations.json records each case and exact missing/extra sets.',
'F2 PASS: root state occurs in every graph; all states retain initial active player and both turn counters. Every action key is an own-turn non-end_turn action. All 126 public --candidate expansions offer stop:true. No next-turn state/action appeared in exhaustive independent comparison.',
'F3 PASS within fixed-suite scope: independent endpoint projector preserves ordered board behavior/current traits, intrinsic card abilities, current keywords, evolution, cost, attacks, entered_turn, own/enemy attack/health/max-health vectors, leader health, PP/EP/SEP and full remaining hand identities. Exact candidate sets match every method. 27 original hand-authored witnesses per method replay with field checks: unused/a/b/ab/ba hand alternatives, bane/barrier/EP evolution, enemy-ability choices, attack-vs-health tradeoff, ordered damage, summon/grant/face-vs-trade. Detailed resulting states and candidate membership are retained in observations.json.',
'F4 PASS: all 123 action groups across methods have exact rational mass 1 and match the independent oracle including unfavorable draws. Random single damage includes both 1/2 branches. Double random includes four 1/4 draw paths, including coincident lr/rl states with separate mass. All 147 debug-state witnesses replay through independent all_outcomes. All 126 saved candidate witnesses were independently replayed and compared to the public --candidate decoded state.',
'F5 PASS: top-level scope explicitly says candidates are not mutually selectable deterministic plans or state reachability probabilities. Full small debug conditional graph matched oracle. Public --expand/--state/--steps performed six adaptive branches: after draw 0 choose remove exposed; after draw 1 choose remove protected. Every selected action was legal in that observed branch and public replay matched its resulting state. Paths/actions/probabilities saved in followup-observations.json and adaptive-*-*.json.',
'F6 PASS: one max-states=1 suite run produces all nine incomplete statuses with cutoffs [states], enumeration_complete:false, candidate_digest_scope:"incomplete prefix only". Summary selection is incomplete, algorithm:null; frontier_complete:true denotes completed prefix projection and does not override overall incomplete. Unsupported-effect probe rejects all three methods with exit_code 1; retained error logs name the exact unsupported effect; no successful result silently removes it.',
'UX1 PASS: exactly two documented product invocations (help + one nine-case/three-method comparison) obtained normal candidate output. Remaining commands are independent validation, explicit tiny-budget test, or documented conditional expansion. No production source edits/internal product imports were needed. Exact commands retained in raw-commands.json.',
'UX2 PASS: ordinary json.load consumed summary.json and every result. Summary directly exposed scope, mode, case_id, algorithm, complete, trial/result/report paths; all 27 normal result/report paths resolve. Tiny summary distinguishes finished harness run_complete:true from incomplete mathematical results via group complete:false and selection incomplete. No raw graph was needed to identify completion or paths.',
'UX3 PASS / CLI usability GO: all interaction used CLI, no UI focus/viewport/scroll acceptance criterion applies. Product command discovery and output consumption succeeded. Largest remaining usability friction: comparator documentation describes behavior/stat exclusions conceptually; readers implementing independent endpoint keys should preserve intrinsic card keywords as abilities. This was a corrected consumer assumption, not a directly observed product defect.',
'Budget/scheduling: first measured comparison started at 2026-09-24T16:05:02Z; final public followup completed at 16:08:58Z. Conservative preflight-inclusive start bound 16:03:00Z used in report (under six minutes through public execution versus fixed 20 minutes). CPU released immediately after public validation; no timing claim is derived from this correctness run.'
]
report={'schema_version':'user-test-report/v1','spec_id':spec['spec_id'],'spec_version':1,'spec_sha256':lock['sha256'],'executor_id':role['executor_id'],'started_at':'2026-09-24T16:03:00Z','finished_at':now,'scheduling':{'available_executor_slots':2,'batch_count':1},'execution_artifacts':{'preserved_workspace':str(OUT),'completed_record':str(HERE/'observations.json')},'tests':[{'id':'T1','batch':1,'execution_count':1,'status':'PASS','journey_started_at':'2026-09-24T16:03:00Z','journey_stopped_at':'2026-09-24T16:08:58.113Z','stop_reason':'completed','functional_findings':[],'ux_findings':[],'unexpected_findings':[],'test_spec_issues':[],'evidence':evidence,'cleanup':{'status':'completed','finished_at':now,'evidence':'All exclusively owned comparison/followup subprocesses exited (sessions 52680 and 85260 exit 0); no live child remains and no process termination was needed. Preserved output/turn-search-acceptance-t1, -tiny, -unsupported and docs/evidence/turn-search-compare/acceptance-t1. No shared files or global processes were deleted/stopped.'}}],'product_findings_count':0,'blind_spots':['Frozen cases use SEP=0: exact preservation is covered, nonzero SEP tradeoff behavior is outside observed fixture variation. This report does not certify arbitrary effect/card inputs.','Own-turn small correctness only; throughput/heldout/hard-scale judgments belong to independent T2.','Preflight start is a conservative reconstructed bound; exact first help timestamp was not separately saved. Measured product-run interval is recorded by artifact timestamps and each public followup command records wall clock.']}
write(HERE/'report-t1-only.json',report)
report['tests'].append({'id':'T2','batch':1,'execution_count':0,'status':'NOT_RUN','journey_started_at':None,'journey_stopped_at':None,'stop_reason':'impossible','functional_findings':[],'ux_findings':[],'unexpected_findings':[],'test_spec_issues':[],'evidence':['T2 not executed by this T1-only executor; actual T2 report must replace this explicit placeholder before a combined acceptance verdict.'],'cleanup':{'status':'completed','finished_at':now,'evidence':'No T2 environment or process was created by this executor. Separate executor owns its cleanup.'}})
write(HERE/'report.json',report)
md='# T1 independent acceptance: PASS\n\n27 comparisons (9 frozen cases × 3 public methods) passed exact independently projected candidates, canonical full states, actions, outcomes and rational probability checks.\n\n'
md+='\n\n'.join(evidence)+'\n\nNo product or UX findings. Consumer-only projection correction is retained transparently; no product test was retried.\n'
(HERE/'README.md').write_text(md,encoding='utf8')
print('PASS T1 report written; fixtures hash verified; all raw JSON consumed')
if __name__=='__main__':pass
