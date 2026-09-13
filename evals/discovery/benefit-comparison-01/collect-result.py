"""Collect the fixed A/B evaluation, using only formal outputs and public operations."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import shutil
import sys
import tarfile

from svdeck import discovery
from svdeck.discovery_run import check_finish, check_unchanged, copy_session, manifest, verify_submission
from svdeck.journal_store import Journal

root = Path(__file__).resolve().parents[3]
folder = Path(__file__).resolve().parent
arm = sys.argv[1]
assert arm in ('a', 'b')
run = Path('/tmp/benefit-comparison-01-' + arm + '-live')
result = json.loads((run / 'result.json').read_text())
assert result.get('ended_at') and result['status'] not in ('preparing', 'review')
started = datetime.now(timezone.utc)
protocol = json.loads((folder / 'protocol.json').read_text())
check_unchanged(Path(protocol[arm + '_input']), protocol['source_manifest'], exact=True)
runtime = protocol['control_runtime_manifest' if arm == 'a' else 'variant_runtime_manifest']
expected_runtime = {k: v for k, v in runtime.items() if '__pycache__' not in Path(k).parts and not k.endswith('.pyc')}
check_unchanged(run / 'runtime/svdeck', expected_runtime, exact=True)
work = run / 'review'
execution = json.loads((run / 'review-run/run.json').read_text())
checks = {}
if execution['status'] == 'finished_by_request':
    contract = json.loads((work / 'finish-config.json').read_text())
    assert check_finish(work, contract) == execution['finish_evidence']
    assert {'finish_confirmed', 'process_group_gone'} <= {x['event'] for x in execution['events']}
    checks['finish_revalidated_after_completion'] = True
out = folder / arm
out.mkdir(exist_ok=True)
for name in ('prompt.md', 'public-config.json', 'input-summary.json', 'finish-config.json', 'finish-request.json', 'review.json', 'final-message.md'):
    if (work / name).is_file():
        shutil.copyfile(work / name, out / name)
shutil.copyfile(run / 'review-run/run.json', out / 'run.json')
operations = sorted([json.loads(p.read_text()) for p in (work / 'operations').glob('*.json')], key=lambda x: x['started_at'])
with gzip.open(out / 'public-operations.json.gz', 'wt', encoding='utf-8') as stream:
    json.dump(operations, stream, ensure_ascii=False)
completed = result['status'] == 'completed'
source = run / 'session' if completed else work / 'session'
if completed:
    assert result['formal_revisions'] == 0 and result['formal_reviews'] == 1
    verify_submission(source, 'develop', 1)
    verify_submission(work / 'session', 'review', 1)
    check_unchanged(source, protocol['source_manifest'])
    old = discovery.report(Path(protocol[arm + '_input']))['revisions'][-1]['reviews']
    final = discovery.report(source)['revisions'][-1]['reviews']
    assert len(final) == len(old) + 1 and all(value in final for value in old)
destination = root / ('data/discovery/benefit-comparison-01-' + arm + ('-result' if completed else '-partial'))
assert not destination.exists()
copy_session(source, destination)
check_unchanged(destination, manifest(source), exact=True)
with tarfile.open(out / 'session.tar.gz', 'w:gz') as archive:
    archive.add(destination, arcname='session')
for name in ('result.json', 'report.json', 'review-report.json'):
    if (run / name).is_file():
        shutil.copyfile(run / name, out / name)
assert hashlib.sha256((root / 'data/cards.db').read_bytes()).hexdigest() == '11aef89fae292ce671781ce31da124d695b15b28f64d7813c6e0c9ad720e1414'
ended = datetime.now(timezone.utc)
evidence = {'arm': arm, 'status': result['status'], 'failure': result.get('failure'), 'judgment': result.get('judgment'),
            'collection_started_at': started.isoformat(), 'collection_ended_at': ended.isoformat(),
            'end_to_collection_seconds': (started - datetime.fromisoformat(result['ended_at'])).total_seconds(),
            'actor_started_at': execution['started_at'], 'actor_ended_at': execution['ended_at'],
            'actor_monitor_seconds': execution['elapsed_seconds'], 'operations': len(operations),
            'operation_errors': [{k: o.get(k) for k in ('args', 'exit_code', 'ended_at', 'stderr')} for o in operations if o['exit_code'] != 0],
            'checks': checks, 'preserved_session': str(destination), 'source_and_runtime_unchanged': True,
            'original_reviews_preserved': completed, 'main_db_unchanged': True,
            'limits': '正式保存と公開操作のみを回収。私的stdout/JSONLは未読。完了と評価方法の有用性は別。'}
(out / 'verification.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
journal = Journal(root)
item = journal.get(folder.name)
record = item['record']
record['stages'].append({'id': arm + '-collection', 'title': arm.upper() + 'の正式評価と終了証拠を回収', 'status': 'completed',
                         'started_at': started.isoformat(), 'ended_at': ended.isoformat(), 'note': '結果: ' + result['status'] + '。元評価を保持して保存と終了を再検査。方法の採否は未判定。', 'budget_minutes': 2})
record['status'] = 'running'
record['summary'] = '評価結果を回収中。通常側にもある利益と残る交換の説明を事前の観察項目で照合する。'
record['evidence_paths'] = [str(p.relative_to(root)) for p in folder.rglob('*') if p.is_file() and p.name not in ('journal-record.json', 'delivery-check.json')]
saved = journal.save(record, item['revision'], 'codex', '固定した評価の正式結果を回収')
(folder / 'journal-record.json').write_text(json.dumps(saved, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: evidence[k] for k in ('arm', 'status', 'judgment', 'actor_monitor_seconds', 'end_to_collection_seconds')}, ensure_ascii=False))
