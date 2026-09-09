import json, os, subprocess
from pathlib import Path
from datetime import datetime,timezone
out=Path('/tmp/sv-class-choice-01/a-work/round-1')
session='/tmp/sv-class-choice-01/a-4/session'
exe=['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery']
env=dict(os.environ,PYTHONPATH='/tmp/sv-class-choice-prototype/src')
log=[{'argv':exe+['packet',session,'--summary'],'started_at_utc':None,'time_note':'先行実行。正確な時刻は未保存','exit_code':0,'stdout_file':'dragon-summary.json','purpose':'公開資料の概要と回答形式を確認'}]
def run(args,label):
 started=datetime.now(timezone.utc).isoformat()
 r=subprocess.run(exe+args,cwd='/tmp/sv-class-choice-prototype',env=env,text=True,capture_output=True)
 (out/(label+'.json')).write_text(r.stdout)
 if r.stderr: (out/(label+'.stderr.txt')).write_text(r.stderr)
 log.append({'argv':exe+args,'started_at_utc':started,'ended_at_utc':datetime.now(timezone.utc).isoformat(),'exit_code':r.returncode,'stdout_file':label+'.json','stderr_file':label+'.stderr.txt' if r.stderr else None})
 (out/'public-command-log.json').write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'command':args[0],'exit_code':r.returncode,'output':r.stdout},ensure_ascii=False))
 if r.returncode: raise SystemExit(r.returncode)
 return json.loads(r.stdout)
run(['attach',session,str(out/'sources-to-attach.json')],'attach-result')
p=run(['packet',session,'--summary'],'after-attach-summary')
run(['report',session],'session-report')
execution=json.load(open(out/'execution.json'))
execution['public_commands']={'success_count':sum(c['exit_code']==0 for c in log),'failure_count':sum(c['exit_code']!=0 for c in log),'log':'public-command-log.json','commands':log,'submit_count':0,'compare_count':0,'review_count':0}
execution['after_attach_packet_hash']=p.get('sha256')
(out/'execution.json').write_text(json.dumps(execution,ensure_ascii=False,indent=2)+'\n')
