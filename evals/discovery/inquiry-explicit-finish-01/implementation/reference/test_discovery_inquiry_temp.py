from pathlib import Path
import json
import sys
import pytest

from svdeck import discovery as d
from svdeck import discovery_inquiry as i
from svdeck import discovery_run as r
from svdeck.discovery_evidence import digest, write_new
from svdeck.discovery_read import read_packet
from svdeck.discovery_sources import load_sources
from test_discovery import make_db, proposal, assessment


@pytest.fixture
def source(tmp_path):
    db=tmp_path/'cards.db';make_db(db);folder=tmp_path/'source'
    d.start(folder,db,'ウィッチ','rotation','保存評価から資料だけを調べる')
    d.submit(folder,proposal(d.packet(folder,0,'develop')))
    d.review(folder,assessment(d.packet(folder,1,'review')))
    d.attach(folder,{'sources':[{'title':'元資料','kind':'test','location':'test://original','observed_at':None,'content':'元の本文\n複数行\n','limitations':['合成資料']}]})
    return folder


def run(source,tmp_path,monkeypatch,mode='ok',inspect_source=None):
    calls=[]
    def execute(command,output,timeout,grace,cwd,stdin,clock,journal):
        config=json.loads((cwd/'public-config.json').read_text());stage=config['stage'];calls.append(stage)
        session=cwd/'session';fixed=d._read_envelope(session/'packets'/(config['packet_hash']+'.json'))
        assert fixed['inquiry_focus']['question']=='継続して得るものは何か'
        assert fixed['previous_reviews']==fixed['review_contexts']==[]
        assert not list(session.glob('review-*.json'))
        assert timeout>0 and clock=='elapsed'
        if stage=='inspect':assert any(s['kind']=='inquiry-result' for s in fixed['sources'])
        if mode=='timeout' and stage=='inquiry':return 124,{'status':'timed_out'}
        if mode=='extra_help':assert r.public_main(cwd,['attach-file','--help'])==0
        if mode=='missing' and stage=='inquiry' or mode=='missing_inspection' and stage=='inspect':return 0,{'status':'completed'}
        (cwd/'answer.md').write_text('問いの照合結果\n根拠は合成資料のみ。実Web調査ではない。\n未確認\n')
        if mode=='not_attached' and stage=='inquiry':return 0,{'status':'completed'}
        attach=['attach-file','answer.md','--title','検査報告','--kind',config['report_kind'],'--location',config['report_location']]
        assert r.public_main(cwd,attach)==0
        if mode=='extra_help':
            for command_name in ['attach-file','attach','read','report','packet']:
                assert r.public_main(cwd,[command_name,'--help'])==0
        if mode=='duplicate_report' and stage=='inquiry':
            (cwd/'answer.md').write_text('改めた別の報告')
            assert r.public_main(cwd,attach)==0
        assert r.public_main(cwd,['packet','--summary'])==0
        updated=i.refresh_packet(session,config['packet_hash'])
        if mode!='no_reread' or stage!='inquiry':
            if mode=='partial_read' and stage=='inquiry':
                assert r.public_main(cwd,['read',updated['sha256'],'sources','--limit','1'])==0
            elif mode=='split_read':
                total=read_packet(session,updated['sha256'],'sources')['total']
                for offset in range(0,total,3):
                    assert r.public_main(cwd,['read',updated['sha256'],'sources','--offset',str(offset),'--limit','3'])==0
            else:assert r.public_main(cwd,['read',updated['sha256'],'sources','--limit','100000'])==0
        if mode=='report_help' and stage=='inquiry':assert r.public_main(cwd,['report','--help'])==0
        elif mode!='no_report' or stage!='inquiry':assert r.public_main(cwd,['report'])==0
        if mode=='changed_report_log' and stage=='inquiry':
            for log in (cwd/'operations').glob('*.json'):
                op=json.loads(log.read_text())
                if op['args']==['report']:
                    op['stdout']='{}';log.write_text(json.dumps(op))
        if mode=='modified_answer' and stage=='inquiry':(cwd/'answer.md').write_text('保存内容とは違う')
        if mode=='modified_input' and stage=='inquiry':(cwd/'input-summary.json').write_text('{}')
        if mode=='modified_source' and stage=='inquiry':(session/'context.json').write_text('{}')
        if mode=='modified_runtime' and stage=='inquiry':(cwd.parent/'runtime/svdeck/discovery.py').write_text('changed')
        if mode=='added_proposal' and stage=='inquiry':d.submit(session,proposal(d.packet(session,1,'develop')))
        if mode=='added_review' and stage=='inquiry':d.review(session,assessment(d.packet(session,1,'review')))
        return 0,{'status':'completed'}
    monkeypatch.setattr(i.worker,'run',execute)
    review_hash=digest(d._reviews(source,1)[0]);before=r.manifest(source)
    result=i.run(source,tmp_path/'out',Path(sys.executable),1,review_hash,0,10,10,inspect_source=inspect_source)
    assert r.manifest(source)==before
    return result,calls,tmp_path/'out'


@pytest.mark.parametrize('mode',['ok','split_read','extra_help'])
def test_source_only_handoff_preserves_original_reviews(source,tmp_path,monkeypatch,mode):
    before=d.report(source)
    result,calls,out=run(source,tmp_path,monkeypatch,mode)
    assert result['status']=='completed',result
    assert calls==['inquiry','inspect']
    assert result['formal_revisions']==result['formal_reviews']==0
    after=d.report(out/'session')
    assert after['revisions'][0]['reviews']==before['revisions'][0]['reviews']
    assert result['additional_sources']==2
    assert len(after['revisions'][0]['review_contexts'][0]['additional_source_hashes'])==3
    assert all(s['submission']['public_reread'] for s in result['stages'])


@pytest.mark.parametrize('mode,status,calls',[
    ('timeout','inquiry_failed',1),('missing','inquiry_missing',1),('missing_inspection','inspect_missing',2),
    ('not_attached','failed',1),('duplicate_report','failed',1),('no_reread','failed',1),('partial_read','failed',1),
    ('no_report','failed',1),('report_help','failed',1),('changed_report_log','failed',1),
    ('modified_answer','failed',1),('modified_input','failed',1),('modified_source','failed',1),
    ('modified_runtime','failed',1),('added_proposal','failed',1),('added_review','failed',1)])
def test_incomplete_or_changed_outputs_do_not_advance(source,tmp_path,monkeypatch,mode,status,calls):
    result,actual,out=run(source,tmp_path,monkeypatch,mode)
    assert result['status']==status,result
    assert len(actual)==calls
    assert not (out/'session').exists()
    assert result['ended_at']


@pytest.mark.parametrize('revision,key,index,seconds',[(1,'0'*64,0,10),(1,None,-1,10),(1,None,1,10),(0,None,0,10),(1,None,True,10),(1,None,0,0),(1,None,0,float('nan'))])
def test_invalid_focus_or_budget_rejected_before_output(source,tmp_path,revision,key,index,seconds):
    key=key or digest(d._reviews(source,1)[0])
    with pytest.raises(ValueError):i.run(source,tmp_path/'out',Path(sys.executable),revision,key,index,seconds,10)
    assert not (tmp_path/'out').exists()


def test_public_stage_blocks_grade_and_altered_question(source,tmp_path):
    work=tmp_path/'work';r.copy_session(source,work/'session')
    p=d.packet(work/'session',1,'review')['data'];p.update(stage='inquiry',inquiry_focus={'question':'fixed'})
    fixed=d._envelope(p);write_new(work/'session/packets'/(fixed['sha256']+'.json'),fixed)
    write_new(work/'public-config.json',{'stage':'inquiry','revision':1,'packet_hash':fixed['sha256']})
    for args in [['submit','answer.json'],['review','answer.json'],['attach-file','../outside'],['packet','--revision','0']]:
        assert r.public_main(work,args)==2
    changed=d._envelope({**p,'inquiry_focus':{'question':'changed'}});write_new(work/'session/packets'/(changed['sha256']+'.json'),changed)
    assert r.public_main(work,['read',changed['sha256'],'packet_metadata'])==2
    assert len(list((work/'operations').glob('*.json')))==5


def test_inspect_saved_report_without_repeating_research(source,tmp_path,monkeypatch):
    saved=d.attach(source,{'sources':[{'title':'先の調査','kind':'inquiry-result','location':'test://prior-inquiry','observed_at':None,'content':'保存済みの調査結果。合成資料。','limitations':['合成資料']}]})['added'][0]
    result,calls,out=run(source,tmp_path,monkeypatch,'extra_help',saved)
    assert result['status']=='completed',result
    assert calls==['inspect'] and result['inspect_source']==saved
    assert result['additional_sources']==1
    assert len(d.report(out/'session')['revisions'][0]['reviews'])==1


@pytest.mark.parametrize('source_key',['0'*64,'wrong_kind'])
def test_inspect_requires_a_saved_research_report(source,tmp_path,source_key):
    if source_key=='wrong_kind':source_key=load_sources(source)[0]['source_hash']
    with pytest.raises(ValueError):i.run(source,tmp_path/'out',Path(sys.executable),1,digest(d._reviews(source,1)[0]),0,10,10,inspect_source=source_key)
    assert not (tmp_path/'out').exists()


def test_actual_process_reads_frozen_public_entry(source,tmp_path):
    fake=tmp_path/'fake-codex'
    fake.write_text(f'''#!{sys.executable}
from pathlib import Path
import json,subprocess,sys
work=Path.cwd();config=json.loads((work/'public-config.json').read_text())
def call(args):return json.loads(subprocess.check_output([sys.executable,'public.py',*args],text=True))
p=call(['packet']);assert p['data']['previous_reviews']==[]
(work/'answer.md').write_text('合成プロセス検査の報告。実際のカード調査や有用性評価ではない。')
call(['attach-file','answer.md','--title','検査用','--kind',config['report_kind'],'--location',config['report_location']])
p=call(['packet']);call(['read',p['sha256'],'sources','--limit','100000']);call(['report'])
(work/'final-message.md').write_text('Synthetic process verification only.')
''')
    fake.chmod(0o755)
    result=i.run(source,tmp_path/'out',fake,1,digest(d._reviews(source,1)[0]),0,10,10)
    assert result['status']=='completed',result
    assert all(s['run']['status']=='completed' for s in result['stages'])
    assert not list((tmp_path/'out/runtime').rglob('*.pyc'))
