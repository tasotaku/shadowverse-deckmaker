import subprocess,sys,json,time,datetime,pathlib
root=pathlib.Path('docs/evidence/combat-benchmark-tests/execution')
selected=['empty','incomparable','tall-wide','super-finish']
base=[str(pathlib.Path('.venv/Scripts/python.exe').resolve()),'-X','utf8','-m','svdeck.combat_benchmark']
def run(name,args,budget):
    command=base+args
    start=time.monotonic(); stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
    killed=False
    try: out,err=p.communicate(timeout=budget)
    except subprocess.TimeoutExpired:
        killed=True
        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
        out,err=p.communicate(timeout=10)
    record={'command':command,'started_at':stamp,'pid':p.pid,'exit_code':p.returncode,'wall_seconds':time.monotonic()-start,'killed_budget':killed,'stdout':out,'stderr':err}
    (root/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False),flush=True)
run('normal-command',['--output',str(root/'normal'),'--repeat','2','--timeout','30']+sum([['--case',c] for c in selected],[]),180)
