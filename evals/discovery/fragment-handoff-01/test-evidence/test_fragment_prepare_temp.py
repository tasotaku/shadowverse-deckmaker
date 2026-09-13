"""Prepare A/B, then use real public CLI with synthetic workers only."""
from pathlib import Path
import json
import os
import subprocess
import sys

import pytest
from svdeck import discovery as d, discovery_run as r
from svdeck.discovery_evidence import read_object
from test_fragment_scout_temp import source, invoke

ENTRY=Path('evals/discovery/fragment-handoff-01/prepare-arms.py').resolve()
PROTOCOL=Path('evals/discovery/fragment-handoff-01/test-evidence/prepare-protocol-input.json').resolve()


def prepared(source,tmp_path,supplement=False):
    process,saved=invoke(source,tmp_path)
    assert process.returncode==0,process.stdout+process.stderr
    shared=Path(saved['session'])
    if supplement:
        shared=tmp_path/'shared';r.copy_session(Path(saved['session']),shared)
        d.attach(shared,{'sources':[{'title':'追加参考資料','kind':'reference','location':'test://reference',
            'observed_at':None,'content':'合成の参考条件。期待するカード名や結果は指定しない。','limitations':['実デッキではない']} ]})
    args=[sys.executable,str(ENTRY),str(shared),str(tmp_path/'arms'),'--scout-result',str(tmp_path/'out/result.json'),'--protocol',str(PROTOCOL)]
    process=subprocess.run(args,capture_output=True,text=True)
    assert process.returncode==0,process.stdout+process.stderr
    return read_object(tmp_path/'arms/launch.json'),saved,args


def synthetic(tmp_path):
    path=tmp_path/'fake-arms'
    path.write_text(f'''#!{sys.executable}
import json,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,{str(Path('tests').resolve())!r})
from test_discovery import proposal,assessment
work=Path.cwd();cfg=json.loads((work/'public-config.json').read_text())
def call(*args,code=0):
    p=subprocess.run([sys.executable,'public.py',*args],capture_output=True,text=True)
    assert p.returncode==code,p.stdout+p.stderr
    return json.loads(p.stdout) if code==0 else None
p=call('packet')
if cfg['stage']=='develop':
    key=p['data']['finish_from_source']
    assert key in {{s['source_hash'] for s in p['data']['sources']}}
    call('read',p['sha256'],'finish_source','--limit','100000')
    (work/'bridge.md').write_text('変更前/引受/変更後/代償/選択。合成の公開操作検査だけ。')
    call('attach-file','bridge.md','--title','合成記録','--kind','experiment-bridge','--location','test://bridge')
    q=call('packet');assert q['sha256']!=p['sha256'] and q['data']['finish_from_source']==key
    assert q['data']['instruction']==p['data']['instruction']
    response=proposal(q)
else:
    assert 'finish_from_source' not in p['data']
    assert p['data']['previous_reviews']==[]
    response=assessment(p)
(work/'response.json').write_text(json.dumps(response))
call('submit' if cfg['stage']=='develop' else 'review','response.json');call('report');call('finish')
time.sleep(60)
''')
    path.chmod(0o755)
    return path


@pytest.mark.parametrize('supplement',[False,True])
def test_prepare_and_full_public_round_trip(source,tmp_path,supplement):
    launch,saved,args=prepared(source,tmp_path,supplement)
    assert launch['status']=='prepared'
    assert launch['finish_from_source']==saved['submission']['source_hash']
    assert all(launch['assertions'].values())
    assert bool(launch['additional_input_files'])==supplement
    scout_before=r.manifest(Path(saved['session']))
    source_before=r.manifest(Path(launch['source']))
    results={}
    fake=synthetic(tmp_path)
    for arm,settings in launch['arms'].items():
        env={**os.environ,**settings['environment']}
        source=Path(settings['source']);runtime=Path(settings['runtime'])
        assert r.manifest(source)==source_before
        # The wrapper must also run before discovery's direct module main.
        direct=subprocess.run([sys.executable,'-m','svdeck.discovery','packet',str(tmp_path/'arms'/arm/'check-session'),
            '--stage','develop','--revision','0'],env=env,capture_output=True,text=True)
        assert direct.returncode==0,direct.stderr
        assert json.loads(direct.stdout)['data']['finish_from_source']==launch['finish_from_source']
        wrong=subprocess.run([sys.executable,'-m','svdeck.discovery','packet',str(source),'--stage','develop','--revision','0',
            '--finish-from-source','0'*64],env=env,capture_output=True,text=True)
        assert wrong.returncode!=0
        command=[str(fake) if word=='CODEX_PATH' else word for word in settings['command']]
        command[command.index('--develop-seconds')+1]='15'
        command[command.index('--review-seconds')+1]='15'
        process=subprocess.run(command,env=env,capture_output=True,text=True,timeout=40)
        assert process.returncode==0,process.stdout+process.stderr
        result=read_object(Path(settings['output'])/'result.json');results[arm]=result
        assert result['status']=='completed' and result['formal_revisions']==result['formal_reviews']==1
        assert all(stage['run']['status']=='finished_by_request' for stage in result['stages'])
        for stage in ['develop','review']:
            work=Path(settings['output'])/stage
            assert r.check_finish(work,read_object(work/'finish-config.json'))
            packet=d._read_envelope(work/'session/packets'/(read_object(work/'public-config.json')['packet_hash']+'.json'))
            if stage=='develop':assert packet['instruction']==settings['instruction']
            else:assert packet['instruction']==d.REVIEW
        assert r.manifest(source)==source_before
        assert r.manifest(runtime)==settings['runtime_manifest']
    assert results['A']['judgment']==results['B']['judgment']
    assert r.manifest(Path(saved['session']))==scout_before
    assert r.manifest(Path(launch['source']))==source_before
    before=(tmp_path/'arms/launch.json').read_bytes()
    again=subprocess.run(args,capture_output=True,text=True)
    assert again.returncode!=0 and (tmp_path/'arms/launch.json').read_bytes()==before


@pytest.mark.parametrize('changed',['status','session','answer','source_hash'])
def test_invalid_shared_completion_is_not_prepared(source,tmp_path,changed):
    process,saved=invoke(source,tmp_path)
    assert process.returncode==0
    if changed=='status':
        saved['status']='timed_out';(tmp_path/'out/result.json').write_text(json.dumps(saved))
    elif changed=='session':
        (Path(saved['session'])/'context.json').write_text('{}')
    elif changed=='answer':
        (Path(saved['work'])/'answer.md').write_text('changed')
    else:
        saved['submission']['source_hash']='0'*64;(tmp_path/'out/result.json').write_text(json.dumps(saved))
    process=subprocess.run([sys.executable,str(ENTRY),saved['session'],str(tmp_path/'arms'),'--protocol',str(PROTOCOL)],capture_output=True,text=True)
    assert process.returncode!=0 and not (tmp_path/'arms').exists()
