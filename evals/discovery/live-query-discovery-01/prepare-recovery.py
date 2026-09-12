from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, subprocess, os, tarfile, time
from svdeck import discovery
from svdeck.discovery_run import manifest, copy_session
from svdeck.journal_store import Journal
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker')
e=root/'evals/discovery/live-query-discovery-01'
proto=json.loads((e/'protocol.json').read_text())
fix=json.loads((e/'intake-implementation.json').read_text())
source=Path(proto['source']); common=Path('/tmp/sv-live-query-discovery-01-common'); j=Journal(root)
assert not source.exists()
assert hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest()==proto['db_sha256']
assert manifest(common/'docs')==proto['common_docs_manifest']
assert (root/'src/svdeck/meta.py').read_bytes()==Path(fix['worktree'],'src/svdeck/meta.py').read_bytes()
started=datetime.now(timezone.utc).isoformat(); tick=time.monotonic()
(e/'prepare-recovery-start.json').write_text(json.dumps({'started_at':started,'fixed_articles':proto['articles'],'method':'初回失敗を残したまま、同じ8記事を共通修正した公開startで再取得。実AIは未起動。'},ensure_ascii=False,indent=2)+'\n')
c=j.get(e.name);r=c['record'];r['stages'].insert(3,{'id':'prepare-recovery','title':'共通修正後の8記事取得と両方式の入力照合','status':'running','started_at':started,'ended_at':None,'note':'実探索前に同じ8記事を再取得し、旧条件・旧実装も保持する。','budget_minutes':5});r['status']='running';j.save(r,c['revision'],'codex-root','共通修正後の入力準備を開始')
try:
    frozen={}
    for side in ['a','b']:
        prior=json.loads((e/(side+'-runtime.json')).read_text())
        old=Path(prior['runtime']); assert manifest(old)==prior['manifest']
        launch=Path('/tmp/sv-live-query-discovery-01-'+side+'-fixed-launch'); launch.mkdir(exist_ok=False)
        shutil.copytree(old,launch/'runtime'); shutil.copyfile(root/'src/svdeck/meta.py',launch/'runtime/svdeck/meta.py'); shutil.copytree(common/'docs',launch/'docs')
        frozen[side]={'runtime':str(launch/'runtime'),'frozen_at':datetime.now(timezone.utc).isoformat(),'manifest':manifest(launch/'runtime'),'docs_manifest':manifest(launch/'docs'),'common_intake_commit':fix['commit'],'based_on_runtime_file':side+'-runtime.json'}
        assert [k for k,v in frozen[side]['manifest'].items() if prior['manifest'][k]!=v]==['svdeck/meta.py']
        (e/(side+'-frozen-runtime.json')).write_text(json.dumps(frozen[side],ensure_ascii=False,indent=2)+'\n')
    differences=[k for k,v in frozen['a']['manifest'].items() if frozen['b']['manifest'][k]!=v]
    assert differences==['svdeck/discovery.py','svdeck/discovery_run.py']
    result=discovery.start(source,root/'data/cards.db',proto['class_name'],proto['format'],'独自で、強い基盤に無理なく入り、通常構築との比較から試す理由があるデッキの種を考案してください。',docs=common/'docs',articles=proto['articles'])
    packet=discovery.packet(source,0,'develop')
    hashes={}
    for side in ['a','b']:
        preview=common/(side+'-recovery-preview');copy_session(source,preview)
        p=subprocess.run(['/tmp/sv-system-venv/bin/python','-B','-m','svdeck.discovery','packet',str(preview),'--revision','0','--summary'],capture_output=True,text=True,check=True,env={**os.environ,'PYTHONPATH':frozen[side]['runtime']})
        hashes[side]=json.loads(p.stdout)['sha256']
    assert hashes['a']==hashes['b']==packet['sha256']
    assert hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest()==proto['db_sha256']
    assert discovery.report(source)['revisions']==[]
    ended=datetime.now(timezone.utc).isoformat()
    proof={'started_at':started,'ended_at':ended,'elapsed_seconds':time.monotonic()-tick,'article_start':result,'initial_packet_hash':packet['sha256'],'packet_hashes':hashes,'packet_same_both':True,'source_manifest':manifest(source),'only_runtime_differences':differences,'common_docs_identical':True,'cards_count':len(packet['data']['context']['cards']),'sources_count':len(packet['data']['sources']),'formal_revisions':0,'formal_reviews':0,'main_db_unchanged':True}
    (e/'preparation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    with tarfile.open(e/'input.tar.gz','w:gz') as tar:tar.add(source,arcname='session')
    c=j.get(e.name);r=c['record'];st=next(s for s in r['stages'] if s['id']=='prepare-recovery');st.update(status='completed',ended_at=ended,note='同じ8記事を取得。両方式で初回入力が完全一致し、カードDBを保持。正式案・評価はまだ0件。');r['summary']='共通修正後に8記事を取得し、両方式の固定入力一致を確認。比較AIは未起動。';r['evidence_paths']+=['evals/discovery/live-query-discovery-01/'+name for name in ['prepare-recovery-start.json','a-frozen-runtime.json','b-frozen-runtime.json','preparation.json','input.tar.gz','prepare-recovery.py']];j.save(r,c['revision'],'codex-root','共通修正後の8記事入力と両方式一致を確認');(e/'journal-record.json').write_text(json.dumps(j.get(e.name),ensure_ascii=False,indent=2)+'\n');print({k:proof[k] for k in ['started_at','ended_at','elapsed_seconds','initial_packet_hash','cards_count','sources_count']})
except Exception as exc:
    ended=datetime.now(timezone.utc).isoformat();(e/'prepare-recovery-failure.json').write_text(json.dumps({'started_at':started,'ended_at':ended,'elapsed_seconds':time.monotonic()-tick,'error':repr(exc),'source_exists':source.exists(),'ai_started':False},ensure_ascii=False,indent=2)+'\n');c=j.get(e.name);r=c['record'];next(s for s in r['stages'] if s['id']=='prepare-recovery').update(status='interrupted',ended_at=ended,note='復旧準備失敗。残った入力と資料を保存し、実AIは起動していない。');r['status']='waiting';r['evidence_paths'].append('evals/discovery/live-query-discovery-01/prepare-recovery-failure.json');j.save(r,c['revision'],'codex-root','復旧準備の失敗を保存');raise
