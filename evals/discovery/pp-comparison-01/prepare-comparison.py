from pathlib import Path
from datetime import datetime,timezone
import os,json,subprocess,hashlib
base=Path('/tmp/sv-pp-comparison-01');code=Path('/tmp/sv-pp-comparison-prototype');cmd=['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery'];env={**os.environ,'PYTHONPATH':str(code/'src'),'PYTHONDONTWRITEBYTECODE':'1'};ops=[]
def call(*args):
 start=datetime.now(timezone.utc).isoformat();r=subprocess.run(cmd+list(map(str,args)),env=env,cwd=code,capture_output=True,text=True);ops.append({'command':cmd+list(map(str,args)),'started_at':start,'ended_at':datetime.now(timezone.utc).isoformat(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr});r.check_returncode();return json.loads(r.stdout)
source={'sources':[{'title':'過去に保存した二案の比較本文','kind':'考案担当による比較資料','location':'過去の保存資料 original-comparison.md','observed_at':None,'content':(base/'inputs/original-comparison.md').read_text(),'limitations':['初手からの実測・対戦結果ではない。記載された状態と行動を検算するための元資料。']},{'title':'検証開始時のゲームルール','kind':'固定ルール','location':'docs/rules.md の保存版','observed_at':None,'content':(base/'inputs/rules.md').read_text(),'limitations':['この固定資料の範囲で照合する。最新環境への一般化はしない。']}]}
(base/'inputs/sources.json').write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n');idx={}
for arm in ['a','b']:
 session=base/arm/'session';(base/arm/'work').mkdir(parents=True,exist_ok=True)
 assert not session.exists()
 call('start',session,'--db','/tmp/sv-sketch-first-01/cards-reference-refresh.db','--class','エルフ','--format','rotation','--objective','保存された二案のPP推移と同じ終点を検算する。カードの探索は行わない。')
 added=call('attach',session,base/'inputs/sources.json');packet=call('packet',session,'--summary')
 idx[arm]={'session':str(session),'work':str(base/arm/'work'),'source_hashes':added['added'],'packet_summary':packet}
assert idx['a']['source_hashes']==idx['b']['source_hashes']
(base/'session-index.json').write_text(json.dumps(idx,ensure_ascii=False,indent=2)+'\n');(base/'preparation-operations.json').write_text(json.dumps(ops,ensure_ascii=False,indent=2)+'\n')
print({'arms':list(idx),'source_hashes':idx['a']['source_hashes'],'operations':len(ops)})
