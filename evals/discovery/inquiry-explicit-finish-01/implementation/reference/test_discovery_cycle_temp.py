from pathlib import Path
import json
import os
import subprocess
import sys

import pytest
from svdeck import discovery as d, discovery_run as engine, discovery_cycle as cycle
from svdeck.discovery_evidence import write_new
from test_discovery import make_db, proposal, assessment


@pytest.fixture
def source(tmp_path):
    db = tmp_path / 'cards.db'
    make_db(db)
    folder = tmp_path / 'source'
    d.start(folder, db, 'ウィッチ', 'rotation', '検証用の種を考案')
    return folder


def fake_worker(monkeypatch, values=('develop', 'develop'), questions=True, failure=None):
    calls = []
    def execute(command, output, timeout, grace, cwd, stdin, clock, journal):
        cfg = json.loads((cwd / 'public-config.json').read_text())
        stage, revision = cfg['stage'], cfg['revision']
        calls.append((stage, revision, journal.stage_id if journal else None))
        if failure == ('timeout', len(calls)):
            return 124, {'status': 'timed_out'}
        if failure == ('missing', len(calls)):
            return 0, {'status': 'completed'}
        session = cwd / 'session'
        p = json.loads((session / 'packets' / (cfg['packet_hash'] + '.json')).read_text())
        if stage == 'review':
            assert p['data']['previous_reviews'] == []
            assert p['data']['review_contexts'] == []
            assert not list(session.glob('review-*.json'))
            assert len(list((session / 'packets').glob('*.json'))) == 1
            response = assessment(p)
            response['value'] = values[min(revision - 1, len(values) - 1)]
            response['next_questions'] = response['next_questions'] if questions else []
        else:
            response = proposal(p)
            if revision:
                response['roles'].append({'card_id': 2, 'role': '保護役を追加して生存条件を変える'})
            response['plan'] = {k: '検証用の利用説明' for k in ('early','transition','finish','without_core','allocation','comparison')}
            if revision:
                assert p['data']['previous_reviews'][0]['next_questions'] == ['継続して得るものは何か']
        write_new(cwd/'answer.json', response)
        assert engine.public_main(cwd, ['submit' if stage == 'develop' else 'review', 'answer.json']) == 0
        if failure == ('corrupt', len(calls)):
            path = next(session.glob('review-*.json'))
            path.write_text('{}')
        return 0, {'status': 'completed'}
    monkeypatch.setattr(engine.worker, 'run', execute)
    return calls


@pytest.mark.parametrize('values,questions,n,reason', [
    (('develop','develop'), True, 2, 'round_limit'),
    (('develop','test'), True, 2, 'round_limit'),
    (('test',), True, 1, 'value_test'),
    (('drop',), True, 1, 'value_drop'),
    (('unknown',), True, 1, 'value_unknown'),
    (('develop',), False, 1, 'no_next_questions'),
])
def test_branches_keep_formal_history(source,tmp_path,monkeypatch,values,questions,n,reason):
    original=engine.manifest(source)
    calls=fake_worker(monkeypatch,values,questions)
    out=cycle.prepare(source,tmp_path/'out',Path(sys.executable),10,10, tmp_path,'experiment','trial')
    assert cycle.run_prepared(out)==0
    result=json.loads((out/'result.json').read_text())
    assert result['status']=='completed'
    assert result['stop_reason']==reason
    assert result['verified_revisions']==result['verified_reviews']==n
    assert len(calls)==n*2
    assert [c[2] for c in calls]==[f'trial-{i}-{s}' for i in range(1,n+1) for s in ('develop','review')]
    assert len(d.report(out/'session')['revisions'])==n
    for i in range(1,n+1):
        r=d.report(out/f'round-{i}'/'session')['revisions'][-1]
        decision=json.loads((out/f'round-{i}'/'decision.json').read_text())
        assert decision['next_questions']==r['reviews'][0]['next_questions']
        assert decision['at'] and decision['review_hash']
        assert result['rounds'][i-1]['started_at'] and result['rounds'][i-1]['ended_at']
    assert engine.manifest(source)==original
    assert not (out/'round-3').exists()
    saved=(out/'result.json').read_bytes()
    with pytest.raises(ValueError,match='開始済み'):
        cycle.run_prepared(out)
    assert (out/'result.json').read_bytes()==saved


@pytest.mark.parametrize('failure,calls_n',[(('timeout',1),1),(('missing',2),2),(('corrupt',2),2),(('timeout',3),3),(('missing',4),4)])
def test_failure_never_advances_or_relabels_first_success(source,tmp_path,monkeypatch,failure,calls_n):
    calls=fake_worker(monkeypatch,failure=failure)
    out=cycle.prepare(source,tmp_path/'out',Path(sys.executable),10,10)
    assert cycle.run_prepared(out)==2
    r=json.loads((out/'result.json').read_text())
    assert r['status']=='round_failed' and r['ended_at']
    assert len(calls)==calls_n and not (out/'session').exists()
    if calls_n>2:
        assert (out/'round-1/session').is_dir()
        assert r['verified_revisions']==1


@pytest.mark.parametrize('change',['source','runtime','config','interrupt'])
def test_protected_files_and_between_round_interrupt(source,tmp_path,monkeypatch,change):
    calls=fake_worker(monkeypatch)
    out=cycle.prepare(source,tmp_path/'out',Path(sys.executable),10,10)
    original=cycle.next_step
    def decision(session, revision, number):
        result=original(session,revision,number)
        if change=='interrupt': raise KeyboardInterrupt
        if change=='config':
            (out/'config.json').write_text('{}')
        elif change=='source':
            (source/'extra').write_text('changed')
        else:
            (out/'runtime/extra').write_text('changed')
        return result
    monkeypatch.setattr(cycle,'next_step',decision)
    assert cycle.run_prepared(out)==2
    result=json.loads((out/'result.json').read_text())
    assert result['status']==('interrupted' if change=='interrupt' else 'failed')
    assert len(calls)==2 and not (out/'round-2').exists()


@pytest.mark.parametrize('limits',[(0,1),(1,-1),(float('nan'),1),(1,float('inf'))])
def test_invalid_limits_do_not_prepare(source,tmp_path,limits):
    with pytest.raises(ValueError):
        cycle.prepare(source,tmp_path/'out',Path(sys.executable),*limits)
    assert not (tmp_path/'out').exists()


def test_existing_and_nested_output_are_rejected(source,tmp_path):
    out=tmp_path/'out';out.mkdir();(out/'keep').write_text('keep')
    with pytest.raises(FileExistsError): cycle.prepare(source,out,Path(sys.executable),1,1)
    assert (out/'keep').read_text()=='keep'
    with pytest.raises(ValueError): cycle.prepare(source,source/'nested',Path(sys.executable),1,1)


def test_public_cli_uses_same_frozen_runtime_twice(source,tmp_path):
    backend=tmp_path/'fake-codex'
    backend.write_text('#!'+sys.executable+'\n'+'''import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json
work=Path.cwd()
sys.path.insert(0,str(work.parent/'runtime'))
'''+f'sys.path.insert(1,{str(Path(__file__).resolve().parents[1])!r})\n'+'''from svdeck import discovery_run as engine
from test_discovery import proposal,assessment
cfg=json.loads((work/'public-config.json').read_text())
p=json.loads((work/'session/packets'/(cfg['packet_hash']+'.json')).read_text())
response=proposal(p) if cfg['stage']=='develop' else assessment(p)
if cfg['stage']=='develop' and cfg['revision']:
    response['roles'].append({'card_id':2,'role':'保護役の追加'})
(work/'answer.json').write_text(json.dumps(response))
raise SystemExit(engine.public_main(work,['submit' if cfg['stage']=='develop' else 'review','answer.json']))
''')
    backend.chmod(0o755)
    out=tmp_path/'out'
    process=subprocess.run([sys.executable,'-B','-m','svdeck.discovery_cycle',str(source),str(out),'--codex',str(backend),'--develop-seconds','10','--review-seconds','10'],capture_output=True,text=True,timeout=45)
    assert process.returncode==0,process.stdout+process.stderr
    result=json.loads((out/'result.json').read_text())
    assert len(result['rounds'])==2 and result['stop_reason']=='round_limit'
    runtime=engine.manifest(out/'runtime')
    assert engine.manifest(out/'round-1/runtime')==engine.manifest(out/'round-2/runtime')==runtime
    for i in (1,2):
        for stage in ('develop','review'):
            script=(out/f'round-{i}'/stage/'public.py').read_text()
            assert str(out/f'round-{i}'/'runtime') in script


def test_real_interrupt_stops_worker_group_without_next_round(source,tmp_path):
    import signal,time
    backend=tmp_path/'sleep-codex'
    backend.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(30)\n')
    backend.chmod(0o755)
    out=tmp_path/'out'
    process=subprocess.Popen([sys.executable,'-B','-m','svdeck.discovery_cycle',str(source),str(out),'--codex',str(backend),'--develop-seconds','20','--review-seconds','10'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    runfile=out/'round-1/develop-run/run.json'
    try:
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if runfile.exists():
                run=json.loads(runfile.read_text())
                if run.get('worker_pid') and run['status']=='running':break
            time.sleep(.05)
        else:pytest.fail('test worker did not start')
        os.kill(process.pid,signal.SIGTERM)
        stdout,stderr=process.communicate(timeout=8)
        assert process.returncode==2,stdout+stderr
        result=json.loads((out/'result.json').read_text())
        assert result['status']=='round_failed'
        assert not (out/'round-2').exists()
        final=json.loads(runfile.read_text())
        assert final['status']=='interrupted'
        assert final['ended_at']
        with pytest.raises(ProcessLookupError): os.killpg(run['worker_pid'],0)
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=8)
