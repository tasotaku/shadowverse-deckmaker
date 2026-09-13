from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, shutil, tarfile, time
from svdeck import discovery
from svdeck.discovery_run import manifest
from svdeck.journal_store import Journal
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');e=root/'evals/discovery/same-slot-alternative-01';j=Journal(root)
started=datetime.now(timezone.utc).isoformat();tick=time.monotonic();c=j.get(e.name);r=c['record'];s=next(s for s in r['stages'] if s['id']=='prepare');s.update(status='running',started_at=started,note='前試験の考案担当が終了を明示した時点の保存一覧だけを照合して複製。後の別評価入力は渡さない。');j.save(r,c['revision'],'codex-root','評価前に封じた共通入力の復元を開始')
source=Path('/tmp/sv-live-query-discovery-01-b-live/develop/session');request=Path('/tmp/sv-live-query-discovery-01-b-live/develop/finish-request.json');destination=root/'data/discovery/same-slot-alternative-01-input'
try:
 expected=json.loads(request.read_text())['session_manifest']; assert not destination.exists(); destination.mkdir()
 for name,digest in expected.items():
  relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts
  assert relative.parts[0] in {'context.json','snapshot.db','packets','sources','revision-0001.json'}
  p=source/relative;assert not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==digest
  out=destination/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
 assert manifest(destination)==expected
 report=discovery.report(destination);assert len(report['revisions'])==1 and not report['revisions'][0]['reviews'];assert not list(destination.glob('review-*'));assert len(list((destination/'sources').glob('*.json')))==25
 assert hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest()=='11aef89fae292ce671781ce31da124d695b15b28f64d7813c6e0c9ad720e1414'
 ended=datetime.now(timezone.utc).isoformat();proof={'started_at':started,'ended_at':ended,'elapsed_seconds':time.monotonic()-tick,'source':str(destination),'sealed_request':str(request),'request_sha256':hashlib.sha256(request.read_bytes()).hexdigest(),'manifest':expected,'sealed_manifest_matches':True,'formal_revisions':1,'formal_reviews':0,'sources':25,'main_db_unchanged':True,'later_review_packet_excluded':sorted(set(manifest(source))-set(expected)),'limitation':'保存済み旧案からの改訂試験。評価結果は渡さない。初見の新規探索ではない。'}
 (e/'preparation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n');shutil.copyfile(request,e/'input-finish-request.json')
 with tarfile.open(e/'input.tar.gz','w:gz') as tar:tar.add(destination,arcname='session')
 c=j.get(e.name);r=c['record'];next(s for s in r['stages'] if s['id']=='prepare').update(status='completed',ended_at=ended,note='提出終了時点の全30ファイルが保存一覧と一致。正式案1・評価0・資料25。後の別評価入力は除外。カードDBを保持。');r['evidence_paths']+=['evals/discovery/same-slot-alternative-01/'+n for n in ['preparation.json','input-finish-request.json','input.tar.gz','prepare-input.py']];j.save(r,c['revision'],'codex-root','後の評価を含まない共通入力を復元確認');(e/'journal-record.json').write_text(json.dumps(j.get(e.name),ensure_ascii=False,indent=2)+'\n');print({k:v for k,v in proof.items() if k not in {'manifest'}})
except Exception as exc:
 ended=datetime.now(timezone.utc).isoformat();(e/'preparation-failure.json').write_text(json.dumps({'started_at':started,'ended_at':ended,'error':repr(exc)},ensure_ascii=False,indent=2)+'\n');c=j.get(e.name);r=c['record'];next(s for s in r['stages'] if s['id']=='prepare').update(status='interrupted',ended_at=ended,note='共通入力の復元失敗。比較AIは未起動。失敗記録を保持。');r['evidence_paths'].append('evals/discovery/same-slot-alternative-01/preparation-failure.json');j.save(r,c['revision'],'codex-root','入力復元の失敗を記録');raise
