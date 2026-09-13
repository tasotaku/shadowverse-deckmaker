"""Common fragment scout: synthetic data, public CLI, no real AI or private log reads."""
from pathlib import Path
import json
import signal
import subprocess
import sys

import pytest
from svdeck import discovery as d, discovery_run as r
from svdeck.discovery_evidence import read_object
from test_discovery import make_db, proposal, assessment
from test_worker_journal_temp import setup

ENTRY = Path('evals/discovery/fragment-handoff-01/scout-run.py').resolve()


@pytest.fixture
def source(tmp_path):
    db = tmp_path/'cards.db'
    make_db(db)
    source = tmp_path/'source'
    d.start(source, db, 'ウィッチ', 'rotation', '合成資料から未完成断片だけを保存する')
    return source


def synthetic(tmp_path, source, mode='finish'):
    path = tmp_path/('fake-'+mode)
    path.write_text(f'''#!{sys.executable}
import json,signal,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
work=Path.cwd(); mode={mode!r}
cfg=json.loads((work/'public-config.json').read_text())
def call(*args,code=0):
    p=subprocess.run([sys.executable,'public.py',*args],capture_output=True,text=True)
    assert p.returncode==code,p.stdout+p.stderr
    return json.loads(p.stdout) if code==0 else None
p=call('packet')
assert p['data']['stage']=='inquiry' and p['data']['revision']==0
assert p['data']['proposal'] is None and p['data']['previous_reviews']==[]
assert set(p['data']['inquiry_focus'])=={{'question','origin'}}
assert p['data']['inquiry_focus']['origin']=='experiment-fragments'
assert 'review_hash' not in p['data']['inquiry_focus']
call('read',p['sha256'],'cards','--limit','10')
call('read',p['sha256'],'sources','--limit','100000')
call('submit','answer.json',code=2); call('review','answer.json',code=2)
if mode=='missing':sys.exit(0)
(work/'answer.md').write_text('実数0件。合成資料の公開操作だけを検査。未完成着想の有用性は未検証。')
if mode=='timeout':time.sleep(60)
if mode=='nonzero':sys.exit(7)
if mode=='answer_only':sys.exit(0)
call('attach-file','answer.md','--title','合成断片','--kind',cfg['report_kind'],'--location',cfg['report_location'])
p=call('packet');call('read',p['sha256'],'sources','--limit','100000');call('report')
if mode=='proposal':(work/'session/revision-0001.json').write_text('{{}}');sys.exit(0)
if mode=='review':(work/'session/review-0001-x.json').write_text('{{}}');sys.exit(0)
if mode=='input':(work/'session/context.json').write_text('{{}}');sys.exit(0)
if mode=='runtime':(work.parent/'runtime/svdeck/worker.py').write_text('changed');sys.exit(0)
if mode=='source':(Path({str(source)!r})/'context.json').write_text('{{}}');sys.exit(0)
if mode=='natural':sys.exit(0)
if mode=='stop_change':
    def changed(*args):
        (work/'answer.md').write_text('終了受付後の変更')
        sys.exit(0)
    signal.signal(signal.SIGTERM,changed)
call('finish')
time.sleep(60)
''')
    path.chmod(0o755)
    return path


def invoke(source, tmp_path, mode='finish', extra=(), seconds='15'):
    command = [sys.executable, str(ENTRY), str(source), str(tmp_path/'out'), '--codex',
               str(synthetic(tmp_path,source,mode)), '--seconds', seconds, *extra]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    result = read_object(tmp_path/'out/result.json') if (tmp_path/'out/result.json').exists() else None
    return completed, result


@pytest.mark.parametrize('mode', ['finish', 'natural'])
def test_public_cli_and_recheck(source, tmp_path, mode):
    before = r.manifest(source)
    process, result = invoke(source,tmp_path,mode)
    assert process.returncode == 0, process.stdout+process.stderr
    assert result['status']=='completed'
    assert result['run']['status']==('finished_by_request' if mode=='finish' else 'completed')
    assert result['formal_revisions']==result['formal_reviews']==0
    assert result['report']['revisions']==[]
    assert r.manifest(source)==before
    assert result['source_manifest']==before
    assert result['submission']['public_reread'] is True
    assert result['runtime_manifest']==r.manifest(tmp_path/'out/runtime')
    work=tmp_path/'out/inquiry'; config=read_object(work/'public-config.json')
    assert config['explicit_finish'] is True and config['report_kind']=='inquiry-result'
    packet=d._read_envelope(work/'session/packets'/(config['packet_hash']+'.json'))
    instruction=packet['instruction']
    assert all(s in instruction for s in ['最大3件','順位','採否','創作で埋めず','カードID','field','quote'])
    assert not list((tmp_path/'out/runtime').rglob('*.pyc'))
    if mode=='finish':
        assert result['run']['worker_returncode']==-signal.SIGTERM
        events={e['event'] for e in result['run']['events']}
        assert {'finish_request_verified','process_group_gone','finish_confirmed'}<=events
        contract=read_object(work/'finish-config.json')
        proof=r.check_finish(work,contract)
        assert proof and r.check_finish(work,contract)==proof
        assert r.public_main(work,['read',config['packet_hash'],'packet_metadata'])==0
        assert r.check_finish(work,contract)==proof
        (work/'answer.md').write_text('後からの変更')
        with pytest.raises(ValueError):r.check_finish(work,contract)
    old=(tmp_path/'out/result.json').read_bytes()
    again,_=invoke(source,tmp_path,mode)
    assert again.returncode!=0 and (tmp_path/'out/result.json').read_bytes()==old


@pytest.mark.parametrize('mode,status', [('missing','missing'),('timeout','timed_out'),('nonzero','failed'),
    ('answer_only','failed'),('proposal','failed'),('review','failed'),('input','failed'),('runtime','failed'),
    ('source','failed'),('stop_change','finish_invalid')])
def test_failed_or_missing_scout_keeps_evidence(source,tmp_path,mode,status):
    process,result=invoke(source,tmp_path,mode,seconds='1' if mode=='timeout' else '15')
    assert process.returncode!=0
    assert result['status']==status,result
    assert result['ended_at'] and result['run']
    assert not (tmp_path/'out/session').exists()
    if mode!='missing':assert (tmp_path/'out/inquiry/answer.md').exists()


@pytest.mark.parametrize('seconds',['0','-1','nan','inf'])
def test_bad_seconds_do_not_prepare(source,tmp_path,seconds):
    process,result=invoke(source,tmp_path,seconds=seconds)
    assert process.returncode!=0 and result is None
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('with_review',[False,True])
def test_existing_formal_input_is_rejected(source,tmp_path,with_review):
    d.submit(source,proposal(d.packet(source,0,'develop')))
    if with_review:d.review(source,assessment(d.packet(source,1,'review')))
    before=r.manifest(source)
    process,result=invoke(source,tmp_path)
    assert process.returncode!=0 and result is None
    assert r.manifest(source)==before and not (tmp_path/'out').exists()


def test_journal_records_worker_only(source,tmp_path):
    root=tmp_path/'synthetic-journal'
    journal,_,initial=setup(root,('scout',))
    process,result=invoke(source,tmp_path,extra=['--journal-root',str(root),'--experiment-id','worker-link','--stage-id','scout'])
    assert process.returncode==0,process.stdout+process.stderr
    state=journal.get('worker-link')['record']
    assert state['stages'][0]['status']=='completed'
    assert state['stages'][0]['started_at']==result['run']['started_at']
    assert state['stages'][0]['ended_at']==result['run']['ended_at']
    assert state['result']==initial['result'] and state['decision']==initial['decision']
    assert state['status']=='running'


@pytest.mark.parametrize('extra',[['--experiment-id','x'],['--stage-id','x']])
def test_partial_journal_args_do_not_prepare(source,tmp_path,extra):
    process,result=invoke(source,tmp_path,extra=extra)
    assert process.returncode!=0 and result is None
