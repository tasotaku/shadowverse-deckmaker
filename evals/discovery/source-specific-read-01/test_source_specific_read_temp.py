import json
from pathlib import Path
import subprocess
import sys

import pytest
from svdeck import discovery as d, discovery_read as reader, discovery_inquiry as inquiry, discovery_run as runner
from svdeck.discovery_evidence import digest, write_new, read_object
from svdeck.discovery_sources import load_sources
from test_discovery_read import session
from test_inquiry_explicit_finish_temp import prepared, source


def add_sources(session):
    bodies=['短い報告\r\n二行目\n三行目\r終わり','data:image/png;base64,'+'A'*1_400_000]
    added=d.attach(session,{'sources':[{'title':f'資料{n}','kind':'test','location':f'test://{n}',
        'observed_at':None,'content':body,'limitations':['合成資料']} for n,body in enumerate(bodies)]})
    return bodies,added['added']


def test_index_and_body_stay_small_and_preserve_newlines(session,monkeypatch):
    bodies,keys=add_sources(session)
    packet=d.packet(session,0,'develop');key=packet['sha256']
    before=runner.manifest(session)
    old=reader.read_packet(session,key,'sources',limit=100000)
    expected=json.dumps([{**s,'content':s['content'].splitlines(keepends=True)} for s in packet['data']['sources']],ensure_ascii=False,indent=2)
    assert ''.join(old['content'])==expected
    summary=reader.packet_summary(session,key)
    assert 'source_index' in {section['section'] for section in summary['sections']}
    assert 'source:HASH' in summary['reading']
    monkeypatch.setattr(reader,'_sections',lambda *a:pytest.fail('must not format all sources'))
    index=reader.read_packet(session,key,'source_index',limit=100)
    assert len(json.dumps(index,ensure_ascii=False))<4096
    item=next(item for item in index['content'] if item['source_hash']==keys[0])
    assert set(item)=={'source_hash','title','kind','location','observed_at','limitations','line_count','char_count','section'}
    assert item['line_count']==4 and item['char_count']==len(bodies[0])
    assert item['section']=='source:'+keys[0]
    first=reader.read_packet(session,key,item['section'],limit=2)
    second=reader.read_packet(session,key,item['section'],offset=first['next_offset'],limit=2)
    assert ''.join(first['content']+second['content'])==bodies[0]
    assert second['next_offset'] is None
    assert runner.manifest(session)==before


@pytest.mark.parametrize('suffix',['0'*64,'../context','A'*64,'a'*63,'g'*64,''])
def test_unknown_or_invalid_source_hash(session,suffix):
    add_sources(session);packet=d.packet(session,0,'develop')
    with pytest.raises(ValueError):reader.read_packet(session,packet['sha256'],'source:'+suffix)


@pytest.mark.parametrize('mode',['duplicate','hash_mismatch','malformed_hash'])
def test_packet_source_identity_is_required(session,mode):
    add_sources(session);data=d.packet(session,0,'develop')['data']
    if mode=='duplicate':data['sources'].append(data['sources'][0])
    elif mode=='hash_mismatch':data['sources'][0]['content']+='changed'
    else:data['sources'][0]['source_hash']='wrong'
    packet=d._envelope(data);write_new(session/'packets'/(packet['sha256']+'.json'),packet)
    for section in ['source_index','source:'+data['sources'][-1]['source_hash']]:
        with pytest.raises(ValueError):reader.read_packet(session,packet['sha256'],section)


def public_ready(work,mode='full'):
    config=read_object(work/'public-config.json')
    answer='調査報告\n根拠と用途\n未確認\n'
    (work/'answer.md').write_text(answer)
    if mode=='before_attach':
        d.attach(work/'session',{'sources':[{'title':'調査報告','kind':config['report_kind'],'location':config['report_location'],
            'observed_at':None,'content':answer,'limitations':[]} ]})
        packet=inquiry.refresh_packet(work/'session',config['packet_hash'])
        key=next(s['source_hash'] for s in packet['data']['sources'] if s['location']==config['report_location'])
        assert runner.public_main(work,['read',packet['sha256'],'source:'+key,'--limit','100'])==0
    assert runner.public_main(work,['attach-file','answer.md','--title','調査報告','--kind',config['report_kind'],'--location',config['report_location']])==0
    packet=inquiry.refresh_packet(work/'session',config['packet_hash'])
    key=next(s['source_hash'] for s in packet['data']['sources'] if s['location']==config['report_location'])
    assert runner.public_main(work,['read',packet['sha256'],'source_index','--limit','100'])==0
    if mode=='wrong_source':
        other=next(s['source_hash'] for s in packet['data']['sources'] if s['source_hash']!=key)
        assert runner.public_main(work,['read',packet['sha256'],'source:'+other,'--limit','100'])==0
    elif mode=='old_packet':
        assert runner.public_main(work,['read',config['packet_hash'],'source:'+key,'--limit','100'])==2
    elif mode=='mixed':
        assert runner.public_main(work,['read',packet['sha256'],'source:'+key,'--offset','2','--limit','1'])==0
        assert runner.public_main(work,['read',packet['sha256'],'sources','--offset','0','--limit','2'])==0
    elif mode=='partial':
        assert runner.public_main(work,['read',packet['sha256'],'source:'+key,'--limit','1'])==0
    elif mode!='before_attach':
        assert runner.public_main(work,['read',packet['sha256'],'source:'+key,'--offset','0','--limit','2'])==0
        assert runner.public_main(work,['read',packet['sha256'],'source:'+key,'--offset','2','--limit','2'])==0
    assert runner.public_main(work,['report'])==0


def test_public_report_only_reread_and_finish_recheck(prepared):
    work,contract=prepared
    public_ready(work)
    assert runner.public_main(work,['finish'])==0
    proof=runner.check_finish(work,contract)
    assert proof
    assert runner.public_main(work,['finish'])==0
    assert runner.check_finish(work,contract)==proof
    request=read_object(work/'finish-request.json')
    path=next(work/'operations'/name for name in request['operation_manifest'] if read_object(work/'operations'/name)['args'][0]=='read')
    op=read_object(path);op['extra']='changed';path.write_text(json.dumps(op))
    with pytest.raises(ValueError):runner.check_finish(work,contract)


@pytest.mark.parametrize('mode',['wrong_source','old_packet','mixed','partial','before_attach'])
def test_incomplete_specific_rereads_do_not_finish(prepared,mode):
    work,contract=prepared
    public_ready(work,mode)
    assert runner.public_main(work,['finish'])==2
    assert runner.check_finish(work,contract) is None


def test_actual_inquiry_workers_use_index_then_only_report(source,tmp_path):
    fake=tmp_path/'fake-source-reader'
    fake.write_text(f'''#!{sys.executable}
import json,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
work=Path.cwd();cfg=json.loads((work/'public-config.json').read_text())
def call(*args):
 p=subprocess.run([sys.executable,'public.py',*args],capture_output=True,text=True)
 assert p.returncode==0,p.stderr
 return json.loads(p.stdout)
p=call('packet');call('read',p['sha256'],'source_index')
(work/'answer.md').write_text('合成報告\\n本文だけ再読\\n未確認\\n')
call('attach-file','answer.md','--title','合成報告','--kind',cfg['report_kind'],'--location',cfg['report_location'])
p=call('packet');index=call('read',p['sha256'],'source_index','--limit','100')
section=next(item['section'] for item in index['content'] if item['location']==cfg['report_location'])
call('read',p['sha256'],section,'--limit','2');call('read',p['sha256'],section,'--offset','2','--limit','2')
call('report');call('finish');time.sleep(60)
''')
    fake.chmod(0o755)
    before=runner.manifest(source)
    result=inquiry.run(source,tmp_path/'out',fake,1,digest(d._reviews(source,1)[0]),0,15,15,explicit_finish=True)
    assert result['status']=='completed',result
    assert [s['run']['status'] for s in result['stages']]==['finished_by_request','finished_by_request']
    for stage in ['inquiry','inspect']:
        work=tmp_path/'out'/stage
        assert runner.check_finish(work,read_object(work/'finish-config.json'))
        operations=[read_object(p) for p in (work/'operations').glob('*.json')]
        assert not any(op['args'][0]=='read' and op['args'][2]=='sources' for op in operations)
    assert runner.manifest(source)==before
