"""Trial command log; both arms use the same public discovery interface."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json,os,subprocess,sys

WORK=Path.cwd()/'work/round-1';WORK.mkdir(parents=True,exist_ok=True)
now=datetime.now(timezone.utc)
if sys.argv[1:] == ['--begin']:
    data={'started_at':now.isoformat(),'research_deadline':(now+timedelta(minutes=25)).isoformat(),'save_deadline':(now+timedelta(minutes=30)).isoformat(),'source':'datetime.now(timezone.utc) at first worker action'}
    with (WORK/'clock.json').open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2)
    print(json.dumps(data));raise SystemExit(0)
if sys.argv[1:] == ['--clock']:
    start=json.loads((WORK/'clock.json').read_text())
    print(json.dumps({'now':now.isoformat(),**start,'elapsed_seconds':(now-datetime.fromisoformat(start['started_at'])).total_seconds()}));raise SystemExit(0)
code=Path('/tmp/sv-principles-scope-prototype')
command=['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery']+sys.argv[1:]
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(code/'src')}
result=subprocess.run(command,cwd=code,env=env,capture_output=True,text=True)
finished=datetime.now(timezone.utc)
number=len(list(WORK.glob('operation-*.json')))+1
stem=WORK/f'operation-{number:03d}'
output=stem.with_suffix('.stdout.txt');output.write_text(result.stdout)
record={'started_at':now.isoformat(),'ended_at':finished.isoformat(),'command':command,'exit_code':result.returncode,'stderr':result.stderr,'output':str(output)}
stem.with_suffix('.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
sys.stdout.write(result.stdout);sys.stderr.write(result.stderr)
raise SystemExit(result.returncode)
