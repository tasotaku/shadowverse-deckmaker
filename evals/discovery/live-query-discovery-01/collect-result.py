from pathlib import Path
from datetime import datetime,timezone
import json,gzip,shutil,tarfile,tempfile,hashlib,time
from svdeck import discovery
from svdeck.discovery_run import check_finish,check_unchanged,manifest,verify_submission,copy_session
from svdeck.journal_store import Journal
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');e=root/'evals/discovery/live-query-discovery-01';proto=json.loads((e/'protocol.json').read_text());prep=json.loads((e/'preparation.json').read_text());started=datetime.now(timezone.utc);tick=time.monotonic();records=[]
(e/'collection-start.json').write_text(json.dumps({'started_at':started.isoformat(),'first_completed_observed_at':'2026-09-12T23:13:45+00:00','source':proto['source']},ensure_ascii=False,indent=2)+'\n')
try:
    check_unchanged(Path(proto['source']),prep['source_manifest'],exact=True)
    for side in ['a','b']:
        run=Path('/tmp/sv-live-query-discovery-01-'+side+'-live');result=json.loads((run/'result.json').read_text());fixed=json.loads((e/(side+'-frozen-runtime.json')).read_text());assert result['status']=='completed' and result['formal_revisions']==result['formal_reviews']==1
        check_unchanged(Path(fixed['runtime']),fixed['manifest'],exact=True);check_unchanged(run/'runtime',fixed['manifest'],exact=True);check_unchanged(run/'session',prep['source_manifest']);verify_submission(run/'session','develop',1);verify_submission(run/'session','review',1)
        out=e/side;out.mkdir(exist_ok=False);stages=[]
        for stage in ['develop','review']:
            work=run/stage;contract=json.loads((work/'finish-config.json').read_text());request=json.loads((work/'finish-request.json').read_text());execution=json.loads((run/(stage+'-run/run.json')).read_text())
            if stage=='develop':
                actual=manifest(work/'session');sealed=request['session_manifest'];review_packet=json.loads((run/'review/public-config.json').read_text())['packet_hash'];extra='packets/'+review_packet+'.json';assert set(actual)-set(sealed)=={extra} and all(actual.get(k)==v for k,v in sealed.items());assert (work/'session'/extra).read_bytes()==(run/'review/session'/extra).read_bytes()
                with tempfile.TemporaryDirectory(prefix='sv-query-finish-check-') as temp:
                    replay=Path(temp);paths=set(contract['fixed'])|{'finish-config.json','finish-request.json','.public.lock'}|{'session/'+name for name in sealed}|{'operations/'+p.name for p in (work/'operations').glob('*.json')}
                    for name in paths:
                        dst=replay/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(work/name,dst)
                    assert check_finish(replay,contract)==execution['finish_evidence']
            else:assert check_finish(work,contract)==execution['finish_evidence']
            assert execution['status']=='finished_by_request' and execution['runner_returncode']==0 and {'finish_confirmed','process_group_gone'}<={x['event'] for x in execution['events']}
            ops=sorted([json.loads(q.read_text()) for q in (work/'operations').glob('*.json')],key=lambda x:x['started_at']);dst=out/stage;dst.mkdir()
            for name in ['prompt.md','public-config.json','input-summary.json','finish-config.json','finish-request.json','proposal.json','review.json','final-message.md']:
                if (work/name).is_file():shutil.copyfile(work/name,dst/name)
            shutil.copyfile(run/(stage+'-run/run.json'),dst/'run.json')
            with gzip.open(dst/'public-operations.json.gz','wt',encoding='utf-8') as stream:json.dump(ops,stream,ensure_ascii=False)
            stages.append({'stage':stage,'started_at':execution['started_at'],'ended_at':execution['ended_at'],'wall_seconds':(datetime.fromisoformat(execution['ended_at'])-datetime.fromisoformat(execution['started_at'])).total_seconds(),'monitor_seconds':execution['elapsed_seconds'],'status':execution['status'],'operations':len(ops),'operation_errors':[{k:o[k] for k in ['args','exit_code','started_at','ended_at','stderr']} for o in ops if o['exit_code']!=0],'query_operations':sum(o['args'][0]=='query' for o in ops),'finish_revalidated':True,'worker_pid':execution['worker_pid']})
        dest=root/('data/discovery/live-query-discovery-01-'+side+'-result');assert not dest.exists();copy_session(run/'session',dest);check_unchanged(dest,manifest(run/'session'),exact=True)
        with tarfile.open(out/'session.tar.gz','w:gz') as archive:archive.add(dest,arcname='session')
        for name in ['result.json','report.json','develop-report.json','review-report.json']:shutil.copyfile(run/name,out/name)
        records.append({'side':side,'started_at':result['started_at'],'ended_at':result['ended_at'],'end_to_collection_seconds':(started-datetime.fromisoformat(result['ended_at'])).total_seconds(),'stages':stages,'formal_revisions_added':1,'formal_reviews_added':1,'judgment':result['judgment'],'additional_sources':len(list((dest/'sources').glob('*.json')))-prep['sources_count'],'preserved_session':str(dest),'formal_and_finish_revalidated':True,'copy_identical':True,'runtime_and_source_unchanged':True})
    assert hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest()==proto['db_sha256']
    ended=datetime.now(timezone.utc);v={'first_status_observed_at':'2026-09-12T23:13:45+00:00','collection_started_at':started.isoformat(),'collection_ended_at':ended.isoformat(),'elapsed_seconds':time.monotonic()-tick,'sides':records,'main_db_unchanged':True,'limits':'実際のCodex私的stdout/JSONLは未読。正式資料・公開操作のみ保存。次工程が加えた一致済み評価入力だけを除いた複製で提出終了を再照合。時刻差・監視時間と回収までの間隔を区別し、CPU時間や休止原因を推定しない。'};(e/'verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
    j=Journal(root);c=j.get(e.name);r=c['record'];r['summary']='両方式の正式案・別評価各1件を回収。両方とも手順は条件付き・価値は追加検討・独自性未確認。検索の使用と方法の有用性を照合中。';r['stages'].append({'id':'collect-result','title':'両方式の正式案・評価と終了結果を回収','status':'completed','started_at':started.isoformat(),'ended_at':ended.isoformat(),'note':'元入力・固定実装・正式提出・明示終了を再照合。両方式の正式案と別評価は各1件。回収までの長い間隔は実行時間と別記。','budget_minutes':5});r['evidence_paths'] += ['evals/discovery/live-query-discovery-01/'+n for n in ['collection-start.json','collect-result.py','verification.json','a','b']];j.save(r,c['revision'],'codex-root','両方式の完了結果を保持確認して回収');(e/'journal-record.json').write_text(json.dumps(j.get(e.name),ensure_ascii=False,indent=2)+'\n');print({'started_at':started.isoformat(),'ended_at':ended.isoformat(),'sides':[{k:s[k] for k in ['side','judgment','additional_sources','end_to_collection_seconds']} for s in records],'operations':[(s['side'],[(t['stage'],t['operations'],len(t['operation_errors']),t['query_operations']) for t in s['stages']]) for s in records]})
except Exception as exc:
    (e/'collection-failure.json').write_text(json.dumps({'started_at':started.isoformat(),'ended_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-tick,'error':repr(exc),'completed_sides':[r['side'] for r in records],'ai_repeated':False},ensure_ascii=False,indent=2)+'\n');raise
