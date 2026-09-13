"""Collect completed A/B runs from public and formal records only."""
from pathlib import Path
import gzip
import hashlib
import json
import shutil
import sys
import tarfile
from svdeck.discovery_run import check_finish, check_unchanged, copy_session, manifest, verify_submission
from svdeck.journal_store import Journal, now

root = Path(__file__).resolve().parents[3]
folder = Path(__file__).resolve().parent
arm = sys.argv[1]
assert arm in ('A', 'B')
launch = json.loads((folder / 'launch.json').read_text())
run = Path(launch['arms'][arm]['output'])
result = json.loads((run / 'result.json').read_text())
assert result.get('ended_at'), 'Still running'
started = now()
check_unchanged(Path(launch['source']), launch['source_manifest'], exact=True)
check_unchanged(Path(launch['arms'][arm]['source']), launch['source_manifest'], exact=True)
check_unchanged(run / 'runtime', launch['arms'][arm]['runtime_manifest'], exact=True)
out = folder / arm.lower()
out.mkdir(exist_ok=False)
stages = []
for entry in result['stages']:
    stage = entry['stage']
    work = run / stage
    target = out / stage
    target.mkdir()
    execution = json.loads((run / (stage + '-run/run.json')).read_text())
    checked = False
    if execution['status'] == 'finished_by_request':
        contract = json.loads((work / 'finish-config.json').read_text())
        assert check_finish(work, contract) == execution['finish_evidence']
        checked = True
    for name in ('prompt.md', 'public-config.json', 'input-summary.json', 'finish-config.json', 'finish-request.json', 'proposal.json', 'review.json', 'bridge.md', 'final-message.md'):
        if (work / name).is_file():
            shutil.copyfile(work / name, target / name)
    shutil.copyfile(run / (stage + '-run/run.json'), target / 'run.json')
    operations = sorted([json.loads(p.read_text()) for p in (work / 'operations').glob('*.json')], key=lambda x: x['started_at'])
    with gzip.open(target / 'public-operations.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(operations, stream, ensure_ascii=False)
    stages.append({'stage': stage, 'status': execution['status'], 'started_at': execution['started_at'], 'ended_at': execution['ended_at'], 'elapsed_seconds': execution['elapsed_seconds'], 'finish_revalidated_after_whole': checked, 'operation_errors': sum(o['exit_code'] != 0 for o in operations)})
completed = result['status'] == 'completed'
source = run / 'session' if completed else run / result['stages'][-1]['stage'] / 'session'
if completed:
    assert result['formal_revisions'] == result['formal_reviews'] == 1
    verify_submission(source, 'develop', 1)
    verify_submission(source, 'review', 1)
    check_unchanged(source, launch['source_manifest'])
preserved = root / ('data/discovery/fragment-handoff-01-' + arm.lower() + ('-result' if completed else '-partial'))
assert not preserved.exists()
copy_session(source, preserved)
check_unchanged(preserved, manifest(source), exact=True)
with tarfile.open(out / 'session.tar.gz', 'w:gz') as archive:
    archive.add(preserved, arcname='session')
for name in ('result.json', 'report.json', 'develop-report.json', 'review-report.json'):
    if (run / name).is_file():
        shutil.copyfile(run / name, out / name)
db_hash = hashlib.sha256((root / 'data/cards.db').read_bytes()).hexdigest()
assert db_hash == '11aef89fae292ce671781ce31da124d695b15b28f64d7813c6e0c9ad720e1414'
ended = now()
evidence = {'started_at': started, 'ended_at': ended, 'status': result['status'], 'judgment': result.get('judgment'), 'stages': stages, 'input_and_runtime_unchanged': True, 'main_db_sha256': db_hash, 'preserved_session': str(preserved), 'limits': 'Formal outputs and public operations only; private logs unread. Execution completion is separate from usefulness.'}
(out / 'verification.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
journal = Journal(root)
saved = journal.get(folder.name)
record = saved['record']
record['status'] = 'running'
record['summary'] = '正式な結果を回収し、使い方や配分が変わったかを事前項目で点検中。'
record['stages'].append({'id': arm.lower() + '-collection', 'title': arm + 'の結果保存と入力・終了証拠を再検査', 'status': 'completed', 'started_at': started, 'ended_at': ended, 'note': result['status'] + '。方法の採否は未判定。', 'budget_minutes': 2})
record['evidence_paths'] = [p.relative_to(root).as_posix() for p in folder.rglob('*') if p.is_file() and p.name not in ('journal-record.json', 'delivery-check.json')]
saved = journal.save(record, saved['revision'], 'codex', '比較の正式結果を保存')
(folder / 'journal-record.json').write_text(json.dumps(saved, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'arm': arm, 'status': evidence['status'], 'judgment': evidence['judgment'], 'stages': stages}, ensure_ascii=False, indent=2))
