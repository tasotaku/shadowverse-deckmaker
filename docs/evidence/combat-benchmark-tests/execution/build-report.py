import pathlib,json,math,statistics,datetime
p=pathlib.Path('docs/evidence/combat-benchmark-tests/execution')
n=json.loads((p/'normal/report.json').read_text(encoding='utf-8')); md=(p/'normal/report.md').read_text(encoding='utf-8')
assert {c['id'] for c in n['cases']}=={'empty','incomparable','tall-wide','super-finish'}
checks=[]
for c in n['cases']:
    runs=c['runs']; assert len(runs)==2 and [r['iteration'] for r in runs]==[1,2]
    assert c['reference']['status']=='PASS'
    assert len({r['answers_sha256'] for r in runs})==1
    for r in runs:
        assert r['status']==r['correctness']=='PASS' and r['replay_coverage']=='all'
        assert r['answer_diff']['missing_count']==r['answer_diff']['extra_count']==0
        assert all(math.isfinite(r[k]) and r[k]>=0 for k in ['elapsed_ms','peak_rss_bytes'])
    median=statistics.median(r['elapsed_ms'] for r in runs); peak=max(r['peak_rss_bytes'] for r in runs)/1048576
    expected=f"| {c['id']} | grouped | PASS | PASS | {median:.3f} | {peak:.2f} | 2/2 |"
    assert expected in md
    checks.append(expected)
(p/'comparison.txt').write_text('PASS: exact JSON-to-Markdown rounded median ms / maximum MiB rows\n'+'\n'.join(checks),encoding='utf-8')
started=(p/'started.txt').read_text(encoding='utf-8-sig').strip(); stopped=(p/'stopped.txt').read_text(encoding='utf-8-sig').strip(); cleanup=json.loads((p/'cleanup.json').read_text(encoding='utf-8-sig'))
report={
'schema_version':'user-test-report/v1','spec_id':'combat-benchmark-public-cli','spec_version':1,'spec_sha256':'3e2876702d6c455cc487e2cf9ae111ad7e010a6bb579a0b930f2e349ab0f700e','executor_id':'fresh-benchmark-acceptance-T1','started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
'scheduling':{'available_executor_slots':1,'batch_count':1},'execution_artifacts':{'preserved_workspace':str(p.resolve()),'completed_record':str((p/'report.json').resolve())},
 'tests':[{'id':'T1','batch':1,'execution_count':1,'status':'PASS','journey_started_at':started,'journey_stopped_at':cleanup['checked_at'],'stop_reason':'completed','functional_findings':[],'ux_findings':[],'unexpected_findings':[],'test_spec_issues':[],
'evidence':[
'F1 PASS: help and catalog each exit 0 (help-exit.txt/catalog-exit.txt). 12 selectable IDs. Selected empty (smallest empty fixture), incomparable, tall-wide (also multiple sacrifices), super-finish from descriptions, without source inspection or edits.',
'F2 PASS: normal-command.json exit 0 in 2.125 seconds. Public normal/report.json contains exactly four selected cases with iterations 1 and 2, all eight PASS. elapsed_ms 0.376–5.1124; peak_rss_bytes 21729280–22470656; all finite/nonnegative. Memory method explicitly Windows PeakWorkingSetSize.',
'F3 PASS at disclosed black-box scope: all four reference records report PASS with sequence/endpoint counts, replay_coverage all, no missing/extra answers, matching answer hashes across repetitions. Empty reference has one sequence/endpoint and each run replays its one candidate. JSON identifies independent Battle legal-action enumeration in separate process. Internal independence remains a stated blind spot, not inferred proof.',
'F4 PASS: comparison.txt verifies every Markdown row against JSON median elapsed_ms rounded to 3 decimals and max bytes converted to MiB rounded to 2 decimals. Markdown explicitly labels median/max. JSON and Markdown disclose new child per measurement, analysis-only time, peak before replay, and reference/replay work outside measurement. No large fixture or partial reference claimed exhaustive in these selected reports.',
'F5 PASS: invalid-case.json/invalid-repeat.json/invalid-timeout.json each exit 2 with usage. Missing case diagnostic names definitely-missing-case; numeric diagnostic requires positive repeat/timeout and valid max-states. No successful run presented.',
'F6 PASS: timeout-command.json launched empty once with 0.000001 seconds; monotonic subprocess clock measured 0.422 seconds until exit 1. Both timeout reports show TIMEOUT and UNKNOWN correctness; JSON omits elapsed/memory, Markdown shows em dashes and 0/1 completion. cleanup.json observes no remaining owned Python process by unique output directory command-line identity.',
'UX1 PASS: directly counted two discovery commands, --help and --list-cases, no source edits or private-file consultation.',
'UX2 PASS: normal command stdout gives absolute JSON and Markdown paths; zero directory listings used to locate reports.',
'UX3 GO: directly read Markdown. Case/status/units and 2/2 completion are clear; timeout is TIMEOUT/UNKNOWN with missing-value dashes. UNVERIFIED explained in prose. No material comprehension issue.',
'UX4 PASS: direct captured stderr contains usage and requested missing ID or positive-value correction guidance; all three invalid inputs rejected.',
'UX5: CLI/file journey; GUI click/focus/scroll/surface transitions inapplicable. Discovery commands 2, report-location directory listings 0; normal report reads one JSON and one Markdown, timeout reads one each.',
'Budget: journey completed within 9 minutes; normal run 2.125 s below 180 s, timeout 0.422 s below 30 s. One test in one isolated output directory, one batch, one execution. No retries.'
], 'cleanup':{'status':'completed','finished_at':stopped,'evidence':'All launched parents exited; read-only Windows process observation found zero Python processes referencing this executor-owned output directory. No process kill necessary. Evidence and outputs preserved under '+str(p.resolve())}}],
'product_findings_count':0,'blind_spots':[
'Black-box output inspection verifies disclosed scope but cannot prove internal timing boundaries, memory sampling boundaries, child isolation, or reference algorithm independence; separate implementation tests required.',
'Battle engine and analyzer may share rule defects; no mathematical engine proof in this journey.',
'No large/partial case executed, no hardware-specific performance threshold. Injected crashes, unavailable sampler, arbitrary fixtures, concurrency, non-Windows platforms outside fixed journey.'
]}
(p/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS report saved and JSON/Markdown comparison assertions passed')
