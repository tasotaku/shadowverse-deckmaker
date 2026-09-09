from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

worktree = Path('/tmp/sv-pp-comparison-prototype')
folder = Path('/tmp/sv-pp-comparison-01/implementation/public')
folder.mkdir(exist_ok=False)
sys.path[:0] = [str(worktree / 'src'), str(worktree / 'tests')]
from test_discovery import make_db
from svdeck.discovery_evidence import digest

db, session = folder / 'synthetic.db', folder / 'session'
make_db(db)
db_hash = hashlib.sha256(db.read_bytes()).hexdigest()
base = ['/tmp/sv-system-venv/bin/python', '-m', 'svdeck.discovery']
env = {**os.environ, 'PYTHONPATH': str(worktree / 'src')}
records = []

def save(name, value):
    path = folder / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    return path


def run(label, *args, expected=0):
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(base + list(args), cwd=worktree, env=env, text=True, capture_output=True)
    record = dict(index=len(records) + 1, label=label, command=base + list(args),
                  started_at=started, ended_at=datetime.now(timezone.utc).isoformat(),
                  expected_returncode=expected, returncode=result.returncode,
                  expected_outcome=result.returncode == expected, stdout=result.stdout, stderr=result.stderr)
    records.append(record)
    save(f'{len(records):02d}-{label}.json', record)
    save('operations.json', records)
    assert result.returncode == expected, record
    if expected:
        assert 'Traceback' not in result.stderr and '探索入力エラー' in result.stderr
        return None
    value = json.loads(result.stdout)
    save(f'{len(records):02d}-{label}-result.json', value)
    return value


def plan(actions, *, turn=6, pp=6, extra='available', side='second', name='人工案'):
    return dict(name=name, side=side, start=dict(turn=turn, pp=pp, extra_pp=extra), actions=actions)


def payload(first, second=None):
    return dict(source_hashes=[source_hash], plans=[first, second or plan([], name='比較相手')])


def check_pp(name, value):
    path = save(name + '-input.json', value)
    return run(name, 'pp', str(session), str(path))


def session_files():
    return {str(p.relative_to(session)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in session.rglob('*') if p.is_file()}

run('start', 'start', str(session), '--db', str(db), '--class', 'ウィッチ', '--objective', '人工状態のPP算術と保存確認')
sources = save('sources-input.json', {'sources': [dict(title='人工の開始状態と量', kind='検査用宣言',
    location='この検査が作成した架空のPP状態', observed_at=None,
    content='後攻T6現在6PP・追加分未使用の二案で、片方は追加使用後5PPを支払い、片方は6PPを支払う。ほかの境界例も架空の入力である。',
    limitations=['実カードの条件・開始状態の発生可能性・効果・強さを示す資料ではない。'])]})
source_hash = run('attach', 'attach', str(session), str(sources))['added'][0]
normal_input = payload(plan([{'kind':'use_extra'}, {'kind':'pay', 'amount':5}], name='追加使用'),
                       plan([{'kind':'pay', 'amount':6}], name='温存'))
normal = check_pp('normal', normal_input)
assert normal['difference']['current_pp'] == 2 and normal['difference']['available_pp'] == 1
assert normal['input_hash'] == digest(normal_input)
reordered = check_pp('same-input-reordered', json.loads(json.dumps(normal_input, sort_keys=True)))
assert reordered['source_hash'] == normal['source_hash'] and reordered['saved_new'] is False
packet = run('packet-summary', 'packet', str(session), '--summary')
read = run('read-sources', 'read', str(session), packet['sha256'], 'sources', '--limit', '1000')
read_sources = json.loads(''.join(read['content']))
saved = next(s for s in read_sources if s['source_hash'] == normal['source_hash'])
assert json.loads(''.join(saved['content']))['input'] == normal_input
report = run('report', 'report', str(session))
assert normal['source_hash'] in [s['source_hash'] for s in report['sources']]
needs = check_pp('needs-extra', payload(plan([{'kind':'pay', 'amount':7}, {'kind':'gain', 'amount':2}])))
assert needs['plans'][0]['status'] == 'needs_extra' and needs['plans'][0]['end'] is None
assert needs['plans'][0]['last_state']['pp'] == 6 and needs['plans'][0]['skipped_actions'] == 1
unknown = check_pp('unknown-extra', payload(plan([{'kind':'use_extra'}], extra='unknown')))
assert unknown['plans'][0]['status'] == 'unknown' and unknown['plans'][0]['end'] is None
invalid = check_pp('reused-extra', payload(plan([{'kind':'use_extra'}, {'kind':'use_extra'}])))
assert invalid['plans'][0]['status'] == 'invalid' and invalid['plans'][0]['last_state']['pp'] == 7
ranges = check_pp('range', payload(plan([], pp=2, extra='unknown'), plan([], pp=0)))
assert ranges['difference']['available_pp'] is None and ranges['difference']['available_pp_range'] == [1,2]
reset = check_pp('early-late', payload(plan([{'kind':'use_extra'}, {'kind':'pay', 'amount':6},
    {'kind':'next_turn', 'turn':6, 'pp':6}, {'kind':'use_extra'}, {'kind':'pay', 'amount':7}], turn=5, pp=5)))
assert reset['plans'][0]['end']['pp'] == 0 and reset['plans'][0]['end']['extra_pp'] == 'used'
for name, value in [('bad-bool', payload(plan([{'kind':'gain','amount':True}]))),
                    ('bad-source', dict(source_hashes=['0'*64], plans=normal_input['plans'])),
                    ('first-available', payload(plan([],side='first')))]:
    path = save(name + '-input.json', value)
    before = session_files()
    run(name, 'pp', str(session), str(path), expected=2)
    assert before == session_files()
invalid_path = folder / 'invalid-json-input.json'
invalid_path.write_text('{')
before = session_files()
run('invalid-json', 'pp', str(session), str(invalid_path), expected=2)
assert before == session_files()
final_packet = run('packet-final', 'packet', str(session))
final_read = run('read-final', 'read', str(session), final_packet['sha256'], 'sources', '--limit', '5000')
assert final_read['next_offset'] is None
final_report = run('report-final', 'report', str(session))
assert len(final_report['sources']) == 7
assert final_report['revisions'] == []
assert hashlib.sha256(db.read_bytes()).hexdigest() == db_hash
save('summary.json', dict(session=str(session), database=str(db), artificial_database=True,
    database_unchanged=True, public_operations=len(records), expected_successes=sum(r['returncode']==0 for r in records),
    expected_rejections=sum(r['returncode']==2 for r in records), unexpected_failures=0,
    source_count=len(final_report['sources']), comparison_source_hash=normal['source_hash'],
    input_hash=normal['input_hash'], context_hash=normal['context_hash'], final_packet_hash=final_packet['sha256'],
    current_difference=normal['difference']['current_pp'], available_difference=normal['difference']['available_pp'],
    finished_at=datetime.now(timezone.utc).isoformat()))
print(json.dumps(json.loads((folder/'summary.json').read_text()), ensure_ascii=False, indent=2))
