"""明示終了の公開往復・競合を、架空データと合成プロセスで検査する。"""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import signal
import subprocess
import sys
import time

import pytest
from svdeck import discovery as d, discovery_run as r, worker
from test_discovery import make_db, proposal, assessment
from test_discovery_run_temp import source
from test_worker_journal_temp import setup as journal_setup


@pytest.fixture
def prepared(source, tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(r.worker, 'run', lambda *a, **k: (124, {'status': 'timed_out'}))
        r.run(source, tmp_path/'out', Path(sys.executable), 10, 10, explicit_finish=True)
    work=tmp_path/'out/develop'
    return work, json.loads((work/'finish-config.json').read_text())


def save_answer(work):
    config=json.loads((work/'public-config.json').read_text())
    packet=json.loads((work/'session/packets'/(config['packet_hash']+'.json')).read_text())
    answer=proposal(packet);answer['roles'].append({'card_id':2,'role':'追加保護'})
    (work/'answer.json').write_text(json.dumps(answer))
    assert r.public_main(work,['submit','answer.json'])==0


def ready(work):
    save_answer(work)
    assert r.public_main(work,['report'])==0


def test_request_is_explicit_and_idempotent(prepared):
    work,contract=prepared
    assert r.public_main(work,[])==0
    assert r.public_main(work,['submit','--help'])==0
    ready(work)
    assert r.check_finish(work,contract) is None
    assert r.public_main(work,['finish'])==0
    before=(work/'finish-request.json').read_bytes()
    evidence=r.check_finish(work,contract)
    assert evidence['request_hash']
    assert r.public_main(work,['finish'])==0
    assert (work/'finish-request.json').read_bytes()==before
    assert r.check_finish(work,contract)==evidence
    (work/'operations/partial-unrelated.json').write_text('{')
    assert r.check_finish(work,contract)==evidence
    assert r.public_main(work,['submit','answer.json'])==2
    assert r.public_main(work,['attach','answer.json'])==2
    assert r.public_main(work,['packet'])==2
    assert r.public_main(work,['report'])==2
    assert r.check_finish(work,contract)==evidence


@pytest.mark.parametrize('mode',['missing','no_report','old_report','wrong_args'])
def test_incomplete_finish_is_not_published(prepared,mode):
    work,contract=prepared
    if mode=='old_report': assert r.public_main(work,['report'])==0
    if mode!='missing': save_answer(work)
    if mode=='wrong_args': assert r.public_main(work,['report'])==0
    assert r.public_main(work,['finish',*(['extra'] if mode=='wrong_args' else [])])==2
    assert not (work/'finish-request.json').exists()
    assert r.check_finish(work,contract) is None


@pytest.mark.parametrize('mode',['old_run','broken','wrong_operation','tamper_input','tamper_session','extra_session','tamper_runtime','tamper_source','operation_changed'])
def test_invalid_or_changed_request_fails(prepared,mode):
    work,contract=prepared;ready(work)
    assert r.public_main(work,['finish'])==0
    path=work/'finish-request.json';request=json.loads(path.read_text())
    if mode=='old_run':request['config_hash']='0'*64;path.write_text(json.dumps(request))
    elif mode=='broken':path.write_text('{')
    elif mode=='wrong_operation':request['operation']='../../answer.json';path.write_text(json.dumps(request))
    elif mode=='tamper_input':(work/'input-summary.json').write_text('{}')
    elif mode=='tamper_session':
        p=work/'session/revision-0002.json';p.write_text(p.read_text()+'\n')
    elif mode=='extra_session':(work/'session/new.txt').write_text('extra')
    elif mode=='tamper_runtime':(work.parent/'runtime/svdeck/worker.py').write_text('changed')
    elif mode=='tamper_source':
        original=next(Path(folder) for folder in contract['protected'] if Path(folder).name=='source')
        (original/'extra').write_text('changed')
    else:(work/'operations'/request['operation']).write_text('{}')
    with pytest.raises((ValueError,KeyError,OSError)):r.check_finish(work,contract)


def test_public_lock_defers_poll_and_serializes_duplicate_requests(prepared):
    import fcntl
    from concurrent.futures import ThreadPoolExecutor
    work,contract=prepared;ready(work)
    with (work/'.public.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        assert r.poll_finish(work,contract) is None
    def finish():
        return subprocess.run([sys.executable,'public.py','finish'],cwd=work,capture_output=True).returncode
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda _:finish(),range(2)))
    assert codes==[0,0]
    assert r.check_finish(work,contract)


def synthetic(tmp_path, mode='finish'):
    script=tmp_path/('fake-'+mode)
    script.write_text(f'''#!{sys.executable}
import json,sys,time,subprocess,signal
sys.dont_write_bytecode=True
from pathlib import Path
sys.path.insert(0,{str(Path('tests').resolve())!r})
sys.path.insert(0,str(Path.cwd().parent/'runtime'))
from test_discovery import proposal,assessment
work=Path.cwd();config=json.loads((work/'public-config.json').read_text())
p=json.loads((work/'session/packets'/(config['packet_hash']+'.json')).read_text())
stage=config['stage']
if stage=='review':
 assert not list((work/'session').glob('review-*.json'))
 assert p['data']['previous_reviews']==[]
a=proposal(p) if stage=='develop' else assessment(p)
if stage=='develop':a['roles'].append({{'card_id':2,'role':'追加保護'}})
(work/'answer.json').write_text(json.dumps(a))
def call(*args):
 result=subprocess.run([sys.executable,'public.py',*args],capture_output=True,text=True)
 if result.returncode: print(result.stderr,flush=True)
 assert result.returncode==0,result.stderr
call('submit' if stage=='develop' else 'review','answer.json')
call('report')
mode={mode!r}
if mode=='natural':sys.exit(0)
if mode!='no_finish':call('finish')
if mode=='tamper_stop':
 def change(*args):
  path=work/'session'/('revision-0002.json' if stage=='develop' else 'context.json')
  path.write_text(path.read_text()+'\\n')
  sys.exit(0)
 signal.signal(signal.SIGTERM,change)
time.sleep(60)
''')
    script.chmod(0o755)
    return script


@pytest.mark.parametrize('review_only',[False,True])
def test_real_public_process_flow(source,tmp_path,review_only):
    before=r.manifest(source)
    result=r.run(source,tmp_path/'real',synthetic(tmp_path),None if review_only else 10,10,
                 revision=1 if review_only else None,review_only=review_only,explicit_finish=True)
    assert result['status']=='completed',result
    assert result['formal_revisions']==(0 if review_only else 1)
    assert result['formal_reviews']==1
    assert all(s['run']['status']=='finished_by_request' for s in result['stages'])
    assert all(s['run']['worker_returncode']==-signal.SIGTERM for s in result['stages'])
    assert all(any(e['event']=='process_group_gone' for e in s['run']['events']) for s in result['stages'])
    assert r.manifest(source)==before
    report=d.report(Path(result['session']))
    assert sum(len(p['reviews']) for p in report['revisions'])==2


@pytest.mark.parametrize('mode,expected',[('natural','completed'),('no_finish','develop_failed'),('tamper_stop','develop_failed')])
def test_real_natural_timeout_and_stop_tamper(source,tmp_path,mode,expected):
    result=r.run(source,tmp_path/'real',synthetic(tmp_path,mode),2 if mode=='no_finish' else 10,10,explicit_finish=True)
    assert result['status']==expected,result
    if mode=='natural':assert all(s['run']['status']=='completed' for s in result['stages'])
    if mode=='no_finish':assert result['stages'][0]['run']['status']=='timed_out' and len(result['stages'])==1
    if mode=='tamper_stop':assert result['stages'][0]['run']['status']=='finish_invalid'


def run_worker(tmp_path,check,child='import time;time.sleep(60)',timeout=2,journal=None):
    return worker.run([sys.executable,'-c',child],tmp_path/'worker',timeout,.05,clock='elapsed',journal=journal,finish_check=check)


def test_finish_check_timeout_race(tmp_path):
    def check():time.sleep(.12);return {'proof':'yes'}
    code,record=run_worker(tmp_path,check,timeout=.1)
    assert code==124 and record['status']=='timed_out'


def test_finish_check_nonzero_exit_wins(tmp_path):
    def check():time.sleep(.15);return {'proof':'yes'}
    code,record=run_worker(tmp_path,check,'import sys;sys.exit(7)')
    assert code==7 and record['status']=='failed'


def test_finish_check_natural_exit_is_separate(tmp_path):
    def check():time.sleep(.15);return {'proof':'yes'}
    code,record=run_worker(tmp_path,check,'pass')
    assert code==0 and record['status']=='completed'


def test_finish_check_interrupt_wins(tmp_path):
    def check():os.kill(os.getpid(),signal.SIGTERM);return {'proof':'yes'}
    code,record=run_worker(tmp_path,check)
    assert code==143 and record['status']=='interrupted'


def test_stop_time_is_not_a_success_grace(tmp_path):
    calls=0
    def check():
        nonlocal calls
        calls+=1
        if calls>1:time.sleep(.2)
        return {'proof':'yes'}
    code,record=run_worker(tmp_path,check,timeout=.15)
    assert code==124 and record['status']=='timed_out'


def test_post_stop_evidence_change_fails(tmp_path):
    calls=0
    def check():
        nonlocal calls
        calls+=1
        return {'proof':calls}
    code,record=run_worker(tmp_path,check)
    assert code==125 and record['status']=='finish_invalid'


def test_group_not_confirmed_fails(tmp_path,monkeypatch):
    real=worker.signal_group
    def signal_group(process,sig,**kwargs):
        if sig==0:return True
        return real(process,sig,**kwargs)
    monkeypatch.setattr(worker,'signal_group',signal_group)
    code,record=run_worker(tmp_path,lambda:{'proof':'yes'},timeout=4)
    assert code==125 and record['status']=='termination_unconfirmed'


def test_journal_keeps_explicit_reason_and_failure(tmp_path,monkeypatch):
    j,target,initial=journal_setup(tmp_path/'journal')
    code,record=run_worker(tmp_path,lambda:{'proof':'yes'},journal=target)
    assert code==0 and record['status']=='finished_by_request'
    saved=j.get('worker-link')['record']
    assert saved['stages'][0]['status']=='completed'
    assert 'finished_by_request' in saved['stages'][0]['note']
    assert saved['result']==initial['result'] and saved['decision']==initial['decision']


def test_journal_failure_does_not_advance(tmp_path,monkeypatch):
    j,target,_=journal_setup(tmp_path/'journal')
    monkeypatch.setattr(target,'finish',lambda run:(_ for _ in ()).throw(OSError('cannot save')))
    code,record=run_worker(tmp_path,lambda:{'proof':'yes'},journal=target)
    assert code==125 and record['journal_sync']['status']=='finish_failed'
    assert record['status']=='finished_by_request' and record['execution_returncode']==0
    assert record['runner_returncode']==125


@pytest.mark.parametrize('signal_number',[signal.SIGTERM,signal.SIGKILL])
def test_exit_seen_inside_signal_delivery_wins(tmp_path,monkeypatch,signal_number):
    original=worker.signal_group
    def signal_group(process,sig,require_running=False):
        if require_running:
            os.killpg(process.pid,signal_number)
            process.wait(timeout=1)
        return original(process,sig,require_running)
    monkeypatch.setattr(worker,'signal_group',signal_group)
    code,record=run_worker(tmp_path,lambda:{'proof':'yes'})
    assert code==128+signal_number and record['status']=='failed'
    assert record['worker_returncode']==-signal_number
    assert not any(e['event']=='finish_confirmed' for e in record['events'])


@pytest.mark.parametrize('when',['before','after'])
@pytest.mark.parametrize('reason',['timeout','interrupt'])
def test_invalid_finish_still_preserves_stop_priority(tmp_path,when,reason):
    calls=0
    def check():
        nonlocal calls
        calls+=1
        if (when=='before' and calls==1) or (when=='after' and calls==2):
            if reason=='timeout':time.sleep(.2)
            else:os.kill(os.getpid(),signal.SIGTERM)
            raise ValueError('changed during check')
        return {'proof':'yes'}
    code,record=run_worker(tmp_path,check,timeout=.15)
    assert record['status']==('timed_out' if reason=='timeout' else 'interrupted')
    assert code==(124 if reason=='timeout' else 143)


@pytest.mark.parametrize('parent_exits',[False,True])
def test_actual_descendant_group_is_gone(tmp_path,parent_exits):
    ready=tmp_path/'child-ready'
    child=f"import signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path({str(ready)!r}).write_text('ready');time.sleep(60)"
    parent=f"import subprocess,sys,time;from pathlib import Path;subprocess.Popen([sys.executable,'-c',{child!r}]);\nwhile not Path({str(ready)!r}).exists():time.sleep(.01)\n"+('sys.exit(0)' if parent_exits else 'time.sleep(60)')
    def check():return {'proof':'ready'} if ready.exists() and not parent_exits else None
    code,record=run_worker(tmp_path,check,parent,timeout=3)
    assert code==0,record
    assert record['status']==('completed' if parent_exits else 'finished_by_request')
    with pytest.raises(ProcessLookupError):os.killpg(record['worker_pid'],0)
    assert any(e['event']=='kill_requested' for e in record['events'])


def test_public_runner_cli_option(source,tmp_path):
    command=[sys.executable,'-m','svdeck.discovery_run',str(source),str(tmp_path/'cli'),
             '--codex',str(synthetic(tmp_path)),'--review-only','--revision','1','--review-seconds','10','--explicit-finish']
    result=subprocess.run(command,env={**os.environ,'PYTHONPATH':str(Path('src').resolve())},capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    saved=json.loads((tmp_path/'cli/result.json').read_text())
    assert saved['status']=='completed' and saved['explicit_finish'] is True
    assert saved['formal_revisions']==0 and saved['formal_reviews']==1
    assert saved['stages'][0]['run']['status']=='finished_by_request'
