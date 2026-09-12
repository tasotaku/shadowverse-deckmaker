from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest
from svdeck import worker
from svdeck.journal_store import Conflict, Journal, template
from svdeck.worker_journal import RunJournal


def setup(root, ids=('a',)):
    j = Journal(root)
    r = template('worker-link')
    r.update(title='接続検査', summary='検査', method='検査', procedure='検査', inputs='架空', criteria='変わらない')
    r['stages'] = [dict(id=i, title=i, status='planned', started_at=None, ended_at=None,
                        note='元の注記', budget_minutes=1) for i in ids]
    j.save(r, 0, 'test', 'fixture')
    return j, RunJournal(root, r['id'], ids[0]), r


def raw_run(tmp, name='run'):
    return dict(status='starting', started_at=datetime.now(timezone.utc).isoformat(), ended_at=None,
                output=str(tmp/name), worker_returncode=None)


def finish_raw(run, status='completed'):
    run.update(status=status, ended_at=datetime.now(timezone.utc).isoformat(), worker_returncode=0)
    return run


def test_child_observes_start_and_terminal_preserves_result(tmp_path):
    j, target, initial = setup(tmp_path)
    child = """from pathlib import Path
import json,sys
from svdeck.journal_store import Journal
r=Journal(Path(sys.argv[1])).get('worker-link')['record']
assert r['stages'][0]['status']=='running'
print(r['stages'][0]['started_at'],flush=True)
"""
    code, r = worker.run([sys.executable,'-c',child,str(tmp_path)],tmp_path/'run',2,0.1,journal=target)
    final = j.get('worker-link')['record']
    assert code == 0 and r['journal_sync']['status'] == 'completed'
    assert (tmp_path/'run/stdout.log').read_text().strip() == r['started_at']
    assert final['stages'][0]['started_at'] == r['started_at']
    assert final['stages'][0]['ended_at'] == r['ended_at']
    assert final['stages'][0]['status'] == 'completed'
    assert final['status'] == 'running' and final['ended_at'] is None
    assert (final['result'],final['decision']) == (initial['result'],initial['decision'])


@pytest.mark.parametrize('command,timeout,status,code', [
    ([sys.executable,'-c','import sys;print("partial",flush=True);sys.exit(7)'],2,'failed',7),
    ([sys.executable,'-c','import time;print("partial",flush=True);time.sleep(10)'],1,'timed_out',124),
    (['/definitely-missing-svdeck-worker'],2,'launch_failed',127),
])
def test_failure_paths_close_stage(tmp_path,command,timeout,status,code):
    j,target,_=setup(tmp_path)
    actual,r=worker.run(command,tmp_path/'run',timeout,.05,journal=target)
    stage=j.get('worker-link')['record']['stages'][0]
    assert actual==code and r['status']==status
    assert stage['status']=='interrupted' and stage['ended_at']==r['ended_at']
    assert status in stage['note']
    if status!='launch_failed':assert (tmp_path/'run/stdout.log').read_text()=='partial\n'


def test_missing_stage_never_launches(tmp_path,monkeypatch):
    j,_,_=setup(tmp_path)
    monkeypatch.setattr(worker.subprocess,'Popen',lambda *a,**k:pytest.fail('must not launch'))
    code,r=worker.run(['irrelevant'],tmp_path/'run',2,.1,journal=RunJournal(tmp_path,'worker-link','absent'))
    assert code==125 and r['status']=='journal_start_failed' and r['worker_pid'] is None
    assert j.get('worker-link')['revision']==1


def test_start_write_failure_never_launches(tmp_path,monkeypatch):
    j,target,_=setup(tmp_path)
    monkeypatch.setattr(Journal,'save',lambda *a,**k:(_ for _ in ()).throw(OSError('write failed')))
    monkeypatch.setattr(worker.subprocess,'Popen',lambda *a,**k:pytest.fail('must not launch'))
    code,r=worker.run(['irrelevant'],tmp_path/'run',2,.1,journal=target)
    assert code==125 and r['journal_sync']['status']=='start_failed'
    assert j.get('worker-link')['record']['stages'][0]['status']=='planned'


def test_same_stage_has_one_owner(tmp_path):
    j,_,_=setup(tmp_path)
    def claim(n):
        try:return RunJournal(tmp_path,'worker-link','a').begin(raw_run(tmp_path,str(n)))
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,[1,2]))
    assert sum(isinstance(v,dict) for v in results)==1 and results.count('rejected')==1
    assert j.get('worker-link')['revision']==2


def test_parallel_different_stages_merge_and_end(tmp_path):
    j,_,_=setup(tmp_path,('a','b'))
    runs={a:raw_run(tmp_path,a) for a in ['a','b']}
    def begin(a):runs[a]['journal_sync']=RunJournal(tmp_path,'worker-link',a).begin(runs[a])
    def end(a):return RunJournal(tmp_path,'worker-link',a).finish(finish_raw(runs[a]))
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(begin,['a','b']))
    assert all(s['status']=='running' for s in j.get('worker-link')['record']['stages'])
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(end,['a','b']))
    item=j.get('worker-link')
    assert item['revision']==5 and all(s['status']=='completed' for s in item['record']['stages'])


def test_manual_edit_is_not_overwritten(tmp_path):
    j,target,_=setup(tmp_path);r=raw_run(tmp_path);r['journal_sync']=target.begin(r)
    item=j.get('worker-link');item['record']['stages'][0]['note']='利用者による訂正'
    j.save(item['record'],item['revision'],'user','訂正')
    with pytest.raises(ValueError,match='上書き'):target.finish(finish_raw(r))
    assert j.get('worker-link')['record']['stages'][0]['note']=='利用者による訂正'


@pytest.mark.parametrize('child_code',[0,7])
def test_end_failure_preserves_execution_and_recovery_does_not_rerun(tmp_path,monkeypatch,child_code):
    j,target,_=setup(tmp_path);original=target.finish
    monkeypatch.setattr(target,'finish',lambda r:(_ for _ in ()).throw(OSError('end write failed')))
    code,r=worker.run([sys.executable,'-c',f'from pathlib import Path;import sys;Path(sys.argv[1]).write_text("once");sys.exit({child_code})',str(tmp_path/'once')],tmp_path/'run',2,.05,journal=target)
    assert code==(125 if child_code==0 else 7)
    assert r['execution_returncode']==r['worker_returncode']==child_code
    assert r['journal_sync']['status']=='finish_failed'
    assert j.get('worker-link')['record']['stages'][0]['status']=='running'
    initial_run=(tmp_path/'run/run.json').read_bytes()
    (tmp_path/'once').write_text('must remain')
    result=subprocess.run([sys.executable,'-m','svdeck.worker_journal',str(tmp_path/'run')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    expected='completed' if child_code==0 else 'interrupted'
    assert j.get('worker-link')['record']['stages'][0]['status']==expected
    assert (tmp_path/'once').read_text()=='must remain' and (tmp_path/'run/run.json').read_bytes()==initial_run
    revision=j.get('worker-link')['revision']
    monkeypatch.setattr(target,'finish',original);target.finish(r)
    assert j.get('worker-link')['revision']==revision


def test_budget_expired_while_starting_does_not_launch(tmp_path,monkeypatch):
    j,target,_=setup(tmp_path);original=target.begin
    def begin(r):
        result=original(r);time.sleep(.03);return result
    monkeypatch.setattr(target,'begin',begin)
    monkeypatch.setattr(worker.subprocess,'Popen',lambda *a,**k:pytest.fail('must not launch'))
    code,r=worker.run(['irrelevant'],tmp_path/'run',.01,.05,journal=target)
    assert code==124 and r['status']=='timed_out' and r['worker_pid'] is None
    assert j.get('worker-link')['record']['stages'][0]['status']=='interrupted'


def test_finite_conflict_retries(tmp_path,monkeypatch):
    j,target,_=setup(tmp_path);calls=[]
    def conflict(*a,**k):calls.append(1);raise Conflict('another writer')
    monkeypatch.setattr(Journal,'save',conflict)
    with pytest.raises(Conflict):target.begin(raw_run(tmp_path))
    assert len(calls)==3 and j.get('worker-link')['revision']==1


def test_unconfirmed_termination_is_not_claimed_stopped(tmp_path):
    j,target,_=setup(tmp_path);r=raw_run(tmp_path);r['journal_sync']=target.begin(r)
    target.finish(finish_raw(r,'termination_unconfirmed'))
    stage=j.get('worker-link')['record']['stages'][0]
    assert stage['status']=='interrupted' and '子の停止未確認' in stage['note']


def test_incomplete_connection_arguments_fail_before_output(tmp_path):
    output=tmp_path/'run'
    result=subprocess.run([sys.executable,'-m','svdeck.worker','--output',str(output),'--timeout','1','--stage-id','a','--',sys.executable,'-c','print(1)'],capture_output=True,text=True)
    assert result.returncode==2 and not output.exists()


def test_old_default_timeout_error_is_still_launch_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(worker.subprocess,'Popen',lambda *a,**k:(_ for _ in ()).throw(TimeoutError('old path')))
    code,r=worker.run(['irrelevant'],tmp_path/'run',2,.05)
    assert code==127 and r['status']=='launch_failed' and 'journal_sync' not in r


def test_reverse_save_order_uses_actual_earliest_start(tmp_path):
    j,_,_=setup(tmp_path,('a','b'))
    a=raw_run(tmp_path,'a');time.sleep(.001);b=raw_run(tmp_path,'b')
    b['journal_sync']=RunJournal(tmp_path,'worker-link','b').begin(b)
    a['journal_sync']=RunJournal(tmp_path,'worker-link','a').begin(a)
    result=j.get('worker-link')['record']
    assert result['started_at']==a['started_at']
    assert [s['started_at'] for s in result['stages']]==[a['started_at'],b['started_at']]


def test_unknown_overall_start_is_not_inferred_from_new_worker(tmp_path):
    from datetime import timedelta
    j,target,_=setup(tmp_path)
    item=j.get('worker-link');item['record']['status']='running'
    old=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    item['record']['stages'].append(dict(id='old',title='過去',status='completed',started_at=old,ended_at=old,note='全体開始は不明',budget_minutes=None))
    j.save(item['record'],item['revision'],'test','過去工程')
    code,r=worker.run([sys.executable,'-c','print("new work")'],tmp_path/'run',2,.05,journal=target)
    final=j.get('worker-link')['record']
    assert code==0 and final['started_at'] is None and final['stages'][0]['status']=='completed'
    assert final['stages'][1]==item['record']['stages'][1]


@pytest.mark.parametrize('failed_revision',[2,3])
def test_committed_write_with_failed_ack_is_recoverable(tmp_path,monkeypatch,failed_revision):
    import sqlite3
    j,target,_=setup(tmp_path);original=Journal.get
    def get(self,identifier,revision=None):
        if revision==failed_revision:raise sqlite3.OperationalError('reply failed after commit')
        return original(self,identifier,revision)
    monkeypatch.setattr(Journal,'get',get)
    code,r=worker.run([sys.executable,'-c','print("child ran")'],tmp_path/'run',2,.05,journal=target)
    assert code==125
    assert r['journal_sync']['status']==('start_failed' if failed_revision==2 else 'finish_failed')
    assert bool(r['worker_pid'])==(failed_revision==3)
    assert 'claimed_stage' in r['journal_sync']
    monkeypatch.setattr(Journal,'get',original)
    result=target.finish(r)
    assert result['status']=='completed'
    stage=j.get('worker-link')['record']['stages'][0]
    assert stage['status']==('interrupted' if failed_revision==2 else 'completed')
    assert stage['ended_at']==r['ended_at']
