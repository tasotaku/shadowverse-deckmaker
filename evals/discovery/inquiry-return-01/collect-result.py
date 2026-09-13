from pathlib import Path
from datetime import datetime,timezone
import json,gzip,shutil,tarfile,tempfile,hashlib,time,sys
from svdeck.discovery_run import check_finish,check_unchanged,manifest,verify_submission,copy_session
from svdeck.journal_store import Journal
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');e=root/'evals/discovery/inquiry-return-01';arm=sys.argv[1]
assert arm in {'a','b'}
proto=json.loads((e/'protocol.json').read_text());launch=json.loads((e/'launch.json').read_text());run=Path(proto['outputs'][arm]);result=json.loads((run/'result.json').read_text());assert result.get('ended_at') and result['status'] not in {'preparing','develop','review'}
started=datetime.now(timezone.utc);tick=time.monotonic();j=Journal(root);item=j.get(e.name);rec=item['record'];stage_id=arm+'-collection';assert not any(s['id']==stage_id for s in rec['stages']);rec['status']='running';rec['summary']='終了した方式の正式保存・途中資料と記録を回収中。採否は未判定。';rec['stages'].append(dict(id=stage_id,title=arm.upper()+'の提出物と終了記録を回収',status='running',started_at=started.isoformat(),ended_at=None,note='元入力・固定実装と正式保存を再照合し、失敗時も途中資料を保持する。',budget_minutes=3));j.save(rec,item['revision'],'codex-root','終了後の回収を開始')
out=e/arm;out.mkdir(exist_ok=False);stages=[]
try:
    inp=proto['inputs'][arm];check_unchanged(Path(inp['path']),inp['manifest'],exact=True);check_unchanged(run/'runtime',launch['runtime_manifest'],exact=True)
    for s in ['develop','review']:
        work=run/s;expath=run/(s+'-run/run.json')
        if not expath.is_file():continue
        ex=json.loads(expath.read_text());assert ex.get('ended_at')
        dst=out/s;dst.mkdir();checks={}
        if ex['status']=='finished_by_request':
            contract=json.loads((work/'finish-config.json').read_text());request=json.loads((work/'finish-request.json').read_text())
            if s=='develop' and (run/'review/public-config.json').exists():
                actual=manifest(work/'session');sealed=request['session_manifest'];review_packet=json.loads((run/'review/public-config.json').read_text())['packet_hash'];extra='packets/'+review_packet+'.json';assert set(actual)-set(sealed)=={extra} and all(actual.get(k)==v for k,v in sealed.items());assert (work/'session'/extra).read_bytes()==(run/'review/session'/extra).read_bytes()
                with tempfile.TemporaryDirectory(prefix='sv-return-finish-check-') as temp:
                    replay=Path(temp);paths=set(contract['fixed'])|{'finish-config.json','finish-request.json','.public.lock'}|{'session/'+name for name in sealed}|{'operations/'+p.name for p in (work/'operations').glob('*.json')}
                    for name in paths:
                        d=replay/name;d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(work/name,d)
                    assert check_finish(replay,contract)==ex['finish_evidence']
            else:assert check_finish(work,contract)==ex['finish_evidence']
            assert ex['runner_returncode']==0 and {'finish_confirmed','process_group_gone'}<={x['event'] for x in ex['events']}
            checks['finish_revalidated']=True
        ops=sorted([json.loads(q.read_text()) for q in (work/'operations').glob('*.json')],key=lambda x:x['started_at'])
        for name in ['prompt.md','public-config.json','input-summary.json','finish-config.json','finish-request.json','proposal.json','review.json','final-message.md']:
            if (work/name).is_file():shutil.copyfile(work/name,dst/name)
        shutil.copyfile(expath,dst/'run.json')
        with gzip.open(dst/'public-operations.json.gz','wt',encoding='utf-8') as stream:json.dump(ops,stream,ensure_ascii=False)
        stages.append(dict(stage=s,started_at=ex['started_at'],ended_at=ex['ended_at'],wall_seconds=(datetime.fromisoformat(ex['ended_at'])-datetime.fromisoformat(ex['started_at'])).total_seconds(),monitor_seconds=ex['elapsed_seconds'],status=ex['status'],operations=len(ops),operation_errors=[{k:o.get(k) for k in ['args','exit_code','started_at','ended_at','stderr']} for o in ops if o['exit_code']!=0],query_operations=sum(o['args'][0]=='query' for o in ops),checks=checks))
    completed=result['status']=='completed';session=run/'session' if completed else run/'develop/session'
    if completed:
        assert result['formal_revisions']==result['formal_reviews']==1
        verify_submission(session,'develop',4);verify_submission(session,'review',4)
    review_partial = None
    if not completed and (run/'review/session').is_dir():
        review_partial = root/('data/discovery/inquiry-return-01-'+arm+'-review-partial')
        assert not review_partial.exists()
        copy_session(run/'review/session',review_partial)
        check_unchanged(review_partial,manifest(run/'review/session'),exact=True)
        with tarfile.open(out/'review-partial-session.tar.gz','w:gz') as archive:archive.add(review_partial,arcname='session')
    check_unchanged(session,inp['manifest'])
    dest=root/('data/discovery/inquiry-return-01-'+arm+('-result' if completed else '-partial'));assert not dest.exists();copy_session(session,dest);check_unchanged(dest,manifest(session),exact=True)
    with tarfile.open(out/'session.tar.gz','w:gz') as archive:archive.add(dest,arcname='session')
    for name in ['result.json','report.json','develop-report.json','review-report.json']:
        if (run/name).is_file():shutil.copyfile(run/name,out/name)
    assert hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest()==proto['main_db_sha256']
    ended=datetime.now(timezone.utc);v=dict(arm=arm,collection_started_at=started.isoformat(),collection_ended_at=ended.isoformat(),collection_seconds=time.monotonic()-tick,end_to_collection_seconds=(started-datetime.fromisoformat(result['ended_at'])).total_seconds(),status=result['status'],failure=result.get('failure'),stages=stages,judgment=result.get('judgment'),preserved_session=str(dest),preserved_review_partial=str(review_partial) if review_partial else None,session_manifest=manifest(dest),formal_revisions=len(list(dest.glob('revision-*.json'))),formal_reviews=len(list(dest.glob('review-*.json'))),additional_sources=len(list((dest/'sources').glob('*.json')))-inp['sources'],original_input_and_runtime_unchanged=True,main_db_unchanged=True,limits='正式資料・公開操作と実行メタデータだけを保存。実Codexの私的stdout/JSONL/推論ログは未読。時刻差と監視時間・回収待ちを分け、実作業時間や休止原因は推定しない。')
    (out/'verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
    item=j.get(e.name);rec=item['record'];s=next(s for s in rec['stages'] if s['id']==stage_id);s.update(status='completed',ended_at=ended.isoformat(),note='正式保存・入力と実装保持を再検査して回収。結果: '+result['status']+'。採否は未判定。');rec['evidence_paths'].append(str(out.relative_to(root)));j.save(rec,item['revision'],'codex-root','終了した方式の原本保持を確認して回収');(e/'journal-record.json').write_text(json.dumps(j.get(e.name),ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v[k] for k in ['arm','status','judgment','formal_revisions','formal_reviews','additional_sources','end_to_collection_seconds','collection_seconds']},ensure_ascii=False))
except Exception as exc:
    (out/'collection-failure.json').write_text(json.dumps(dict(started_at=started.isoformat(),ended_at=datetime.now(timezone.utc).isoformat(),error=repr(exc),ai_repeated=False),ensure_ascii=False,indent=2)+'\n');raise
