from pathlib import Path
from datetime import datetime,timezone
import json,gzip,shutil,tarfile,hashlib,time,sys
from svdeck.discovery_run import check_finish,check_unchanged,manifest,verify_submission,copy_session
from svdeck.journal_store import Journal
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');e=root/'evals/discovery/opponent-response-01';arm=sys.argv[1];assert arm in ('a','b')
run=Path('/tmp/sv-opponent-response-01-'+arm+'-live');result=json.loads((run/'result.json').read_text());assert result.get('ended_at') and result['status'] not in ('preparing','review')
started=datetime.now(timezone.utc);tick=time.monotonic();j=Journal(root);item=j.get(e.name);r=item['record'];sid=arm+'-collection';r['stages'].append(dict(id=sid,title=arm.upper()+'の正式評価と終了記録を回収',status='running',started_at=started.isoformat(),ended_at=None,note='固定入力・実装・正式保存を再照合し、失敗時も部分結果を保持する。',budget_minutes=2));r['status']='running';j.save(r,item['revision'],'codex-root','終了した評価の回収を開始')
out=e/arm;out.mkdir();inp=json.loads((e/'input-manifest.json').read_text());runtime=json.loads((e/'runtime-manifest.json').read_text());check_unchanged(Path(inp['cases'][arm]['session']),inp['cases'][arm]['manifest'],exact=True);check_unchanged(run/'runtime',runtime['files'],exact=True)
try:
    work=run/'review';ex=json.loads((run/'review-run/run.json').read_text());assert ex.get('ended_at');checks={}
    if ex['status']=='finished_by_request':
        contract=json.loads((work/'finish-config.json').read_text());assert check_finish(work,contract)==ex['finish_evidence'];assert ex['runner_returncode']==0;assert {'finish_confirmed','process_group_gone'}<={x['event'] for x in ex['events']};checks['finish_revalidated']=True
    for name in ('prompt.md','public-config.json','input-summary.json','finish-config.json','finish-request.json','review.json','final-message.md'):
        if (work/name).is_file():shutil.copyfile(work/name,out/name)
    shutil.copyfile(run/'review-run/run.json',out/'run.json');ops=sorted([json.loads(p.read_text()) for p in (work/'operations').glob('*.json')],key=lambda x:x['started_at'])
    with gzip.open(out/'public-operations.json.gz','wt',encoding='utf-8') as stream:json.dump(ops,stream,ensure_ascii=False)
    completed=result['status']=='completed';source=run/'session' if completed else work/'session'
    if completed:
        assert result['formal_revisions']==0 and result['formal_reviews']==1;verify_submission(source,'develop',1);verify_submission(source,'review',1)
    dest=root/('data/discovery/opponent-response-01-'+arm+('-result' if completed else '-partial'));assert not dest.exists();copy_session(source,dest);check_unchanged(dest,manifest(source),exact=True)
    with tarfile.open(out/'session.tar.gz','w:gz') as archive:archive.add(dest,arcname='session')
    for name in ('result.json','report.json','review-report.json'):
        if (run/name).exists():shutil.copyfile(run/name,out/name)
    assert hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest()==inp['main_db_sha256'];ended=datetime.now(timezone.utc)
    v=dict(arm=arm,status=result['status'],failure=result.get('failure'),judgment=result.get('judgment'),collection_started_at=started.isoformat(),collection_ended_at=ended.isoformat(),collection_seconds=time.monotonic()-tick,end_to_collection_seconds=(started-datetime.fromisoformat(result['ended_at'])).total_seconds(),actor_started_at=ex['started_at'],actor_ended_at=ex['ended_at'],actor_wall_seconds=(datetime.fromisoformat(ex['ended_at'])-datetime.fromisoformat(ex['started_at'])).total_seconds(),actor_monitor_seconds=ex['elapsed_seconds'],operations=len(ops),operation_errors=[{k:o.get(k) for k in ('args','exit_code','started_at','ended_at','stderr')} for o in ops if o['exit_code']!=0],checks=checks,new_revisions=result.get('formal_revisions',0),new_reviews=result.get('formal_reviews',0),preserved_session=str(dest),session_manifest=manifest(dest),main_db_unchanged=True,input_and_runtime_unchanged=True,limits='正式保存・公開操作・実行メタデータだけを回収。非公開のstdout/JSONL/思考ログは未読。経過時間をCPU時間や実作業時間と同一視しない。')
    (out/'verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');item=j.get(e.name);r=item['record'];next(s for s in r['stages'] if s['id']==sid).update(status='completed',ended_at=ended.isoformat(),note='結果 '+result['status']+'。正式保存・終了・入力保持を再検査して回収。本人評価との照合は未実施。');r['evidence_paths']=[str(p.relative_to(root)) for p in e.iterdir() if p.name!='journal-record.json'];j.save(r,item['revision'],'codex-root','正式評価と終了時刻の回収を保存');(e/'journal-record.json').write_text(json.dumps(j.get(e.name),ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v[k] for k in ('arm','status','judgment','actor_wall_seconds','end_to_collection_seconds','collection_seconds')},ensure_ascii=False))
except Exception as exc:
    (out/'collection-failure.json').write_text(json.dumps(dict(started_at=started.isoformat(),ended_at=datetime.now(timezone.utc).isoformat(),error=repr(exc),ai_repeated=False),ensure_ascii=False,indent=2)+'\n');raise
