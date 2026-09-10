from pathlib import Path
import os,subprocess,sys
w=Path(__file__).resolve().parent
config=__import__('json').loads((w/'public-config.json').read_text())
args=sys.argv[1:]; own=(w/'session').resolve(); lib=Path(config['library']).resolve()
def fail(message):
 print(message,file=sys.stderr); raise SystemExit(2)
if not args:fail('操作を指定してください')
cmd=args[0]
if cmd=='recall':
 if not config['recall']:fail('この担当では別探索の経験検索は使用しません')
 args=['recall',str(lib),*args[1:]]
elif cmd in ['-h','--help']:pass
elif cmd in ['read','report','packet','compare','attach','attach-file','submit','review']:
 if len(args)>1 and args[1] in ['-h','--help']:pass
 else:
  if len(args)<2:fail('保存先が必要です')
  target=Path(args[1]).resolve()
  if target!=own and not(config['recall'] and cmd in ['read','report'] and target.is_relative_to(lib)):
   fail('自分のsession、または許可された過去記録への読出しだけを使ってください')
  if cmd=='review' and config['phase']!='review':fail('考案担当は別評価を提出できません')
else:fail('この担当の公開操作に含まれません')
raise SystemExit(subprocess.call(['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery',*args],env={**os.environ,'PYTHONPATH':config['runtime'],'PYTHONDONTWRITEBYTECODE':'1'}))
