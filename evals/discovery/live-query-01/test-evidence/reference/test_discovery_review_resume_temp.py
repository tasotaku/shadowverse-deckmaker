from pathlib import Path
import json
import os
import subprocess
import sys
import pytest

from svdeck import discovery as d
from svdeck import discovery_run as r
from test_discovery import proposal, assessment
from test_discovery_run_temp import source, fake_worker


@pytest.fixture
def latest(source):
    payload = proposal(d.packet(source, 1, 'develop'))
    payload['roles'].append({'card_id': 2, 'role': '追加保護'})
    d.submit(source, payload)
    return source


def test_review_only_preserves_parent_review_and_every_proposal(latest, tmp_path, monkeypatch):
    before = r.manifest(latest)
    calls = fake_worker(monkeypatch)
    out = tmp_path/'out'
    result = r.run(latest,out,Path(sys.executable),None,10,revision=2,review_only=True)
    assert result['status'] == 'completed',result
    assert calls == ['review']
    assert not (out/'develop').exists()
    assert result['formal_revisions'] == 0 and result['formal_reviews'] == 1
    assert result['review_only'] is True and result['expected_revision'] == 2
    assert r.manifest(latest) == before
    after = r.manifest(out/'session')
    assert all(after.get(name) == key for name,key in before.items())
    report = d.report(out/'session')
    assert len(report['revisions']) == 2
    assert report['revisions'][0]['reviews'][0]['author'] == 'independent'
    assert report['revisions'][1]['reviews'][0]['author'] == result['stages'][0]['author']


@pytest.mark.parametrize('revision,budget,review_only',[(None,None,True),(0,None,True),(-1,None,True),(2,1,True),(None,None,False)])
def test_incompatible_options_fail_before_output(latest,tmp_path,revision,budget,review_only):
    with pytest.raises(ValueError):
        r.run(latest,tmp_path/'out',Path(sys.executable),budget,10,revision=revision,review_only=review_only)
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('revision',[1,3])
def test_only_latest_saved_revision_runs(latest,tmp_path,monkeypatch,revision):
    calls = fake_worker(monkeypatch)
    result = r.run(latest,tmp_path/'out',Path(sys.executable),None,10,revision=revision,review_only=True)
    assert result['status']=='failed' and not calls
    assert '最新' in result['failure']


@pytest.mark.parametrize('broken',['proposal','packet','source'])
def test_invalid_saved_input_rejected_before_worker(latest,tmp_path,monkeypatch,broken):
    p = d._revision(latest,2)
    path = latest/'revision-0002.json' if broken=='proposal' else latest/'packets'/(p['packet_hash']+'.json')
    if broken=='source':
        path = latest/'snapshot.db'
    path.write_bytes(b'broken')
    calls = fake_worker(monkeypatch)
    result=r.run(latest,tmp_path/'out',Path(sys.executable),None,10,revision=2,review_only=True)
    assert result['status']=='failed' and not calls
    assert not (tmp_path/'out/session').exists()


@pytest.mark.parametrize('mode,expected',[('no_review','review_missing'),('invalid_saved_review','failed'),('wrong_saved_author','failed')])
def test_failed_review_not_merged(latest,tmp_path,monkeypatch,mode,expected):
    before = r.manifest(latest)
    calls = fake_worker(monkeypatch,mode)
    result=r.run(latest,tmp_path/'out',Path(sys.executable),None,10,revision=2,review_only=True)
    assert result['status']==expected and calls==['review']
    assert not (tmp_path/'out/session').exists()
    assert r.manifest(latest)==before


@pytest.mark.parametrize('mode',['timeout','prepared_change','forbidden_operations'])
def test_review_guardrails(latest,tmp_path,monkeypatch,mode):
    fake_worker(monkeypatch)
    original = r.worker.run
    def execute(*args):
        result = original(*args)
        work=args[4]
        if mode=='timeout': return -15,{'status':'timed_out'}
        if mode=='prepared_change': (work.parent/'prepare/session/revision-0001.json').write_text('{}')
        if mode=='forbidden_operations':
            for command in ('submit','attach','attach-file'):
                assert r.public_main(work,[command,'answer.json'])==2
        return result
    monkeypatch.setattr(r.worker,'run',execute)
    result=r.run(latest,tmp_path/'out',Path(sys.executable),None,10,revision=2,review_only=True)
    assert result['status']==({'timeout':'review_failed','prepared_change':'failed','forbidden_operations':'completed'}[mode])
    if mode!='forbidden_operations': assert not (tmp_path/'out/session').exists()


def test_actual_cli_review_only_uses_frozen_public_entry(latest,tmp_path):
    response=assessment(d.packet(latest,2,'review'))
    fake=tmp_path/'fake-codex'
    fake.write_text(f'''#!{sys.executable}
from pathlib import Path
import json,subprocess,sys
p=json.loads(subprocess.check_output([sys.executable,'public.py','packet'],text=True))
assert p['data']['stage']=='review' and p['data']['revision']==2
assert p['data']['previous_reviews']==[] and p['data']['review_contexts']==[]
assert not list(Path('session').glob('review-*.json'))
assert len(list(Path('session/packets').glob('*.json')))==1
payload={response!r}
payload['packet_hash']=p['sha256']
Path('answer.json').write_text(json.dumps(payload))
subprocess.run([sys.executable,'public.py','review','answer.json'],check=True)
subprocess.run([sys.executable,'public.py','report'],check=True)
Path('final-message.md').write_text('Synthetic CLI check, no utility judgment.')
''')
    fake.chmod(0o755)
    out=tmp_path/'out'
    env={**os.environ,'PYTHONPATH':str(Path(r.__file__).resolve().parents[1])}
    command=[sys.executable,'-m','svdeck.discovery_run',str(latest),str(out),'--codex',str(fake),'--review-only','--revision','2','--review-seconds','10']
    p=subprocess.run(command,text=True,capture_output=True,env=env)
    assert p.returncode==0,p.stderr+p.stdout
    result=json.loads(p.stdout)
    assert result['formal_revisions']==0 and result['formal_reviews']==1
    saved=json.loads((out/'result.json').read_text())
    assert [s['stage'] for s in saved['stages']]==['review']
    assert saved['stages'][0]['run']['status']=='completed'
