from pathlib import Path
import json
import sys
import pytest

from svdeck import discovery as d
from svdeck import discovery_run as r
from svdeck.discovery_evidence import digest, write_new
from test_discovery import make_db, proposal, assessment


@pytest.fixture
def source(tmp_path):
    db = tmp_path / 'cards.db'
    make_db(db)
    folder = tmp_path / 'source'
    d.start(folder, db, 'ウィッチ', 'rotation', '保存評価から別用途を改訂')
    d.submit(folder, proposal(d.packet(folder, 0, 'develop')))
    d.review(folder, assessment(d.packet(folder, 1, 'review')))
    return folder


def fake_worker(monkeypatch, mode='ok'):
    calls = []
    def execute(command, output, timeout, grace, cwd, stdin, clock, journal):
        config = json.loads((cwd / 'public-config.json').read_text())
        stage, revision = config['stage'], config['revision']
        calls.append(stage)
        assert clock == 'elapsed' and timeout > 0
        session = cwd / 'session'
        p = json.loads((session / 'packets' / (config['packet_hash'] + '.json')).read_text()) if stage == 'review' else d.packet(session, revision, stage)
        if stage == 'review':
            assert p['data']['previous_reviews'] == []
            assert p['data']['review_contexts'] == []
            assert not list(session.glob('review-*.json'))
            assert len(list((session / 'packets').glob('*.json'))) == 1
            assert r.public_main(cwd, ['packet', '--summary']) == 0
        else:
            assert len(p['data']['previous_reviews']) == (1 if revision else 0)
        if mode == 'no_proposal' and stage == 'develop':
            return 0, {'status': 'completed'}
        if mode == 'no_review' and stage == 'review':
            return 0, {'status': 'completed'}
        if mode == 'attach' and stage == 'develop':
            (cwd/'observation.txt').write_text('検証用に観察した事実。未採点。')
            assert r.public_main(cwd,['attach-file','observation.txt','--title','追加観察','--kind','test','--location','test://observation'])==0
            p=d.packet(session,revision,stage)
        response = proposal(p) if stage == 'develop' else assessment(p)
        response['author'] = '/root'
        if mode == 'missing_author':
            response.pop('author')
        if stage == 'develop':
            response['roles'].append({'card_id': 2, 'role': '追加保護'})
        path = cwd / 'answer.json'
        write_new(path, response)
        if mode == 'changed_parent_packet' and stage == 'develop':
            original=d._revision(session,revision)
            altered=p['data'].copy();altered['proposal']=None
            forged=d._envelope(altered)
            write_new(session/'packets'/(forged['sha256']+'.json'),forged)
            copied={**original,'packet_hash':forged['sha256'],'parent_revision':revision,'title':'only title changed','change':'only explanation','author':config['author']}
            d.submit(session,copied)
        elif mode == 'invalid_saved_review' and stage == 'review':
            response['value'] = 'not-a-judgment'
            response['author'] = config['author']
            value = {**response, 'revision': revision, 'proposal_hash': digest(p['data']['proposal'])}
            write_new(session / f'review-{revision:04d}-{digest(value)[:16]}.json', d._envelope(value))
        elif mode == 'wrong_saved_author' and stage == 'review':
            response['author'] = 'unassigned-reviewer'
            d.review(session, response)
        else:
            assert r.public_main(cwd, ['submit' if stage == 'develop' else 'review', 'answer.json']) == 0
        if mode == 'extra_parent_review' and stage == 'develop':
            injected = assessment(d.packet(session, 1, 'review'))
            injected['author'] = 'unexpected-parent-review'
            d.review(session, injected)
        if mode == 'extra_proposal' and stage == 'develop':
            assert r.public_main(cwd, ['submit', 'answer.json']) == 0
        if mode == 'changed_input' and stage == 'develop':
            (cwd / 'input-summary.json').write_text('{}')
        if mode == 'changed_runtime' and stage == 'develop':
            runtime_file = cwd.parent / 'runtime/svdeck/discovery.py'
            runtime_file.write_text(runtime_file.read_text() + '\n# changed\n')
        if mode == 'timed_out' and stage == 'develop':
            return 124, {'status': 'timed_out'}
        return 0, {'status': 'completed'}
    monkeypatch.setattr(r.worker, 'run', execute)
    return calls


@pytest.mark.parametrize('mode',['ok','attach','missing_author'])
def test_revision_and_review_are_joined_without_touching_source(source, tmp_path, monkeypatch, mode):
    before = r.manifest(source)
    calls = fake_worker(monkeypatch,mode)
    out = tmp_path / 'out'
    result = r.run(source, out, Path(sys.executable), 10, 10)
    assert result['status'] == 'completed', result
    assert calls == ['develop', 'review']
    assert r.manifest(source) == before
    report = d.report(out / 'session')
    assert len(report['revisions']) == 2
    assert report['revisions'][0]['reviews'][0]['author'] == 'independent'
    assert report['revisions'][1]['reviews'][0]['author'] == result['stages'][1]['author']
    assert d._revision(out/'session',2)['author'] == result['stages'][0]['author']
    assert result['stages'][0]['author'] != result['stages'][1]['author']
    for stage in ('develop','review'):
        work = out/stage
        raw = json.loads((work/'answer.json').read_text())
        assert raw.get('author') == (None if mode == 'missing_author' else '/root')
        logs=[json.loads(p.read_text()) for p in (work/'operations').glob('*.json')]
        saved = next(x['submission'] for x in logs if 'submission' in x)
        assert saved['response'] == raw
        formal = d._revision(work/'session',2) if stage == 'develop' else d.report(work/'session')['revisions'][-1]['reviews'][0]
        assert all(formal[k] == value for k,value in raw.items() if k != 'author')
    assert report['revisions'][1]['parent_revision'] == 1
    assert result['judgment']['value'] == 'develop'
    assert result['formal_revisions'] == result['formal_reviews'] == 1


@pytest.mark.parametrize('mode,expected,calls_expected', [
    ('no_proposal','develop_missing',['develop']),
    ('timed_out','develop_failed',['develop']),
    ('extra_proposal','failed',['develop']),
    ('extra_parent_review','failed',['develop']),
    ('changed_parent_packet','failed',['develop']),
    ('changed_input','failed',['develop']),
    ('changed_runtime','failed',['develop']),
    ('no_review','review_missing',['develop','review']),
    ('invalid_saved_review','failed',['develop','review']),
    ('wrong_saved_author','failed',['develop','review']),
])
def test_failure_does_not_advance_or_publish_success(source,tmp_path,monkeypatch,mode,expected,calls_expected):
    before=r.manifest(source)
    calls=fake_worker(monkeypatch,mode)
    out=tmp_path/'out'
    result=r.run(source,out,Path(sys.executable),10,10)
    assert result['status']==expected, result
    assert calls==calls_expected
    assert not (out/'session').exists()
    assert r.manifest(source)==before
    assert json.loads((out/'result.json').read_text())['ended_at']


@pytest.mark.parametrize('limits', [(0,1), (1,-1), (float('nan'),1), (1,float('inf'))])
def test_invalid_limits_fail_before_output(source,tmp_path,limits):
    with pytest.raises(ValueError):
        r.run(source,tmp_path/'out',Path(sys.executable),*limits)
    assert not (tmp_path/'out').exists()


def test_existing_or_nested_output_is_not_overwritten(source,tmp_path):
    out=tmp_path/'out';out.mkdir();(out/'keep').write_text('keep')
    with pytest.raises(FileExistsError):
        r.run(source,out,Path(sys.executable),1,1)
    assert (out/'keep').read_text()=='keep'
    with pytest.raises(ValueError):
        r.run(source,source/'nested',Path(sys.executable),1,1)


def test_symlink_is_rejected(source,tmp_path):
    (source/'linked').symlink_to(tmp_path/'cards.db')
    with pytest.raises(ValueError,match='共有リンク'):
        r.run(source,tmp_path/'out',Path(sys.executable),1,1)


def test_public_rejections_and_help_are_logged(source,tmp_path):
    work=tmp_path/'work';r.copy_session(source,work/'session')
    p=d.packet(work/'session',1,'develop')
    write_new(work/'public-config.json',{'stage':'develop','revision':1})
    attempts=[(['--help'],0),(['read','--help'],0),(['attach-file','--help'],0),
              (['packet','--stage','review'],2),(['submit','../outside.json'],2),
              (['recall','anything'],2),(['review','answer.json'],2)]
    for args,code in attempts:
        assert r.public_main(work,args)==code
    logs=[json.loads(p.read_text()) for p in (work/'operations').glob('*.json')]
    assert len(logs)==len(attempts)
    assert all(p['started_at'] and p['ended_at'] for p in logs)
    assert sum(p['exit_code']!=0 for p in logs)==4


def test_public_review_cannot_read_prior_develop_packet(source,tmp_path):
    work=tmp_path/'work';r.copy_session(source,work/'session')
    p=d.packet(work/'session',1,'develop')
    write_new(work/'public-config.json',{'stage':'review','revision':1})
    assert r.public_main(work,['read',p['sha256'],'previous_reviews'])==2
    assert r.public_main(work,['submit','answer.json'])==2


def test_initial_generation_supported(tmp_path,monkeypatch):
    db=tmp_path/'cards.db';make_db(db);source=tmp_path/'source'
    d.start(source,db,'ウィッチ','rotation','初回')
    calls=fake_worker(monkeypatch)
    result=r.run(source,tmp_path/'out',Path(sys.executable),10,10)
    assert result['status']=='completed',result
    assert result['parent_revision']==0 and result['expected_revision']==1
    assert calls==['develop','review']


def test_actual_subprocess_uses_frozen_public_entry(source,tmp_path):
    template=proposal(d.packet(source,1,'develop'))
    template['author']='/root'
    template['roles'].append({'card_id':2,'role':'追加保護'})
    review_template=assessment(d.packet(source,1,'review'))
    review_template['author']='/root'
    fake=tmp_path/'fake-codex'
    fake.write_text(f'''#!{sys.executable}
from pathlib import Path
import json,subprocess,sys
work=Path.cwd()
p=json.loads(subprocess.check_output([sys.executable,'public.py','packet'],text=True))
is_review=p['data']['stage']=='review'
assert not is_review or (not p['data']['previous_reviews'] and len(list((work/'session/packets').glob('*.json')))==1)
payload={review_template!r} if is_review else {template!r}
payload['packet_hash']=p['sha256']
if not is_review: payload['parent_revision']=p['data']['revision']
(work/'answer.json').write_text(json.dumps(payload))
subprocess.run([sys.executable,'public.py','review' if is_review else 'submit','answer.json'],check=True)
subprocess.run([sys.executable,'public.py','report'],check=True)
(work/'final-message.md').write_text('Synthetic process test; no model or utility judgment.')
''')
    fake.chmod(0o755)
    before=r.manifest(source)
    output=tmp_path/'out'
    result=r.run(source,output,fake,10,10)
    assert result['status']=='completed',result.get('failure',result)
    assert r.manifest(source)==before
    assert all(s['run']['status']=='completed' for s in result['stages'])
    assert not list((output/'runtime').rglob('*.pyc'))
    for stage in ('develop','review'):
        operations=list((output/stage/'operations').glob('*.json'))
        assert len(operations)==3
        assert all(json.loads(p.read_text())['exit_code']==0 for p in operations)


def test_bound_identity_does_not_allow_self_review(source,tmp_path):
    work=tmp_path/'work';r.copy_session(source,work/'session')
    packet=d.packet(work/'session',1,'review')
    author=packet['data']['proposal']['author']
    write_new(work/'public-config.json',{'stage':'review','revision':1,'packet_hash':packet['sha256'],'author':author})
    payload=assessment(packet);payload['author']='different-claim'
    write_new(work/'answer.json',payload)
    before=r.manifest(work/'session')
    assert r.public_main(work,['review','answer.json'])==2
    assert r.manifest(work/'session')==before
    logs=[json.loads(p.read_text()) for p in (work/'operations').glob('*.json')]
    assert '異なるセッション' in logs[0]['stderr']
    assert logs[0]['submission']['response']['author']=='different-claim'
    assert logs[0]['submission']['assigned_author']==author
