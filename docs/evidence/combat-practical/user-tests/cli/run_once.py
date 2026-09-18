from pathlib import Path
import sys,subprocess,json,time,datetime,platform
p=Path('docs/evidence/combat-practical/user-tests/cli')
runs=[]
def run(name,args):
 t=time.monotonic(); started=datetime.datetime.now(datetime.timezone.utc).isoformat()
 try:
  cp=subprocess.run([sys.executable,'-X','utf8',*args],capture_output=True,text=True,encoding='utf-8',timeout=60)
  status=cp.returncode;out=cp.stdout;err=cp.stderr
 except subprocess.TimeoutExpired as e:
  status='TIMEOUT';out=str(e.stdout);err=str(e.stderr)
 elapsed=time.monotonic()-t
 (p/(name+'.stdout.txt')).write_text(out,encoding='utf-8');(p/(name+'.stderr.txt')).write_text(err,encoding='utf-8')
 runs.append(dict(name=name,command=[sys.executable,'-X','utf8',*args],started_at=started,elapsed_seconds=elapsed,exit_code=status))
 (p/'runs.json').write_text(json.dumps({'runtime':sys.version,'executable':sys.executable,'platform':platform.platform(),'runs':runs},indent=2),encoding='utf-8')
 print(name,status,round(elapsed,3),flush=True)
run('reference',['scripts/practical_reference.py','--output',str(p/'reference.json')])
cs=json.loads((p/'cases.json').read_text(encoding='utf-8'))
w=dict.fromkeys(['leader','attack','health','body','hand','pp','ep','sep','keyword','win','own_board_health'],0);w['own_board_health']=1
for c in cs:
 for obj in (('lethal','value') if c['id']=='objective-preserve-versus-win' else ('lethal',)):
  name=c['id']+'-'+obj
  args=['-m','svdeck.battle_practical','--cases',str(p/'cases.json'),'--case',c['id'],'--objective',obj,'--output',str(p/name)]
  if c['id']=='objective-preserve-versus-win':args+=['--weights',json.dumps(w)]
  run(name,args)
for name,extra in [('limited',['--max-states','1']),('invalid',['--max-states','0'])]:
 run(name,['-m','svdeck.battle_practical','--cases',str(p/'cases.json'),'--case','random-half-anchor','--output',str(p/name),*extra])
run('legacy',['-m','svdeck.combat_benchmark','--case','cheap-trade','--repeat','1','--strategy','grouped','--output',str(p/'legacy')])
