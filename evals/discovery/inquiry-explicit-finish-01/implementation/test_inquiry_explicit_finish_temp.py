"""調査・照合の任意終了を合成資料と公開CLIで検査する。実AIは起動しない。"""
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys

import pytest
from svdeck import discovery as d, discovery_inquiry as i, discovery_run as r
from svdeck.discovery_evidence import digest, read_object
from svdeck.discovery_sources import load_sources
from test_discovery_inquiry_temp import source


def saved_inquiry(source):
    return d.attach(source, {'sources': [{'title': '合成調査', 'kind': 'inquiry-result', 'location': 'test://saved',
        'observed_at': None, 'content': '保存済み合成資料', 'limitations': ['実際の調査ではない']} ]})['added'][0]


@pytest.fixture(params=['inquiry', 'inspect'])
def prepared(source, tmp_path, monkeypatch, request):
    stage = request.param
    key = saved_inquiry(source) if stage == 'inspect' else None
    with monkeypatch.context() as patch:
        patch.setattr(i.worker, 'run', lambda *a, **kw: (124, {'status': 'timed_out'}))
        result = i.run(source, tmp_path/'out', Path(sys.executable), 1, digest(d._reviews(source, 1)[0]),
                       0, 10, 10, inspect_source=key, explicit_finish=True)
    assert result['status'] == stage + '_failed'
    work = tmp_path/'out'/stage
    contract = read_object(work/'finish-config.json')
    contract['fixed'] = r.manifest(work)
    return work, contract


def ready(work, mode='ok'):
    config = read_object(work/'public-config.json')
    if mode == 'missing':
        return
    (work/'answer.md').write_text('調査対象の問い\n合成資料の照合結果。\n実際の有用性は未確認。\n')
    if mode == 'answer_only':
        return
    if mode == 'old_report':
        assert r.public_main(work, ['report']) == 0
    args = ['attach-file', 'answer.md', '--title', '検査用', '--kind',
            'wrong' if mode == 'wrong_kind' else config['report_kind'], '--location',
            'test://wrong' if mode == 'wrong_location' else config['report_location']]
    assert r.public_main(work, args) == 0
    assert r.public_main(work, ['packet', '--summary']) == 0
    packet = i.refresh_packet(work/'session', config['packet_hash'])
    if mode != 'no_read':
        assert r.public_main(work, ['read', packet['sha256'], 'sources', '--limit', '1' if mode == 'partial_read' else '100000']) == 0
    if mode == 'help_report':
        assert r.public_main(work, ['report', '--help']) == 0
    elif mode not in {'old_report', 'no_report'}:
        assert r.public_main(work, ['report']) == 0
    if mode == 'changed_answer':
        (work/'answer.md').write_text('添付した本文と不一致')
    if mode == 'later_source':
        (work/'more.md').write_text('report後の別資料')
        assert r.public_main(work, ['attach-file', 'more.md', '--title', '追加', '--kind', 'test', '--location', 'test://extra']) == 0


def test_sealed_public_flow_and_operation_identity(prepared):
    work, contract = prepared
    assert r.public_main(work, ['finish', '--help']) == 0
    assert not (work/'finish-request.json').exists()
    assert r.public_main(work, ['finish', 'extra']) == 2
    ready(work)
    assert r.public_main(work, ['finish']) == 0
    request = read_object(work/'finish-request.json')
    assert request['operation_manifest']
    assert request['answer_sha256'] == hashlib.sha256((work/'answer.md').read_bytes()).hexdigest()
    evidence = r.check_finish(work, contract)
    original = (work/'finish-request.json').read_bytes()
    assert r.public_main(work, ['finish']) == 0
    config = read_object(work/'public-config.json')
    assert r.public_main(work, ['read', config['packet_hash'], 'packet_metadata']) == 0
    for args in [['packet'], ['report'], ['attach', 'answer.md'], ['attach-file', 'answer.md']]:
        assert r.public_main(work, args) == 2
    (work/'operations/unrelated-partial.json').write_text('{')
    assert r.check_finish(work, contract) == evidence
    assert (work/'finish-request.json').read_bytes() == original
    with (work/'.public.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert r.poll_finish(work, contract) is None
    assert r.poll_finish(work, contract) == evidence
    # フィクスチャの旧期限停止はfinishを事後実行しても変更されない。
    assert read_object(work.parent/'result.json')['status'] == config['stage'] + '_failed'


@pytest.mark.parametrize('mode', ['missing', 'answer_only', 'wrong_kind', 'wrong_location', 'no_read',
    'partial_read', 'no_report', 'help_report', 'old_report', 'changed_answer', 'later_source'])
def test_incomplete_report_cannot_finish(prepared, mode):
    work, contract = prepared
    ready(work, mode)
    assert r.public_main(work, ['finish']) == 2
    assert not (work/'finish-request.json').exists()
    assert r.check_finish(work, contract) is None


@pytest.mark.parametrize('mode', ['answer', 'source', 'packet', 'revision', 'review', 'author', 'stage',
    'packet_hash', 'operation', 'operation_renamed', 'operation_missing', 'request', 'operation_path',
    'finish_operation', 'finish_config', 'input', 'runtime', 'original'])
def test_changed_evidence_is_rejected(prepared, mode):
    work, contract = prepared
    ready(work)
    assert r.public_main(work, ['finish']) == 0
    request = read_object(work/'finish-request.json')
    if mode in {'author', 'stage', 'packet_hash'}:
        path = work/'public-config.json'; config = read_object(path)
        config[mode] = 'inspect' if mode == 'stage' and config['stage'] == 'inquiry' else 'inquiry' if mode == 'stage' else 'wrong'
        path.write_text(json.dumps(config))
    elif mode == 'answer':
        (work/'answer.md').write_text('changed')
    elif mode == 'source':
        path = next((work/'session/sources').glob('*.json')); path.write_text(path.read_text()+'\n')
    elif mode == 'packet':
        path = next((work/'session/packets').glob('*.json')); path.write_text(path.read_text()+'\n')
    elif mode in {'revision', 'review'}:
        (work/'session'/(mode+'-9999.json')).write_text('{}')
    elif mode in {'operation', 'operation_renamed', 'operation_missing'}:
        path = work/'operations'/next(iter(request['operation_manifest']))
        if mode == 'operation':
            op = read_object(path); op['harmless_extra'] = 'same public result'; path.write_text(json.dumps(op))
        elif mode == 'operation_renamed':
            path.rename(path.with_name('equivalent.json'))
        else:
            path.unlink()
    elif mode == 'request':
        request['report_hash'] = '0'*64
        (work/'finish-request.json').write_text(json.dumps(request))
    elif mode == 'operation_path':
        request['operation_manifest'] = {'../answer.md': '0'*64}
        (work/'finish-request.json').write_text(json.dumps(request))
    elif mode == 'finish_operation':
        (work/'operations'/request['operation']).write_text('{}')
    elif mode == 'finish_config':
        (work/'finish-config.json').write_text('{}')
    else:
        name = {'input': 'input', 'runtime': 'runtime', 'original': 'source'}[mode]
        folder = next(Path(folder) for folder in contract['protected'] if Path(folder).name == name)
        (folder/'extra.txt').write_text('changed')
    with pytest.raises((ValueError, KeyError, OSError, TypeError)):
        r.check_finish(work, contract)


def synthetic(tmp_path, mode='finish'):
    path = tmp_path/('fake-'+mode)
    path.write_text(f'''#!{sys.executable}
from pathlib import Path
import json,signal,subprocess,sys,time
sys.dont_write_bytecode=True
work=Path.cwd();config=json.loads((work/'public-config.json').read_text())
def call(*args):
    p=subprocess.run([sys.executable,'public.py',*args],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    return json.loads(p.stdout)
mode={mode!r}
if mode=='tamper_stop':
    def changed(*args):
        (work/'answer.md').write_text('停止時の変更')
        sys.exit(0)
    signal.signal(signal.SIGTERM,changed)
(work/'answer.md').write_text('合成プロセスでの公開添付と終了の検査。実際の調査や有用性評価ではない。')
call('attach-file','answer.md','--title','検査','--kind',config['report_kind'],'--location',config['report_location'])
p=call('packet');call('read',p['sha256'],'sources','--limit','100000');call('report')
if mode in ('inspect_natural','previous_add','previous_change') and config['stage']=='inspect':
    previous=work.parent/'inquiry/session'
    if mode=='previous_add':(previous/'added.json').write_text('{{}}')
    if mode=='previous_change':
        path=previous/'context.json';path.write_text(path.read_text()+'\\n')
    sys.exit(0)
if mode=='natural':sys.exit(0)
if mode=='nonzero':sys.exit(7)
if mode!='no_finish':call('finish')
time.sleep(60)
''')
    path.chmod(0o755)
    return path


@pytest.mark.parametrize('inspect_only', [False, True])
def test_actual_public_cli_finish_stops_both_stages(source, tmp_path, inspect_only):
    key = saved_inquiry(source) if inspect_only else None
    before = r.manifest(source)
    argv = [sys.executable, '-m', 'svdeck.discovery_inquiry', str(source), str(tmp_path/'real'),
            '--codex', str(synthetic(tmp_path)), '--revision', '1', '--review-hash', digest(d._reviews(source,1)[0]),
            '--question-index', '0', '--research-seconds', '15', '--inspect-seconds', '15', '--explicit-finish']
    if key:
        argv += ['--inspect-source', key]
    process = subprocess.run(argv, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr + process.stdout
    result = read_object(tmp_path/'real/result.json')
    assert result['status'] == 'completed' and result['explicit_finish'] is True
    assert result['formal_revisions'] == result['formal_reviews'] == 0
    assert [s['stage'] for s in result['stages']] == (['inspect'] if inspect_only else ['inquiry','inspect'])
    assert r.manifest(source) == before
    assert d.report(Path(result['session']))['revisions'][0]['reviews'] == d.report(source)['revisions'][0]['reviews']
    for stage in result['stages']:
        run = stage['run']
        assert run['status'] == 'finished_by_request'
        assert run['worker_returncode'] == -signal.SIGTERM
        assert {'finish_request_verified','process_group_gone','finish_confirmed'} <= {e['event'] for e in run['events']}
        work = tmp_path/'real'/stage['stage']
        assert r.check_finish(work, read_object(work/'finish-config.json'))
    assert not list((tmp_path/'real/runtime').rglob('*.pyc'))
    old = (tmp_path/'real/result.json').read_bytes()
    again = subprocess.run(argv, capture_output=True, text=True)
    assert again.returncode != 0 and (tmp_path/'real/result.json').read_bytes() == old


@pytest.mark.parametrize('mode,status,worker_status', [('natural','completed','completed'),
    ('no_finish','inquiry_failed','timed_out'), ('nonzero','inquiry_failed','failed'),
    ('tamper_stop','inquiry_failed','finish_invalid')])
def test_actual_natural_failure_timeout_and_stop_change(source, tmp_path, mode, status, worker_status):
    result = i.run(source,tmp_path/'out',synthetic(tmp_path,mode),1,digest(d._reviews(source,1)[0]),
                   0,1.5 if mode=='no_finish' else 15,15,explicit_finish=True)
    assert result['status'] == status, result
    assert result['stages'][0]['run']['status'] == worker_status
    if mode == 'natural':
        assert not (tmp_path/'out/inquiry/finish-request.json').exists()
    else:
        assert len(result['stages']) == 1 and not (tmp_path/'out/session').exists()


def test_default_stages_still_reject_finish(source, tmp_path, monkeypatch):
    def execute(command, output, timeout, grace, cwd, stdin, clock, journal):
        assert read_object(cwd/'public-config.json')['explicit_finish'] is False
        assert not (cwd/'finish-config.json').exists()
        assert r.public_main(cwd, ['finish']) == 2
        ready(cwd)
        return 0, {'status': 'completed'}
    monkeypatch.setattr(i.worker, 'run', execute)
    result = i.run(source,tmp_path/'out',Path(sys.executable),1,digest(d._reviews(source,1)[0]),0,10,10)
    assert result['status'] == 'completed' and result['explicit_finish'] is False


def test_removed_request_after_worker_return_fails(source, tmp_path, monkeypatch):
    def execute(command, output, timeout, grace, cwd, stdin, clock, journal, finish_check):
        ready(cwd)
        assert r.public_main(cwd, ['finish']) == 0
        assert finish_check()
        (cwd/'finish-request.json').unlink()
        return 0, {'status': 'finished_by_request'}
    monkeypatch.setattr(i.worker, 'run', execute)
    result = i.run(source,tmp_path/'out',Path(sys.executable),1,digest(d._reviews(source,1)[0]),0,10,10,explicit_finish=True)
    assert result['status'] == 'failed' and '終了要求' in result['failure']
    assert len(result['stages']) == 1


@pytest.mark.parametrize('mode', ['inspect_natural', 'previous_add', 'previous_change'])
def test_natural_inspector_preserves_finished_research(source, tmp_path, mode):
    result = i.run(source, tmp_path/'out', synthetic(tmp_path,mode), 1, digest(d._reviews(source,1)[0]),
                   0, 15, 15, explicit_finish=True)
    assert result['status'] == ('completed' if mode=='inspect_natural' else 'failed'), result
    assert [entry['run']['status'] for entry in result['stages']] == ['finished_by_request', 'completed']
    assert not (tmp_path/'out/inspect/finish-request.json').exists()
    if mode != 'inspect_natural':
        assert '固定ファイル' in result['failure']
        assert not (tmp_path/'out/session').exists()


@pytest.mark.parametrize('final_check_fails', [False, True])
def test_overall_journal_waits_for_submission_recheck(source, tmp_path, monkeypatch, final_check_fails):
    from test_worker_journal_temp import setup
    journal_root = tmp_path/'synthetic-journal'
    journal, _, initial = setup(journal_root, ('overall', 'live-inquiry', 'live-inspect'))
    original = i.worker.run
    def execute(*args, **kwargs):
        result = original(*args, **kwargs)
        state = journal.get('worker-link')['record']
        assert state['stages'][0]['status'] == 'running'
        if final_check_fails:
            (args[4]/'answer.md').write_text('担当終了後の改変')
        return result
    monkeypatch.setattr(i.worker, 'run', execute)
    result = i.run(source, tmp_path/'out', synthetic(tmp_path), 1, digest(d._reviews(source,1)[0]), 0, 15, 15,
                   journal_root=journal_root, experiment_id='worker-link', journal_run_stage='overall', explicit_finish=True)
    state = journal.get('worker-link')['record']
    assert state['stages'][0]['status'] == ('interrupted' if final_check_fails else 'completed')
    assert result['status'] == ('failed' if final_check_fails else 'completed')
    assert result['stages'][0]['run']['status'] == 'finished_by_request'
    assert state['result'] == initial['result'] and state['decision'] == initial['decision']


def test_overall_journal_sync_failure_returns_nonzero(source, tmp_path, monkeypatch):
    from test_worker_journal_temp import setup
    journal_root = tmp_path/'synthetic-journal'
    setup(journal_root, ('overall', 'live-inquiry', 'live-inspect'))
    def fail(*args, **kwargs):
        raise OSError('synthetic terminal sync failure')
    monkeypatch.setattr(i.InquiryJournal, 'finish', fail)
    code = i.main([str(source), str(tmp_path/'out'), '--codex', str(synthetic(tmp_path)),
        '--revision', '1', '--review-hash', digest(d._reviews(source,1)[0]), '--question-index', '0',
        '--research-seconds', '15', '--inspect-seconds', '15', '--explicit-finish',
        '--journal-root', str(journal_root), '--experiment-id', 'worker-link', '--journal-run-stage', 'overall'])
    result = read_object(tmp_path/'out/result.json')
    assert code == 2 and result['status'] == 'completed'
    assert result['journal_sync']['status'] == 'failed'
