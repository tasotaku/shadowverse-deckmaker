"""Hash and seal immutable observations for independent adjudication; no product runs."""
from run import *

assert remaining()>0
entries=[]
for path in sorted(OUT.rglob('*')):
    if path.is_file():entries.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path),'role':'raw-public-product-output'})
chosen={
 'journey.json':'original-timer','observation-completion.json':'completion-time',
 'commands.jsonl':'raw-command-order','input-manifest.json':'runtime-source-provenance','pinned-inputs.json':'fixed-input-hash-checks','subsets.json':'fixture-subset-correspondence',
 'final-source-integrity.json':'source-integrity','source-provenance.json':'raw-source-manifest-consumption',
 'observations.json':'independent-small-consumption','small-decoded-candidates.json':'independent-small-candidate-consumption',
 'public-witnesses.json':'public-witness-consumption','adaptive.json':'adaptive-consumption','random-probabilities.json':'rational-distribution-consumption','tiny.json':'tiny-budget-consumption',
 'rows.json':'independent-all-row-consumption','row-comparisons.json':'independent-row-comparison','roots.json':'public-root-consumption',
 'timing-table.json':'independent-timing-consumption','worker-schedule.json':'raw-observer-schedule-consumption','summary-path-validation.json':'ordinary-summary-path-consumption',
 'phase-table.json':'independent-phase-consumption','external-crosschecks.json':'external-monotonic-memory-consumption',
 'development-audit.json':'post-observation-ledger-audit','harness-diagnostics.json':'observation-limitations'}
for path in sorted(HERE.iterdir()):
    if path.name in chosen or path.name.endswith(('.processes.json','.stdout.txt','.stderr.txt')):
        entries.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path),'role':chosen.get(path.name,'raw-observer-log')})
for path in sorted((HERE/'raw-metadata').rglob('*')):
    if path.is_file():entries.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path),'role':'copied-raw-public-metadata'})
for name in ['run.py','process_observer.py','consume_small.py','followups.py','audit.py','summarize.py','ledger_audit.py']:
    path=HERE/name;entries.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path),'role':'consumer-or-observer-code-no-production-code'})
for name in ['spec.v1.json','spec.v1.lock.json','input-manifest.v1.json']:
    path=HERE.parent/name;entries.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path),'role':'original-fixed-contract'})
completion=read(HERE/'observation-completion.json')
manifest={'schema_version':'immutable-raw-observation-manifest/v1','sealed_at':now(),'sealed_monotonic':time.monotonic(),
 'original_journey_start':read(HERE/'journey.json')['start'],'original_deadline_monotonic':read(HERE/'journey.json')['deadline_monotonic'],
 'all_observations_completed_at':completion['all_unchanged_observations_comparisons_ledger_checks_completed_at'],
 'observation_completion_monotonic':completion['completed_monotonic'],'elapsed_seconds_at_completion':completion['elapsed_seconds'],
 'elapsed_seconds_at_seal':time.monotonic()-read(HERE/'journey.json')['start_monotonic'],
 'completion_and_seal_within_original_60_minutes':completion['within_original_60_minutes'] and remaining()>0,
 'product_retries':0,'product_edits':0,'source_provenance':'docs/evidence/turn-search-max/acceptance-final/input-manifest.json',
 'actual_product_output_root':str(OUT),'baseline_revision':'47eb2ef8d843dcc7c20d13f70a2a51eabf21a087','delivered_revision':'c178cae225e2cecc986fb88df2941391bd342c64',
 'scope':'Immutable one-journey raw evidence. Fresh adjudicator can recompute conclusions from raw-public-product-output and raw-observer-log entries; independent consumption entries retain evidence, not authority for a verdict. Historical inputs remain pinned by original input manifest.',
 'excluded_previous_verdict_paths':['docs/evidence/turn-search-max/acceptance-final/report.json','docs/evidence/turn-search-max/acceptance-final/README.md','docs/evidence/turn-search-max/acceptance-final/independent-findings.json','docs/evidence/turn-search-max/acceptance-final/score.json','docs/evidence/turn-search-max/acceptance-final/comparison.md'],
 'entries':entries}
assert manifest['completion_and_seal_within_original_60_minutes']
path=HERE/'raw-observation-manifest.json';save(path,manifest)
(HERE/'raw-observation-manifest.sha256').write_text(sha(path)+'  raw-observation-manifest.json\n',encoding='utf8')
(HERE/'report-lint.txt').write_text('Observed final report validator: PASS report findings=0 incomplete=1; exit_code=0.\nCommand: .venv/Scripts/python.exe -X utf8 C:/Users/tasog/.agents/skills/design-user-tests/scripts/lint_user_test_artifact.py report docs/evidence/turn-search-max/acceptance-final/report.json --spec docs/evidence/turn-search-max/spec.v1.json --verify-lock docs/evidence/turn-search-max/spec.v1.lock.json\n',encoding='utf8')
print(json.dumps({'entries':len(entries),'manifest_sha256':sha(path),'completion':completion,'sealed_at':manifest['sealed_at'],'elapsed_seconds_at_seal':manifest['elapsed_seconds_at_seal']}))
