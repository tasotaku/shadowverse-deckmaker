import datetime,json,os,pathlib,subprocess,sys
out=pathlib.Path('/tmp/sv-class-choice-01/b-work/round-1')
args=sys.argv[1:]
env=os.environ.copy();env['PYTHONPATH']='/tmp/sv-class-choice-prototype/src'
cmd=['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery',*args]
t=datetime.datetime.now(datetime.timezone.utc).isoformat()
r=subprocess.run(cmd,cwd='/tmp/sv-class-choice-prototype',env=env,text=True,capture_output=True)
p=out/'execution.json';d=json.loads(p.read_text());n=len(d['public_commands'])+1
log=out/f'public-{n:02d}-{args[0]}.json';log.write_text(r.stdout if r.stdout else r.stderr)
d['public_commands'].append({'command':cmd,'started_utc':t,'success':r.returncode==0,'exit_code':r.returncode,'output':str(log),'stderr':r.stderr});p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
print(r.stdout);print(r.stderr,file=sys.stderr)
sys.exit(r.returncode)
