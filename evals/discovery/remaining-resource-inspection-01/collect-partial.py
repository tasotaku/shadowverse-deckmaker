"""Preserve public inspection output without replacing its failed submission."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import shutil
import tarfile
import tempfile

from svdeck import discovery
from svdeck.discovery_run import check_unchanged, copy_session, manifest
from svdeck.discovery_sources import load_sources

root = Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker')
e = root / 'evals/discovery/remaining-resource-inspection-01'
p = json.loads((e / 'protocol.json').read_text())
run = Path(p['output'])
work = run / 'inspect'
start = datetime.now(timezone.utc)
(e / 'collection-start.json').write_text(json.dumps({'started_at': start.isoformat()}, indent=2) + '\n')
result = json.loads((run / 'result.json').read_text())
assert result['status'] == 'failed'
assert [s['stage'] for s in result['stages']] == ['inspect']
assert not (run / 'inquiry').exists()
check_unchanged(Path(p['source']), p['source_manifest'], exact=True)
check_unchanged(Path(p['runtime']), p['runtime_manifest'], exact=True)
with tempfile.TemporaryDirectory(prefix='sv-inspect-input-check-') as temp:
    expected = Path(temp) / 'session'
    copy_session(Path(p['source']), expected)
    discovery.packet(expected, p['revision'], 'review')
    check_unchanged(run / 'input', manifest(expected), exact=True)

retained = {k: v for k, v in p['source_manifest'].items()
            if not k.startswith('packets/') and not k.startswith('review-')}
check_unchanged(work / 'session', retained)
assert not list((work / 'session').glob('review-*.json'))
assert {q.name for q in (work / 'session').glob('revision-*.json')} == {
    Path(k).name for k in retained if k.startswith('revision-')}
cfg = json.loads((work / 'public-config.json').read_text())
sources = load_sources(work / 'session')
original = {q.name for q in (Path(p['source']) / 'sources').glob('*.json')}
new = [s for s in sources if s['source_hash'] + '.json' not in original]
answer = (work / 'answer.md').read_text()
matches = [s for s in new if s['kind'] == cfg['report_kind'] and s['location'] == cfg['report_location']]
assert len(matches) == 1 and matches[0]['content'] == answer
ops = sorted([json.loads(q.read_text()) for q in (work / 'operations').glob('*.json')],
             key=lambda x: x['started_at'])
out = e / 'partial'
out.mkdir(exist_ok=False)
for name in ['answer.md', 'inspection-completion.json', 'input-summary.json', 'prompt.md',
             'public-config.json', 'inspection-evidence.md', 'final-message.md']:
    shutil.copyfile(work / name, out / name)
shutil.copyfile(run / 'inspect-run/run.json', out / 'run.json')
shutil.copyfile(run / 'result.json', out / 'result.json')
with gzip.open(out / 'public-operations.json.gz', 'wt', encoding='utf8') as stream:
    json.dump(ops, stream, ensure_ascii=False)
dest = root / 'data/discovery/remaining-resource-inspection-01-partial'
copy_session(Path(p['source']), dest)
for folder in ['sources', 'packets']:
    for q in (work / 'session' / folder).glob('*.json'):
        target = dest / folder / q.name
        if target.exists():
            assert target.read_bytes() == q.read_bytes()
        else:
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(q, target)
check_unchanged(dest, p['source_manifest'])
for source, name in [(work / 'session', 'session.tar.gz'), (dest, 'preserved-session.tar.gz')]:
    with tarfile.open(out / name, 'w:gz') as tar:
        tar.add(source, arcname='session')
report = discovery.report(dest)
(out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
assert hashlib.sha256((root / 'data/cards.db').read_bytes()).hexdigest() == p['main_db_sha256']
ended = datetime.now(timezone.utc)
execution = result['stages'][0]['run']
v = {
    'collection_started_at': start.isoformat(), 'collection_ended_at': ended.isoformat(),
    'collection_seconds': (ended-start).total_seconds(),
    'end_to_collection_seconds': (start-datetime.fromisoformat(result['ended_at'])).total_seconds(),
    'status': 'partial_preserved', 'worker_started_at': execution['started_at'],
    'worker_ended_at': execution['ended_at'], 'worker_monitor_seconds': execution['elapsed_seconds'],
    'worker_status': execution['status'], 'worker_returncode': execution['worker_returncode'],
    'pipeline_status': result['status'], 'pipeline_failure': result['failure'],
    'formal_report_saved': True, 'answer_source_hash': matches[0]['source_hash'],
    'additional_sources': [{k: s[k] for k in ['source_hash', 'kind', 'title']} for s in new],
    'operations': len(ops),
    'operation_errors': [{k: o[k] for k in ['args', 'started_at', 'ended_at', 'exit_code', 'stderr']}
                         for o in ops if o['exit_code'] != 0],
    'inquiry_restarted': False, 'preserved_session': str(dest),
    'preserved_file_count': len(manifest(dest)), 'preserved_source_count': len(load_sources(dest)),
    'original_input_and_runtime_unchanged': True, 'main_db_unchanged': True,
    'limits': '公開資料と操作だけを保存。実Codex私的ログは未読。失敗を成功へ書き換えず、担当の正常終了・報告本文一致・提出確認の失敗を区別。時間差はCPU・能動作業時間ではない。'}
(e / 'verification.json').write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(v, ensure_ascii=False))
