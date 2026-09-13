from pathlib import Path
import json
import subprocess
import sys

import pytest
from svdeck import discovery as d, discovery_run as engine, discovery_cycle as cycle, discovery_inquiry as inquiry
from svdeck.discovery_evidence import digest, write_new
from test_discovery import proposal, assessment
from test_discovery_cycle_temp import source, fake_worker


def reviewed(folder, value='test', novelty='unconfirmed', questions=None):
    p=proposal(d.packet(folder,0,'develop'))
    p['plan']={k:'合成検査の利用説明' for k in ('early','transition','finish','without_core','allocation','comparison')}
    d.submit(folder,p)
    response=assessment(d.packet(folder, 1, 'review'))
    response.update(value=value,novelty=novelty,next_questions=questions or [])
    if novelty=='differentiated':
        response['web_checks']=[{'url':'https://example.test/fixture','query':'合成検査','checked_at':'2026-09-11T00:00:00Z','finding':'テストデータ。実Web調査ではない。'}]
    d.review(folder,response)
    return digest(d._reviews(folder,1)[0])


def inquiry_worker(monkeypatch, failure=None, origin="unconfirmed-novelty"):
    calls=[]
    def execute(command, output, timeout, grace, cwd, stdin, clock, journal):
        cfg=json.loads((cwd/'public-config.json').read_text());stage=cfg['stage'];calls.append(stage)
        session=cwd/'session';p=d._read_envelope(session/'packets'/(cfg['packet_hash']+'.json'))
        assert p['inquiry_focus']['question_index'] is None
        assert p['inquiry_focus']['question']==inquiry.NOVELTY_QUESTION
        assert p['inquiry_focus']['origin']==origin
        prompt=stdin.read_text()
        if origin=='known-use-prevalence':
            assert '同用途の先例ありとされた試用評価から設定した固定の調査目的' in prompt
            assert '独自性未確認の試用評価から設定した固定の調査目的' not in prompt
        else:
            assert '独自性未確認の試用評価から設定した固定の調査目的' in prompt
        assert p['previous_reviews']==p['review_contexts']==[]
        assert not list(session.glob('review-*.json'))
        if failure and failure[0]==stage:
            if failure[1]=='timeout':return 124,{'status':'timed_out'}
            if failure[1]=='missing':return 0,{'status':'completed'}
            (cwd.parent.parent/'runtime/changed').write_text('changed')
        (cwd/'answer.md').write_text('合成検査。実Web調査ではない。先例と普及は未確認。')
        assert engine.public_main(cwd,['attach-file','answer.md','--title','合成報告','--kind',cfg['report_kind'],'--location',cfg['report_location']])==0
        p=inquiry.refresh_packet(session,cfg['packet_hash'])
        assert engine.public_main(cwd,['read',p['sha256'],'sources','--limit','100000'])==0
        assert engine.public_main(cwd,['report'])==0
        return 0,{'status':'completed'}
    monkeypatch.setattr(inquiry.worker,'run',execute)
    return calls,execute


def test_novelty_focus_does_not_need_review_question(source,tmp_path,monkeypatch):
    key=reviewed(source);before=engine.manifest(source)
    calls,_=inquiry_worker(monkeypatch)
    result=inquiry.run(source,tmp_path/'out',Path(sys.executable),1,key,None,10,10)
    assert result['status']=='completed',result
    assert calls==['inquiry','inspect']
    assert result['formal_revisions']==result['formal_reviews']==0
    assert result['additional_sources']==2 and engine.manifest(source)==before
    after=d.report(tmp_path/'out/session')
    assert after['revisions'][0]['reviews']==d.report(source)['revisions'][0]['reviews']
    assert after['revisions'][0]['reviews'][0]['novelty']=='unconfirmed'


@pytest.mark.parametrize('value,novelty',[('test','differentiated'),('develop','unconfirmed'),('drop','unconfirmed'),('unknown','unconfirmed'),('develop','known'),('drop','known'),('unknown','known')])
def test_novelty_rejects_other_judgments_before_output(source,tmp_path,value,novelty):
    key=reviewed(source,value,novelty)
    with pytest.raises(ValueError,match='testで、novelty'):
        inquiry.run(source,tmp_path/'out',Path(sys.executable),1,key,None,10,10)
    assert not (tmp_path/'out').exists()


def test_novelty_rejects_old_revision_and_wrong_review(source,tmp_path):
    key=reviewed(source)
    next_proposal=proposal(d.packet(source,1,'develop'))
    next_proposal['roles'].append({'card_id':2,'role':'保護役追加'})
    d.submit(source,next_proposal)
    for chosen in [key,'0'*64]:
        with pytest.raises(ValueError):inquiry.run(source,tmp_path/'out',Path(sys.executable),1,chosen,None,10,10)
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('flags',[[],['--novelty','--question-index','0']])
def test_focus_cli_is_explicit_and_exclusive(flags):
    with pytest.raises(SystemExit) as exc:
        inquiry.main(['unused','unused-output','--codex',sys.executable,'--revision','1','--review-hash','0'*64,'--research-seconds','10','--inspect-seconds','10',*flags])
    assert exc.value.code==2


@pytest.mark.parametrize('budgets',[(1,None),(None,1),(0,1),(1,float('nan')),(float('inf'),1)])
def test_cycle_requires_paired_finite_positive_budgets(source,tmp_path,budgets):
    with pytest.raises(ValueError):cycle.prepare(source,tmp_path/'out',Path(sys.executable),10,10,research_seconds=budgets[0],inspect_seconds=budgets[1])
    assert not (tmp_path/'out').exists()


def install_cycle_workers(monkeypatch,values=('test',),failure=None):
    discovery_calls=fake_worker(monkeypatch,values=values,questions=True)
    original=engine.worker.run
    research_calls,research=inquiry_worker(monkeypatch,failure)
    def execute(*args):
        cfg=json.loads((args[4]/'public-config.json').read_text())
        return research(*args) if cfg['stage'] in {'inquiry','inspect'} else original(*args)
    monkeypatch.setattr(engine.worker,'run',execute)
    return discovery_calls,research_calls


@pytest.mark.parametrize('values',[('test',),('develop','test')])
def test_cycle_follows_final_review_once_without_regrading(source,tmp_path,monkeypatch,values):
    dc,rc=install_cycle_workers(monkeypatch,values)
    before=engine.manifest(source)
    out=cycle.prepare(source,tmp_path/'out',Path(sys.executable),10,10,research_seconds=10,inspect_seconds=10)
    assert cycle.run_prepared(out)==0
    r=json.loads((out/'result.json').read_text())
    assert rc==['inquiry','inspect'] and len(dc)==2*len(values)
    assert r['followup']['status']=='completed'
    assert r['followup']['result']['focus']['revision']==len(values)
    assert r['judgment']['novelty']=='unconfirmed'
    assert r['verified_revisions']==r['verified_reviews']==len(values)
    assert engine.manifest(source)==before
    assert d.report(out/'session')['revisions'][-1]['reviews']==d.report(out/f'round-{len(values)}/session')['revisions'][-1]['reviews']


@pytest.mark.parametrize('failure,status,n',[(('inquiry','timeout'),'followup_failed',1),(('inquiry','missing'),'followup_failed',1),(('inspect','missing'),'followup_failed',2),(('inspect','change'),'failed',2)])
def test_followup_failure_keeps_formal_round_but_no_final_session(source,tmp_path,monkeypatch,failure,status,n):
    dc,rc=install_cycle_workers(monkeypatch,failure=failure)
    out=cycle.prepare(source,tmp_path/'out',Path(sys.executable),10,10,research_seconds=10,inspect_seconds=10)
    assert cycle.run_prepared(out)==2
    r=json.loads((out/'result.json').read_text())
    assert r['status']==status and len(rc)==n and r['ended_at']
    assert (out/'round-1/session').is_dir() and not (out/'session').exists()
    assert len(d.report(out/'round-1/session')['revisions'])==1


@pytest.mark.parametrize('value,novelty,budgets',[('test','known',True),('develop','unconfirmed',True),('drop','unconfirmed',True),('test','unconfirmed',False)])
def test_cycle_skips_ineligible_or_unrequested_followup(source,tmp_path,monkeypatch,value,novelty,budgets):
    fake_worker(monkeypatch,values=(value,value))
    original=cycle.next_step
    def decide(*args):
        result=original(*args)
        result['judgment']['novelty']=novelty
        return result
    monkeypatch.setattr(cycle,'next_step',decide)
    def forbidden(*args,**kwargs):pytest.fail('ineligible research started')
    monkeypatch.setattr(inquiry,'run',forbidden)
    out=cycle.prepare(source,tmp_path/'out',Path(sys.executable),10,10,research_seconds=10 if budgets else None,inspect_seconds=10 if budgets else None)
    assert cycle.run_prepared(out)==0
    r=json.loads((out/'result.json').read_text())
    assert (r.get('followup') or {'status':'skipped'})['status']=='skipped'
    assert not (out/'novelty').exists()


def test_real_public_process_cycle_to_research_and_inspect(source,tmp_path):
    backend=tmp_path/'fake-codex'
    backend.write_text('#!'+sys.executable+'\n'+f'''import json,sys,subprocess
sys.dont_write_bytecode=True
from pathlib import Path
work=Path.cwd()
sys.path.insert(0,str(work.parent/'runtime'))
sys.path.insert(1,{str(Path(__file__).resolve().parents[1])!r})
from test_discovery import proposal,assessment
cfg=json.loads((work/'public-config.json').read_text())
def call(args):return json.loads(subprocess.check_output([sys.executable,'public.py',*args],text=True))
p=call(['packet'])
if cfg['stage'] in {{'develop','review'}}:
    response=proposal(p) if cfg['stage']=='develop' else assessment(p)
    if cfg['stage']=='develop':response['plan']={{k:'合成検査の利用説明' for k in ('early','transition','finish','without_core','allocation','comparison')}}
    if cfg['stage']=='review':response.update(value='test',next_questions=[])
    (work/'answer.json').write_text(json.dumps(response))
    call(['submit' if cfg['stage']=='develop' else 'review','answer.json'])
else:
    assert p['data']['inquiry_focus']['question_index'] is None
    assert p['data']['previous_reviews']==[]
    (work/'answer.md').write_text('合成プロセス確認のみ。先例と普及は未確認。')
    call(['attach-file','answer.md','--title','合成','--kind',cfg['report_kind'],'--location',cfg['report_location']])
    p=call(['packet']);call(['read',p['sha256'],'sources','--limit','100000']);call(['report'])
''')
    backend.chmod(0o755)
    out=tmp_path/'out'
    p=subprocess.run([sys.executable,'-B','-m','svdeck.discovery_cycle',str(source),str(out),'--codex',str(backend),'--develop-seconds','10','--review-seconds','10','--research-seconds','10','--inspect-seconds','10'],capture_output=True,text=True,timeout=45)
    assert p.returncode==0,p.stdout+p.stderr
    r=json.loads((out/'result.json').read_text())
    assert r['status']=='completed' and r['followup']['status']=='completed'
    assert r['followup']['result']['additional_sources']==2
    assert engine.manifest(out/'runtime')==engine.manifest(out/'novelty/runtime')
    assert len(d.report(out/'session')['revisions'])==1
    assert d.report(out/'session')['revisions'][0]['reviews'][0]['novelty']=='unconfirmed'


def test_novelty_revalidates_formal_payload_before_output(source,tmp_path):
    reviewed(source)
    path=next(source.glob('review-*.json'));raw=d._read_envelope(path)
    raw['procedure']='refuted'
    envelope=d._envelope(raw)
    path.unlink()
    (source/f"review-0001-{envelope['sha256'][:16]}.json").write_text(json.dumps(envelope,ensure_ascii=False,indent=2))
    before=engine.manifest(source)
    with pytest.raises(ValueError):inquiry.run(source,tmp_path/'out',Path(sys.executable),1,digest(raw),None,10,10)
    assert not (tmp_path/'out').exists() and engine.manifest(source)==before


def test_explicit_known_followup_retains_formal_labels_and_scope(source,tmp_path,monkeypatch):
    key=reviewed(source,novelty='known')
    before=engine.manifest(source)
    old=d.report(source)['revisions'][0]['reviews']
    calls,_=inquiry_worker(monkeypatch,origin='known-use-prevalence')
    result=inquiry.run(source,tmp_path/'out',Path(sys.executable),1,key,None,10,10)
    assert result['status']=='completed',result
    assert calls==['inquiry','inspect']
    assert result['focus']['origin']=='known-use-prevalence'
    assert result['focus']['review_hash']==key
    assert result['focus']['question']==inquiry.NOVELTY_QUESTION
    assert result['formal_revisions']==result['formal_reviews']==0
    assert result['additional_sources']==2 and engine.manifest(source)==before
    assert d.report(tmp_path/'out/session')['revisions'][0]['reviews']==old
    assert old[0]['novelty']=='known'
